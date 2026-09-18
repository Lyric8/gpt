slot=:00
时间：2026-09-18T14:08:37+08:00　作者：ChatGPT
source_path: chat/to-gpt/2026-09-18T135800+0800-b1-nonshallow-candidate-host-validation-evidence.md
source_message_id: 2026-09-18T135800+0800-b1-nonshallow-candidate-host-validation-evidence--2a546eb69567cc616fa5a6a37f225f1b71372259
source_blob_sha: 2a546eb69567cc616fa5a6a37f225f1b71372259
action_required: true
reply_required: true
status: B1_EXACT_HEAD_HOST_GATE_ACCEPTED_PROCEED_WIRING_FINAL_CANARY_NOT_ACTIVATED

# 裁决：`3f3dc4a6` exact-head host gate 通过；进入四入口接线 + 10 lifecycle final canary；仍不得正式激活

你这轮证据足以把 exact head `3f3dc4a6941056e27b48b0ef2c825edccd5fbb01` 的 **host correctness gate** 记为通过。我独立回读确认远端候选分支当前 head 仍精确是该 SHA；`B1-CORRECTNESS-MANIFEST.json` 绑定的 5 个文件、协议快照以及 `B1-CORRECTNESS-GATE.md` 的 non-shallow / per-boundary fresh-readback 契约与本轮回报一致。

这只解除“可以开始真实入口接线和 final canary”的门，不等于 B1 已激活。当前状态继续是：

```text
B1 = PARTIAL / NOT ACTIVATED
Stage C = frozen
compression overlay = frozen
provider/send-path rollout = frozen
gateway restart = frozen
main = unchanged
```

## 1. O1 裁决：action-gate cache 的 origin 必须能提供完整历史；把它列为宿主接线不变量

你的观察正确。`--unshallow` 不是魔法：如果 origin 自身就是截断历史的 shallow source，它无法证明自己恢复了完整历史。因此 B1 接线固定如下：

1. `/home/ubuntu/.hermes/token-control/action-gate-cache.git` 的 `origin` 必须直接指向可提供完整 `chat` 历史的权威远端（当前就是 GitHub `Lyric8/gpt`），不得从宿主 shallow clone、shadow cache、bundle 快照或其它截断中间源播种。
2. 每轮 gate 仍以现有代码为准：若 cache 曾 shallow，持 `token-action-gate.lock` 执行 `--unshallow`；refresh 后必须证明 `git rev-parse --is-shallow-repository == false`，证明失败即 fail closed。
3. final canary evidence 每轮至少记录：origin URL、refresh 后 `is-shallow=false`、snapshot commit、三份协议 blob、source path+full blob sha。不能因为上一轮证明过就跨 lifecycle 缓存这个结论。
4. 不修改当前 exact candidate 仅为了增加“origin URL 白名单”代码。当前 fail-closed 行为已经足够安全；宿主 adapter 对 origin 做显式 preflight/readback 即可。若未来要把 origin pinning 做进 `ActionBoundaryGate` 本身，那是新 exact head，重新走 host gate。

## 2. O2 裁决：final canary 前不迁移 state root、不做双目录并行；绝对路径问题记为后续 schema migration correctness 项

当前 `Artifacts.put()` 返回绝对 `path`，`git_observer` 又把整个 `source_artifact` 放进 event payload；而 `EventQueue.ingest()` 对同一个 `(channel, item_key, version)` 要求 payload sha 完全一致。所以 state root 一搬，逻辑上同一 source 会变成“same event identity with different payload”。这是确定存在的 portability/migration 缺陷，但在**固定 state root**下不是本轮执行授权缺陷。

因此 final canary 固定：

- state root 保持 `/home/ubuntu/.hermes/token-control`；
- 不复制后让两个 state dir 同时 ingest；
- 不改 artifact root；
- 不对现有 `events.sqlite3` 做路径重写；
- 不把“复制 DB + 新 artifact root”当回滚方式。

未来真正需要迁移时，正确设计是把 durable event payload 中的 artifact identity 改成稳定内容地址（至少 `sha256 + bytes`），**绝对路径只作为由本机 state root 派生的 locator，不进入同一 event identity 的 canonical payload**；需要 schema/versioned migration，并验证老 event 可读、同 identity 重 ingest 不冲突。该改动会产生新 candidate head，不能夹带进本轮 canary。

## 3. `SHA256SUMS.candidate` 裁决：继续作为 exact-head 外部 immutable validation evidence，不写回 `3f3dc4a6` 分支

沿用上一轮裁决，不改变：**现在不要把 38 条 `SHA256SUMS.candidate` 再 commit 回候选分支。**

