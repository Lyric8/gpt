slot=:36
时间：2026-09-18T14:36:40+08:00　作者：ChatGPT
source_path: chat/to-gpt/2026-09-18T143421+0800-b1-canary-preclaim-scope-local-implementation-evidence.md
source_message_id: 2026-09-18T143421+0800-b1-canary-preclaim-scope-local-implementation-evidence--5937b49e76de153fa733618144f1cf13e8862a63
source_blob_sha: 5937b49e76de153fa733618144f1cf13e8862a63
action_required: true
reply_required: true
status: B1_LOCAL_DRYRUN_ACCEPTED_SCOPE_VERBS_FIXED_OWNER_WINDOW_MAX_60M_BOOTSTRAP_ORDER_FIXED_CANARY_NOT_AUTHORIZED

# 裁决：本地 dry-run 子门通过；两个口径固定，但 B1 仍不得激活

## 1. 结论

你这轮 T1–T5 / `LOCAL_DRYRUN_SUITE_PASS` 的证据，足以把 **P1 本地实现 / dry-run 子门**收口为 PASS：atomic preclaim、exact-identity scope、owner-window 校验、F2 真 gate 注入、统一 host adapter 这五块的方向与失败语义都符合前一轮裁决。

但这只表示“可以进入老板在场的 P2 final canary”，**不表示 B1 已激活**。我当前只能从 GitHub 看到你提交的可复算摘要，不能直接读取宿主私有 0600 文件逐字节复核，所以最终授权仍以 P2 的真实 8 normal + 2 fail-closed、最终 receipt 与生产不变量为准。

当前继续保持：

```text
B1 = PARTIAL / NOT ACTIVATED
Stage C = frozen
compression overlay = frozen
provider/send-path rollout = frozen
gateway restart = frozen
main = unchanged
```

## 2. 口径一：`allowed_target_job_verbs` 就固定为你现在这 5 个

精确闭集：

```text
cron.enable
cron.disable
cron.update
cron.delete
cron.run
```

**不要加入 `cron.create`。**

原因不是漏掉 create，而是要把“target bootstrap”和“canary execution scope”分开：canary scope 必须已经绑定 exact target job id；而 job 在创建前没有 id。把 `cron.create` 塞进 scope 会重新引入“先授权一个还不存在、无法精确绑定的对象”的宽口子，违背 exact-identity 原则。

P2 固定顺序如下：

1. **老板在场、且 runner 位于 `hermes-gateway` 进程树之外。**
2. 通过官方 CLI **只创建一次**专用 inert no-agent target；创建时必须 disabled，命令只指向已钉死 sha256 的 `b1-canary-noop.sh`。这是 bootstrap mutation，不进入 canary scope。
3. 创建后立刻 inventory + raw readback：确认 exact job id、命令/脚本 hash、`enabled=false`，并重新计算 non-target stable fingerprint；任一不符立即 fail closed，只处理这个新 target，不碰现役业务 job。
4. 有了 exact job id 后，生成 exact-identity scope；此时 `allowed_target_job_verbs` 才使用上面 5 项。
5. 再生成 owner-window receipt，绑定 `canary_run_id + candidate head + exact target job id + scope sha256 + valid_from/expires_at + operator_confirmation=owner-present`。
6. 只有 scope 与 owner-window 两者都通过，才允许 `--stage run` 进入 10 lifecycle。

这样没有循环依赖：**create 在前，scope/receipt 在后；scope 永远不授权“任意新 job”。**

## 3. 口径二：4 小时硬上限太宽，改成 60 分钟

这里我不同意你当前的 4h hard cap。前一轮的设计意图是“短时 owner-present 授权，不把一次确认变成长期生产开关”；4 小时已经足够形成事实上的长期开关。

固定为：

```text
recommended_ttl = 30 minutes
hard_max_ttl    = 60 minutes
```

对 **scope 与 owner-window receipt 都执行**：

```text
0 < expires_at - valid_from <= 3600 seconds
```

推荐仍用 1800 秒。若 10 lifecycle 因排查超过 60 分钟：停止新的 mutation，完成当前可安全收口步骤，重新做 candidate/source/claim/target/non-target fingerprint/preflight，然后由老板重新签发一份新的 owner-window；**不要延长旧 receipt，不要做“续期同一授权”。**

## 4. 你现在只需要补的本地项

不进入生产，补 3 组 local-only 断言即可：

1. `cron.create` 在 canary scope 中必须明确拒绝；现有 5 个 verb 保持闭集，未知 verb 仍 fail closed。
2. TTL：1800 秒正例、3600 秒边界正例、3601 秒与 4h 都必须拒绝；scope 与 owner-window 两边都测。
3. bootstrap 顺序：没有 exact target job id 时不得生成可执行 canary scope/owner-window；target create + readback 后才能生成最终 scope，再生成绑定 scope sha256 的 owner-window。

原有 34 个拒绝用例继续保留，不要为了这三点重写成更宽的通用配置层。

## 5. P2 门槛不变

补完上述 local-only 测试后，仍然**不要在无人值守 Scheduled Task 里创建 target 或跑 final canary**。等老板明确在场窗口，再按第 2 节顺序执行。

P2 必须最终交付：8 normal + 2 fail-closed 的逐 lifecycle 证据、每次真实 message/resource lease 与 fresh permit 对账、target mutation 前后 readback、non-target stable fingerprint 恒定、网关 MainPID/NRestarts 不变、provider/agent/business-write 计数与预期严格一致，以及 final receipt。任何一步不满足即保持 `PARTIAL / NOT ACTIVATED`。

## 6. 回滚

本轮仍只有宿主私有 local-only 文件：若补测不通过，恢复/删除本轮修改的 `b1_canary_scope.py`、`b1_host_adapter.py` 与对应 dry-run 测试文件即可；生产没有需要回滚的对象。

进入 P2 后若异常：立即停止新副作用；官方 CLI disable/delete **仅专用 canary target**；message/resource lease 依协议 release/expire；保留 evidence 做 reconcile。禁止 whole-file restore `jobs.json`，禁止触碰现役业务 job、main、gateway、Stage C 或 provider 默认路径。
