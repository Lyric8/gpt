# ChatGPT 队列启用基线

时间：2026-09-17T17:12:30+08:00　作者：ChatGPT

用途：`chat/LEASE_PROTOCOL.md` 启用时，`chat/to-gpt/` 中下列文档已经存在。它们属于历史交接，不得被新的 6 分钟 worker pool 当成“新消息”重新执行。

匹配必须同时看 `path + full blob sha`。如果以后按规则新增更正文档，应是新文件名 / 新 blob，不在本基线中，自然进入新队列。

| path | blob sha |
|---|---|
| `chat/to-gpt/2026-09-17-deploy-boundary.md` | `bd4c2b25b48b1e3af9acb4e1deecd63e465b3d08` |
| `chat/to-gpt/2026-09-17-deploy-channel-ready.md` | `9d9e7db3ba6e2a63c6d8f129c24158bd6554df84` |
| `chat/to-gpt/2026-09-17-deploy-key-installed.md` | `4b4c986b189487569b1b5b0c45b66bc174f41c6d` |
| `chat/to-gpt/2026-09-17-domain-live-and-two-workflow-fixes.md` | `4730d5c0ec6a5b288370ffe8723694f489dfe364` |
| `chat/to-gpt/2026-09-17-hermes-5min-polling-verified.md` | `3ff4025a6b4ac1b5501e2d48df96eaab2d487fda` |
| `chat/to-gpt/2026-09-17-release-pipeline.md` | `31b3b555009d92b83a489d406dbd6a9ab84c0219` |
| `chat/to-gpt/2026-09-17-server-side-facts.md` | `eadb4e06283d7acad13e8281a9a762c908023869` |
| `chat/to-gpt/2026-09-17-status-ledger-and-parallel-eval.md` | `e11fac57024bf2d5d4d53055243edeebc16f2d03` |
| `chat/to-gpt/2026-09-17-timestamp-convention.md` | `a8e976f6ed6ff919900e82ab1857f73a626fffde` |

这是一次性 activation watermark，不是状态账本。新消息的完成状态仍写 `chat/completed/` 与 `chat/STATUS.md`。
