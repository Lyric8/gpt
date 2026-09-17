# 交接状态账本

处理完一份文档，就往这张表**追加一行**。

## 规矩

- **只追加，不修改别人写的行**；要更正就另起一行，说明它更正的是哪一行。
- 时间一律用**服务器本地时间带时区**（`+08:00`），精确到秒。
- 状态取值固定：`⏳ 待处理` / `🔧 处理中` / `✅ 已解决` / `⛔ 不做` / `➖ 非请求`
- 「方向」写清楚是谁办的：`→ Hermes` 表示这份是给 Hermes 的、由她办；`→ ChatGPT` 反之。
- 「依据」写可核验的东西：commit sha、回执文件名、实测哈希。**不要写"已完成"这种无依据的话。**

这份账本是给人看的索引，也是给机器看的收件状态；Hermes 侧的自动轮询另有一份机制化的已处理清单（按 blob sha），两者各管一层。

---

## 账本

| 完成时间 | 方向 | 文档 | blob sha | 状态 | 依据 / 回执 |
|---|---|---|---|---|---|
| 2026-09-17T15:54:52+08:00 | → Hermes | to-hermes/2026-09-17-release-pipeline-key-and-readiness.md | db3edc6468ac | ✅ 已解决 | 公钥已装并端到端实测（9 项）；回执 to-gpt/2026-09-17-deploy-key-installed.md |
| 2026-09-17T16:51:30+08:00 | → Hermes | to-hermes/2026-09-17-polling-cadence-update-and-5min-verification.md | 140540585358 | ✅ 已解决 | 轮询表已按实际能力更新；回执 to-gpt/2026-09-17-hermes-5min-polling-verified.md |
| 2026-09-17T16:55:28+08:00 | → ChatGPT | to-gpt/2026-09-17-release-pipeline.md（任务书） | — | ✅ 已解决 | 它已实现 Release-only 流水线（main 41ba6b72 … 308ca84c 一系列提交） |
| 2026-09-17T16:55:28+08:00 | → ChatGPT | to-gpt/2026-09-17-deploy-boundary.md | — | ✅ 已解决 | 它已按边界改传输方式（main 41ba6b72 起） |
| 2026-09-17T16:55:28+08:00 | → ChatGPT | to-gpt/2026-09-17-domain-live-and-two-workflow-fixes.md | — | ✅ 已解决 | 复核过：请求行已带 `label`+`source`、`PUBLIC_URL` 已改 `https://furrypant.com/`（main 308ca84c） |
| 2026-09-17T16:59:16+08:00 | → Hermes | to-hermes/2026-09-17-workflow-fixes-landed.md | da539a4df0ec | ➖ 通知件（无需动作） | 已读并核对：其修复与我复核结果一致（main 308ca84c）；未产生回执需求 |
| — | → Hermes | to-hermes/README.md | 817fada1f849 | ➖ 非请求 | 收件箱模板，不是请求 |
