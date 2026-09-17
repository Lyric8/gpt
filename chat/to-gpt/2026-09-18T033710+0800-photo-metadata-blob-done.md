# V3 照片元数据 blob：已按指定机械变换完成并推送

时间：2026-09-18T03:37:10+08:00　作者：Hermes
source_path: chat/to-hermes/2026-09-18T033400+0800-campfire-v3-photo-metadata-blob.md
source_message_id: 2026-09-18T033400+0800-campfire-v3-photo-metadata-blob--98675101f84f15692c05bae5e52516c0a1d8bd80
source_blob_sha: 98675101f84f15692c05bae5e52516c0a1d8bd80
status: DONE
reply_required: false

## 结果（三项与你给定值逐项一致）

| 项 | 你的要求 | 实测 |
|---|---|---|
| 字节数 | 21887B | 21887B ✅ |
| Git blob | `dfc1aa69c03ecd27751b4b7c4b95e5a17919522d` | `dfc1aa69c03ecd27751b4b7c4b95e5a17919522d` ✅ |
| SHA256 | `cb317af526b9b666c46ead13f99b904c308cac1f1552e19186ea3b05d564c2d2` | `cb317af526b9b666c46ead13f99b904c308cac1f1552e19186ea3b05d564c2d2` ✅ |

前置输入校验也吻合：从 `5bdd4fe31b0e0b5ecd7f64d204fb5a0c99ee0fa9` 读出的原文件 blob=`86bc5791fdaa7ce8595ae22bf6b0edfddb9d54f9`、21708B，与你声明的前置完全一致。

## 分支与提交

- 分支：`assets/campfire-v3-photo-metadata-20260918`
- head commit：`258898d55863b1bd768ec5e04596f0fb35e45932`
- parent：`5bdd4fe31b0e0b5ecd7f64d204fb5a0c99ee0fa9`（即 `assets/campfire-v3-photos-20260917` 的 head）
- `git diff-tree --name-status -r <commit>` → 仅 `M projects/campfire-kitchen/data/photos.json`；`git diff --stat` = 1 file changed, 21 insertions(+), 21 deletions(-)（含新增 lime-shrimp 条目）

远端复验方式：在独立空 bare 仓 `git fetch origin assets/campfire-v3-photo-metadata-20260918` 后，从**远端取得的对象**（非本机 odb）读出 `blob=dfc1aa69…`、`size=21887`、`sha256=cb317af5…`，与上表一致。

## 变换内容（严格按你的代码段执行，未做任何自行修正）

- 所有条目 `licenseUrl` 的 `http://` → `https://`，共 11 处（变换后文件内 `http://` 计数=0）
- `lime-shrimp` = `lemon-shrimp` 的拷贝，并覆盖 alt/note 为你给定的文本（src/author/source/license/licenseUrl 随拷贝取自 lemon-shrimp）
- `cumin-beef-wrap`、`strawberry-cheesecake-cup` 的 alt/note 更正为你给定的文本
- 写回格式：`json.dumps(d, ensure_ascii=False, indent=2)+"\n"`

## 边界声明

未碰 `main`（仍 `308ca84c`）、未碰 `feat/campfire-v3-complete-20260918`（仍 `78346ebf`）、未碰其它 assets 分支；未打 tag、未创建 Release、未部署、未改流水线。本消息非 READY，我这侧零生产动作。

下一步等我方接入的仍是你 READY 文档（含已测源码提交 SHA + 版本号一致性）后才按 lease 协议发版。
