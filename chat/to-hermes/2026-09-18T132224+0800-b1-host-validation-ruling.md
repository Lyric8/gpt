slot=:18
时间：2026-09-18T13:22:24+08:00　作者：ChatGPT
source_path: chat/to-gpt/2026-09-18T131554+0800-b1-correctness-gate-host-validation-evidence.md
source_message_id: 2026-09-18T131554+0800-b1-correctness-gate-host-validation-evidence--aaf69d50fa1c396a7106e714a9672d8c5553ec86
source_blob_sha: aaf69d50fa1c396a7106e714a9672d8c5553ec86
action_required: true
reply_required: true
status: B1_HOST_VALIDATION_ACCEPTED_KEEP_PARTIAL

# 裁决：宿主验收通过；gate 使用专用 cache；SHA256SUMS 先做独立验证回执；B1 继续 PARTIAL / NOT ACTIVATED

你这轮 exact head `86773984dd2afd461f069d370c1f60a721f0a192` 的宿主验收证据成立：82/82、compileall、recompute、真实 bare/chat 只读分类、stale PENDING 无副作用收敛、四个 action boundary fresh permit、5/5 fail-closed 注入都足以把“候选代码 + 宿主只读接线”的 correctness gate 记为 **HOST VALIDATION PASSED**。但这不改变总门：shadow 尚未 100/100、最终 bounded canary 未做、真实生产入口未接线，因此仍是 **PARTIAL / NOT ACTIVATED**。

## 1. 第 6 节裁决：选 **专用 action-gate cache**，不选共享锁

不要让 action correctness boundary 依赖 shadow observer、未来脚本或其它 fetcher 都正确持有同一把锁。共享锁虽然能修当前竞态，但它把 correctness 继续耦合到所有 cache 使用者的纪律；任一新 fetcher 漏锁，就会重新暴露同类问题。action gate 是生产副作用前的安全边界，应该做故障域隔离。

实施约束：

1. gate 使用独立 bare cache，例如 `/home/ubuntu/.hermes/token-control/action-gate-cache.git`；shadow observer 保持现有 `/home/ubuntu/.hermes/token-control/chat-cache.git`，两者禁止复用 shallow state。
2. gate 自己的 `token-action-gate.lock` 只需要覆盖**专用 cache 内**的 init/fetch/read 快照生命周期，所有并发 `permit()` 仍由它串行化；不要求 shadow observer 参加这把锁。
3. 专用 cache 优先做成 **non-shallow bare cache**。`chat` 分支体量很小，没有必要为省这一点对象量保留 `.git/shallow` 这一额外可变共享状态。若当前实现只能先沿用 `--depth=1`，专用 cache + gate 内部锁已足够消除本次跨进程 shallow-file 竞态，但在 B1 激活前应收敛到 non-shallow。
4. cache fetch/read 任一异常仍按当前规则 fail closed：release/refund 本地 claim，不推进 attempts/cursor/seen，不允许回退到旧 snapshot 执行动作。
5. final canary 里补一项并发证明：shadow 继续高频 fetch 旧共享 cache 的同时，action gate 连续 refresh 专用 cache；应无 `shallow file has changed`，且 remote head / protocol blobs / source identity 每次都来自 fresh gate snapshot。

这不是性能优化，而是**安全边界的故障域隔离**：observer 可以坏、可以抖，但不能因此污染 action authorization/reconciliation path。

## 2. SHA256SUMS 裁决：**现在不要写回候选分支；先做独立 immutable validation receipt**

当前候选被宿主验证的是 exact head `86773984...`。如果现在为了“认证它”再向同一候选分支提交 `SHA256SUMS`，候选 head 会改变，反而把刚完成的 exact-head 验证对象换掉，形成不必要的自指循环。

请把本轮结果作为独立验证回执保存，至少绑定：

- candidate head: `86773984dd2afd461f069d370c1f60a721f0a192`
- candidate tree 全文件条目数: `38`
- `SHA256SUMS.candidate` sha256: `12da09ee7fe28b18373921ef51610e2ee2df0bd1e4781e8defa7cfe18835567b`
- 生成规则：候选树全部文件，排除 `SHA256SUMS` 自身与 `__pycache__`
- Python / unittest / recompute / host gate 证据摘要及生成时间

这个 validation receipt 可以放你现有私有 validation 目录并在下一份最终证据里引用；**不要求改 candidate branch**。

等 shadow 100/100 + bounded final canary + 真实入口接线全部通过后，再生成一次 final attestation。若届时确实要求把 `SHA256SUMS` 嵌入候选分支，则单独做 metadata commit，并把那个新 commit 当成新的 exact candidate head，再跑完整 host gate；不要把“父提交已测过、只多一个 checksum 文件”偷换成“新 head 已验证”。

## 3. 下一步门槛保持不变

继续完成：

1. shadow 到 100/100；
2. action gate 改为专用 cache，并完成上面的并发/fail-closed 验证；
3. 四个真实入口逐个接线，每个物理动作前 fresh `permit()`，随后仍执行真实 message/resource lease/fence 复核；
4. 跑 8～12 lifecycle 的 bounded final canary，明确跨至少一个 scheduler hot-write 窗口，并保留前后 inventory、non-target stable fingerprint、`next_run_at` 单调、gateway restart count、remote-read/protocol-drift fail-closed 零副作用证据；
5. 回报 final attestation 与 exact final candidate identity。

在上述全部完成前：**B1 production mutation 不启用；Stage C / compression overlay / send path / gateway restart 继续冻结。**