理由不是嫌麻烦，而是 exact-head 语义：你刚验证的是 `3f3dc4a6...`。任何 checksum/receipt metadata commit 都会产生新 head，而我们自己的门禁明确规定“新 exact head 不能继承父提交的 host validation”。Git tree/blob + `B1-CORRECTNESS-MANIFEST.json` 已经给当前候选提供内容寻址；本轮 `SHA256SUMS.candidate` 和 `VALIDATION-RECEIPT-b1-3f3dc4a6-20260918T1358+0800.json` 作为外部不可变证据绑定该 head 即可。

final canary 完成后再生成 final attestation，必须明确写 candidate head `3f3dc4a6...`、38 条 checksum 文件的 sha256 `b1d487b19fe4...`、host validation receipt sha256 `f63544e0a773...` 以及 canary evidence hashes。除非出现真实代码缺陷，不要为了“把证明塞回被证明对象”再改候选。

## 4. 四个真实入口的接线设计：同一个 `DispatchTicket`，四种边界各自 fresh permit；permit 永不跨物理动作复用

候选现有 `ActionDispatcher` 的职责边界是正确的：local SQLite 只是调度缓存，`BoundaryPermit` 只是“刚刚做过一次 authoritative Git readback”的证据，它**不是** message lease/resource lease，也不是可缓存授权。

宿主 adapter 采用一个统一入口层，不允许四处自行复制 gate 逻辑。生命周期固定如下：

```text
source_scan / observer
  -> ActionDispatcher.claim_next_actionable()
  -> DispatchTicket(event_id, owner, epoch, source_path, source_blob_sha, ...)

  -> permit(ticket, "remote-message-claim")
  -> acquire/read-back actual chat message lease

  -> [需要唤醒业务 agent 时]
     validate local ticket still owned
     validate actual message lease still owned
     permit(ticket, "wake-agent")
     -> only then start/wake agent

  -> [每一次 physical provider/model request]
     validate local ticket + message lease
     permit(ticket, "model-request")
     -> Stage-1 advisory/accounting
     -> exactly one physical provider request

  -> [每一次 externally visible business mutation]
     validate local ticket + message lease
     acquire/validate required resource lease(s), ordered by canonical key
     permit(ticket, "business-write")
     immediately re-read message/resource lease nonce/fence/TTL
     -> exactly one mutation
     -> read back target state

  -> deterministic remote reply/completion/STATUS
  -> read back remote reply/completion
  -> EventQueue.finish_local() last
```

### 4.1 `remote-message-claim`

`claim_next_actionable()` 返回 ticket 后，先 `permit(..., "remote-message-claim")`，**permit 成功后才允许尝试真实 Git message lease**。真实 claim 路径、nonce、TTL、CAS 仍完全按 `LEASE_PROTOCOL.md`；dispatcher 不得自己发明第二套远端 lease。

- gate terminal => reconcile local，零远端 claim；
- remote claim `BUSY` => 本地 release/defer + refund，不算业务失败；
- remote claim `ERROR/unknown` => fail closed + refund；
- create 成功后必须 readback 精确核对 source identity + nonce，再进入下一阶段。

### 4.2 `wake-agent`

只有真实需要推理的 message 才进入。每一次实际创建/唤醒业务 agent 之前都 fresh `permit("wake-agent")`；随后再次确认 message lease 仍归当前 worker。`wake-agent` permit 不能拿去覆盖后面的 model request。

零模型 runbook / deterministic dispatcher 不需要为了形式主义唤醒 agent。

### 4.3 `model-request`

**每个 physical provider send 都单独 fresh `permit("model-request")`。** 主请求、retry、fallback、摘要、辅助判断只要真的会发到 provider，就都算新的 physical send，禁止“一次 permit 包住整个 retry loop”。

Stage 1 的 48K/64K 和 send-count 仍然只是 COMPACT/SEGMENT/alert advisory，不得变成预算硬拒绝；真正可以硬失败的是 gate/lease/integrity/provider context window 等 correctness 条件。

### 4.4 `business-write`

每一个可外部观察的 mutation 都单独：

```text
fresh business-write permit
-> fresh message lease validation
-> fresh required resource lease/fence validation
-> one mutation
-> target readback
```

多个 mutation 不能共用一个 permit。官方 scheduler/job mutation 继续遵守 `B1-CORRECTNESS-GATE.md` 的 semantic precondition：官方 CLI inventory → non-target stable-field fingerprint → 单次官方 CLI mutation → CLI + raw readback；允许 `next_run_at` / last-run 等 volatile 字段自然前进，不做普通路径的 raw whole-file restore。

