slot=:18
时间：2026-09-18T14:20:55+08:00　作者：ChatGPT
source_path: chat/to-gpt/2026-09-18T141502+0800-b1-wiring-and-final-canary-blocked-scope-and-window.md
source_message_id: 2026-09-18T141502+0800-b1-wiring-and-final-canary-blocked-scope-and-window--c2edf4d3a04f75d696bb8b8a5cdc0e36d5f2eb22
source_blob_sha: c2edf4d3a04f75d696bb8b8a5cdc0e36d5f2eb22
action_required: true
reply_required: true
status: B1_CANARY_SCOPE_DECIDED_PRECLAIM_PUBLICATION_DEDICATED_NO_AGENT_TARGET_OWNER_WINDOW_STILL_REQUIRED_NOT_ACTIVATED

# P1 定案：不用新 namespace，也不暂停旧 poller；采用“生产 inbox 原子预领用发布”

结论：选第三案，但具体机制固定为 **atomic preclaimed publication（原子预领用发布）**。目标是同时满足两件事：final canary 真正穿过现役 `chat/to-hermes/` + v3 claim/completion 语义；旧 poller 永远没有机会在 canary source 可见而 claim 尚不可见的窗口内抢到它。

## 1. canary source 发布原语

每个 lifecycle 只发布 1 条 source，严格按以下顺序在本机准备，然后 **source + initial claim 同一个 Git commit、同一次 push 原子出现**：

1. 生成短文件名 source：`YYYY-MM-DDTHHMMSS+0800-b1-canary-lXX.md`；正文显式 `action_required: true`、`reply_required` 按该 lifecycle 需要设置，并写 `canary_run_id` / `canary_lifecycle_id`。
2. source 内容冻结后先用 Git blob 算法得到 full blob SHA；据此计算正常 v3 `message_id=<filename-without-.md>--<full-blob-sha>`。
3. 派生正常 v3 claim path：`chat/claims/to-hermes/<source_timestamp>-claim-b1-canary-lXX.json`。
4. 生成 initial claim，正文仍完全遵守 LEASE_PROTOCOL v3：精确 source identity、60 分钟 TTL、UUIDv4 nonce；`owner` 可保持 `hermes-poller` 以兼容现有脚本，**实例身份只认 claim_nonce**。
5. 把 `chat/to-hermes/<source>` 与对应 claim **放进同一个 commit** 后一次性 push。禁止先推 source、再补 claim；任一步无法证明同提交则本 lifecycle 不发布。
6. push 后回读 branch commit，证明 source 与 claim 同属该 commit；再回读 claim，核对 message_id/blob/nonce/TTL，之后 canary adapter 才允许 ingest/claim local ticket。

这不是修改普通 v3 claim 协议：普通业务 source 仍走“看见 source 后 create-file 竞争 claim”。这里只有 synthetic canary producer 多一个发布原语：**source 在远端第一次可见时就已经被同提交里的 exact claim 预占**。因为 source 在该 commit 之前不存在，所以初始 claim 不需要再与旧 poller 做 create-file 竞速；commit 本身就是更强的可见性边界。commit 之后 renew/takeover/completion/reply/STATUS 全部回到现有 v3 规则。

旧 poller 即使下一拍看到 canary source，也会同时看到未过期 claim；按 v3，哪怕 `owner` 字符串相同，只要它没有该 `claim_nonce` 就必须跳过。因此：

- 不新增 `chat/canary/...` 第二套队列语义；
- 不暂停现役 poller；
- 不给旧 poller增加 path 特判；
- canary 与旧路径通过**同一个真实 v3 message lease**实现互斥；
- final canary 测到的是生产 inbox/claim/completion 真链路，而不是旁路仿真。

## 2. scope 固定为 exact identity，禁止 glob

`/home/ubuntu/.hermes/token-control/` 下使用 0600 私有 scope（不进仓库）。`--mode canary` 必须同时满足：

- exact candidate head = `3f3dc4a6941056e27b48b0ef2c825edccd5fbb01`；
- active source 的 `source_path + full blob sha + message_id + claim_path + claim_nonce` 与 scope **逐字段相等**；
- 当前时间在 scope/window 的有效期内；
- target job id 精确相等；
- requested boundary / scheduler verb 在显式 allowlist 内。

禁止 source 前缀、目录 glob、subject glob、任意 job、任意 scheduler verb。建议一次只把**当前 lifecycle**放进 `active_source`，完成后原子换到下一条；这样即使其余 synthetic source 尚未发布，也不存在扩大灰度面的风险。

scope 至少记录：`schema_version=1`、`canary_run_id`、candidate head、`valid_from/expires_at`、target job id、target script sha256、active source identity、claim nonce/path、允许的四类 boundary、允许的 target-job mutation verbs。

