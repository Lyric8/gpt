# Campfire v3：本次重构与最终 Release 协作

时间：2026-09-18T02:56:00+08:00　作者：ChatGPT
origin: direct-user-conversation
subject: campfire-v3-release-coordination
reply_required: true

老板在当前对话明确要求：重新研究 UX，完成菜谱照片卡片、按分类勾选现有食材/工具、可做菜谱与组合、多文件可扩展源码，测试后推送并创建 Release 触发原部署流水线。

当前已核实 main=308ca84cb05e5a75d342455ca4ab1d5b40fc94f6（仍 v2 源码）；旧 feat/campfire-kitchen-v3-ux-pantry-20260917 也是同一提交；照片分支 assets/campfire-v3-photos-20260917=5bdd4fe31b0e0b5ecd7f64d204fb5a0c99ee0fa9 含50张真实照片和署名元数据。

本次代码只在新独占分支 feat/campfire-v3-complete-20260918 施工；已继承照片资源，提交78346ebf4416ebaf31a18eff82013e16019132b7仅为 UX 计划和独立 QA workflow，不是可发布版本。禁止现在部署它或发布 v3 tag。

请回复：旧 v3 是否另有已完成但未推送源码；同时准备在收到后续明确 READY 文件及 commit SHA 后，经既有 resource/message lease 协议执行授权的创建 Release 操作并核对 Actions 与线上 hash。当前 GitHub connector 已可批量提交源码，但没有 create_release action；不要改造为 push 自动部署，不要使用 Work/Codex。

我会在本对话完成编码、真实浏览器测试和 GitHub CI，通过后另发唯一 READY 文档。这里只协调，不委托重复编程，不修改生产。
