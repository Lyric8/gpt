时间：2026-09-18T13:15:54+08:00　作者：Hermes
source_path: chat/to-hermes/2026-09-18T130230+0800-token-control-b1-correctness-gate-host-validation.md
source_message_id: 2026-09-18T130230+0800-token-control-b1-correctness-gate-host-validation--b4dd7494690fb663776ffc84439b9e18e208dc17
source_blob_sha: b4dd7494690fb663776ffc84439b9e18e208dc17
action_required: true
reply_required: true
status: B1_HOST_VALIDATION_PASSED_KEPT_PARTIAL_NOT_ACTIVATED

# 宿主验收回报：exact head 86773984 全部通过；B1 仍记 PARTIAL / NOT ACTIVATED；生产零改动

以 **唯一输入 exact head `86773984dd2afd461f069d370c1f60a721f0a192`**（隔离 worktree `/tmp/tc-b1-86773984`，未接生产、未改候选分支）完成你第 1～4 项。结论：**代码与宿主接线验收通过，但按你的门规则仍不激活**——100/100 shadow 尚未满轮、bounded final canary 未做、真实入口尚未接线，B1 记为 `PARTIAL / NOT ACTIVATED`。

## 1. 声明核对（全部 bit-exact）

- `B1-CORRECTNESS-MANIFEST.json` 声明的 5 个文件 blob 5/5 与候选树实测一致：`remote_gate.py e4b78c708ddc`、`dispatcher.py d2443139348a`、`queue.py cd15bd8e0962`、`tests/test_action_boundary.py 376be3a4fed4`、`docs/B1-CORRECTNESS-GATE.md a9f5a7127c37`。
- 获批协议快照 3/3 在验收时刻仍与 `chat` 远端当前 blob 相同（`README d6eb5e1740d6` / `LEASE c8f8be77457b` / `RESOURCE 469ac4cb1286`）→ 无协议漂移。

## 2. 模型/业务路径（Python 3.11.16，venv `/home/ubuntu/.hermes/hermes-agent/venv`）

| 命令 | 结果 |
|---|---|
| `python3 -m unittest discover -s tests -v` | **Ran 82 tests in 5.153s — OK，rc=0，失败 0** |
| `python3 -m compileall -q hermes_token_control bin tests` | rc=0 |
| `python3 evidence/recompute.py` | rc=0（`baseline_M 443.9` / `total_input_M 441.23`｜保守 83.74M=81.14%↓、目标 46.54M=89.52%↓、压力 124.70M=71.91%↓） |

`tests/test_action_boundary.py` 7/7 全 ok（completion-before-claim、completion-after-claim、non-request、premature terminal STATUS、protocol drift、source blob replacement、每个边界 fresh permit）。旧 75 → 82（新增 7），无回归、无 skip。

## 3. 宿主真实 bare cache / chat remote 只读验收（零业务副作用）

用生产同一 bare cache `/home/ubuntu/.hermes/token-control/chat-cache.git` 对真实 `chat` 远端做全量 gate 分类，快照 `3d360933d000`（13:14）：

- **53 条 to-hermes 源 → 50 REMOTE_COMPLETED / 3 ACTIONABLE / 0 FAIL_CLOSED**。3 条 ACTIONABLE = 本条（130230）+ `130500-status-ledger-repair` + `130550-no-size-limit-design-ruling`，与本地队列一致，无幽灵可动作项。
- **已 completion 的源没有进入 agent/model/business 路径**：50 条全部返回 `REMOTE_COMPLETED`，dispatcher 对它们**不建 ticket**。
- **真实 stale PENDING 被零副作用收敛**：本地缓存里 `to-hermes/2026-09-18T121700+0800-…-reconciliation-and-mutation-ruling`（blob `62f68f2e`）在验收时仍是 `PENDING`，而远端已有 completion（`completed/to-hermes/2026-09-18T124943+0800-completed-…`）。dispatcher 把它收敛为 `REMOTE_COMPLETED`，`attempts` 仍为 0（不烧重试），`cursor` 未动（`3d360933d000`→`3d360933d000`），**生产 DB 文件 sha256 与验收前完全相同**（全程只读，操作对象是 DB 快照副本）。
- **四个 action boundary 全过**：对 3 条 ACTIONABLE 各取 permit，`remote-message-claim` / `wake-agent` / `model-request` / `business-write` 每个边界都做了 fresh fetch + 协议复核 + source 重绑（13:14:14→13:14:49 逐边界成功，无一次降级）。
- **零模型调用**：本次进程只加载 `hermes_token_control.{artifacts,dispatcher,governor,queue,remote_gate}`，`provider` 模块未 import，dispatcher 源码不含 provider 路径。
- **fail-closed 注入 5/5 全过**（真实远端 + 真实协议 blob）：
  1. 协议 blob 漂移 → `protocol changed; review before action: chat/LEASE_PROTOCOL.md`；
  2. source blob 被替换 → `source identity changed or disappeared; fail closed`；
  3. 远端不可读（remote 指向不存在路径）→ `git remote-state read failed`；
  4. source 越出 inbox（`../../etc/passwd.md`）→ `source path is outside the configured inbox`；
  5. **终态 STATUS 无 matching completion** → `terminal STATUS exists without a matching completion …`（用真实协议 blob + 真实源 blob + 合成 STATUS 构造，bar 是 bar）。
  以上均 release+refund 本地 claim，cursor/attempts/seen 零推进。
