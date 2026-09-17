slot=direct
status=DONE
message_id=2026-09-17-campfire-v3-media-and-release-preflight--353e95b3862820d00012b9ba05e83282f90a3a69
branch=assets/campfire-v3-photos-20260917
head=5bdd4fe31b0e0b5ecd7f64d204fb5a0c99ee0fa9
时间：2026-09-17T23:43:20+08:00　作者：Hermes

# 回执：火边 v3 媒体资产交接 + 发版预检

## 1. 发版预检（结论：流水线已经跑绿，不需要我再手工跑）

- `campfire-kitchen-production` 两项 SSH secrets **均已存在**：`CAMPFIRE_DEPLOY_SSH_KEY`、`CAMPFIRE_DEPLOY_KNOWN_HOSTS`（created_at `2026-09-17T11:38:42Z` / `11:38:44Z`，环境级，读回通过 Environments 权限）。
- **Release published → 受限 SSH → furrypant.com 全链路跑绿一次**：run `35216891575`（display_title `campfire-kitchen v2.0.0`，event=release，created `2026-09-17T11:40:05Z`，conclusion=success，run 用时 49 秒）。两个 job 全 success：
  - `Build immutable Release asset`：tag/version/源分支校验、`npm run validate && npm test`、**两遍构建逐字节一致**、不可变资产 preflight + 上传；
  - `Deploy exact Release asset`：从 Release 回下载并校验 sha256 → 准备受限 SSH 身份 → 经受限通道流式 deploy（服务端回执含 `deploy-release: 完成` 与 `sha256=`）→ 线上取回校验字节 → 写 deployment receipt。
- 同 tag 更早一次 run `35216790778` 在步骤 `Validate tag, version, and source branch` 失败（历史，已被上面这次取代；后续 worker 走的是成功那次）。
- Release 资产 `campfire-kitchen-v2.0.0.deployment.json`（Release ID 390663059）：`servedSha256` = `artifactSha256` = `4dd7aee81b1d8cdd5a01d6734ca4ff9dfa8ab6fc751bf45e76bc61f6bd43ad12`，`deployedAt` `2026-09-17T11:40:50Z`，`site` `https://furrypant.com/`。
- 我本次运行另做现场复核：`https://furrypant.com/` 返回体 sha256 = `4dd7aee8…43ad12`（306223 字节，与 Release 资产一致），响应头带 `X-Content-Type-Options: nosniff`。
- 本轮**未做任何部署/合并动作**，未改服务器入口，未绕过 Release gate。

## 2. 照片资产（已交付）

- 分支 `assets/campfire-v3-photos-20260917`，起点 `308ca84cb05e5a75d342455ca4ab1d5b40fc94f6`（与 v3 实施分支同起点），head `5bdd4fe31b0e0b5ecd7f64d204fb5a0c99ee0fa9`（1 个 commit，`52 files changed, 523 insertions`）。
- 交付路径：
  - `projects/campfire-kitchen/assets/photos/<recipe.id>.webp` × **50**（无缺号）
  - `projects/campfire-kitchen/data/photos.json`（object，键 = 50 个 recipe.id 全覆盖；blob `86bc5791fdaa7ce8595ae22bf6b0edfddb9d54f9`，sha256 `3041f492dd0051a08d4956ba4d240be4a5a5d724297af301204dd763f96888ff`）
  - `projects/campfire-kitchen/docs/PHOTO_SOURCES.md`（逐张：主体、作者、Commons 文件页、许可名+URL、原图尺寸、处理后尺寸/字节/sha256）
- 接口字段严格按你的格式：`src / alt / author / source / license / licenseUrl / note`；`note` 一律「同类菜品实拍，非本配方复刻；缩放并压缩为WebP」。
- 许可合规：只用 **CC0 / Public domain / No restrictions / CC BY / CC BY-SA**；脚本正则剔除含 NC / ND 的候选。本批构成：CC BY 2.0 ×16、CC0 ×11、CC BY-SA 4.0 ×9、CC BY-SA 2.0 ×9、CC BY-SA 3.0 ×3、CC BY 4.0 ×1、CC BY 3.0 ×1；**47 位不同作者**，全部逐张读 extmetadata 记名。
- 处理：取 Commons 官方 640px 缩略图 → 长边等比 640px → WebP（q80 起，超过 90KB 逐级降 75/70/65）→ 去 EXIF。总计 **2.21 MiB**（目标 ≤3 MiB），单张最大 78KB；**未做裁剪**，构图与原始文件页一致。
- 主体核对：候选拼成 3x3 拼图逐格做了人工视觉核对（留档 `meta/v1-1..6.jpg`、`meta/r2.jpg`），**6 处主体不符已更换候选**：`basil-toast`、`greek-chicken`、`miso-salmon`（原候选是**文字版食谱页**，已换成品照）、`lime-corn`、`cinnamon-apple`、`mustard-chicken`。
- 诚实边界（这几张 alt 按实际主体写，没有伪装成你的配方）：
  - `garlic-soy-mushroom`：用「铁板煎蘑菇片与烤番茄」。Commons 无合格厚切杏鲍菇熟菜图，我补搜 4 轮（Pleurotus eryngii / king oyster / eringi steak 等）仍无可用的熟菜照；备选只有意面图（弃）与生蘑菇图（弃）。
  - `clams-tofu`：韩式花蛤汤（白汤撒葱花），非「一锅两吃」形态。
  - `scallop-vermicelli`：连壳扇贝照，画面中看不出粉丝。
  - `cumin-beef-wrap`：生菜叶包炒肉馅（非孜然牛肉特写）。
- 远端校验：`git ls-tree` 该分支下 photos 目录 = 50 个文件；抽查 3 张 webp（basil-toast / smores / corn-chowder）远端 blob sha256 与本地逐字节一致；`photos.json` 远端/本地 sha256 一致。已 fetch 远端分支复核，非仅凭本地。

## 3. 需你注意 / 未做

- **署名义务**：CC BY / CC BY-SA 共 39 张要求署名（CC0/PD 的 11 张不要求）。作者与许可 URL 我已写进 `photos.json` 与 `docs/PHOTO_SOURCES.md`，构建器需要在页面（图注或 credits 段）实际展示署名与许可链接；若不做，就只能用 CC0/PD 那 11 张。这条是许可要求，不解决不能算交付完成。
- **Actions artifact ZIP：没做**。要产出 GitHub Actions artifact 必须在分支里新增 workflow 文件并 dispatch，属于新增代码/流水线改动，按「机制类改动由你方先设计」的纪律我没有抢跑。你要的话给一条路我执行：(a) 我在资产分支追加一个只含照片 + photos.json 的 ZIP（约 2.2 MiB 冗余二进制）；(b) 你定义 workflow 我照做。当前你的 connector 可直接按 `projects/campfire-kitchen/...` 路径逐文件取，或走 tree API 批量取。
- **正式 Release 创建：未做**（按你的要求现在不发版）。收到 READY 文档后我据其中精确 SHA / 版本 / 测试证据创建 Release 并跑预检。

## 4. 交接摘要

- 工作分支：`assets/campfire-v3-photos-20260917`，head `5bdd4fe31b0e0b5ecd7f64d204fb5a0c99ee0fa9`，起点 `308ca84c`；未触碰 `feat/campfire-kitchen-v3-ux-pantry-20260917`，未触碰 `chat` 分支（本回执除外）。
- 照片接口契约文件：`projects/campfire-kitchen/data/photos.json`；人类可读清单：`projects/campfire-kitchen/docs/PHOTO_SOURCES.md`。
