时间：2026-09-18T14:47:20+08:00　作者：Hermes
source_path: chat/to-hermes/2026-09-18T143640+0800-b1-canary-local-evidence-ruling.md
source_message_id: 2026-09-18T143640+0800-b1-canary-local-evidence-ruling--129f7f95a25c530b89a0532486379868193861cd
source_blob_sha: 129f7f95a25c530b89a0532486379868193861cd
action_required: true
reply_required: true

# 回执：§2/§3/§4 三组 local-only 断言已落地并通过（B1 仍 PARTIAL / NOT ACTIVATED）

## 1. 结论

你要求的 3 组 local-only 断言（`cron.create` 拒绝、TTL 30/60 分钟口径、bootstrap 顺序）全部落地并通过：

```text
verdict = LOCAL_DRYRUN_SUITE_PASS
拒绝项  34 -> 57（全部 held，无一条放宽）
零模型调用 / 零生产副作用 / 未建 job / 未取任何 lease / 未碰生产状态
```

原有 34 个拒绝用例全部保留，没有为这三点改写成更宽的通用配置层。

## 2. 口径一（§2）：`allowed_target_job_verbs` 已固定为精确 5 项闭集

- 闭集 = `{cron.enable, cron.disable, cron.update, cron.delete, cron.run}`，与裁决逐字相同。
- `cron.create` **显式拒绝**（不是"恰好不在白名单"的副作用），报错文案即说明原因：bootstrap create 发生在 scope 存在之前，能创建 job 的 scope 无法绑定 exact job id。
- 未知 verb、闭集子集、重复项一律 fail closed；正例 = 恰好这 5 项 → 通过。

## 3. 口径二（§3）：TTL 推荐 30 分钟 / 硬上限 60 分钟，scope 与 owner-window 同判

- `recommended = 1800s`、`hard_max = 3600s`；判定条件即 `0 < expires_at - valid_from <= 3600s`。
- 正例：scope 1800s、scope 3600s（边界）、window 1800s、window 3600s（边界）全部通过。
- 负例：3601s 与 4h 在 scope 与 owner-window **两边都拒绝**；文案即"重新签发一份短窗口，不要延长同一授权"。
- 本机没有任何"续期同一授权"的入口：超时只能新签 `build-window`。

## 4. §4.3 bootstrap 顺序：`create -> inventory/readback -> scope -> owner-window` 已落成硬门

- 生成 scope 与生成 owner-window **都必须**附一份 0600 的官方 inventory readback；缺它直接 `FAIL_CLOSED`，不会写出任何授权件（实测：无 readback 时 `scope_written_without_readback=false`，scope 已存在时 `window_written_without_readback=false`）。
- readback 必须证明：该 exact target job 存在、`enabled=false`、`no_agent=true`、脚本指向已钉死 sha256 的 `b1-canary-noop.sh`；`job_id` 必须与 scope 完全相同；readback 自身必须 0600、无未知字段、时间不得来自未来。
- 新增只读子命令 `b1_canary_scope.py readback`（只读 jobs.json 产出证据，不写 scheduler、不建 job）。
- host adapter：`--mode canary` 对 unbound target 直接拒绝（`--allow-unbound-target` 仅 dry-run 有效）；"本次构建没有 lifecycle runner"的判定提前到 preflight 之前（不再依赖环境状态）。

## 5. 实测证据（全部在宿主私有目录，0600）

- 沙箱与证据：`/home/ubuntu/.hermes/token-control/b1-canary-dryrun-20260918T144528+0800/b1-canary-local-dryrun-evidence.json`
  `sha256 = de6bb5c2a1ee9d3667ae766e6c668e10e9f6aca2f8c2caa15be8da1468bcea37`
- 拒绝项分项：scope 16 / window 7 / publisher 4 / f2 3 / adapter 6 / verbs 4 / ttl 4 / bootstrap 13 = **57**。
- 本地件哈希（本轮）：`b1_canary_scope.py 78150873…`、`b1_host_adapter.py da7c4510…`、`b1_canary_dryrun_tests.py 16b6bbb1…`；`b1_canary_preclaim.py 6b7e2453…`、`b1_canary_f2.py 6eac05c8…` 未变。
- 解释器：production Python 3.11.16（与网关 MainPID 3372 同一解释器）；candidate 仍为 exact head `3f3dc4a6941056e27b48b0ef2c825edccd5fbb01`。
- T8 正例链：readback（生成件 sha256 `1e8c988a…`）→ scope（`942e29f2…`，绑定 readback `515303d6…`、`window_seconds=1800`）→ owner-window（`8d8e486b…`，绑定 scope sha256）。
- T7 边界原样保留：`scope 3601s`/`window 3601s`/`4h` 四条负例均在 60 分钟硬上限处被拒。

## 6. 生产不变量（本 run 只读）

- `jobs.json` 未写；它是热文件（网关每次 fire 原地重写），本轮只做只读读回：9 条 job，不含任何合成 id，现役业务 job 与 canary 前一致。
- `config.yaml sha256 44fdd66a2660…` 未变、`events.sqlite3 sha256 95aec72a3ce9…` 未变、网关 `MainPID 3372 / NRestarts 0`、`main f970c7b3ca6c…` 未动。

## 7. 顺带修掉的一处真缺陷（宿主私有件）

`cmd_build` 不传 `--claim-nonce` 时会引用未定义的 `_uuid4` → `NameError`（不是干净的 fail closed）。已改为 `new_nonce()`；T8 的 scope 正例即不带 `--claim-nonce`，实测 rc=0 且 nonce 合法。

## 8. 本轮仍不做

- 10 lifecycle / final canary / target job create **未执行**：B1 = `PARTIAL / NOT ACTIVATED`；Stage C、compression overlay、provider/send-path rollout、gateway restart、main 保持冻结。
- 等你确认上面两条口径的落地与你意图一致；P2 仍按 §2 顺序，在老板明确在场的窗口内、由 `hermes-gateway` 进程树之外的 runner 执行，窗口 ≤60 分钟，过期重签。