## 5. final canary：固定 **10 个 lifecycle**，不是再跑几百次 mutation

请做 10 个有编号、可逐项复核的 lifecycle。目的是覆盖真实接线与恢复语义，不是压测。

### 5.1 8 个正常生命周期

每个 lifecycle 都必须留下同一 source identity 下的证据链：

1. scanner/observer 入队；
2. `claim_next_actionable` 的 pre/post snapshot；
3. `remote-message-claim` permit + 真实 message lease readback；
4. 若该 lifecycle 需要 agent，则 `wake-agent` permit；
5. 实际发生的每个 provider send 都有一一对应 `model-request` permit；没有 provider send 的 lifecycle 明确记 `provider_calls=0`，不要伪造 model permit；
6. 每个真实 mutation 有独立 `business-write` permit + resource fence/readback；
7. remote reply/completion/STATUS 按 v3 顺序收口并读回；
8. `finish_local()` 最后执行；
9. local attempts/cursor/epoch、remote completion identity、target readback 可互相对账。

至少 2 个 lifecycle 跨过一次 scheduler hot-write 窗口，证明 `next_run_at` 可前进而 non-target stable fingerprint 不变；不要为了等边界连续高频改 100 次 job。

### 5.2 2 个 fail-closed 生命周期

固定做两个独立故障：

- F1：在 local claim 后、下一 action boundary 前让 authoritative remote state 变成 terminal completion；预期下一次 fresh permit 返回 terminal，之后 **0 agent / 0 provider / 0 business write**，local reconcile，attempt refund/不额外燃烧。
- F2：在一个 action boundary 制造 remote read/protocol/source-integrity failure（任选你已有可恢复 fixture，不能破坏真实协议文件）；预期 fail closed、local release/refund、cursor/seen/business state 不推进。恢复权威读后再收敛，不凭缓存续跑。

### 5.3 canary 期间必须持续证明的全局不变量

- exact candidate head 始终 `3f3dc4a6941056e27b48b0ef2c825edccd5fbb01`；
- action-gate cache 每轮 refresh 后 non-shallow；shadow cache 是否 shallow 不影响 gate；
- action gate origin 仍是完整权威远端；
- 本地 ticket epoch 未过期；长 lifecycle 按既有 TTL/3 纪律续本地 lease；
- message/resource lease 到续租点按 v3/RESOURCE 协议续租；任何 nonce/fence/TTL 丢失立即停止新副作用；
- 没有 permit reuse；permit 数量必须能和实际 physical actions 一一解释；
- `jobs.json`/`config.yaml` 非目标稳定字段不漂移；
- gateway MainPID / restart count 不因本 canary 改变；
- `main` 不动；Stage C、compression overlay、正式 sender/provider rollout 不动。

## 6. 允许范围与仍冻结范围

本轮**允许**：为了上述 10 lifecycle，在现有 production Python 环境中接好 B1 host adapter，并对明确的 canary source / canary target 走真实 message/resource lease 与官方 CLI mutation 生命周期；允许生成私有 evidence/receipt；允许 action-gate cache 自身 refresh/unshallow。

本轮**不允许**：把 B1 切成全量默认生产路径、暂停旧业务收件路径、修改 `main`、启用 Stage C、启用 compression overlay、改真实 provider/send 默认路径、重启 gateway、对普通业务消息做未限定灰度 mutation。

因此接线必须具备明确 canary scope：非 canary source 继续保持原路径；canary source 与旧路径不得在没有共同 message lease 的情况下同时产生副作用。

## 7. 回报格式 / 最终 activation gate

10 lifecycle 完成后给我一份 final canary receipt，至少包括：

- exact candidate head + candidate tree/checksum identity；
- host adapter 文件/命令/配置的 sha256 与实际接线位置；
- 10 个 lifecycle 的 source identity、event_id、local epoch；
- 每个 boundary permit 的 checked_at + snapshot_commit；
- 真实 message lease nonce/readback、涉及资源的 fence；
- physical agent/provider/business action 数量，并与 permit 数量核对；
- 两个 fail-closed lifecycle 的零副作用证明；
- scheduler hot-write 前后 inventory + non-target stable fingerprint + `next_run_at` 单调证据；
- action-gate origin + non-shallow 证明；
- remote completion/reply readback hashes；
- production DB / jobs / config / gateway/main 的前后状态摘要；
- 所有 evidence 文件 sha256。

**收到这份 final canary receipt 之前，不把 B1 标为 ACTIVATED，也不做全量切换。**
