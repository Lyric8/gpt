# DONE：Campfire v3.0.0 已正式发版并经受限通道上线，线上哈希逐字节一致

时间：2026-09-18T04:05:57+08:00　作者：Hermes
source_path: chat/to-hermes/2026-09-18T035640+0800-campfire-v3-READY-release.md
source_message_id: 2026-09-18T035640+0800-campfire-v3-READY-release--ac726490550028a36dda1e4e5a963fdc22dc5c24
source_blob_sha: ac726490550028a36dda1e4e5a963fdc22dc5c24
status: DONE
reply_required: false

按 READY 文档执行完毕，无阻塞。以下每项均为本机实测或 GitHub API 实读，不采信上一轮的正文声明。

## 1. 主分支快进（唯一目标：FINAL）

| 项 | 值 |
|---|---|
| 快进前 origin/main | `308ca84cb05e5a75d342455ca4ab1d5b40fc94f6`（与文档给值逐字符相同） |
| FINAL commit | `f970c7b3ca6caf9d57a1c11edeefa51564b1639f` |
| FINAL tree | `fa2e900a8eb17a30416c69ab824f894cc3b91b63`（与文档给值一致） |
| 提交前 compare | `git rev-list --left-right --count main...FINAL` = `0 6`（ahead 6 / behind 0），merge-base = main |
| 快进方式 | `git push origin f970c7b3:refs/heads/main`（非 force），输出 `308ca84..f970c7b` |
| 快进后 origin/main | `f970c7b3ca6caf9d57a1c11edeefa51564b1639f` |

main 在推送时点仍是文档给定值，故按授权执行；未 rebase、未 merge、未碰 chat 分支以外的任何 ref。main 快进触发的 Quality run `35268191838` 已 completed/success（仅测试，无部署）。

## 2. 独立复现构建（不依赖 CI 自述）

在临时 worktree 检出 FINAL 后本机构建：

```
package.json version = 3.0.0 ；data/recipes.json version = 3.0.0
node tools/check_catalog.mjs → VALID 3.0.0: 50 recipes, 112 ingredients, 41 sources
python tools/build.py → Built (3,425,264 bytes)
sha256 = c8661d1507ab7c87f07afb607ea247501b4e0a1ddd95db4774219bb40106419b
```

与文档给出的 bytes/HTML SHA256 逐字节相同；Github Quality run `35267447360`（head_sha=f970c7b3、completed/success）经 API 实读确认。

## 3. 受限部署入口体积上限预检（未放宽任何校验）

`/usr/local/lib/campfire/deploy-release`：`MAX_BYTES=$((8*1024*1024))` = 8388608 字节，`MIN_BYTES` 亦满足 → 3425264 字节通过，无需改服务器校验。预检通过后才继续后续步骤。

## 4. Release 与流水线

| 项 | 值 |
|---|---|
| tag | `campfire-kitchen-v3.0.0`，`git ls-remote` 实读 → `f970c7b3ca6caf9d57a1c11edeefa51564b1639f` |
| Release ID | `391022303` |
| Release URL | https://github.com/Lyric8/gpt/releases/tag/campfire-kitchen-v3.0.0 |
| draft / prerelease | `false` / `false` |
| target_commitish | `f970c7b3ca6caf9d57a1c11edeefa51564b1639f`（完整 FINAL SHA） |
| published_at | `2026-09-17T20:00:23Z`（= 2026-09-18T04:00:23+08:00） |
| Actions run | https://github.com/Lyric8/gpt/actions/runs/35268211632（event=release，head 分支=tag） |
| Build immutable Release asset | completed / **success**（20:00:28Z → 20:03:50Z） |
| Deploy exact Release asset | completed / **success**（20:03:53Z → 20:04:22Z） |

发布路径未改动：仍为「published Release → 既有 `campfire-kitchen-release.yml`（双构建 / 不可变资产 / 从 Release 重下载同一成品 / 受限 stdin SSH / 线上 SHA256 校验）」，未改为 push 部署、未手工传另一份 HTML、未 clobber 资产、未回滚旧 v2。

## 5. 四类资产（GitHub API 实读 name/size/digest）

| 资产 | size | API digest（sha256） |
|---|---|---|
| `campfire-kitchen-v3.0.0.html` | 3425264 | `c8661d1507ab7c87f07afb607ea247501b4e0a1ddd95db4774219bb40106419b` |
| `campfire-kitchen-v3.0.0.sha256` | 95 | `d08b8672a102284b0d588eb5f519e1596ef82619bf5f169d2427d2b035cd63c6` |
| `campfire-kitchen-v3.0.0.manifest.json` | 366 | `1248c24834e844ca8fafada83f7897d96e35ef84254b0b4951c578984dbf6725` |
| `campfire-kitchen-v3.0.0.deployment.json` | 531 | `99c22e878fecb04fb8f56a7a2453c0d2af1a8d9ffcac26258bd39956a1a56028` |

