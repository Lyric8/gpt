# V4 三张主体不符照片已替换并导出（附 1 处我按像素证据未照改的说明）

时间：2026-09-18T07:44:36+08:00　作者：Hermes
source_path: chat/to-hermes/2026-09-18T071300+0800-campfire-v4-three-photo-replacements.md
source_message_id: 2026-09-18T071300+0800-campfire-v4-three-photo-replacements--1a1228926e2a750f6bd5c3d6ecdff0a80a6a3c6f
source_blob_sha: 1a1228926e2a750f6bd5c3d6ecdff0a80a6a3c6f
status: DONE
reply_required: false
action_required: false

## 1. 三张替换：只换了我素材分支的 WebP + metadata/provenance

分支 `feat/campfire-v4-photo-assets` head = **`508ca11f9186bfd92ba6c085ecdd4bc5669d9801`**（父 `8d10612dd080bfcb937f147d81ac61a5b3b85021`）；`git diff --stat` 仅 5 files（3 webp + 2 json），54 insertions / 54 deletions。

| key | 采用来源（你指定的那三个） | 许可 / 作者 | 处理 | 字节 / 尺寸 / q | 文件 sha256 | git blob |
| --- | --- | --- | --- | --- | --- | --- |
| `v4-enoki` | `File:Enoki mushrooms (50313211173).jpg` | CC BY-SA 2.0 / Dushan Hanuska | 白细柄小菌盖，成丛长在深色菌棒上（下载后目视确认） | 32662B / 480×640 / q72 | `597810de707c2250860f9e6f8a6cfcf9d1765a9c182a70cd0a0d9a25d2b43879` | `423cc70abe1cf16ce94dbc802a995b5f8364ad79` |
| `v4-chives` | `File:Garlic chives 2.jpg` | CC BY 2.0 kr / 경빈마마 | 成堆择净的 Allium tuberosum（叶片扁平，非管状细香葱） | 48012B / 640×479 / q72 | `399597e2f6cfcf7e98a1b271e2ca351b6ce345ff97158dbe5536578e014faf4a` | `3b7aa5ecacb1aa047026abbe6d54b5c2d9435d7c` |
| `v4-tofu-skin` | `File:White tofu sheet.jpg` | CC0 / Fumikas Sagisavas | 黑色托盘里折叠叠放的白色薄片（可卷的鲜豆皮/千张），非干碎腐竹 | 19392B / 640×640 / q72 | `41b603ac0db155f74ec0f36160d27ebfd16eafaaef64da07f52322a3bdd33206` | `cf2d6173b805ac9c673cfb1902c55f871d549ee7` |

三者 `kind` 均保持 `"ingredient"`、note 仍写「食材参考，非成品；按长边640px等比缩放并转WebP；沿用原许可」。provenance 逐张记 `download_url / download_bytes / download_sha256 / source_file_url / source_file_size / source_file_page / commons_file / license / license_url / author / exif_camera / exif_datetime / webp_size / webp_bytes / webp_quality / webp_sha256`；两张 EXIF 可取证（enoki `Apple iPhone 7 Plus` @2020-08-30、tofu `HUAWEI FRL-AN00a` @2024-06-19），chives 源文件 700×524、2010 年原图（无 EXIF）。

`photos-v4.json` 26759B / sha256 `9656150d37ad4a5c1d7da994bca61539b1297631a76adbc08a2d4e9c04aee199`；`photos-v4-provenance.json` 70099B / sha256 `b53d44a35cd2f1c7d24b00c6b20cd65b01c5681ac669abcdfc556493bb0d9bcf`；key 数前后均为 60（只替换、不增删）。

## 2. alt 更正（画面与原文不符）

| key | 原 alt | 现 alt |
| --- | --- | --- |
| `v4-cucumber` | 黑盘中拍碎后用红油拌好的黄瓜块 | 黑盘中拍碎的黄瓜块，裹奶白色酱汁、淋辣椒油并撒脆葱酥 |
| `v4-pumpkin` | 黑色烤盘上切成块的烤南瓜 | 切开摊成花瓣状的去皮南瓜块，放在带孔金属蒸架上 |
| `v4-meat-patties` | 烤架上翻烤的肉饼，旁边放着面包胚 | 烤架上并排翻烤的肉饼，左侧金属盘里放着切开烤过的面包胚 |

## 3. 一处我按像素证据没照改：`v4-meat-patties` 确有面包胚

你写「只看见烤肉饼，没有面包胚」。我把该 WebP 原图左上角裁出 4 倍放大核对：**左上深色煎盘里明确有两片切开、切面烤过的面包胚**（一片完整半球朝上、一片只露局部），所以我把 alt 收紧成「左侧金属盘里放着切开烤过的面包胚」，而不是删掉面包胚。若你要的是画面里完全没有面包胚的肉饼图，需要换源图 —— 本件没换，只改描述；要换请发一句，我按你给的 Commons 文件走同一流水线。

## 4. 核对证据（下载 → 导出 → 回读）

- 导出：临时 workflow（只 checkout + upload-artifact，不部署）run **`35287994407`** success，head_sha = `508ca11f91`；job `export` 四步全 success。
- 取件口：artifact **`10524639236`** / `campfire-v4-photo-assets` / 2437787B / `digest sha256:8791c60ee7a6b0deef27505ce48d2660acf1630260bba4a6901cd68f4bec15c0`。
- 我用 GitHub connector 下载该 artifact：zip 落盘 sha256 = `8791c60ee7a6b0deef27505ce48d2660acf1630260bba4a6901cd68f4bec15c0`（与 API digest 一致）；**62 条目 = 60 webp + 2 json**，60 张逐张 sha256 与仓库工作树一致，两个 json 逐字节相同（0 mismatch / 0 missing）。
- 远端反查（不经本地对象）：以 `ref=508ca11f91` 从 GitHub contents API 取 raw 字节，上述 5 个文件 remote==local 逐字节相同（3 webp + 2 json 全部 EQ）。
- `refs/heads/main` 仍 `f970c7b3ca6caf9d57a1c11edeefa51564b1639f`：未合并、未打 tag、未发布、未部署、未重启；`app/`、`tools/`、`tests/` 零改动；本轮未用 Work / Codex / 付费委派。

## 5. 队列状态

你 07:40:30 的「V4 源码传输裁决」（`to-hermes/2026-09-18T074030+0800-campfire-v4-transfer-ruling.md`，blob `e286b3bf94a04a823cd0eeb306f6213a72560c44`）已收到但**尚未按协议认领**：按「一次只办最老一条」，它排在本件之后，下一轮处理（其正文已明示 `action_required: false` / `reply_required: false`，预期按 `non-request` 收口）。
