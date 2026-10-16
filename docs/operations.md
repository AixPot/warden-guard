# 运行与恢复指南

## 支持范围与维护窗口

支持个人条目：1 登录、2 笔记、3 银行卡、4 身份、5 SSH。
附件、组织成员/组织项目、未知类型被拒绝，不会悄悄丢弃。
预检读取 CLI list items/organizations，仅作只读完整性检查，源无创建/编辑/删除命令。
导出必须非空，条目/文件夹 ID 唯一、引用完整、类型子对象完整；正常可选 null 可接受。
只同步 CLI 正常导出的活跃个人条目/文件夹，不备份回收站、Send、账号设置或附件。

执行期间必须暂停两边其他写入，留出维护窗口。本程序的 flock 只约束使用同一 state 的本程序，
无法锁住其他客户端。替换不是事务；临时存在新旧两份项目，读者可能看到重复。
流程为：源原始 JSON 加密备份及解密字节往返校验 → 清理过期源备份 →
目标原始 JSON 密文快照往返校验 → 比较 → 持久 importing → 导入 →
重新 sync/export 验证新增内容和原目标未变 → 持久 deleting → 只删除最初旧 ID →
全量核验 → complete。相等写 unchanged，绝不导入/删除。
目标恢复快照**永不自动清理**，操作者负责容量监控与经核对的手动归档。
文件夹也按首次旧 ID 删除，重复内容保留 multiplicity，而非只比较数量。

### 比较规则

条目仅移除顶层 `id, organizationId, collectionIds, revisionDate, creationDate, deletedDate, object`；
文件夹仅移除顶层 `id, object`。organization/collections/deleted 内容存在时先拒绝。
folderId 按文件夹完整内容映射，缺失/null 都表示没有文件夹；文件夹自身也是多重集合的一部分。
仅 type1.login.username/totp 的精确空字符串等价 null/缺失。其他字段缺失/null/空数组/空字符串、
空白字符都严格区分；数组顺序保留，字典键顺序忽略。passwordHistory、自定义 fields、
passkeys/fido2Credentials 和 SSH 全部保留；未知内容字段也保留，不做宽松“修复”。
服务器/CLI 不保留的字段会导致导入后校验失败，保留 journal 并阻断后续任务，不删除旧数据。

## 凭据和设备身份

credentials.json 必须 0600（或仅所有者可读更严格权限），state 建议 0700，所有持久生成文件 0600。
密码经环境变量或匿名 fd 交给子进程，不放 argv/日志；宿主 root、同权限进程和 Docker 管理员仍可读取。
不要启用 CLI debug，不向不可信监控发送内存或凭据。凭据配置本身是操作者提供的秘密文件，
可以用宿主 tmpfs 或秘密管理器供给；运行产生的 profile、JSON、session 只在 tmpfs/进程内存。
禁用或加密宿主 swap、core dump、休眠及宿主快照，tmpfs 本身并不保证不会换出。

每 role + 精确 server + 精确 account 独立持久 UUID，位于 state/devices 下哈希文件名的 JSON，
只白名单 appId 字段。每次新临时 profile 写入官方存储键 global_applicationId_appId。
更换容器但保留 state 会维持身份，损坏会拒绝而非随机重置。改变 URL/账户拼写会产生新 scope。
不保存整个 CLI config/token，不伪装其他设备、不关闭邮件。首次登录可能一次新设备通知；
邮件策略由服务器控制，不能保证绝不再次通知。

退出尽力 logout 并删除临时目录；SIGTERM/SIGINT 正常展开清理。
SIGKILL、宿主崩溃无法执行 finally/logout；容器销毁后其 tmpfs 消失，但服务器 token
可能直到过期/管理员吊销仍有效。清理失败/强杀时不要把“本地消失”当成服务端吊销成功。

## 备份解密与人工恢复

格式为 OpenSSL `enc -aes-256-cbc -pbkdf2 -iter 100000 -md sha256`，随机 salt，`.enc` 文件。
**AES-256-CBC 没有认证，不是 AEAD。** 往返字节比较只是验证此次写入可还原，不保证日后未被篡改。
兼容相同参数的旧 OpenSSL enc .enc；旧文件若使用不同迭代数/摘要，需要操作者明确原参数，
不能盲猜。备份密码与主密码独立，请离线保管。

停调度，在隔离恢复环境用 tmpfs 解密，OpenSSL 交互提示密码（不写 argv）：

```sh
umask 077
mkdir -p /dev/shm/warden-restore
openssl enc -d -aes-256-cbc -pbkdf2 -iter 100000 -md sha256   -in state/backups/REPLACE_SNAPSHOT.enc -out /dev/shm/warden-restore/vault.json
# 检查解密 JSON，不将其打印到日志；优先导入全新空的恢复账户。
# 将官方 CLI profile 也指向 tmpfs，通过交互登录/unlock 后：
export BITWARDENCLI_APPDATA_DIR=/dev/shm/warden-restore/cli
bw config server https://restore.example.invalid
bw login
# 按 CLI 提示设置 BW_SESSION，避免把 session 放到 argv 或共享 shell 历史。
bw import bitwardenjson /dev/shm/warden-restore/vault.json
bw sync
# 用导出逐项核对恢复结果；导入不是恢复原 ID，也不是覆盖事务。
bw logout
rm -r /dev/shm/warden-restore
```

### journal 阻断处理

1. 停止调度，保留 state/journal.json 和全部快照；不要直接删除 journal 或再次导入。
2. importing 表示可能导入零个/部分/全部新项目；deleting 表示可能已有部分旧项目被删除。
   导入失败不会启动删除，但 CLI 自身部分导入不能保证回滚。
3. 用全新 tmpfs profile 只读导出两边，解密 source_snapshot/target_snapshot 对照。
   journal 记录本轮最初 old_ids/old_folder_ids；人工逐项确认，不按项目数量判断成功。
4. 优先在新空恢复账户核验快照。对受影响目标制定明确人工恢复或完成删除方案；本工具不自动回滚。
5. 只有人工核对确认目标已恢复到已知状态并批准下一次替换后，将 journal **归档到 state 外的受保护目录**，
   保留快照及操作记录，再重新单次执行。无 force/万能重试命令。归档不是自动化恢复机制。

