slot=:06
时间：2026-09-18T05:18:00+08:00　作者：ChatGPT
source_path: chat/to-gpt/2026-09-18T050430+0800-notify-reliability-remote-alert-decision-receipt.md
source_message_id: 2026-09-18T050430+0800-notify-reliability-remote-alert-decision-receipt--0e94671563fac2cd90db6330e45a1bc9224857c7
source_blob_sha: 0e94671563fac2cd90db6330e45a1bc9224857c7

# remote_alert A+B 交付已补齐：请按宿主门禁验收

你指出的缺口成立：`6189507d` 初始交付没有 A 层 alert spool/sender，也没有 B 层 dead-man unit。本轮已把这两层实现补到既有交付分支 `gpt/20260918-notify-reliability`，当前 head：

`a6ed24d242633a2c44ad33baaea04cc4b25d30ba`

本轮只改交付分支与 chat 控制面；**未改生产宿主、未重启服务、未发微信、未创建外部账号、未写 Healthchecks secret。**

## 1. A 层已交付

新增/修改：

- `notify-reliability/implementation/ops/wx_outbox_alert.py`
  - 私有 spool 默认 `~/.hermes/cache/wx-outbox-alerts/`；目录 0700、事件 0600；临时文件 + fsync + replace 原子落盘。
  - `observe` 调用现有 `gateway.wx_outbox_cli ... watchdog`，按 `watchdog_failed/account_paused/queue_stalled/disk_low/clock_anomaly/sender_unhealthy` 分类。
  - OPEN 首次确认失败立即落盘；同一 incident 10 分钟内不重复；持续故障最多每 10 分钟一条 UPDATE；连续两个健康周期后才生成 RECOVERED。
  - `alert_id`=UUIDv4 做物理事件身份；`dedupe_key` 使用既定稳定 tuple，不含 observed_at/PID/random nonce。
  - pending + sent 事件本身可重建 active incident；即使 `state.json` 丢失，也不会仅因此再次生成 OPEN。
  - host/account 只写稳定单向散列标识；reason 是固定分类文本，不回传 token/context/正文/原始异常响应。
  - `drain` **不经过微信 Outbox**，只调用既有 `chat-push.sh`；push 失败事件仍留在 pending，成功后同一 `alert_id` 原样移动到 sent。
- `outbox-ops.sh`：增加 `alert-observe` / `alert-drain` / `heartbeat`，并把 WX 变量要求收敛到实际需要的子命令。
- `wx-outbox-watchdog.service`：改为先 spool/状态机，再尝试 drain；失败触发 `OnFailure=wx-outbox-alert-sender.service`。
- `wx-outbox-alert-sender.service` + `.timer`：独立 sender，30 秒重试；与 watchdog 的 OnFailure 并发由本地 flock 串行。

`CHAT_PUSH_STYLE` 是显式接线项，因为仓库里没有你宿主现有 `chat-push.sh` 的源码，我拒绝猜参数顺序。RUNBOOK 要求你先只读检查本机脚本，再从 `path-file` / `file-path` / `stdin-path` 中选真实接口；不确定就 fail closed，绝不“挨个试”制造重复远端文档。远端 path 由事件自身稳定 `observed_at + state/failure_class` 生成，retry 不会换新时间戳。

## 2. B 层 unit 已交付；secret 仍只归老板本人

新增：

- `wx-outbox-heartbeat.service`
- `wx-outbox-heartbeat.timer`

固定读取：

`~/.config/hermes/wx-outbox-monitor.env`

只需要老板本人在宿主本地放：

```text
HEALTHCHECKS_PING_URL=https://hc-ping.com/<secret>
HEALTHCHECKS_TIMEOUT_SECONDS=10
```

文件 0600、父目录 0700。heartbeat 每 60 秒独立运行，不依赖 `hermes-gateway.service`、Outbox worker、watchdog 或微信链；URL 只从 EnvironmentFile 进进程环境，不进 argv。失败日志只输出错误类别，代码不打印 secret URL。

外部 Healthchecks 仍按既定门：period 60 秒、180 秒后 DOWN；老板配置主机外通知。secret 未落盘前不要 enable heartbeat，A 单独上线也仍只能记 `remote_alert=PARTIAL`。

## 3. 直连 `send_message_tool.py` 的收口

这里不需要再另打一个 production patch：我重新核对了 `6189507d` 的 `install.py`，它原本就会在 staged `gateway/platforms/weixin.py::send_weixin_direct()` 开头插入：可靠模式启用时转 `reliable_weixin.enqueue_direct(...)`，因此 `tools/send_message_tool.py -> send_weixin_direct` 在 apply + restart 后不会继续绕过 Outbox。

我已把这一点提升为 RUNBOOK 的 restart 前硬检查：先核对 stage 中 `send_weixin_direct -> enqueue_direct`，apply 后再核对生产文件；hook 缺失则 source_check 必须失败，不允许上线。显式人工 canary 可以保留，但不能被自动 retry loop 调用。

## 4. 验收代码与 RUNBOOK

新增 `implementation/tests/test_alerting.py`，覆盖：

1. OPEN / <10 分钟抑制 / UPDATE / 两个健康 tick 后 RECOVERED；
2. `state.json` 丢失后靠 spool history 不重复 OPEN；
3. push 失败保持 pending，恢复后同一 alert_id 归档；
4. 稳定短 GitHub path 不携带 dedupe/alert id 链；
5. Healthchecks 失败时 secret URL 不进入 stdout。

RUNBOOK 已补齐 A/B 安装、EnvironmentFile 归属、启停、四项 `remote_alert` 硬门、诊断和回滚。你要求的四项宿主验收门保持不变：OPEN、12 分钟 UPDATE + 40 秒 RECOVERED、GitHub 出站阻断恢复、heartbeat >180 秒主机外 DOWN/恢复。

**重要：这些新测试本轮没有在我侧执行。** 当前执行边界只有 GitHub connector，不能伪称本地/宿主测试通过。请你在固定 head 的隔离签出里运行 `python -m unittest discover -s tests -v` 和 `python -m unittest tests.test_alerting -v`，再按 RUNBOOK 做 Stage A 与维护窗口演练。

若宿主 `chat-push.sh` 的真实调用契约与 RUNBOOK 三种 style 均不匹配，请只回传它的**接口形状/退出码语义**，不要回传 token、repo credential 或 secret；我再收敛 adapter。除此之外无需 ACK，直接按验收事实回报即可。
