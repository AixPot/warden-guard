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
|Bitwarden CLI OSS 2026.10.0|官方 Release 的 bw-oss-linux-2026.10.0.zip|GPL-3.0；不打包 npm 商业构建；见下述源码及许可保留|
|Vaultwarden 1.37.4|官方 vaultwarden/server 镜像，仅隔离测试|AGPL-3.0；不进运行镜像|
|OpenSSH client|Debian 包，仅隔离验收生成 SSH key|BSD-style 等第三方许可；不进运行镜像|

Bitwarden 上游 [LICENSE.txt](https://github.com/bitwarden/clients/blob/cli-v2026.10.0/LICENSE.txt)
明确默认 GPL-3.0，bitwarden_license 目录为 [Bitwarden License v1.0](https://github.com/bitwarden/clients/blob/cli-v2026.10.0/LICENSE_BITWARDEN.txt)。
## CLI 分发边界与官方证据

- [对应 tag 构建工作流](https://github.com/bitwarden/clients/blob/cli-v2026.10.0/.github/workflows/build-cli.yml) 明确分开 `oss` 和 `commercial`，OSS 构建移除 `@bitwarden/commercial-sdk-internal`，执行 `dist:oss:lin`，产物命名 `bw-oss-linux-2026.10.0.zip`。同一文件的 npm build artifact 仅从 `bit`（commercial）上传。
- [发布 shim](https://github.com/bitwarden/clients/blob/cli-v2026.10.0/.github/workflows/publish-cli.yml) 调用 [官方 npm 发布工作流](https://github.com/bitwarden/gh-actions/blob/dd063adbd3f94f8c305d0179a5336b71a90027fd/.github/workflows/_publish-cli-npm.yml)，其下载上述 npm build artifact 而不重新执行 `build:oss:prod`。仅凭 [package.json](https://github.com/bitwarden/clients/blob/cli-v2026.10.0/apps/cli/package.json) 中旧 `publish:npm` 脚本不能认定实际 npm 包是 OSS。
- Bitwarden License v1.0 §2.1 仅授予内部非生产开发/测试，§2.3(i) 不允许向第三方分发商业模块。因此这里不分发默认 npm 商业构建；改用官方明确标记的 OSS Release，无需自行重建整个 CLI。
- [官方 OSS 下载](https://github.com/bitwarden/clients/releases/tag/cli-v2026.10.0) 的 amd64 ZIP SHA256 为 `a300959a347bd71ff571da75687c8388da2ecd747a20f0abddd18643eb9466ba`（GitHub Release asset digest，Dockerfile 下载后强制校验）。未修改二进制。
- clients 对应提交为 `b449ac1d255784380d75ef026343198891286be7`；其 package-lock 锁定 GPL SDK `@bitwarden/sdk-internal@0.2.0-main.1075`，[npm 元数据](https://registry.npmjs.org/@bitwarden/sdk-internal/0.2.0-main.1075) 的 gitHead 为 `c5e53d3e82ab80fdc9fd79ebd74058399a6444b6`，对应 [官方 SDK 源码](https://github.com/bitwarden/sdk-internal/tree/c5e53d3e82ab80fdc9fd79ebd74058399a6444b6)。

- SDK 的根 `LICENSE` 允许默认代码选择 GPL-3.0 或 SDK License，任意层级名为 `bitwarden_license` 的目录仅适用 SDK License；本分发选择 GPL-3.0，并保留根三份许可及 `crates/bitwarden-wasm-internal/npm/LICENSE`（GPL-3.0）。SDK 官方 `build-wasm-internal.yml` 将 `npm`（OSS，空 build_flags）与 `bitwarden_license/npm`（商业，`-b`）分开；`build.sh` 的 OSS 分支不启用 `bitwarden-license`，且设置 `bitwarden_ensure_non_commercial` 防止商业 crate 混入。归档同时排除 SDK 根目录和 WASM 包内嵌套商业目录，不将 SDK License-only 内容误当 GPL。

镜像携带对应源码归档（含构建脚本、依赖 lockfile，移除不参与 OSS 构建的 `bitwarden_license/` 商业源码目录，避免再分发商业模块），位于 `/usr/share/warden-guard/sources`，同样附在版本 Release；归档内 GPL 源码文件未修改，商业目录仅删除而非改许可；上游构建脚本的商业构建目标不适用。注意 SDK Cargo workspace/可选依赖仍引用被排除的商业路径，SDK build.sh 还使用 git 元数据；这些上游脚本原样保留，本项目没有验证删除商业目录后的独立源码重建，也不宣称逐字节可重现或已完成 GPL Corresponding Source 法律完整性认证；公开分发前维护者仍应核实重建输入与间接依赖源码义务。上游 LICENSE*.txt 与 NOTICE 位于 `/usr/share/licenses`。GPL 组件不因与 MIT 编排程序通过独立 subprocess 聚合而改成 MIT。

项目无 pip 第三方依赖，CLI 仍包含 npm/Rust 间接依赖。这里不是法律认证或逐包许可证审计；Node/Debian 保留镜像原始 notices。后续升级应重新核对上游构建和 SDK 源码提交，不能无校验切回 npm 包。
