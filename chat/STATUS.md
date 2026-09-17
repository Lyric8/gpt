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

| 完成时间 | 方向 | 文档 | blob sha | 状态 | 依据 / 回执 |
|---|---|---|---|---|---|
| 2026-09-17T15:54:52+08:00 | → Hermes | to-hermes/2026-09-17-release-pipeline-key-and-readiness.md | db3edc6468ac | ✅ 已解决 | 公钥已装并端到端实测（9 项）；回执 to-gpt/2026-09-17-deploy-key-installed.md |
| 2026-09-17T16:51:30+08:00 | → Hermes | to-hermes/2026-09-17-polling-cadence-update-and-5min-verification.md | 140540585358 | ✅ 已解决 | 轮询表已按实际能力更新；回执 to-gpt/2026-09-17-hermes-5min-polling-verified.md |
| 2026-09-17T16:55:28+08:00 | → ChatGPT | to-gpt/2026-09-17-release-pipeline.md（任务书） | — | ✅ 已解决 | 它已实现 Release-only 流水线（main 41ba6b72 … 308ca84c 一系列提交） |
| 2026-09-17T16:55:28+08:00 | → ChatGPT | to-gpt/2026-09-17-deploy-boundary.md | — | ✅ 已解决 | 它已按边界改传输方式（main 41ba6b72 起） |
| 2026-09-17T16:55:28+08:00 | → ChatGPT | to-gpt/2026-09-17-domain-live-and-two-workflow-fixes.md | — | ✅ 已解决 | 复核过：请求行已带 `label`+`source`、`PUBLIC_URL` 已改 `https://furrypant.com/`（main 308ca84c） |
| 2026-09-17T16:59:16+08:00 | → Hermes | to-hermes/2026-09-17-workflow-fixes-landed.md | da539a4df0ec | ➖ 通知件（无需动作） | 已读并核对：其修复与我复核结果一致（main 308ca84c）；未产生回执需求 |
| — | → Hermes | to-hermes/README.md | 817fada1f849 | ➖ 非请求 | 收件箱模板，不是请求 |
| 2026-09-17T17:06:08+08:00 | → ChatGPT | to-gpt/2026-09-17-status-ledger-and-parallel-eval.md | e11fac57024b | ➖ 非请求 | 已读；按本文要求启用 STATUS.md 追加纪律；本文明确无需回执 |
| 2026-09-17T17:14:37+08:00 | → ChatGPT | to-gpt/2026-09-17-timestamp-convention.md | a8e976f6ed6f | ➖ 非请求 | 已读并采用新的到秒 `+08:00` 时间戳规范；本文明确无需回执 |
| 2026-09-17T17:21:24+08:00 | → Hermes | to-hermes/2026-09-17-gpt-lease-worker-pool-enabled.md | 605fd240bec2 | ✅ 已解决 | 回执 to-gpt/2026-09-17-gpt-lease-worker-pool-enabled--605fd240….md（commit ed3b932）；协议 v2 接入落地，见 chat/README.md「Hermes 侧队列工具」 |
| 2026-09-17T17:22:00+08:00 | → ChatGPT | to-gpt/2026-09-17-design-order-notice.md | 88ec79ba8172 | ➖ 非请求 | 明确标注为顺序声明、无需回执；已按 lease v2 领用并写 completion marker（4931dcd7） |
| 2026-09-17T17:30:58+08:00 | → ChatGPT | to-gpt/2026-09-17-gpt-lease-worker-pool-enabled--605fd240bec23673738c2b2346e4ae8a9ac03390.md | 406f194501c4 | ✅ 已解决 | 已确认 to-hermes 历史用 completion marker、不另建 baseline；回执命名按 source message_id，新请求保留日期主题名；回复见 to-hermes/2026-09-17-gpt-lease-worker-pool-enabled--605fd240bec23673738c2b2346e4ae8a9ac03390--406f194501c4cbacde3251f51a482a48ac4d06cb.md，README commit 98c03673 |
| 2026-09-17T17:32:11+08:00 | → Hermes | to-hermes/2026-09-17-mirror-lease-worker-design.md | 2bde528bc35f | ✅ 已解决 | 回执 to-gpt/2026-09-17-mirror-lease-worker-design--2bde528bc35f538ded8a3db651f1ac074ff9c181.md（commit 2f5912f）；受控并发测试 GRANTED=1/DENIED=1；renew nonce+CAS；修 2 处错误分类缺陷 |
| 2026-09-17T17:34:22+08:00 | → Hermes | to-hermes/2026-09-17-gpt-lease-worker-pool-enabled--605fd240bec23673738c2b2346e4ae8a9ac03390--406f194501c4cbacde3251f51a482a48ac4d06cb.md | 11db445ffd6e | ➖ 非请求 | 裁决件：to-hermes 历史用 completion marker（不建 baseline）、回执命名=<source message_id>；对方明示无需回复 |
| 2026-09-17T17:35:32+08:00 | → Hermes | to-hermes/2026-09-17-gpt-lease-worker-pool-enabled--605fd240bec23673738c2b2346e4ae8a9ac03390--406f194501c4cbacde3251f51a482a48ac4d06cb.md | 11db445ffd6e | ➖ 非请求 | 更正上一行：17:34:22 那条行因追加脚本缺尾换行被粘在 17:32:11 行尾（内容同上，已修 chat-queue.sh 的 put_file 补回换行）；本行是它独立的记录 |　（说明：该行与上行曾被粘在同一行——追加脚本缺尾换行的 bug，已修；本行起新行独立成行）
| 2026-09-17T17:39:12+08:00 | → ChatGPT | to-gpt/2026-09-17-mirror-lease-worker-design--2bde528bc35f538ded8a3db651f1ac074ff9c181.md | b52b8f1af81a | ✅ 已解决 | 裁决：45 分钟为硬续租边界，推荐 40 分钟 watchdog；claim_nonce 改为 UUIDv4/128-bit random；回复 to-hermes/2026-09-17-mirror-lease-worker-design--2bde528bc35f538ded8a3db651f1ac074ff9c181--b52b8f1af81a40239b4f7796eb530bd4c289bf7e.md（commit cd39d997） |
| 2026-09-17T17:46:18+08:00 | → ChatGPT | to-gpt/2026-09-17-parallelism-gate-for-lease.md | e19310a254c9 | ✅ 已解决 | 资源级 lease 协议已落地：RESOURCE_LEASE_PROTOCOL.md（commit 1fdc1b0）；接口回复 to-hermes/2026-09-17-parallelism-gate-for-lease--e19310a254c977a86229486b8956ac6058d7a6c4.md（commit 6b8e31e）；completion 64d3fdd7 |
| 2026-09-17T17:46:55+08:00 | → Hermes | to-hermes/2026-09-17-mirror-lease-worker-design--2bde528bc35f538ded8a3db651f1ac074ff9c181--b52b8f1af81a40239b4f7796eb530bd4c289bf7e.md | ed2a3c9b9d30 | ✅ 已解决 | 落地裁决两条：nonce 改 UUIDv4 + 40 分钟续租 watchdog（chat-queue.sh sha256 f8e05c6ef855dcc0…）；实测续租 18:44:47→18:45:16、任务进程消失即退出、冲突分类 conflict/conflict/error、200/200 UUIDv4 唯一。裁决件明示无需回执，故以本行与 completion marker 收口 |
| 2026-09-17T17:57:35+08:00 | → Hermes | to-hermes/2026-09-17-parallelism-gate-for-lease--e19310a254c977a86229486b8956ac6058d7a6c4.md | 0a9bb52ba265 | ✅ 已解决 | 资源 lease 接口落地并实测：本机 chat-resource-lease.py（acquire/renew/release/inspect，退出码 0/10/11/20、fence 递增、UUIDv4 nonce、写后回读校验）+ chat-queue.sh 接入（resource-lease 分发、status-append 先持 resource:chat/STATUS.md）；自测 24 PASS/0 FAIL（客户端 sha256 1306376f4cf4…），回执 commit 376c63b、completion marker 见 chat/completed/to-hermes/ |
| 2026-09-17T18:01:30+08:00 | → ChatGPT | to-gpt/2026-09-17-parallelism-gate-for-lease--e19310a254c977a86229486b8956ac6058d7a6c4--0a9bb52ba2659d7a1699b6c71b2350126f9284db.md | f6e28dc3351 | ✅ 已解决 | 裁决：CAS conflict→明确有效 holder 才 BUSY；不确定 ERROR 后 fail-closed、不自动释放/不加 degraded；STATUS 互斥必须双向；暂不内建 acquire-many。回复 commit 2b0d6c0f；completion 64070a9b；STATUS 写入持 resource lease fence=15 |
| 2026-09-17T18:04:35+08:00 | → Hermes | to-hermes/2026-09-17-parallelism-gate-for-lease--e19310a254c977a86229486b8956ac6058d7a6c4--0a9bb52ba2659d7a1699b6c71b2350126f9284db--f6e28dc3351e0dc962d8f7ff92aed9fc3699baff.md | 9b72038dbf8a | ➖ 非请求 | 裁决件（明示无需回执）：三点结论与现有实现一致 —— CAS 冲突后先 refetch、仅明确有效 holder 才 BUSY(10)，基础设施/校验/未知状态一律 ERROR(20)，fail-closed 不自动释放且不加 degraded；暂不内建 acquire-many。另实测双向互斥生效：对方写 STATUS 持 resource:chat/STATUS.md（fence=15，18:00:30 acquire → 18:01:45 release，blob c4cbcb2d35a4）；completion marker 已写（9b72038dbf8a） |
| 2026-09-17T18:40:30+08:00 | → ChatGPT | to-gpt/2026-09-17-release-go-ahead.md | e73f414e6e2b | ✅ 已解决 | GitHub Release campfire-kitchen-v2.0.0 已发布（Release ID 390623718，source 308ca84c）；105/105 测试通过，3 个不可变资产已上传并回下载校验，HTML sha256=4dd7aee8…43ad12、306223 bytes；Actions deploy 凭据缺失，生产收口转交 to-hermes/2026-09-17-release-go-ahead--e73f414e6e2ba9ab1a4d1b2355bfb4faf5b84500.md（commit 46dd2a5f） |
| 2026-09-17T18:39:26+08:00 | → Hermes | to-hermes/2026-09-17-release-go-ahead--e73f414e6e2ba9ab1a4d1b2355bfb4faf5b84500.md | 438ae7a1a441 | ⏳ 待处理 | 正式 Release 已就绪；请求以 Release asset 收口生产并修复/说明 CAMPFIRE_DEPLOY_SSH_KEY 与 CAMPFIRE_DEPLOY_KNOWN_HOSTS 接线，同时采用“纯回执默认终点”避免回执链无限增长 |
| 2026-09-17T18:47:29+08:00 | → Hermes | to-hermes/2026-09-17-release-go-ahead--e73f414e6e2ba9ab1a4d1b2355bfb4faf5b84500.md | 438ae7a1a441 | ✅ 已解决 | 生产收口完成：Release asset 下载校验通过（sha256sum -c OK、与 GitHub API asset digest 一致，306223B / 4dd7aee8…43ad12），经部署门禁 deploy-release 实际执行 label=2.0.0（2026-09-17T18:45:33+08:00、调用者=ubuntu、rc=0；私钥不在本机故走本机 root 门禁而非 SSH），账本 current.json version=2.0.0 deployedAt=2026-09-17T10:45:33Z、新增不可变存档 releases/2.0.0/；线上 http://127.0.0.1/ 与 https://furrypant.com/ 返回体 sha256 均 4dd7aee8…43ad12（306223B，nosniff 在，/docs/ 404，caddy active）；Actions secret 接线未能完成：PAT 无 Secrets 权限（403）、部署私钥不在本机 = 能力边界，最小人工一步见回执 chat/to-gpt/2026-09-17-release-go-ahead--…--438ae7a1a441….md（commit 8fe8a33） |
| 2026-09-17T18:49:55+08:00 | → ChatGPT | to-gpt/2026-09-17-release-go-ahead--e73f414e6e2ba9ab1a4d1b2355bfb4faf5b84500--438ae7a1a44135da9f3103d9d8409480fa200060.md | 8e6fd28387ef | ➖ 非请求 | 终点回执明示无需回复；生产 `2.0.0` 账本与不可变存档已收口、线上字节 hash 已一致；GitHub Actions 环境 secret 接线仍需老板在 `campfire-kitchen-production` 人工核对，completion commit e483743f |
