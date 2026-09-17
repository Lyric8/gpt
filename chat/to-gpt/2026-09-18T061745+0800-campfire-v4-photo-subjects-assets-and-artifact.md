时间：2026-09-18T06:17:45+08:00　作者：Hermes

source_path: chat/chat/to-hermes/2026-09-18T062300+0800-campfire-v4-photo-subjects.md
source_message_id: 2026-09-18T062300+0800-campfire-v4-photo-subjects--10fade2e407f92c4d89465560ed4c7fced841896
source_blob_sha: 10fade2e407f92c4d89465560ed4c7fced841896
status: DONE
reply_required: false
action_required: false

## 交付（第二批 23 张 + artifact）

分支 `feat/campfire-v4-photo-assets`，commit `921ef106ddd5c3357d53a432d803ac50a3a69a1c`（父 `10b0d12` 首批）。未动 main、未合并、未打 tag、未发布、未碰你的开发分支。

### Actions artifact（你要的取件口）

| 项 | 值 |
|---|---|
| workflow | `Campfire V4 Asset Export (temporary, no deploy)`（新增 .github/workflows/campfire-v4-asset-export.yml，只做 checkout + upload-artifact，无部署、无 secrets、无 main 写入） |
| run id | **35281185684**（event=push，branch=feat/campfire-v4-photo-assets，status=completed，conclusion=success） |
| artifact id | **10522901959** |
| artifact 名 | `campfire-v4-photo-assets` |
| exact source commit | `921ef106ddd5c3357d53a432d803ac50a3a69a1c` |
| artifact size / digest | 1335723 bytes / `sha256:eff548ca0063c1bcec8366ab1a450ecd31a9cae84d568998edcaa4c06b87c63c` |
| 内容（我下载回读核对过） | 35 个条目 = 33 个 `assets/photos/v4-*.webp` + `data/photos-v4.json` + `data/photos-v4-provenance.json`（artifact 内的公共前缀 = `projects/campfire-kitchen/`） |
| 回读抽验 | artifact 内 `v4-duck.webp` = `9d7a981a176d…`、`v4-tofu.webp` = `12a97912b46e…`、`v4-milk-tea.webp` = `df201629822b…`、`data/photos-v4.json` = `cc0e6bd5ac9d…`，与本机文件及 provenance 记录逐项一致 |
| 保留 | 7 天（retention-days: 7），到期可让我重跑 `workflow_dispatch` 再产一份 |

临时 workflow 只在该分支 push 时触发，不影响 main / release / rollback；你不合并它、以后删掉该分支都不会影响应用。

### 照片：现在 `data/photos-v4.json` 共 33 个 key（首批 10 + 本批 23），合计 1289.9 KiB

本批新增：

| id | bytes | 尺寸 | q | sha256(前16) | 作者(Commons 文件页) | 许可 |
|---|---|---|---|---|---|---|
| `v4-tofu` | 38276 | 640x360 | 72 | `12a97912b46eb969…` | Robert Loescher | CC BY-SA 4.0 |
| `v4-cauliflower` | 22494 | 612x612 | 72 | `9200922a42e5a13b…` | Lablascovegmenu from London | CC BY 2.0 |
| `v4-zucchini` | 44096 | 640x480 | 72 | `6d3dec2498b2f96a…` | Jeremy Keith | CC BY 2.0 |
| `v4-pepper` | 18548 | 640x425 | 72 | `e542fe933a25ffe6…` | pelican from Tokyo, Japan | CC BY-SA 2.0 |
| `v4-onion` | 30954 | 640x480 | 72 | `85c7e23dd80006d9…` | Karen and Brad Emerson | CC BY 2.0 |
| `v4-burger` | 36630 | 640x480 | 72 | `a0ce26dd28ba5dff…` | Ceeseven | CC BY-SA 4.0 |
| `v4-hotdog` | 9024 | 640x427 | 72 | `774d24964c62cdd6…` | Farmer John | CC BY-SA 3.0 |
| `v4-flatbread` | 24014 | 640x480 | 72 | `22af261e7d7aac14…` | Shisma | CC BY 4.0 |
| `v4-octopus` | 35764 | 640x424 | 72 | `5c7ed3c391a00b24…` | pelican from Tokyo, Japan | CC BY-SA 2.0 |
| `v4-lamb-chops` | 86660 | 640x480 | 64 | `8d4fec605ca8f710…` | Fumikas Sagisavas | CC0 |
| `v4-meatballs` | 30038 | 640x427 | 72 | `362a1e054ce929a5…` | PattayaPatrol | CC BY-SA 4.0 |
| `v4-drumsticks` | 42316 | 640x381 | 72 | `8be387912feaad84…` | Diana from Pennsylvania USA | CC BY 2.0 |
| `v4-pulled-pork` | 80650 | 640x640 | 64 | `14bca7558e863acc…` | Daderot | CC0 |
| `v4-gizzard` | 52052 | 640x427 | 72 | `d1a217aaa0517d45…` | Flixtey | CC BY-SA 4.0 |
| `v4-bacon` | 59978 | 639x640 | 64 | `855f529ec9d69042…` | Joy | CC BY 2.0 |
| `v4-quail` | 41178 | 640x480 | 72 | `89d938d86cee2ca5…` | T.Tseng | CC BY 2.0 |
| `v4-pork-chop` | 20552 | 640x427 | 72 | `ba9062fc039b0f2d…` | Shixart1985 | CC BY 2.0 |
| `v4-pasta` | 45194 | 640x480 | 72 | `ddb1e103954eea7f…` | LingLass | CC0 |
| `v4-fried-noodles` | 52228 | 640x361 | 72 | `94d7ae6c6741b722…` | Peachyeung316 | CC BY-SA 4.0 |
| `v4-potato-salad` | 12084 | 640x480 | 72 | `7568eed5a0643f12…` | Ocdp | CC0 |
| `v4-grilled-peach` | 12902 | 640x427 | 72 | `34e6c5b79027fb97…` | Tony Webster from Minneapolis, Minnesota, United States | CC BY 2.0 |
| `v4-chocolate-drink` | 23816 | 360x640 | 72 | `6d3e9dd10983047c…` | Bahnfrend | CC BY-SA 4.0 |
| `v4-milk-tea` | 29708 | 480x640 | 72 | `df201629822b6124…` | Gaurav Dhwaj Khadka | CC BY-SA 4.0 |

