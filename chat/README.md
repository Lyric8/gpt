# chat —— 跨执行者交接频道

时间：2026-09-17T17:12:30+08:00　作者：ChatGPT

本目录只存在于 `chat` 分支，用于 ChatGPT、Hermes 与老板之间的文字交接；不要把 `chat` 分支合回 `main`。

## 目录

| 路径 | 用途 |
|---|---|
| `chat/to-gpt/` | Hermes / 老板交给 ChatGPT 的消息 |
| `chat/to-hermes/` | ChatGPT / 老板交给 Hermes 的消息 |
| `chat/claims/` | ChatGPT Scheduled Tasks 的租约记录 |
| `chat/completed/` | ChatGPT 已完成消息的机器去重记录 |
| `chat/LEASE_PROTOCOL.md` | Claim / lease / takeover / 幂等完成协议 |
| `chat/QUEUE_BASELINE.md` | 新队列启用前已有历史消息基线 |
| `chat/STATUS.md` | 人类可读状态账本 |

## 文档纪律

1. 新交接文档文件名使用 `YYYY-MM-DD-主题.md`。
2. 每份新文档头部写：`时间：YYYY-MM-DDTHH:MM:SS+08:00　作者：<谁>`。
3. 一份文档只处理一件事；写完不原地修改，需要更正就新增一份替代文档。
4. 不修改对方留下的交接文档。
5. 真有事项才写入对方收件目录；回执完成后停止，不互发纯“收到”。
6. `claims/`、`completed/`、`QUEUE_BASELINE.md` 是队列元数据，不属于给对方的新请求。

## 时间戳规矩（老板强制，五条）

1. 每份文档头部必须**到秒**：`时间：YYYY-MM-DDTHH:MM:SS+08:00　作者：<谁>`
2. 时区统一东八区，写作 `UTC+8` 或 `+08:00`
3. **不许用城市名或地区名代替时区** —— 只写 `UTC+8`。纯技术记号，避免与工作无关的歧义
4. 账本 `STATUS.md` 每行完成时间用同一格式（到秒 + `+08:00`）
5. 引用时间一律带时区，**不留裸时间**

（本节补回完整五条：2026-09-17T17:12 的 README 重写把格式并进了「文档纪律」第 2 条，但丢掉了第 1、3、4、5 条。）

## Hermes 侧队列工具（协议 v2）

Hermes 侧 worker 身份：`hermes-poller`。实现为本机脚本 `~/.hermes/scripts/chat-queue.sh`：

```
chat-queue.sh list                              列出候选 + 领用状态
chat-queue.sh claim <path>                      原子领租约（create-file 裁决）
chat-queue.sh complete <path> <status> <evidence>  写 completed marker（幂等）
chat-queue.sh status-append "<账本行>"           按 blob SHA CAS 追加账本行
```

推送 `chat` 分支一律走 `~/.hermes/scripts/chat-push.sh`：`flock` 串行 + 推前 fetch + rebase 重试 3 次，**绝不强推**。

## 自动轮询

Hermes 继续按约 5～6 分钟检查 `chat/to-hermes/`。

ChatGPT 侧使用 10 个彼此独立的普通 Scheduled Tasks，分别在每小时：

`00 / 06 / 12 / 18 / 24 / 30 / 36 / 42 / 48 / 54`

触发，因此整体约每 6 分钟检查一次 `chat/to-gpt/`。

这 10 个任务不是 10 个“看到消息就开工”的机器人，而是一个共享队列的 worker pool。任何 ChatGPT task 在处理消息前都必须先遵守 `chat/LEASE_PROTOCOL.md`：

1. 排除 `QUEUE_BASELINE.md` 中的历史消息；
2. 检查 `completed/<message_id>.json`；
3. 通过 `claims/<message_id>.json` 竞争 60 分钟 lease；
4. 没拿到 lease 就跳过；
5. 只有 lease owner 能产生新的业务动作；
6. 回复采用 deterministic path；
7. 完成后写 `completed/` 与 `STATUS.md`；
8. owner 异常退出后，只有 lease 过期才允许其他 worker 用 blob SHA CAS 接管，并且接管前必须先核对已经发生的副作用。

详细算法、message_id、CAS 规则、续租、崩溃恢复与幂等顺序全部以 `chat/LEASE_PROTOCOL.md` 为准。

## STATUS

每处理完一份交接消息，在 `chat/STATUS.md` 追加一行。只追加，不删除或覆盖别人的历史行。并发更新时必须基于当前 blob SHA；冲突就重新读取、保留新行后再提交。

状态固定使用：`⏳ 待处理` / `🔧 处理中` / `✅ 已解决` / `⛔ 不做` / `➖ 非请求`。

## ChatGPT 资源边界

这套 relay 只允许普通 ChatGPT Scheduled Tasks 与 GitHub connector。不要把 relay 自动升级到 ChatGPT Work、Codex、Codex automation、Codex CLI 或其他 delegated agent 执行路径；需要这些能力的事项留给用户的正式开发流程。
