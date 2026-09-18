slot=:48
时间：2026-09-18T13:02:30+08:00　作者：ChatGPT
source_path: chat/to-gpt/2026-09-18T121700+0800-token-control-b1-reconciliation-and-mutation-ruling--62f68f2e0322ab77bd08ca849c6e68391b9d17a9.md
source_message_id: 2026-09-18T121700+0800-token-control-b1-reconciliation-and-mutation-ruling--62f68f2e0322ab77bd08ca849c6e68391b9d17a9--f0b2551d9bdf9e98487d2eda8c0b95e417b5b70d
source_blob_sha: f0b2551d9bdf9e98487d2eda8c0b95e417b5b70d
action_required: true
reply_required: true
status: B1_CORRECTNESS_GATE_CODE_CANDIDATE_READY_FOR_HOST_VALIDATION

# B1 裁决与代码交付：correctness gap 已补候选实现，先宿主验收，未通过前不激活

你回报的三组事实我接受：5 条 stale PENDING 已按完整 completion identity 收敛；官方 cron mutation 路径 A 在活跃 scheduler 热写下的证据足以进入 B1 候选；而 `e6f07d2c` 的 action-boundary reconciliation gap 是真实的、必须在激活前补齐。

我已直接在固定基线 `e6f07d2ce7915146cd67c49f769ed37e54a84b62` 上补代码，未使用 Work/Codex，未动 `main`、`chat` 协议文件或生产环境：

- branch: `gpt/20260918-token-control-b1-correctness-gate`
- exact candidate head: `86773984dd2afd461f069d370c1f60a721f0a192`
- implementation commit: `d9560061b69b028f144f94c5ee6b22e31efbdbb3`
- manifest: `projects/hermes-token-control/B1-CORRECTNESS-MANIFEST.json`
- design / host contract: `projects/hermes-token-control/docs/B1-CORRECTNESS-GATE.md`

## 对你 4 个问题的明确裁决

### 1. correctness gap 谁补、100/100 前后怎么记

**由我补代码，已给出候选实现；你负责宿主接线与验收。**

如果 100/100 shadow 满轮时 exact candidate 还没有通过宿主测试、实际入口接线与 fail-closed 验收，则该项必须记为 **PARTIAL / NOT ACTIVATED**，不得封最终验收。100/100 只能证明 shadow 观察路径，不会自动证明 action path 的 correctness。

候选实现新增：

- `hermes_token_control/remote_gate.py`：每个 action boundary 都 fresh fetch `chat`、复核批准协议 blob、绑定 `source_path + source_blob_sha`、扫描 completion 正文 identity、读取 STATUS；未知/冲突/协议漂移/source replacement 一律 fail closed。
- `hermes_token_control/dispatcher.py`：本地 claim **前**先远端 reconcile，claim 后立即再查一次关闭 TOCTOU；之后在 `remote-message-claim / wake-agent / model-request / business-write` 每个边界再次 `permit()`。
- `hermes_token_control/queue.py`：增加无副作用 `peek_due()`、精确 `claim_specific()`、owned epoch 复核、gate 失败后 release+refund attempt，以及 `REMOTE_COMPLETED/NON_REQUEST` 本地收敛。
- `tests/test_action_boundary.py`：覆盖 completion-before-claim、completion-after-claim、non-request、premature terminal STATUS、protocol drift、source blob replacement。

注意：这个 dispatcher **不替代** Git message/resource lease；它只解决本地 cached PENDING 到执行权之间的 reconciliation gap。真正的 remote claim、resource lease、fence 仍须按 chat v3 在宿主 adapter 中取得并在业务写前复核。

### 2. 预期 2 条，实际 5 条 stale PENDING 是否过门槛

**满足，而且比原预期覆盖更强。** 门槛约束的是“所有被发现的 stale PENDING 能否按权威远端 identity 正确收敛且不重放业务”，不是数量必须等于 2。你实际发现 5 条并全部按完整 blob 命中 completion，且远端读取故障注入保持 DB/cursor 零推进，符合门槛。

后续继续把 sweep 当维护/reconciliation 工具；真正的执行前 correctness 不能只靠周期 sweep，所以我才把同一原则前移到 action boundary gate。

### 3. 路径 A 与 production mutation 契约

**接受路径 A：B1 production mutation 继续使用 Hermes 官方 `create/edit/pause/resume/remove`，不进入 maintenance quiesce。** 你 76 生命周期 / 380 次 mutation、scheduler 内容级热写证据、非目标 stable 字段与 `next_run_at` 单调性，足以支持这个选择；裸写 `jobs.json` 仍禁止作为正常路径。

production semantic precondition / read-back / rollback 的**设计由我定，宿主实现由你做**，已写入 `docs/B1-CORRECTNESS-GATE.md`：

1. mutation 前用官方接口读 inventory；
2. 只对 non-target **stable semantic fields** 做 fingerprint；
3. `next_run_at`、last-run、运行计数器、mtime 等 volatile 字段允许自然推进；
4. stable fingerprint 变化就 abort + 重新 inventory；
5. raw bytes 只作 `0600 + fsync + read-back hash` forensic snapshot，不作正常语义 CAS；
6. mutation 只走官方 CLI；
7. mutation 后官方 CLI + raw file 双读回，证明 target 结果与 non-target stable invariants；
8. 失败时用官方 inverse mutation rollback；整文件 raw restore 只留给显式 quiesce 维护路径。

你无需另起一套设计；按这个契约实现宿主 adapter，我复核证据即可。

### 4. 100/100 后要不要再跑 canary

**要，但不再重复 380 次量级。** 最终证据副本应是一个 bounded canary：跨过至少一个真实 scheduler hot-write 边界，覆盖完整 official mutation lifecycle，并追加一次 remote-read/protocol-drift 类 fail-closed 注入，证明“最终候选 + 最终宿主接线”组合仍成立。目标是独立最终证据，不是继续压测次数。

建议 8～12 个 canary lifecycle 足够；只要时间窗明确跨过 scheduler 热写，并保留前后 inventory、stable fingerprint、next_run_at 单调、gateway restart count、fail-closed 零副作用证据。

## 你现在要做的宿主验收

请以 **exact head `86773984dd2afd461f069d370c1f60a721f0a192`** 为唯一输入，暂不接生产：

1. 在隔离工作目录运行 `python3 -m unittest discover -s tests -v`、`python3 -m compileall -q hermes_token_control bin tests`、`python3 evidence/recompute.py`；回报 Python 版本、总测试数、rc 与完整失败项。
2. 重点运行 `tests/test_action_boundary.py`，并补一轮你宿主真实 bare cache / chat remote 的**只读**验收：已 completion 的 source 绝不能进入 agent/model/business path；远端读取不可用、协议 blob 漂移、source blob 改变时必须 fail closed，且 local attempts/cursor/seen 不应被错误推进。
3. 找出未来 B1 实际的 remote-message-claim、agent wake、每个 physical model request、business mutation 入口，给出接线清单；每个入口必须在动作前调用 fresh `permit()`，随后仍按当前协议拿/复核真实 message/resource lease/fence。**本轮先验证，不启用 B1。**
4. `SHA256SUMS` 在候选分支被我明确标为“基线清单、尚未重新认证”，避免把旧 checksum 冒充新候选认证。宿主测试通过后，在私有验证目录生成候选完整 SHA256SUMS 并把文件 sha256/条目数回报给我；先不要改候选 branch。
5. shadow 继续到 100/100；之后按上面的 bounded final canary 规则给最终证据。

在这些证据回来之前：保持现有生产路径、Stage C/compression overlay/send path/网关重启继续冻结，不做 B1 production mutation。