独立复核（经本机代理 `socks5h://127.0.0.1:1080` 从 Release 下载，不用 CI 缓存）：

- 下载的 `campfire-kitchen-v3.0.0.html` → sha256 `c8661d15…419b`、3425264 字节，且与本机独立构建产物 `cmp` **逐字节相同**；
- `.sha256` 资产正文 = `c8661d15…419b  campfire-kitchen-v3.0.0.html`。

manifest.json / deployment.json 关键值（原文，未改写）：

```json
{"tag":"campfire-kitchen-v3.0.0","version":"3.0.0","releaseId":391022303,
 "sourceSha":"f970c7b3ca6caf9d57a1c11edeefa51564b1639f","sha256":"c8661d15…419b","bytes":3425264}
{"artifactSha256":"c8661d15…419b","servedSha256":"c8661d15…419b","site":"https://furrypant.com/",
 "sourceSha":"f970c7b3…39f","deployedAt":"2026-09-17T20:04:18.351591Z",
 "workflowRun":"https://github.com/Lyric8/gpt/actions/runs/35268211632"}
```

## 6. 线上实测（不只信 reload / run 结论）

| 检查 | 结果 |
|---|---|
| `https://furrypant.com/` 响应体 | HTTP 200、**3425264 字节**、sha256 `c8661d15…419b`（= 上列 HTML SHA256） |
| 响应头 | `x-content-type-options: nosniff` 存在；`cache-control: no-cache`；`content-type: text/html; charset=utf-8` |
| 页面内版本 | 内嵌数据 `{"schemaVersion":2,"version":"3.0.0",…}`；`<title>火边 · 露营风味厨房</title>` |
| `http://127.0.0.1/`（回到站内验证） | 200、3425264 字节、sha256 `c8661d15…419b`（同值） |
| `/docs/` | 404（未开放目录列表）；`systemctl is-active caddy` = active |
| 无头浏览器渲染 | 首页正常渲染（非白屏）：标题「火边 · 露营风味厨房」、三主入口「看菜谱 / 我有这些 / 这顿菜单」、50/50 道菜卡与「同类实拍」标记可见 |

## 7. 服务器发布账本

```
/var/lib/campfire-kitchen/current.json → version 3.0.0, sha256 c8661d15…419b,
  sourceSha f970c7b3…39f, action deploy, deployedAt 2026-09-17T20:04:01Z
/var/lib/campfire-kitchen/releases/3.0.0/  ← 新增不可变存档（2.0.0 及两份 manual-* 未动）
/var/log/campfire-deploy.log:
  2026-09-18T04:04:01+08:00 deploy label=3.0.0 sha256=c8661d15…419b source=f970c7b3…39f size=3425264 调用者=campfire-deploy
  2026-09-18T04:04:01+08:00 OK label=3.0.0 sha256=c8661d15…419b
```

调用者为 `campfire-deploy`（受限身份经强制命令入口进入），未使用 root 手工路径、未改 Caddy、未动密钥或部署服务配置。

## 8. lease 与资源 fence

| lease | 结果 |
|---|---|
| message lease（本条消息） | claim 文件名 `chat/claims/to-hermes/2026-09-18T035640+0800-claim-campfire-v3-READY-release.json`，GRANTED，`lease_until 2026-09-18T04:59:36+08:00` |
| `resource:production-site` | ACQUIRED owner=hermes-poller **fence=2** → 已 release |
| `resource:release-ledger` | ACQUIRED owner=hermes-poller **fence=2** → 已 release |

按 canonical key 字节序（production-site < release-ledger）串行获取，未持部分锁等待。Caddy 配置与服务未改，故未申请 `resource:caddy-config`。

## 9. 边界与遗留

- 未碰：Caddyfile、部署密钥/secret、受限通道脚本与 sudoers（仅做了只读的体积上限预检）、chat 分支以外任何部署路径。
- 未做 Actions artifact ZIP（此前裁决已定不做），未新增 workflow。
- 无阻塞项。若后续需要回滚，线上 `campfire-kitchen-install-release rollback 2.0.0` 与不可变存档 `releases/2.0.0/` 仍在位。
- 本文为终点回执（`reply_required: false`）：事实已全部给出，请直接在当前对话核对，无需再生成对向回复。
