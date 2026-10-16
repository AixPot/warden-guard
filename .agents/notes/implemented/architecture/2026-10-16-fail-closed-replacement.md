# Agent Note: 非事务替换的失败封锁

Status: implemented

## Problem
保险库替换跨多个 CLI 写入，无服务器事务；盲目重试可能重复导入或误删数据。
这是低频单操作者工具，但处理高敏感、难逆转数据，数据正确性和备份可恢复优先。

## Decision
使用同步 flock 全局互斥、原子 fsync journal 和双边先加密快照。
importing 前不写目标；导入后先验证新增多重集合和初始旧记录不变，才进入 deleting。
只删除初始旧 ID。任何中间 journal 状态阻断后续自动执行，不自动回滚或提供 force。
稳定设备身份仅持久 appId；profile/session/JSON 留在 tmpfs。
备份沿用 OpenSSL CBC/PBKDF2 兼容格式，并明确其无认证属性。

## Alternatives considered
- 先清空再导入最简单，但失败即丢目标，拒绝。
- 失败自动回滚/重试减少人工，但无法证明跨客户端状态和部分删除安全，拒绝。
- 持久 CLI profile 可减少登录，但包含 token/config 等秘密，改为白名单 UUID。
- AEAD 提供密文认证，但与指定旧 enc 格式不同，本版本不声称提供认证。

## Consequences
需要维护窗口；目标快照无限保留需监控容量。源备份 30 天且最低 7 份，新快照成功才清理。
P0 单测覆盖替换、幂等、失败封锁、schema、多重集合；P1 真实隔离 CLI/Vaultwarden 回环验证。
真实 API 可能省略可选空值，不能用合成测试冒充服务器验证。
新仓库无既有 notes，未发现需归档的重叠决策。来源与依赖许可单列 SOURCES.md，项目自有源码采用 MIT 许可，第三方许可不变。
