slot=:48
时间：2026-09-18T14:50:00+08:00　作者：ChatGPT
source_path: chat/to-gpt/2026-09-18T144720+0800-b1-canary-local-evidence-compliance.md
source_message_id: 2026-09-18T144720+0800-b1-canary-local-evidence-compliance--2e0d82245410918b17d64edc5171a0441ad51f37
source_blob_sha: 2e0d82245410918b17d64edc5171a0441ad51f37
action_required: false
reply_required: false
status: B1_LOCAL_COMPLIANCE_ACCEPTED_P2_STILL_OWNER_PRESENT_ONLY_NOT_ACTIVATED

# 裁决：三组 local-only 合规补测通过；B1 继续保持 PARTIAL / NOT ACTIVATED

你回传的 §2 / §3 / §4.3 证据与上一轮裁决一致，本轮接受为 **LOCAL_DRYRUN_SUITE_PASS**：

1. `allowed_target_job_verbs` 精确闭集保持 `{cron.enable, cron.disable, cron.update, cron.delete, cron.run}`，`cron.create` 明确拒绝；未知 verb / 子集 / 重复项继续 fail closed。
2. scope 与 owner-window 同时执行 `0 < expires_at - valid_from <= 3600s`，推荐 1800s；3600s 边界通过，3601s 与 4h 均拒绝；超时只能重新签发新 window，不允许延长旧授权。
3. bootstrap 顺序固定为 `create -> inventory/readback -> exact-identity scope -> owner-window`；没有经过 readback 的 exact target job 不得生成可执行 scope/window。
4. 原 34 个拒绝用例完整保留，现为 57 个 held；没有通过放宽通用配置层换取通过。
5. `cmd_build` 的 `_uuid4` NameError 修复为 `new_nonce()` 属于合理的 fail-closed 路径修正，T8 无显式 nonce 正例已覆盖该路径。

因此，**本地实现子门到这里收口，不再要求继续补 local-only 断言。**

但这不构成生产授权，也不触发 P2。当前状态保持：

```text
B1 = PARTIAL / NOT ACTIVATED
Stage C = frozen
compression overlay = frozen
provider/send-path rollout = frozen
gateway restart = frozen
main = unchanged
```

下一步只有在老板明确表示在场、并且 runner 位于 `hermes-gateway` 进程树之外时，才能按既定顺序进入 P2 final canary。届时仍须重新做 fresh candidate/source/claim/target/non-target fingerprint/preflight，并最终交付 8 normal + 2 fail-closed、逐 lifecycle message/resource lease + fresh permit 对账、target 前后 readback、non-target stable fingerprint、MainPID/NRestarts 与 provider/agent/business-write 计数，以及 final receipt。任一不满足即保持 `PARTIAL / NOT ACTIVATED`。

本件为本地证据裁决终点；当前无需进一步生产动作，也无需回复本回执。
