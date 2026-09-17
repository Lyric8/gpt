时间：2026-09-18T06:09:21+08:00　作者：Hermes

source_path: chat/to-hermes/2026-09-18T055200+0800-campfire-v4-photo-assets.md
source_message_id: 2026-09-18T055200+0800-campfire-v4-photo-assets--0bae728ebbe066cbb394cd0db459138bd812a6e6
source_blob_sha: 0bae728ebbe066cbb394cd0db459138bd812a6e6
status: DONE
reply_required: false
action_required: false

## 交付

分支 `feat/campfire-v4-photo-assets`，commit `10b0d12aa96ebe7a1b440bc13dbbb31044a7e7f7`，parent = `f970c7b3ca6caf9d57a1c11edeefa51564b1639f`（你给的 main 基线；推送前 fetch 复核 origin/main 仍为该值）。未动 main、未合并、未打 tag、未发版、未碰 `feat/campfire-v4-300-fire`、未改应用源码。

相对 main 的差异：`git diff --name-status origin/main origin/feat/campfire-v4-photo-assets` 全部为 `A`（新增 12 个文件，无 M/D）：

| path | bytes |
|---|---|
| `projects/campfire-kitchen/assets/photos/v4-pork-skewers.webp` | 50914 |
| `projects/campfire-kitchen/assets/photos/v4-ribs.webp` | 69438 |
| `projects/campfire-kitchen/assets/photos/v4-squid.webp` | 30220 |
| `projects/campfire-kitchen/assets/photos/v4-wings.webp` | 64556 |
| `projects/campfire-kitchen/assets/photos/v4-sausage.webp` | 23166 |
| `projects/campfire-kitchen/assets/photos/v4-whole-chicken.webp` | 81906 |
| `projects/campfire-kitchen/assets/photos/v4-duck.webp` | 29720 |
| `projects/campfire-kitchen/assets/photos/v4-oyster.webp` | 54760 |
| `projects/campfire-kitchen/assets/photos/v4-whole-fish.webp` | 27442 |
| `projects/campfire-kitchen/assets/photos/v4-pork-belly.webp` | 39618 |
| `projects/campfire-kitchen/data/photos-v4.json` | 4210（blob `d3a67bd8cafb894aa5eee6097fee21b425be79b1`，sha256 `9802a78b02ca9351bcd59ca48b009ee9e9a1260e3c75c99ce469b9ae450cfb44`） |
| `projects/campfire-kitchen/data/photos-v4-provenance.json` | 10633（blob `1a3d96495014969b340f92da52b83319f398845e`） |

抽验字节一致性（本机文件 vs 从远端 ref 取出的对象）：`v4-duck.webp` `9d7a981a176d…`、`v4-whole-chicken.webp` `b3b0ea74829a…`、`v4-ribs.webp` `6be58123a0b8…`、`photos-v4.json` `9802a78b02ca…`，四项 local == remote。

## 处理规格（实测值，非声明）

- 长边 640px、等比缩放、**不裁切**：下载 Commons 960px 宽缩略图后一次 LANCZOS 缩到长边 640（10 张全部为 640 长边，其余边 427~506）
- 编码 WebP `method=6`，quality 从 72 起；仅当结果 >60KB 才试 70/68/66/64
- 单图 22.6–80.0 KiB；10 张中 **7 张 ≤60KB**，3 张超：`v4-ribs` 69438B、`v4-wings` 64556B、`v4-whole-chicken` 81906B
- 合计 460.7 KiB（10 张）
- 这三张降到 q64 后仍超 60KB。按你「**不得为了尺寸失真**」的要求我没有继续降质（q64 已偏离你给的 ~72，再降会出现可见劣化）。**这是唯一需要你决定的点**：若必须硬压到 60KB 以内，请给一个可接受的 quality 下限（例如允许 56/52），我重出一版。
- 无 EXIF/元数据（PIL 默认不写），原始 JPEG 未入库，只入 WebP

## 元数据

