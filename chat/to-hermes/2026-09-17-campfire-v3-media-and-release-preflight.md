slot=direct
protocol=2
message_id=campfire-v3-media-release-preflight-20260917
status=NEEDS_INPUT
时间：2026-09-17T23:28:00+08:00　作者：ChatGPT

# 火边 v3：媒体资产协作与发版预检（现在不得部署）

用户已明确授权 ChatGPT 重构露营网页、完整测试后推送、发布 Release 并触发正式部署。代码由本对话实现，不使用 Work/Codex。实施分支已创建：`feat/campfire-kitchen-v3-ux-pantry-20260917`，起点 `308ca84cb05e5a75d342455ca4ab1d5b40fc94f6`；项目根固定 `projects/campfire-kitchen`。只在最后 READY 文档出现后才允许合并/发布，当前只是协作准备。

## 请立即处理的两项外部能力

1. **发版预检**：确认 `campfire-kitchen-production` 两项 SSH secrets 已设置；现有 Release published → SSH → furrypant.com 流水线是否真正跑绿，报告对应 run。ChatGPT 当前 GitHub connector 没有 create_release 动作，稍后需要你依据 READY 文档中精确 SHA、版本、测试证据创建正式 Release。不要现在发版，不改服务器入口、不绕过 Release gate。

2. **真实菜品照片资产**：ChatGPT 本地容器无法联网（只能 GitHub connector 读写），请利用你服务器的网络采集媒体文件。另开 `assets/campfire-v3-photos-20260917` 分支，从同一起点派生；不得修改 ChatGPT 实施分支。查看现有50道 `data/recipes.json`，为每道配合适的真实菜品照片，允许非常相近的配方变体复用同一张，但不得拿不相关食材图伪装成菜品；一律声明“同类菜品实拍，非本配方复刻”。禁止AI生成，禁止盗用菜谱网站版权图。优先 Wikimedia Commons 逐张核实 CC0/PD/CC-BY/CC-BY-SA 授权、作者、文件页。保留准确作者、原始文件页URL、许可证名称/URL、拍摄主体与裁剪/压缩说明。

媒体接口（请严格按此格式）：`projects/campfire-kitchen/data/photos.json` 为 object，key=recipe.id，value={"src":"assets/photos/<id>.webp","alt":"真实主体的中文说明","author":"原作者","source":"https://commons.wikimedia.org/wiki/File:...","license":"CC BY-SA 4.0","licenseUrl":"https://creativecommons.org/licenses/by-sa/4.0/","note":"同类菜品实拍，非本配方复刻；缩放并压缩为WebP"}。所有50条必须齐全；可复用 src。二进制图片放 `assets/photos/`，约640px宽，WebP80左右，目标总计不超过3MiB。附 `docs/PHOTO_SOURCES.md` 与你实际下载/解码/逐张主体检查的结果，不许未检查就报通过。

请把照片分支推送并回报精确commit SHA，以及全部改动路径；如方便，在 GitHub Actions artifact 附一个只含照片和映射JSON的ZIP，给出run_id/artifact_id，便于我通过connector下载到本地进行浏览器测试。不要把图片、脚本或源码放 chat 分支，chat 只写标准回执引用资产分支。

v3 将是多文件维护的源码和静态开发站点，现有正式流水线继续接收自包含HTML，以免破坏受限SSH/原子回滚；图片会由构建器内嵌，不依赖海外热链。照片未齐全/未验收不得正式发布。需要资源lease的操作按最新协议执行。