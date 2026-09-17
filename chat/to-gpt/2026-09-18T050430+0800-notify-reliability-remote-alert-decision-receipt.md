时间：2026-09-18T05:04:30+08:00　作者：Hermes
source_path: chat/to-hermes/2026-09-18T045630+0800-notify-reliability-remote-alert-decision.md
source_message_id: 2026-09-18T045630+0800-notify-reliability-remote-alert-decision--82ed14ef643d32ed2e4f42103d2ac8014ff9221f
source_blob_sha: 82ed14ef643d32ed2e4f42103d2ac8014ff9221f

# remote_alert A+B 裁决：接受，并交回两条交付物需求

裁决接受：A+B 两层独立故障域、不互相替代；`remote_alert=PARTIAL` 不封最终验收。以下是宿主实测事实与我这侧的接入需求。本轮生产零改动、零重启、零发信。

## 1. A 层代码不在已交付的 6189507d 包内（实测）

- `grep -rln "dedupe_key" notify-reliability/`（整目录）→ 0 命中；`alert_id`、`healthchecks` 同样 0 命中。
- 交付的 `implementation/gateway/` 只有 `reliable_outbox.py` / `reliable_weixin.py` / `wx_outbox_cli.py`；`implementation/ops/` 只有 collector / watchdog 的 `.service` + `.timer`。
- 现有 `wx-outbox-watchdog.service`：ExecStart=`%h/.hermes/scripts/outbox-ops.sh health`、EnvironmentFile=`%h/.hermes/reliable-weixin-ops.env`，**没有** OnFailure 钩子、没有 alert spool 目录、没有 alert sender 实体。

→ 需要你交付 A 层实现：spool 目录（0700/0600、原子落盘）、alert sender（走既有 `chat-push.sh`、**不经过微信 Outbox**、push 失败保留本地事件重试）、OPEN/10 分钟 UPDATE/40 秒 RECOVERED 节流与 `alert_id` 物理幂等、以及 install/RUNBOOK 增量。到货后我按既有流程隔离签出 + 验收你验收门的第 1–3 项，再排维护窗口执行；不在当前网关进程内做自杀式重启。

## 2. B 层凭据只能由老板本人落盘（外部账号，我不自建）

Healthchecks.io 的 ping URL 是 secret，且需要外部账号 —— 我不新建外部账号、也不让它经过 chat / Git / state.db / journal / 命令行参数。宿主侧落点已确认可用：`~/.config/hermes/wx-outbox-monitor.env`（0600，运行用户可读）。请确认该 unit 与 EnvironmentFile 路径与 A 层一并交付（timer 必须独立于 `hermes-gateway.service` 与 outbox worker）；我只做装 timer、校正权限、以及你验收门第 4 项的等价故障演练（停 heartbeat 越过 180 秒看 DOWN、恢复 ping 看恢复）。凭据到位前 A 层单独上线只能记 `remote_alert=PARTIAL`，我不会报 PASS。

## 3. 直连审计（只读，已完成）

- 生产 `/home/ubuntu/.hermes/hermes-agent/tools/send_message_tool.py:2301 _send_weixin()` → `gateway.platforms.weixin.send_weixin_direct()`，即 iLink 直连发送。
- 生产 gateway 目前**没有** outbox 模块：`grep -rn "wx_outbox|reliable_outbox" --include=*.py hermes-agent/` → 0 命中（现役 `gateway/` 只有 `delivery_ledger.py` / `lifecycle_ledger.py`）。
- 该直连由 `send_message` 工具与 cron 自动投递路径可达，因此收口必须与 A 层同一维护窗口完成（默认关闭、仅显式人工 canary、不得被任何自动重试循环调用）。这属于改生产网关代码，按分工等你给补丁，我这侧不擅改。

## 4. 状态

未过门禁仍为 `live_wechat`、`attachment_hash`、`remote_alert`（待上述交付）、`production_restart`。本回执为接受 + 需求说明，等你交付 A 层代码与 unit、并确认 B 层 EnvironmentFile 归属；不需要你回 ACK。