- `data/photos-v4.json`：10 个 key，value 与 `data/photos.json` 同构（`src`/`alt`/`author`/`source`/`license`/`licenseUrl`/`note`）
- `data/photos-v4-provenance.json`：每条含 `download_url`（实际抓取的 Commons 960px 缩略图 URL）、`download_bytes`、`download_sha256`、`source_file_url`（Commons 原文件）、`source_file_size`、`source_file_page`、`commons_file`、`license`/`license_url`/`author`，以及 `webp`/`webp_size`/`webp_bytes`/`webp_quality`/`webp_sha256`
- 说明：`download_sha256` 是**我实际抓取的 960px 缩略图字节**的 SHA256（不是几 MB 的原文件）——原文件 URL 与原始尺寸另列在 `source_file_url`/`source_file_size`，避免把「缩略图哈希」误当「原图哈希」
- 许可分布：CC BY-SA 4.0 ×5、CC BY-SA 3.0 ×1、CC BY-SA 2.0 ×1、CC BY 4.0 ×1、CC BY 2.0 ×2。逐张读 Commons 文件页 `extmetadata`（LicenseShortName / LicenseUrl / Artist）后才采用；剔除含 NC/ND 的候选，无图库水印图、无 AI 图、无「授权不明」条目
- 你指定的三张逐一核验后采用：`Mu ping.jpg`（Phoebus 28，CC BY-SA 4.0）、`Ribs barbecue.jpg`（Gyfjonas，CC BY-SA 3.0）、`Inihaw na Pusit DSCF4327.jpg`（Joy D. Ganaden，CC BY-SA 4.0）——三张的文件页许可与作者与你写的一致

## 主体核对（逐张视觉，含弃用样本）

候选合计 **172 条**（指定 3 + 两个指定分类 60 + 检索补足 109），分组合成拼版逐格视觉核对后选定 10 张。明确弃用的例子（可复现的坑）：

- `Whole grilled fish, Kolkata - West Bengal - DSC 0038.jpg`（CC BY-SA 4.0）：缩略图实际是「白猫 + 两条鱼」，主体是猫不是菜品 → 弃用（同系列 0037 同判）
- `Roast duck 2.jpg`：案板上的**生**鸭，不是烤鸭 → 弃用；`A dish of Pork Belly in the table.jpg`：案板生肉 → 弃用
- 黑白历史照片（芬兰 Ilvespolku 徒步那张「香肠」）、以人物/摊位为主体的（Shilin night market、Guan's Wing Bar）、餐桌场景里主体被稀释的 → 弃用
- 分类里大量 Calçotada 系列（巴塞罗那烤大葱）属同名误入，未采用
- 鸡翅、香肠优先取你点名的 `Category:Grilled chicken wings` / `Category:Grilled sausages`，最终选自其中主体最清晰的条目（鸡翅 = `Dak nalgae wings.jpg`，香肠 = `Sausages on a Barbecue.jpg`）
- 全部 10 张的 `alt` 按**图中实际内容**写（例如 duck 是「整只烧鸭」、whole-chicken 是「整只香料烤鸡配小土豆」），不假称本配方成品

## artifact 与唯一悬空点

本仓库现役 workflow 只有三个：quality（push 到 main 与一个特定 feat 分支 / PR）、release（Release published）、rollback（手动）。本次推送到 `feat/campfire-v4-photo-assets` **未触发任何 workflow**，因此没有 run，也没有可下载的 artifact id 可给。按你 2026-09-18T00:02 对 v3 同款请求的裁决（「不新增 Actions artifact ZIP」，资产分支以固定 commit 寻址），本次同样不新增导出 workflow；文件都在分支上，可按 `feat/campfire-v4-photo-assets` + 上表路径直接取。

若你需要压缩包，请指定可接受的做法（例如允许我在该分支加一个只做 upload-artifact 的 workflow，或让 quality workflow 的触发分支加上这条），我照做——这属于你的设计面，我不抢跑。

未做的动作：不改 main、不合并、不发布、不打 tag、不碰服务器与线上、不碰 `feat/campfire-v4-300-fire`。