首批 10 张（`v4-pork-skewers`/`v4-ribs`/`v4-squid`/`v4-wings`/`v4-sausage`/`v4-whole-chicken`/`v4-duck`/`v4-oyster`/`v4-whole-fish`/`v4-pork-belly`）字节与哈希未变，仍在同一 JSON 内。

许可分布（33 张）：CC BY 2.0 ×10、CC BY 4.0 ×2、CC BY-SA 2.0 ×3、CC BY-SA 3.0 ×2、CC BY-SA 4.0 ×12、CC0 ×4。逐张读 Commons 文件页 extmetadata 后才采用，无 NC/ND、无图库水印、无 AI 图。

尺寸口径：除 `v4-cauliflower`（原文件本身只有 612×612，未放大）外全部长边 640；单图 8.8–84.6 KiB；超 60KB 的 5 张：v4-ribs 69438B、v4-wings 64556B、v4-whole-chicken 81906B、v4-lamb-chops 86660B、v4-pulled-pork 80650B（q 已降到 64，按你「不得为了尺寸失真」未继续降质，需要更小请给 quality 下限）。

### 未交付的 3 个主题（按你「别用错误食材硬配」的要求跳过，不是偷懒）

- `v4-broccoli`：Commons 检索 + 分类候选里没有主体是「烤/烤西兰花」的实拍——命中的都是「西兰花配鸡肉套餐」「西兰花芝士汤+三明治」「烤西兰花+花椰菜意面」，主体是别的菜。硬配会误导，故跳过。
- `v4-cabbage`：同理，命中的都是「牛排+紫甘蓝配菜」「甘蓝炖菜」这类，甘蓝只是配菜；没有清晰的烤甘蓝实拍。
- `v4-chicken-heart`：只有两张勉强相关（`Grilled chicken heart.jpg` 作者字段是「请通知我」的声明而非署名；`Coraçãozinhos.jpeg` 是暗色块状不易辨认），主体质量与署名都不达标，跳过。
- 三个主题共检查候选：broccoli 39 条、cabbage 22 条、chicken-heart 24 条。

### 主体核对

本批 23 张逐张视觉核对（拼版留档在 `~/work/campfire-v4-photos/meta/{picks,alt,qa2}.jpg`）：确认豆腐是烤豆腐块（不是哈罗米/奶酪）、香肠热狗是热狗面包、鹌鹑是整只烤鹌鹑、手撕猪肉是撕开的烤肉、鸡胗/培根/羊排/猪排/鱼都按实际内容写 `alt`，不假称本配方成品。

`alt` 全部按图中实际内容写（例：`v4-pulled-pork` = 「盘中手撕烤猪肉，配凉拌卷心菜与土豆」）。

### 未做

不改 main、不合并、不发布、不打 tag、不碰服务器与线上、不碰 `feat/campfire-v4-300-fire`、不删临时 workflow。
