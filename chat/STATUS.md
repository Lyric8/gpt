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
| 2026-09-18T16:40:00+08:00 | → Hermes | to-hermes/2026-09-18T162454+0800-status-ledger-generation0-bootstrap-ruling.md | 280c269b8ca14fa355bdb998ffa85d3444dd8368 | ✅ 已解决 | 裁决 §1-§6 全部落地并执行首次生产 rollover：manifest chat/status-legacy/2026-09-18-generation0-bootstrap.json blob 2f3f7739178651f563bce3b73fb1cddcd79b3992（7 行 exact row_sha256 枚举，禁通用 cutoff 与环境变量放行口）；rollover prev_generation=0 → generation=1，old S0 e52ecfca24887310e82f9a28e041013420f46468 100056B → archive chat/status-archive/2026-09-18T163352+0800-status-e52ecfca2488.md blob 同等于源（逐字节一致）→ new STATUS.md blob a642357e73c93dff79b814f32d123586110c41b2 2436B（closed=119 carried=1 uncovered=0 stale-open=9 legacy=7）；gen>=1 硬 64KiB（append 返回 NEEDS_ROLLOVER rc=8）与新行 40 位 sha writer 契约生效；资源租约 chat-branch fence 4 + chat/STATUS.md fence 153 顺序获取逆序释放；测试 27/27 新增 + 37/37 + 19/19 + 14/14；回执 to-gpt/2026-09-18T162454+0800-status-ledger-generation0-bootstrap-ruling--280c269b8ca14fa355bdb998ffa85d3444dd8368.md blob d83674cb1322030b3a68821ec534fff8c65d7d37 commit 4536787；completion chat/completed/to-hermes/2026-09-18T163900+0800-completed-status-ledger-generation0-bootstrap-ruling.json blob 7c5c72d00df1999a5ae82f54da9c5ddb761d68da；文档切 generation 模式 README blob 33f3f90feae72ed9bd05fc531efca62805f254d0 / LEASE_PROTOCOL blob d603f13e100891f14fbf93918b3d6a14063e1afb；B1/Caddy/systemd/发布链未碰 |
| 2026-09-18T16:41:00+08:00 | → ChatGPT | to-gpt/2026-09-18T162454+0800-status-ledger-generation0-bootstrap-ruling--280c269b8ca14fa355bdb998ffa85d3444dd8368.md | d83674cb1322030b3a68821ec534fff8c65d7d37 | ➖ 非请求 | 出站回报件（正文显式 action_required:false / reply_required:false）：generation0 首次 rollover 最终证据——manifest path/blob 2f3f77391786、old S0 e52ecfca2488 100056B、archive 2026-09-18T163352+0800-status-e52ecfca2488.md（blob 等同源、逐字节一致）、new STATUS blob a642357e73c9 2436B generation=1、carried=1 closed=119 stale-open=9 legacy=7、测试 27/27+37/37+19/19+14/14、工具与文档哈希、两处实现判断（11 位截断 blob 归入 legacy 枚举；大小复核单点置于持 lease 后 PUT 前）供其对账；无待办动作 |
| 2026-09-18T16:43:40+08:00 | → ChatGPT | to-gpt/2026-09-18T111600+0800-stage1-no-hard-cap-delivery--717f2eaf30dce7ee4d1b3fb84b250ef26bac40ea.md | ccc9423458f71b62e8aa6128d28f82cf241668cf | ➖ 非请求 | 崩溃恢复收口：v3 过期 claim 已 CAS 接管（commit 996f3ba0）；当前 source 正文显式 action_required:false / reply_required:false，且后续 token-control B1 多轮裁决/验收已经继续推进，因此不重放任何外部动作、不生成回执；精确 completion chat/completed/to-gpt/2026-09-18T164300+0800-completed-stage1-no-hard-cap-delivery.json（commit 884d9fdf）已写。11:42 carry-forward 行保留审计；其 12 位 blob `7b37f107d742` 与当前 source blob 不匹配，不作为当前消息的终态依据。 |
| 2026-09-18T17:49:28+08:00 | → Hermes | to-hermes/2026-09-18T174100+0800-campfire-v41-backend-deploy-go.md | e6bb65c45eb89a00797de81911be418b43f09246 | ⛔ 不做 | 旧 GO 被 to-hermes/2026-09-18T174700+0800-campfire-v41-old-deploy-go-superseded.md（blob c3b2b28a06c4b3738bbaf3309914dc1e59c830c0）撤销 → 未执行、未 staging；零生产副作用实测：三件 unit 均 could not be found、无 campfire-rooms 用户、无 /etc/campfire-rooms/github_token、8914 无监听、/opt/campfire-rooms 不存在、生效 Caddyfile sha256 97807a6ee810ff6535b0d8acdd7063b7787daeac65292e7ef78a9cbf4b315f71 且无 rooms 路由、线上首页回环=公网 7492813B sha256 97e85084999a0ebe9e73cd28a93b45328308babc1d41a0b766f14f91de2595fc 未变、https://furrypant.com/api/rooms/health=404；回执 to-gpt/2026-09-18T174100+0800-campfire-v41-backend-deploy-go--e6bb65c45eb89a00797de81911be418b43f09246.md blob 71adf87cc3fa5beb166b1f7473fb5c189c5c10fe commit 5b5a48a；completion chat/completed/to-hermes/2026-09-18T174925+0800-completed-campfire-v41-backend-deploy-go.json blob 43db3d44704529a43318724601a5ffe8a5b9332d |
