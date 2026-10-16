# warden-guard

个人 Bitwarden 保险库的加密备份与单向同步工具，可将源账户中的条目同步到另一个 Bitwarden 或 Vaultwarden 账户。

## 功能

- 定时生成加密备份，支持保留天数和最低备份份数。
- 同步前保存目标快照，导入并核对内容后再删除旧条目。
- 内容未变化时跳过导入，避免重复记录。
- 保留稳定的设备标识，避免每次运行都生成新的登录设备。
- 支持登录、笔记、银行卡、身份和 SSH 密钥条目。

> 目标账户用于单向镜像，原有内容可能被替换。建议使用专用目标账户，并先在测试账户上验证。暂不支持附件、组织库、回收站、Send 和账户设置。

## 部署

### 环境要求

- Linux
- Docker Engine 与 Docker Compose v2
- 两个不同的个人保险库账户及其个人 API Key

镜像使用 Bitwarden CLI **OSS** `2026.10.0`，支持 Linux amd64；已测试 Vaultwarden `1.37.4`。

### 1. 获取源码

```sh
git clone https://github.com/AixPot/warden-guard.git
cd warden-guard
```

### 2. 配置凭据

```sh
cp credentials.example.json credentials.json
chmod 600 credentials.json
mkdir -p state
chmod 700 state
```

用本地编辑器填写 `credentials.json` 中的源账户、目标账户、主密码、个人 API Key 和备份密码。API Key 不能代替主密码；备份密码应独立设置并妥善保管。

服务器地址须使用 HTTPS。使用私有 CA 时，可只读挂载证书，并设置 `NODE_EXTRA_CA_CERTS`，不要关闭 TLS 校验。需要验证码等交互操作的登录流程不适合无人值守运行。

不要将凭据文件、备份或 `state/` 提交到 Git。

### 3. 拉取发布镜像并执行一次

默认使用 `ghcr.io/aixpot/warden-guard:0.1.0`；版本首次发布后可拉取。也可用 `WG_IMAGE` 指定版本或 `@sha256:` 摘要。

```sh
docker compose pull
docker compose run --rm warden-guard once
```

运行结果以 JSON 输出：

| 状态 | 含义 |
| --- | --- |
| `complete` | 同步完成 |
| `unchanged` | 两边内容一致，无需替换 |
| `error` | 执行失败，需要检查配置或恢复状态 |

单次执行成功退出码为 `0`，失败为 `1`。发生同步中断时，不要直接删除状态文件或反复重跑，参阅[运行与恢复指南](docs/operations.md)。

### 4. 启用定时运行

确认首次运行结果后启动：

```sh
docker compose up -d
docker compose logs -f
```

默认每天北京时间 `00:00` 执行。可在 `compose.yaml` 的 `environment` 中修改：

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `TZ` | `Asia/Shanghai` | 调度时区 |
| `WG_HOUR` | `0` | 每日执行小时 |
| `WG_MINUTE` | `0` | 每日执行分钟 |
| `WG_RETENTION_DAYS` | `30` | 源备份保留天数 |
| `WG_MIN_BACKUPS` | `7` | 源备份最低保留份数 |

修改后运行 `docker compose up -d` 使配置生效。调度器不补跑停机期间错过的任务。

### 数据与维护

`state/` 保存加密备份、同步状态及设备标识。升级或重建容器时请保留该目录；首次使用新设备标识可能收到一次登录提醒。

同步不是原子事务，执行期间应避免通过其他客户端修改两边保险库。导入或删除失败后可能需要人工恢复。目标恢复快照不会自动清理，请留意磁盘容量。

备份使用 OpenSSL AES-256-CBC/PBKDF2，**不提供密文认证**。详细的凭据保护、比较规则、备份解密及故障处理见[运行与恢复指南](docs/operations.md)。

## 开发

项目使用 Python 标准库编排 Bitwarden CLI 和 OpenSSL。

```sh
# 运行单元测试（需要 Python 3 和 OpenSSL）
python3 -m unittest discover -s tests -v

# 本地构建及运行（不拉取发布镜像）
docker compose -f compose.yaml -f compose.build.yaml build
docker compose -f compose.yaml -f compose.build.yaml run --rm warden-guard once
```

源码结构：

```text
warden_guard/
  content.py   # 导出结构验证与内容比较
  cycle.py     # 备份和同步流程
  runtime.py   # CLI 会话、配置与调度
  storage.py   # 加密备份、设备身份与持久状态
tests/         # 单元测试及隔离验收工具
```

`tests/live_acceptance.py` 用于隔离环境的真实 CLI/Vaultwarden 验收，需显式设置 `WG_ISOLATED_ACCEPTANCE=yes`。它会创建测试账户并执行导入、删除操作，不要用于真实保险库。测试环境需要额外安装 `openssh-client`，并使用无外网、无发布端口的独立 Vaultwarden 环境。

## 许可证

[MIT](LICENSE)。第三方依赖及许可说明见 [SOURCES.md](SOURCES.md)。
