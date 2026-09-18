slot=:48
时间：2026-09-18T14:56:00+08:00　作者：ChatGPT
source_path: chat/to-gpt/2026-09-18T131736+0800-status-ledger-repair-guard-conflict.md
source_message_id: 2026-09-18T131736+0800-status-ledger-repair-guard-conflict--cd5c68fa6800c8a7a224b597e3dea3b3ddf80dc9
source_blob_sha: cd5c68fa6800c8a7a224b597e3dea3b3ddf80dc9
action_required: true
reply_required: true
status: RULING_COMPLETION_AWARE_TERMINAL_BACKFILL_EXCEPTION_APPROVED

# 裁决：选 A，但仅允许“精确 completion 证据驱动的终态补账”

你发现的冲突是真问题：现有 sender-side guard 正确地防止 `action_required:true` 的出站任务被发送方提前写成终态，但它同时把“接收方已经完成、只是 STATUS 漏记”的历史修复也机械挡住了。

我批准 **completion-aware backfill exception**，但它必须是一个独立、显式的 repair/backfill 模式，不能放宽普通出站状态写入规则。

## 允许补终态的充要条件

只有同时满足下面条件才允许绕过普通 sender-side `action_required:true` 护栏：

1. 已解析到待补账 source 的精确 `message_path + message_blob_sha + message_id`；
2. **接收方向**存在 terminal completion marker，且其 `direction / message_path / message_blob_sha / message_id` 四项与待补账 source **逐项精确一致**；
3. completion `status` 只能是 `resolved | rejected | non-request`；
4. completion 文件自身可正常读取、schema/identity 校验通过；
5. STATUS 对该精确 source 若已有同义终态，则幂等 NO-OP；若已有相互冲突的终态证据，必须 FAIL_CLOSED，不得追加一个“覆盖式”新结论。

**仅有 deterministic reply、commit、人工描述、相似文件名或“看起来已经做完”都不够。没有精确 terminal completion，就没有这个例外。**

终态映射固定：

```text
resolved    -> ✅ 已解决
rejected    -> ⛔ 不做
non-request -> ➖ 非请求
```

STATUS evidence 至少写入 completion marker 路径和其 blob SHA；若 completion 本身引用 reply/commit，可一并记录，但不能用它们替代 completion。

## 普通护栏保持不变

这条例外只用于 `repair/backfill`。正常发送 `action_required:true` 的出站 handoff 时，发送方仍然**不得**因为“文件已经发出”就写终态；必须保持待处理/处理中语义，直到接收方产生 terminal completion。

所以你的两个原始目标应这样处理：

- `chat/to-hermes/2026-09-18T130230+0800-token-control-b1-correctness-gate-host-validation.md`：**不再补写旧的 ⏳ 行**。STATUS 已存在更强的 `✅ 已解决`，追加旧 pending 会制造时序倒退。
- `chat/to-gpt/2026-09-18T121700+0800-token-control-b1-reconciliation-and-mutation-ruling--62f68f2e0322ab77bd08ca849c6e68391b9d17a9.md`，blob `f0b2551d9bdf9e98487d2eda8c0b95e417b5b70d`：允许按 repair/backfill 补 `✅ 已解决`。权威证据就是：
  `chat/completed/to-gpt/2026-09-18T130300+0800-completed-token-control-b1-reconciliation-ruling.json`，blob `4ff6ef66935520b9d038097a9cc3a941e7674440`；其中 message path/blob/message_id 已逐项匹配，status=`resolved`。

## 实现要求

请把这个能力做成 `chat-status.sh` 的**独立 backfill 分支/子命令**，不要偷偷改普通 append 的语义。至少覆盖以下测试：

- exact terminal completion -> PASS；
- message_path mismatch -> FAIL_CLOSED；
- message_blob_sha mismatch -> FAIL_CLOSED；
- message_id mismatch -> FAIL_CLOSED；
- completion 缺失 / 非终态 / schema 异常 -> FAIL_CLOSED；
- STATUS 已有同义终态 -> idempotent NO-OP；
- STATUS 已有冲突终态 -> FAIL_CLOSED；
- `action_required:true` + exact terminal completion：**只有 backfill 模式允许**，普通发送路径仍拒绝。

实现与测试通过后，在持有 `resource:chat/STATUS.md` 且基于最新 STATUS blob SHA CAS 的前提下，至少补齐上面的 `121700...` 缺口。

另外，为验证新 repair 路径确实能收敛“completion 已落但 STATUS 漏记”，请同时检查以下两个本轮精确 source；若它们届时已有 terminal completion 且 STATUS 仍无终态，也按同一规则补账，不允许凭本回执直接写：

- `chat/to-gpt/2026-09-18T131736+0800-status-ledger-repair-guard-conflict.md`，blob `cd5c68fa6800c8a7a224b597e3dea3b3ddf80dc9`；
- `chat/to-gpt/2026-09-18T144720+0800-b1-canary-local-evidence-compliance.md`，blob `2e0d82245410918b17d64edc5171a0441ad51f37`。

这是一项 chat relay 账本一致性修复，不涉及生产服务、provider、网关、Stage C 或 B1 生产激活；不要借此扩大任何生产权限。完成后回传实现文件哈希、测试结果、三条 backfill 的逐条判定与最终 STATUS 证据。
