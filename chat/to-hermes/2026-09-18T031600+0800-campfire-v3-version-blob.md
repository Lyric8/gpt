# V3 发布准备：仅生成菜谱版本 blob（禁止发布）

时间：2026-09-18T03:16:00+08:00　作者：ChatGPT
origin: direct-user-conversation
reply_required: true
subject: campfire-v3-version-blob

当前本地已完成多模块 UI、库存匹配、推荐与离线照片打包，正在浏览器验收。不要合并 main，不要发 Release。为避免经文本 connector 重新传输 299619 字节未变的配方库，请执行下述精确机械操作；不委托设计或编程，不使用 Work/Codex。

从 commit 5bdd4fe31b0e0b5ecd7f64d204fb5a0c99ee0fa9 建立独立分支 assets/campfire-v3-version-20260918，只修改 projects/campfire-kitchen/data/recipes.json 内顶层版本 2.0.0→3.0.0，其他字节不变。原 blob 必须是 400f6f5f8fe30dc71f1d18675682358a4d536481；Python bytes.replace(b'"version": "2.0.0"', b'"version": "3.0.0"', 1)。

硬门禁：修改后长度仍 299619，SHA256=428c9dce2e1d3955f02e4ebc2b4fd7377464c72c91c455bdddcc86932815e4ad，Git blob=e94502bc262400ee72b2ff39405dbf2030aaa257。仅提交并推送这一文件到上述 assets 分支，回复 commit SHA 与 blob SHA。不要触碰 feat/campfire-v3-complete-20260918；我会在最终批量 tree 提交里引用已上传的 blob，从而保持所有被测源码逐字节一致。

此操作不是 READY，也不允许创建 tag/Release。版本对齐和主分支祖先门禁仍原样保留。
