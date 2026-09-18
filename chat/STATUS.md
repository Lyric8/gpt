# 交接状态账本

处理完一份文档，就往这张表**追加一行**。

## 规矩

- **只追加，不修改别人写的行**；要更正就另起一行，说明它更正的是哪一行。
- 时间一律用**东八区**，写作 `YYYY-MM-DDTHH:MM:SS+08:00`，**精确到秒**，带 `+08:00`。
  **不要用城市名或地区名代替时区** —— 只用 `UTC+8` 这个记号。
- 状态取值固定：`⏳ 待处理` / `🔧 处理中` / `✅ 已解决` / `⛔ 不做` / `➖ 非请求`
- 「方向」写清楚是谁办的：`→ Hermes` 表示这份是给 Hermes 的、由她办；`→ ChatGPT` 反之。
- 「依据」写可核验的东西：commit sha、回执文件名、实测哈希。**不要写"已完成"这种无依据的话。**

这份账本是给人看的索引，也是给机器看的收件状态；Hermes 侧的自动轮询另有一份机制化的已处理清单（按 blob sha），两者各管一层。

---

## 账本

## generation

- generation: 1
- rolled_at: 2026-09-18T16:33:52+08:00
- rolled_by: hermes-poller
- previous_archive_path: chat/status-archive/2026-09-18T163352+0800-status-e52ecfca2488.md
- previous_status_blob_sha: e52ecfca24887310e82f9a28e041013420f46468
- previous_file_bytes: 100056
- archived_terminal_rows: 119（每条都有接收方向精确 completion）
- carried_open_rows: 1（原时间戳、原依据 carry-forward，不是新事件）
- legacy_attestation: chat/status-legacy/2026-09-18-generation0-bootstrap.json
- legacy_attestation_blob_sha: 2f3f7739178651f563bce3b73fb1cddcd79b3992
- legacy_attestation_rows: 7（generation0 一次性 bootstrap 豁免，generation>=1 永不再接受）

本代 active 只保留未终结消息的最新行；历史终态行全部保存在上一代 archive（不可变）。
机器终态权威是接收方向精确 completion marker；archive 只用于审计与 legacy repair，正常轮询不遍历。

| 完成时间 | 方向 | 文档 | blob sha | 状态 | 依据 / 回执 |
|---|---|---|---|---|---|
| 2026-09-18T11:42:10+08:00 | → ChatGPT | to-gpt/2026-09-18T111600+0800-stage1-no-hard-cap-delivery--717f2eaf30dce7ee4d1b3fb84b250ef26bac40ea.md | 7b37f107d742 | ⏳ 待处理 | 本机验收回报（正文显式 action_required:false / reply_required:false）：75/75 测试通过 + 100 轮 shadow 已起跑 + 生产零改动；待补 shadow 满 100 轮证据与 Stage B1 迁移（迁移须老板在场且在网关进程之外） |
