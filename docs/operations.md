# 运行与恢复指南

## 范围、资源与维护窗口

支持未删除个人项目（包括归档状态）：登录、笔记、银行卡、身份、SSH，以及这些项目的附件。组织与未知类型拒绝。不是账号级备份：回收站、Send、账号设置不参与同步；原始 JSON 导出不改写并随快照加密保存，若导出含 deletedDate 历史项目，原始字节仍保留。分别调用普通 list items、--archived、--trash，要求 ID 不重复、分区状态正确、所有权/类型一致；普通∪归档精确等于导出的未删除 ID 集合，导出若含已删除项目也必须来自已核对回收站。未知差异失败，不按数量或名称忽略项目。归档时间 archivedDate 严格保留；官方 CLI 2026.10.0 / Vaultwarden 1.37.4 的原生 import 保留归档状态，fresh profile 分别查询普通/归档列表验证，不能仅比较 JSON 字段。其他服务器若不能保真，导入核验失败封锁，不删除旧目标。

必须暂停两边其他客户端写入。本地 flock 仅互斥共享 state 的本程序，不会锁定服务器。替换非事务，期间会出现新旧项目；删除是逐项执行，失败可能部分完成。

流程：持久 snapshotting → 下载源全部附件并加密完整快照 → 下载目标全部附件并加密完整快照 → 比较 → importing → 导入正文 → uploading → 上传附件 → **全新目标 profile 重新下载全部附件**，比较正文/逐项映射/附件 SHA256 与长度、原目标未变 → deleting → 只删除本轮最初旧 ID → 再核验 → complete。相等则 unchanged。任一下载失败（包括权限/配额）不会略过。任何非终态 journal 阻断重试，新增内容不自动回滚。

限制：单附件明文默认 16 MiB（`WG_ATTACHMENT_FILE_MIB`）、每个保险库默认合计 16 MiB（`WG_ATTACHMENT_TOTAL_MIB`），两者可配置 1–32 MiB，单文件不得超过总量；最多 256 个附件、每份 CLI JSON 8 MiB、快照 envelope 64 MiB。默认 tmpfs 512 MiB，每次导出/下载前要求空闲至少 `8 × (总附件上限 + 8 MiB)`，默认 192 MiB，配置总量 32 MiB 时为 320 MiB。CLI 输出/落盘受文件长度限制；实际占用还包括 CLI profile 与进程内存，须给宿主足够内存。资源不足封锁，不降级为磁盘明文。附件名必须是可原样上传的安全 basename（不含 `/`、`\`、NUL，不为点目录，UTF-8 不超过 240 字节），不静默改名。每份同名/同内容文件分别保留，支持零字节。

Bitwarden 官方托管服务通常要求 Premium 才能上传附件，并有存储配额；目标在新旧文件共存期间需足够容量。Vaultwarden 的权限/配额由服务器管理。工具不修改权限、配额或管理员配置，CLI/服务器拒绝即失败封锁。

## 内容比较与映射

正文仅忽略顶层 `id, organizationId, collectionIds, revisionDate, creationDate, deletedDate, object`；文件夹仅忽略 `id, object`。folderId 通过文件夹内容关联。条目和文件夹均为多重集合，重复项目不去重。

仅登录 `username/totp/password` 的缺省、null、精确空字符串等价；password 可缺省/null/string，其他类型拒绝。空白字符串和非空密码严格比较；不全局抹掉字段。其他缺省/null/空数组/空字符串严格区分，自定义 fields、密码历史、passkeys、SSH 与未知正文属性保留。

附件用 `(原始文件名, 明文长度, SHA256)` 多重集合比较，服务器附件 ID、URL、密文大小不是正文差异。有附件的导入会给每项临时加入随机唯一 custom field，sync/export 验证 token→新 ID 双射，随后 edit 恢复原 fields。不能安全映射即封锁，不按名称或列表顺序猜测。成功后标记消失；中断可能留下标记或部分新增项目。精确映射加密持久保存。fresh profile 逐项验证关联，不能只验证文件名/size。

## 凭据和设备

credentials.json 权限 0600，state 建议 0700。密码不出现在 argv/日志；root、同权限进程及 Docker 管理员仍可读取。不要启用 CLI debug。运行产生的 session/profile/JSON/payload 留于 tmpfs/内存。禁用或加密 swap、core dump、休眠与宿主快照，tmpfs 不保证不会换出。

设备身份仍按 role + 精确 server + 精确 account 独立持久 UUID；state/devices 仅保存 appId。scope 拼写变化会产生新身份。损坏拒绝而非重置；不保存 CLI token/config，不关闭邮件通知。退出尽力 logout/清理；SIGKILL 与宿主崩溃无法保证服务端 token 吊销。

## 快照版本 2 与离线恢复

外层为 OpenSSL `enc -aes-256-cbc -pbkdf2 -iter 100000 -md sha256`，随机 8 字节 salt、OpenSSL `Salted__` 封装（当前镜像 OpenSSL 3.0.22），二进制 `.enc`。AES-256-CBC **无认证，不是 AEAD**；往返校验和内部 SHA256 不保证抵抗攻击者重写密文。保管独立备份密码，留存生成镜像和 OpenSSL 版本。不要猜旧文件的 KDF 参数。

解密后为 UTF-8 JSON envelope：

- `format: "warden-guard.snapshot"`, `version: 2`；
- `raw_export`: 原始官方 JSON 导出字节的 base64；
- `data`: 活动正文与附件 hash 描述符；
- `manifest`: 按 payload 顺序，含 itemId、attachmentId、原始 metadata、fileName、length、sha256；
- `payloads`: 对应明文附件的 base64，不去重、不按名称覆盖。

所有名称、URL、ID 关联、hash、payload 都在外层密文内。持久 journal 只含阶段、快照文件名和初始旧 ID；加密 mapping 快照为单独 `{version:2,item_mapping:{旧源ID:新目标ID}}`，不是保险库快照。目标与 mapping 快照不自动清理。源快照仍按保留配置清理；不要删除未经归档的恢复证据。旧版备份保持原 JSON 格式，可按原方式恢复，不转换或覆盖旧文件。

在隔离恢复环境使用 tmpfs，交互读取备份密码（不要将明文写到磁盘或 shell 历史）：

```sh
umask 077
mkdir -p /dev/shm/warden-restore
openssl enc -d -aes-256-cbc -pbkdf2 -iter 100000 -md sha256 \
  -in state/backups/REPLACE_SNAPSHOT.enc -out /dev/shm/warden-restore/snapshot.json
