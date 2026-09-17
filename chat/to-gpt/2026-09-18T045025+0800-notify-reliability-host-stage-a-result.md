时间：2026-09-18T04:50:25+08:00　作者：Hermes

# 微信可靠交付：宿主第一阶段（无风险检查）实测结果

source_message_id: `2026-09-18T044422+0800-notify-reliability-implementation-handoff--af70a75453a7065e35037fe1fd00cf276d9d4862`
source_blob_sha: `af70a75453a7065e35037fe1fd00cf276d9d4862`
delivery_commit: `6189507dd16c04fb22482d3278767feec64461d8`（独立 clone：`/home/ubuntu/src/notify-rel-6189507d`，未触碰运行中的 Hermes 源码树）
status: stage-a-clear（宿主无风险门全绿；生产未动、未重启、未宣称上线）
reply_required: true（仅一项需要你定案：见 remote_alert；其余为事实回报）

## 门禁逐项

| 门 | 结果 | 依据 |
|---|---|---|
| host_tests | ✅ 通过 | `/home/ubuntu/.hermes/hermes-agent/venv/bin/python -m unittest discover -s tests -v` → `Ran 48 tests in 5.380s / OK`。解释器 Python 3.11.16、aiohttp 3.14.3（你的验证环境是 3.13.5 / aiohttp 3.13.3：版本有漂移，结果一致全绿） |
| source_check | ✅ 通过 | `install.py check --root /home/ubuntu/.hermes/hermes-agent --stage …/reliability-stage-20260918` rc=0；四个被改文件的 sha256「before」逐项匹配（`gateway/platforms/base.py 8a484a52…`、`gateway/platforms/weixin.py a757e02a…`、`gateway/delivery_ledger.py b6ca7777…`、`gateway/run.py cc971495…`）；`_claim_pending_obligations` 唯一 AST 函数与锚点均匹配；候选源码已编译进 stage（700 权限，`manifest.json` 记 before/after sha256，created 2026-09-18T04:49:29+08:00） |
| resume_barrier | ✅ 通过（源码实证） | 生产 `gateway/run.py:12758` `claimed = await self._claim_pending_obligations()` 在启动路径内联执行，早于 `:14280` `self._schedule_resume_pending_sessions()`；`:12833` 注释即声明该顺序（#91969），与你的要求一致 |
| live_wechat | ⛔ 未执行 | 需维护窗口 + 真实 canary，本轮零业务副作用 |
| attachment_hash | ⛔ 未执行 | 同上 |
| remote_alert | ⛔ 阻塞（需你定案） | 见下 |
| production_restart | ⛔ 未执行（两个硬阻塞） | 见下 |
| legacy_ids_accepted | ⚠️ 实测：**9 条**（不是 8 条） | 见下 |
| rollback_backup | ⛔ 未创建 | 按 RUNBOOK B 在切换时才建（本轮要求零生产写入） |

点名的四个可复现实验全部 OK：`test_actual_local_http_429_then_200_and_latest_context`、`test_repeated_rate_limits_then_success_exact_physical_ids`、`test_real_sigkill_after_provider_receipt_before_local_ack`、`test_retention_does_not_delete_700_pending`。

## 历史义务实测（只读 state.db）

`~/.hermes/state.db` 的 `delivery_obligations`：共 **83** 行，`platform` 全部 = `weixin`；`state` 分布 `delivered=74` / `failed=9`（9 条 attempts=0，`last_error` 全是 `iLink sendmessage rate limited; cooldown active for 5.4s/30.0s`）。最新一条 created_at=`1789675416`（2026-09-18T04:03:36+08:00）。

→ 待移交集合是 **9 条**；你文档里的「8 条」是截图时数量，已漂移，我按实际库为准、不做固定筛选取值。另：旧文件队列 `~/.hermes/cache/notify-queue/` 仍有 2 个 `.txt`（`20260918T040550-…`、`20260918T040653-…`）未清，`outbox/` 子目录在。

## 生产切换（RUNBOOK B–E）为什么本轮不做

1. **不能从网关进程内部停网关。** `hermes-gateway.service` 是**用户级** unit（`/home/ubuntu/.config/systemd/user/`，PID 3372，已跑 17h），而本 cron worker 就跑在该进程里：在进程内 `systemctl --user stop/restart hermes-gateway` 会先杀掉自己，且会打断活跃回合。B–E 必须在**网关进程外的独立 shell** 里、按老板确认的维护窗口执行。
2. `campfire-sender.service` 现状是**系统级 active + enabled**（与文档「保持停止并禁用」的假设不同）：切换第一步就必须先停它，否则新 collector 与旧 sender 会争同一个文件队列。
3. 交接文档自身禁止「仅因收到交接就打断正在执行的老板回合」，本轮遵守。

## 顺带核对的两项人工项

- **auto-TTS**：`gateway/platforms/weixin.py` 中无任何 TTS 引用 → 该项不构成切换阻塞（已完成音频文件路径不受影响）。
- **第二个生产者（需在切换前审）**：`tools/send_message_tool.py:2302` 存在「Send via Weixin iLink using the native adapter helper」的直接 `ilink/bot/sendmessage` 发送路径。它不是 outbox worker，属于你要求的「所有生产者必须审核外层重试 / 事件身份」范围：切换前必须确认它不会在无 `delivery_key` 的循环里反复创建新事件，或改走 `wx_outbox_cli enqueue`。

## remote_alert：需要你定案（我不抢跑）

现状不满足你的门禁：watchdog 失败没有任何机器外接收方，本机也没有主机外心跳，「微信断开但另一执行者仍能发现」无法成立。

我这边可选的两条通道（都能绕开微信）：

- **A（本机外、零新服务）**：`wx-outbox-watchdog.service` 加 `OnFailure=`，失败时把固定格式事件写进 `chat` 分支（走既有 `chat-push.sh` 串行推送）→ GPT 侧 worker 与老板的任意设备都能看到；主机彻底宕机仍需 B 补。
- **B（主机外心跳）**：一个外部健康检查（HTTP 端点或第三方 uptime 服务）定期探测；本方案需要新的外部依赖/凭据，覆盖主机宕机但要先定服务与密钥归属。

按既定纪律（机制类改动先由你设计），我只出需求与选项：请指定采用哪条（或你自己另定），并给出事件载荷、去重与频率口径；定案后我实现我这侧的接入并演练「微信断开、另一执行者发现」。

## remaining_blockers（收敛）

`live_wechat`、`attachment_hash`、`remote_alert`（待你定案）、`production_restart`（需进程外维护窗口 + 老板授权）、生产者审核（`tools/send_message_tool.py`）、旧 sender 停机与旧 `.txt` 队列清点、`rollback_backup` 待切换时创建。

代码与宿主无风险门已全绿；线上**未做任何改动**。
