# Agent Note: OSS 镜像与标签发布边界

Status: implemented

## Problem
MIT 自有编排源码不覆盖打包的第三方 CLI；npm 发布链实际提升商业构建，不能把旧 publish:npm OSS 脚本当成实际分发证据。

## Decision
镜像采用官方 CLI OSS amd64 Release，强制校验官方 asset SHA256，保留上游 OSS 源码归档与许可（移除不参与构建的商业源码目录）。SDK 提交按该版本 npm gitHead 固定。独立进程边界不变，安全设置和业务流程不放宽。
main 推送测试后更新 main/sha 镜像；PR 不登录不推送；版本标签必须与 VERSION 一致。Release 依赖镜像成功并从不可变摘要提取第三方源码，显式 Git 文件归档不包含环境/状态/证据。发布流程永不 SSH 部署。

## Alternatives considered
- 保持 npm 默认安装最简单，但官方实际发布 artifact 来自商业构建，与商业模块分发限制不兼容。
- 自建整个 OSS CLI 可控制依赖，但官方已提供明确 OSS 产物；选用校验过的官方产物减少构建面。
- 同时声明 arm64 有利兼容，但本次未实际构建验证，只发布 amd64。

## Consequences
镜像额外包含对应源码，尺寸增加；维护者必须重新核对每次升级的源码和 SDK 提交。GPL 依赖保持原许可，项目 MIT 不变。源码归档提供构建输入但不宣称逐字节可重现。已有架构 note 不涉及发布决定，无重叠或过时提案。测试和镜像发布成功不代表生产已部署。
