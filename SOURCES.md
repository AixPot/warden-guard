# 来源与第三方许可

本 Python 编排、测试、Dockerfile、Compose 与中文文档依据用户功能规格独立新写；
未读取/复制/改写原项目实现。没有法律 clean-room 认证或“许可风险已清零”的声明。
项目自有源码采用 MIT License，Copyright (c) 2026 AixPot，见 LICENSE；第三方依赖保留各自许可。

## 查阅资料（接口事实，未粘贴实现）

- [Bitwarden 官方 CLI 文档](https://bitwarden.com/help/cli/)：passwordenv、个人 API key、独立 appdata、export/import/logout。
- 隔离安装 `@bitwarden/cli@2026.10.0`，使用 `bw --version`, `login --help`, `export --help` 验证选项；
  global_applicationId_appId 协议键按用户提供事实初始化，并通过全新 profile 和服务端 devices API 验证。
- [Vaultwarden 1.37.4 accounts API](https://github.com/dani-garcia/vaultwarden/blob/1.37.4/src/api/core/accounts.rs)
  与 [identity API](https://github.com/dani-garcia/vaultwarden/blob/1.37.4/src/api/identity.rs)：
  仅查注册 send-verification-email/finish、注册字段及 devices 接口协议；验收请求/加密构造独立编写，
  不复制 Rust 实现。公开依赖代码为 AGPL-3.0，未嵌入产品。

## 运行/测试依赖

|依赖|来源|许可/注意事项|
|---|---|---|
|Python 3 标准库|Debian 包 / python.org|PSF License 等，见镜像内 /usr/share/doc/python3*|
|OpenSSL 3|Debian 包 / openssl.org|Apache-2.0，见 https://openssl-library.org/source/license/|
|Node.js 22|官方 node:22-bookworm-slim 镜像|Node MIT + 多项第三方许可；Debian 系统包各自许可|
|@bitwarden/cli 2026.10.0|npm 官方包|package.json 为 SEE LICENSE IN LICENSE.txt；npm 安装包实际缺该顶层文件，不据此假定全部 GPL|
|Vaultwarden 1.37.4|官方 vaultwarden/server 镜像，仅隔离测试|AGPL-3.0；不进运行镜像|
|OpenSSH client|Debian 包，仅隔离验收生成 SSH key|BSD-style 等第三方许可；不进运行镜像|

Bitwarden 上游 [LICENSE.txt](https://github.com/bitwarden/clients/blob/cli-v2026.10.0/LICENSE.txt)
明确默认 GPL-3.0，bitwarden_license 目录为 [Bitwarden License v1.0](https://github.com/bitwarden/clients/blob/cli-v2026.10.0/LICENSE_BITWARDEN.txt)。
官方 npm 默认构建可能含非 OSS 功能；不能声称整个 CLI 都是 GPL 或可自由分发。
当前仅本地安装/构建/隔离内部测试，不发布镜像。
若要生产使用或分发容器，必须先确认官方 CLI 构建许可边界，必要时改成并重新验收官方 OSS 构建，
保留适用 notices/source offer/系统包许可。本文件不是法律意见，未逐一审计 npm 间接依赖。
项目无 pip 第三方依赖，但官方 CLI 具有 npm 间接依赖，安装时由其包解析，并非无第三方依赖。