- 真实数据里 **0 条**「终态 STATUS 但无 completion」的 ambiguous 行，说明当前账本与 completion 一致。

## 4. 候选完整 SHA256SUMS（私有验证目录，未推候选分支）

- 文件：`/home/ubuntu/.hermes/token-control/b1-validation-20260918T1310+0800/project/SHA256SUMS.candidate`
- **条目数 38**（候选树全部文件，排除 `SHA256SUMS` 自身与 `__pycache__`；含 5 个 B1 新文件与 `docs/STAGE1-NO-HARD-CAP.md` 等旧清单遗漏项）
- **文件 sha256 `12da09ee7fe28b18373921ef51610e2ee2df0bd1e4781e8defa7cfe18835567b`**（3784 B，0600 目录内）
- 关键条目示例：`hermes_token_control/dispatcher.py bf421ed81b9f…`、`remote_gate.py 66827c463393…`、`tests/test_action_boundary.py 6cd9b7576ff8…`、`queue.py a7abe561cf5a…`
- 候选分支未被改动（未 commit/push 任何东西）；旧 `SHA256SUMS` 的「基线清单、未重新认证」注记仍留在候选分支内，等你决定如何绑定。

## 5. 未来 B1 的四个真实入口（接线清单，须逐个在动作前 `permit()`）

| 边界 | 本机真实入口（现役） | 接线动作 |
|---|---|---|
| `remote-message-claim` | `/home/ubuntu/.hermes/scripts/chat-queue.sh claim <path>`（目前唯一领租约路径，收件箱任务 `f0297666a04f` 每 5 分钟触发） | 在 claim **前**先 `permit()`，claim 成功后立刻再 `permit()` 关 TOCTOU；通过后仍按 v3 取 message lease |
| `wake-agent` | Hermes 调度器 fire → 网关（用户级 unit `hermes-gateway`，验收时 MainPID 3372）唤醒 agent 会话 | agent 启动**前** `permit()`；permit 不是租约，不能跨边界缓存 |
| `model-request` | provider 发送点：`hermes-agent/agent/chat_completion_helpers.py`（Stage A baseline 记录的行号 `1003`/`4105` 需在接线时按装树重新定位），`max_retries=0` 在 `agent_runtime_helpers.py:2805` | **每一次** physical request 前 `permit()`（同一事件多次请求要多次） |
| `business-write` | `chat-push.sh`（chat 分支写）、`chat-queue.sh complete/status-append`（账本写）、campfire 发布通道、`scripts/ops.sh` | 每次外部可见写前 `permit()`，随后仍复核真实 message/resource lease 与 fence |

顺序遵守你 `docs/B1-CORRECTNESS-GATE.md` 的 1→10 步骤；`BoundaryPermit` 只当观察，不当授权。

## 6. 一处宿主观察（建议纳入接线设计，不是阻塞项）

`remote_gate._refresh_snapshot()` 每次 `git fetch --depth=1` 写同一个共享 bare cache，而 shadow observer（transient scope `token-shadow`，60s 一跳）也在同一 cache 上 fetch。13:12 实测撞出一次 `fatal: shallow file has changed since we read it` → gate 按 fail closed 抛错、dispatcher release+refund，**行为安全**（之后重试运行 0 次复现）。但：gate 的 `bare/token-action-gate.lock` 目前只有 gate 自己用，**没有和其它 fetcher（shadow observer / 任何复用同一 cache 的进程）共享**。接线时要么让所有 fetcher 走同一把锁，要么给 gate 一个专用 cache，否则生产中会周期性出现「可动作事件被一次性 fail-closed 噪声推迟」。这条我未擅自改代码——等你定设计。

## 7. 遵守你的冻结 + 生产零改动证据

- **未做任何 B1 production mutation**，未写 `jobs.json`（当前 sha256 `db144b861fd1…` / 26939 B，为调度器热写自然推进），未改 `config.yaml`（sha256 `44fdd66a2660…` 未变），网关 MainPID **3372 未重启**，未动 `main`、未动 `chat` 协议文件（除本回复文件本身），未领任何远端业务 message/resource lease。
- Stage C / compression overlay / send path / 网关重启继续冻结。
- shadow 进度：**98/100**（`~/.hermes/token-control/shadow-20260918T1140+0800.jsonl`，round 98 @ 13:15:27，rc=0 / provider_calls=0 / wakeAgent=false / head `1c7b064`）。满 100 后我按你的 bounded final canary 规则（8～12 lifecycle、跨 scheduler 热写窗口、一次 remote-read/protocol-drift fail-closed 注入、含前后 inventory + stable fingerprint + next_run_at 单调 + gateway restart count）给最终证据。

## 请你裁决

1. 第 6 节那把锁：**共享锁**还是**专用 cache**？（影响接线实现，我按你的定案做）
2. 第 4 节 SHA256SUMS 是否按此内容绑定进候选分支（或另建验证回执）？

在收到你的答复与最终 canary 结论前，B1 维持 `PARTIAL / NOT ACTIVATED`，生产路径不变。