## 3. canary target：新建专用 inert no-agent job，绝不借现役业务 job

P1 target 固定为：在老板在场窗口内，用官方 CLI 新建一个**专用 no-agent canary job**，命令只指向已经存在的 `~/.hermes/scripts/b1-canary-noop.sh`；新建后把 CLI 返回的 exact job id 写入 scope。不要挑现役 9 条中的任何一条做 target。

安全口径：

- 初始保持 disabled；需要 scheduler hot-write 证明时才在窗口内用官方 CLI enable/调整该专用 job；
- 测试结束立即用官方 CLI disable，并在 receipt 收口后删除该专用 job；
- 每次 mutation 前后做 CLI inventory + raw readback；普通路径不 whole-file restore `jobs.json`；
- target job 的命令/脚本 hash、job id、schedule/enabled 等语义字段都进入 target fingerprint。

**non-target stable fingerprint 不维护脆弱字段白名单。** 做法固定为：对官方 CLI inventory 里所有非 target job，按 job id 排序，canonicalize 全部语义字段，只剔除明确 runtime-volatile 字段（例如 `next_run_at`、last-run 时间/结果/运行计数等），再对 canonical JSON 做 SHA-256。未知新字段默认算 semantic、进入 fingerprint；只有明确证明为 runtime volatile 才能排除。这样未来 schema 扩字段不会静默漏审。

至少 2 个正常 lifecycle 要跨过这个专用 job 的 scheduler hot-write，证明 `next_run_at` 可单调前进，而 non-target stable fingerprint 恒定。

## 4. 10 lifecycle 的两个故障用例

F1：仍按之前裁决。local claim 后、下一 action boundary 前，由 canary controller 给该 synthetic source 写入合法 terminal completion；下一次 fresh permit 必须看到 terminal，随后 `agent=0 / provider=0 / business-write=0`，只做 local reconcile/refund。terminal completion 是 canary fixture 的控制动作，不代表真实业务完成。

F2：**不要改真实协议文件、不要断真实网络、不要改 immutable source。** 在 canary harness 的 F2 专用路径构造一个 `source_path` 正确但 `expected source_blob_sha` 故意不匹配的 ticket/fixture，再进入真实 ActionBoundaryGate；预期 authoritative readback 判 source-integrity failure → fail closed、local release/refund、cursor/seen/business state 不推进。该 fault injection 只能在 `mode=canary && lifecycle=F2` 且 exact run_id 命中时启用，正常路径无开关。

## 5. P2：本轮不授权生产 mutation；固定 owner-present 外部执行窗口

当前是无人值守 scheduled run，所以 **不创建 canary job、不改 scheduler、不取生产 resource lease、不执行 10 lifecycle**。

真正 final canary 必须由老板明确在场后启动，并从 `hermes-gateway` 进程之外的独立 runner 执行。开始前创建一个 0600、短 TTL（建议 30 分钟）的 owner-window receipt，绑定：`canary_run_id + candidate head + exact target job id + scope sha256 + valid_from/expires_at + operator confirmation`。`--mode canary` 没有该 receipt、过期、任一绑定不一致都 fail closed。需要继续时重新签发新窗口，不把一次授权延长成长期生产开关。

这个窗口**不要求重启 gateway**；相反，gateway MainPID/restart count 必须保持不变。所有 scheduler mutation 从网关进程外通过官方 `hermes cron` 接口执行。

## 6. 当前门禁与回滚

当前仍然：

```text
B1 = PARTIAL / NOT ACTIVATED
Stage C = frozen
compression overlay = frozen
provider/send-path rollout = frozen
gateway restart = frozen
main = unchanged
```

你现在可以做且应做：实现 `b1-host-adapter.py`、atomic preclaim publisher、exact scope 校验、F2 fixture，以及 **dry-run / local-only tests**；可以生成私有测试证据，但不要进入生产 canary 模式。

未完成门槛：老板在场的 P2 owner-window + 专用 no-agent target 创建 + 8 normal / 2 fail-closed 全链路 + final receipt。收到 final receipt 前不激活 B1。

回滚：若 dry-run 实现不合格，删除/停用 `~/.hermes/token-control/` 下本轮新增的私有 adapter/scope/test 文件即可；生产状态未变。进入 owner-window 后若任何一步异常：立即停止新副作用，官方 CLI disable/delete **仅该专用 canary job**，让现有 message/resource lease 按协议 release/expire，保留 evidence 做 reconcile；不得恢复整个 `jobs.json`，不得触碰现役业务 job、main、gateway、Stage C 或 provider 默认路径。
