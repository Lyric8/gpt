# chat —— 跨执行者交接频道

时间：2026-09-17T17:12:30+08:00　作者：ChatGPT
修订：2026-09-17T17:29:59+08:00　作者：ChatGPT

本目录只存在于 `chat` 分支，用于 ChatGPT、Hermes 与老板之间的文字交接；不要把 `chat` 分支合回 `main`。

## 目录

| 路径 | 用途 |
|---|---|
| `chat/to-gpt/` | Hermes / 老板交给 ChatGPT 的消息 |
| `chat/to-hermes/` | ChatGPT / 老板交给 Hermes 的消息 |
| `chat/claims/to-gpt/` | ChatGPT worker 的 lease 记录 |
| `chat/claims/to-hermes/` | Hermes worker 的 lease 记录 |
| `chat/completed/to-gpt/` | ChatGPT 已完成消息的机器去重记录 |
| `chat/completed/to-hermes/` | Hermes 已完成消息的机器去重记录 |
| `chat/LEASE_PROTOCOL.md` | Claim / lease / takeover / 幂等完成协议 |
| `chat/QUEUE_BASELINE.md` | to-gpt 队列启用前的历史 activation baseline |
| `chat/STATUS.md` | 人类可读状态账本 |

## 文档纪律

1. **新发起的请求 / 通知**使用可读文件名：`YYYY-MM-DD-主题.md`。
2. **针对某条既有消息的回执 / 回复**必须按 `chat/LEASE_PROTOCOL.md` 使用确定性路径：`<source-message_id>.md`。这一条优先于上一条，因为确定性文件名承担幂等去重职责。
3. 每份新文档头部写：`时间：YYYY-MM-DDTHH:MM:SS+08:00　作者：<谁>`。
4. 一份文档只处理一件事；写完不原地修改，需要更正就新增一份替代文档。
5. 不修改对方留下的交接文档。
6. 真有事项才写入对方收件目录；回执完成后停止，不互发纯“收到”。
7. `claims/`、`completed/`、`QUEUE_BASELINE.md` 是队列元数据，不属于给对方的新请求。

## baseline 与 completion 的职责

`QUEUE_BASELINE.md` 是 ChatGPT 侧启用 10-worker 队列时，为当时已经存在的 `to-gpt` 历史消息建立的一次性迁移边界；它不是要求双向长期维护的第二套状态系统。

Hermes 侧协议 v2 接入前已经存在的 `to-hermes` 历史消息，已由 Hermes 补写 `chat/completed/to-hermes/<message_id>.json`。这些 completion marker 已足够，因此 **不再为 to-hermes 另建 baseline**。

正常运行以后，两个方向都以本方向 `completed/<direction>/` + `STATUS.md` 作为完成事实；baseline 只处理启用瞬间的历史迁移问题。

## 时间戳规矩

1. 每份文档头部必须到秒：`时间：YYYY-MM-DDTHH:MM:SS+08:00　作者：<谁>`
2. 时区统一使用 `UTC+8` 或 `+08:00`
3. 不使用城市名或地区名代替时区
4. `STATUS.md` 每行完成时间同样精确到秒并带 `+08:00`
5. 引用时间一律带时区，不留裸时间

## Hermes 侧队列工具（协议 v2）

Hermes worker：`hermes-poller`。本机脚本 `~/.hermes/scripts/chat-queue.sh` 提供 `list / claim / complete / status-append`；业务判断仍由 Hermes 会话层负责。

Hermes 推送 `chat` 分支使用 `~/.hermes/scripts/chat-push.sh` 做本机写通道串行化、fetch/rebase/retry，且不强推。该本地锁只解决同机写仓库并发；消息所有权仍由 Git-backed claim/lease 决定。

## 自动轮询

Hermes 约每 5～6 分钟检查 `chat/to-hermes/`。

ChatGPT 使用 10 个彼此独立的普通 Scheduled Tasks，在每小时：

`00 / 06 / 12 / 18 / 24 / 30 / 36 / 42 / 48 / 54`

触发，整体约每 6 分钟检查一次 `chat/to-gpt/`。

两边都把 inbox 当作 durable queue，而不是“看见文件就直接执行”的目录。任何业务动作前都必须：

1. 计算 source `message_id`；
2. 检查本方向 completion；
3. 通过本方向 `claims/<direction>/<message_id>.json` 获取有效 lease；
4. 没拿到 lease 就退出；
5. 只有 lease owner 可以继续业务动作；
6. 需要回复时使用 deterministic reply path；
7. 完成后写本方向 completion 与 `STATUS.md`；
8. lease 过期接管前先核对已有 reply、STATUS 和真实外部副作用，再决定补收尾还是继续。

详细算法、CAS、续租、崩溃恢复与幂等顺序以 `chat/LEASE_PROTOCOL.md` 为准。

## STATUS

每处理完一份交接消息，在 `chat/STATUS.md` 追加一行。只追加，不删除或覆盖别人的历史行。并发更新必须基于当前 blob SHA；冲突就重新读取、保留新行后再提交。

状态固定使用：`⏳ 待处理` / `🔧 处理中` / `✅ 已解决` / `⛔ 不做` / `➖ 非请求`。

## ChatGPT 资源边界

这套 relay 只允许普通 ChatGPT Scheduled Tasks 与 GitHub connector。不要把 relay 自动升级到 ChatGPT Work、Codex、Codex automation、Codex CLI 或其他 delegated agent 执行路径；需要这些能力的事项留给用户的正式开发流程。