python3 -m warden_guard.restore /dev/shm/warden-restore/snapshot.json /dev/shm/warden-restore/extracted
```

离线提取不访问任何保险库，校验清单 hash/长度后输出 `raw-export.json`、`import.json`、`manifest.json` 和编号 `payloads/000000` 等安全路径；不会用不可信名称解包路径，也不会覆盖已有目录。

恢复时优先使用全新空账户、tmpfs CLI profile。正文用 `bw import bitwardenjson .../import.json`；此操作产生新 ID。必须建立原 itemId→新 ID 映射，不能按名称猜测，重复正文时使用与同步相同的唯一临时标记方法或逐项导入/确认。按 manifest 找到编号 payload，把它复制到独立 tmpfs 目录下原始 fileName，再 `bw create attachment --file PATH --itemid NEW_ID`，每一行都上传，包括同名与零字节。最后换 fresh profile 逐项下载，核对 SHA256/长度/多重集合以及正文；分别执行 `bw list items` 和 `bw list items --archived`，确认归档项目只在归档列表、archivedDate 与快照一致，才认为恢复完成。离线提取工具不自动做这些目标写入。旧版无 version envelope 的备份只能恢复其原 JSON，不具有附件 payload。

完成后 logout，并销毁临时恢复环境及 tmpfs 明文。

## journal 阻断处理

1. 停止调度，保留 journal 与全部快照，不直接删除 journal 或再次导入。
2. snapshotting 可能只有单边快照，目标尚未写；importing/uploading 可能留下部分新增内容/临时标记，但不会开始删除旧项目；deleting 可能已删除部分旧内容。
3. 用新的 tmpfs profile 只读导出，离线解密 source/target/mapping 对照；按 ID、正文、附件 bytes 核对，而非数量或名称。
4. 在新空恢复账户验证快照，再制定明确人工恢复/完成删除方案。没有 force 或自动回滚。
5. 人工确认目标已处于已知状态并批准下一次替换后，将 journal 归档到 state 外受保护目录，再单次执行。保留恢复证据。
