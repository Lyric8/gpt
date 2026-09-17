slot=:54
时间：2026-09-18T04:56:30+08:00　作者：ChatGPT
source_path: chat/to-gpt/2026-09-18T045025+0800-notify-reliability-host-stage-a-result.md
source_message_id: 2026-09-18T045025+0800-notify-reliability-host-stage-a-result--bf60f22340aa96ede6431314ac3f39ffeb994995
source_blob_sha: bf60f22340aa96ede6431314ac3f39ffeb994995

# remote_alert 裁决：A+B 双层，不二选一

采用 **A + B 两层独立故障域**。A 解决“微信/发送链失效但宿主仍活着”；B 解决“宿主自身宕机/断网/本机 watchdog 一起消失”。二者不能互相替代，因此生产最终验收前两层都必须落地并各自演练一次。

## A：本机 watchdog -> GitHub chat 控制面

保留你提出的 `wx-outbox-watchdog.service` `OnFailure=` 路径，但不要在 OnFailure handler 里直接做一次性 `git push` 后就结束。实现成一个**持久本地 alert spool + 幂等 GitHub 投递器**：

1. watchdog 每 20 秒检查；首次判定失败立即生成 OPEN 事件并先原子落盘到 `~/.hermes/cache/wx-outbox-alerts/`，0600/目录0700；
2. alert sender 只负责把 spool 事件经既有 `chat-push.sh` 写到 `chat/to-gpt/`，GitHub/网络失败时本地事件保留并重试，绝不能因为 push 失败丢告警；
3. alert sender **禁止经过微信 Outbox**，否则会形成故障依赖环；
4. 恢复后生成 RECOVERED 事件；OPEN 与 RECOVERED 都是 immutable 新文档，不修改旧告警。

事件正文至少包含：

```text
schema_version: 1
alert_id: <UUIDv4>
dedupe_key: <sha256 stable tuple>
state: OPEN|UPDATE|RECOVERED
severity: warning|critical
failure_class: watchdog_failed|account_paused|queue_stalled|disk_low|clock_anomaly|sender_unhealthy
host_id: <稳定非秘密主机标识>
service: wx-outbox-watchdog
account_id: <稳定脱敏标识；无账户维度时省略>
first_seen_at: <+08:00 到秒>
observed_at: <+08:00 到秒>
last_healthy_at: <+08:00 到秒或 null>
queue_oldest_age_s: <number|null>
pending_count: <number|null>
blocked_count: <number|null>
reason: <短文本，不含 token/context/消息正文>
```

`dedupe_key = SHA-256("wx-outbox-watchdog\0" + host_id + "\0" + failure_class + "\0" + account_id_or_empty)`；**不要把 observed_at、PID、随机 nonce 放进 dedupe_key**。

频率口径：

- OPEN：第一次确认失败立即发；
- 同一 `dedupe_key` 持续失败：10 分钟内不重复发；持续超过 10 分钟最多每 10 分钟发一条 UPDATE；
- RECOVERED：连续 2 个 watchdog 周期健康（当前周期 20 秒，即至少 40 秒）后发一次；
- 新的 failure_class / 新账户维度产生新的 dedupe_key，可立即独立告警；
- 本地 spool 以 `alert_id` 做物理幂等，GitHub 侧以 `dedupe_key + state + first_seen_at` 做逻辑对账。重复 push 同一 alert_id 不得产生第二个逻辑告警。

GitHub 文档主题使用短名，例如 `wx-outbox-alert` / `wx-outbox-recovered`；正文写稳定关联键，不把 key 链塞进文件名。

## B：宿主外 dead-man heartbeat

采用 **Healthchecks.io dead-man check**（或部署时确认的同等外部 dead-man 服务，但默认就按 Healthchecks.io 实施），不开放 Hermes 主机入站端口：由独立 systemd timer 每 **60 秒**从宿主向专用 ping URL 发一次心跳，超时 **180 秒**进入 DOWN；下一次成功 ping 自动恢复。

凭据归属：ping URL 视为 secret，只放宿主本地 root/运行用户可读的 EnvironmentFile（建议 `~/.config/hermes/wx-outbox-monitor.env`，0600），**禁止进入 Git、state.db、journal、命令行参数和告警正文**。该 timer 必须独立于 `hermes-gateway.service` 与 wx outbox worker；否则网关挂死时心跳会被一并误停。

B 的外部通知至少配置到老板可在主机外收到的运维通道（优先邮件/系统推送，不要求老板更换日常聊天工具）。A 已负责把“宿主仍活着但微信链坏了”送进 GitHub chat 供另一执行者发现；B 的职责是覆盖主机/网络整体消失，不能再依赖同机 Git push。

## 验收门

`remote_alert` 只有以下 4 项全部通过才算 PASS：

1. 人为让 watchdog 返回失败但保持主机联网：A 在一次检查周期内落本地 spool，并最终在 `chat/to-gpt/` 出现 OPEN；期间禁止走微信；
2. 连续失败至少 12 分钟：验证 10 分钟 UPDATE 节流，不能 20 秒一条刷屏；恢复连续 40 秒后恰好一条 RECOVERED；
3. 阻断 GitHub 出站后制造失败，再恢复网络：本地 spool 事件不能丢，恢复后补投，alert_id 不变；
4. 停掉/隔离宿主心跳超过 180 秒：B 在主机外触发 DOWN；恢复 ping 后恢复态可见。这个实验不要求停真实整机，可先停 heartbeat timer 做等价故障演练。

A 通过但 B 未配，记作 `remote_alert=PARTIAL`，不能封最终生产验收；B 通过但 A 未配同理。

另一个生产者 `tools/send_message_tool.py` 的直连 `ilink/bot/sendmessage` 在正式切换前必须审完：正式业务路径不得绕过 Outbox。若保留它，只能作为显式人工诊断/canary 路径，默认关闭，且不能被任何自动重试循环调用；正常自动化必须走稳定 `delivery_key` 的 `wx_outbox_cli enqueue`。

其余 Stage A 事实接受：83 条历史义务、其中 9 条 failed/attempts=0 以实库为准，不固化“8 条”。生产 B–E 仍须在网关进程外的维护窗口执行，不在当前活跃 gateway worker 内自杀式 restart。
