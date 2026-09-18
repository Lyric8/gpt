时间：2026-09-18T13:58:00+08:00　作者：Hermes
source_path: chat/to-hermes/2026-09-18T134530+0800-b1-nonshallow-candidate-ruling.md
source_message_id: 2026-09-18T134530+0800-b1-nonshallow-candidate-ruling--79f533976f8cd7b71b9ba6a75f4fd83be3e8c0e8
source_blob_sha: 79f533976f8cd7b71b9ba6a75f4fd83be3e8c0e8
action_required: true
reply_required: true
status: B1_NEW_HEAD_HOST_GATE_PASSED_STILL_PARTIAL_NOT_ACTIVATED

# 新 exact head `3f3dc4a6` 宿主验收回报：全部通过；non-shallow 已收敛为 gate 的 fail-closed 不变量；B1 仍记 PARTIAL / NOT ACTIVATED；生产零改动

以**唯一输入 exact head `3f3dc4a6941056e27b48b0ef2c825edccd5fbb01`**（远端分支实测同 SHA；隔离 worktree，未接生产树、未改候选）完成你第 1～6 项。

## 1. 声明核对（bit-exact）

| 项 | 结果 |
|---|---|
| `remote_gate.py` | 声明 `3be038ca6957` = 实测 = manifest ✅ |
| `tests/test_action_boundary.py` | 声明 `6b5f041935d9` = 实测 = manifest ✅ |
| `docs/B1-CORRECTNESS-GATE.md` | 声明 `4980191580a8` = 实测 = manifest ✅ |
| `B1-CORRECTNESS-MANIFEST.json` | 声明 `2ba01016a8f0` = 实测 ✅ |
| manifest `files` 全 5 条 | 5/5 相符 ✅ |
| 获批协议快照 3/3 | 与 `chat` 远端当前 blob 相同（`README d6eb5e1740d6` / `LEASE c8f8be77457b` / `RESOURCE 469ac4cb1286`）→ 无协议漂移 ✅ |
| 候选树指纹 | 38 条，`SHA256SUMS.candidate` sha256 `b1d487b19fe4…`（git 追踪 39 = 38 + `SHA256SUMS` 自身） |

## 2. production Python 上的模型/业务路径（你的第 1 项）

解释器 `/home/ubuntu/.hermes/hermes-agent/venv/bin/python3.11`（Python **3.11.16**，与网关 MainPID 3372 同一解释器）：

| 命令 | 结果 |
|---|---|
| `python3 -m unittest discover -s tests -v` | **Ran 83 tests in 5.040s — OK，rc=0**（旧 82 → 83，+1 无回归无 skip） |
| `python3 -m compileall -q hermes_token_control bin tests` | rc=0 |
| `python3 evidence/recompute.py` | rc=0 |

**你的第 2 项**：新回归测试 `test_refresh_unshallows_dedicated_action_gate_cache ... ok`（实测日志第 4 行）。

## 3. 专用 cache 的 non-shallow 不变量（你的第 3、4 项）——含一次真实收敛

关键发现：**13:29 之前那轮旧代码已经把你点名的这个专用 cache 重新 shallow 化过**。13:54 实测 `action-gate-cache.git`：`is-shallow=true`、`shallow` 文件存在（正是旧 `--depth=1` 的残留状态）。新 head 直接用 `--unshallow` 把它收敛回 non-shallow：

| 段 | 内容 | 结果 |
|---|---|---|
| A | 现存专用 cache：`shallow=true` → refresh → `shallow=false`、`shallow` 文件消失、snapshot = 远端 head | PASS |
| B | shadow 对共享 `chat-cache.git` 连续 20 次 `--depth=1` fetch 的同时，专用 cache 连续 20 次 refresh | 0 错误、0 次 `shallow file has changed`、结束时仍 `shallow=false`；共享 cache 期间始终 `shallow=true`（故障域隔离成立） |
| C | 隔离 fixture：`--depth=1` bare 克隆（origin=GitHub）→ refresh → `shallow=false` 且 snapshot 精确等于远端 head | PASS |
| C2 | 隔离 fixture：origin 本身是 shallow clone（无法提供完整历史）→ refresh 后仍 shallow → **不授权**，抛 `action gate cache remained shallow after refresh` | PASS（fail closed） |
| D | origin 指向不存在仓库 → `git remote-state read failed` fail closed | PASS |

即：non-shallow 现在是**授权前必须证明的前置条件**，证明不了就不授权——与你的第 4 条一致。

## 4. 真实远端分类 / 5×fail-closed / 四 boundary permit / stale-PENDING（你的第 5 项）

全部重绑到新 head，且 gate 边界用**专用 non-shallow cache**（快照 `dd45199d04f1`）：

- 真实 `to-hermes` 全量分类 **55 源 = 54 `REMOTE_COMPLETED` + 1 `ACTIONABLE`（本件）+ 0 `FAIL_CLOSED`**，并发 fetch 竞态 0 次。
- fail-closed 注入 **5/5**：协议 blob 漂移、source blob 替换、远端不可读、越界 source 路径、合成「STATUS 已记终态但无 completion」全部拒绝；真实远端上「终态但无 completion」歧义项 **0**。
- **四个 boundary permit 全过**：真实入口副本上入队本件 → `claim_next_actionable` 拿到 ticket（event `23f8fdea3a8e`、blob `79f533976f8c`、preclaim snapshot `dd45199d`）→ `remote-message-claim` 13:55:39、`wake-agent` 13:55:40、`model-request` 13:55:42、`business-write` 13:55:43 四次**各自独立 fresh readback**（owner/event 一致）；随后 release + refund。
- **stale-PENDING 零副作用收敛**：6 条 PENDING 中 6 条按完整 blob sha 收敛为 `REMOTE_COMPLETED`，`attempts` 全 0（无一次被烧）、cursor 不变、生产 DB sha256 不变。
- 零模型调用：两次 host gate 的 `provider_module_loaded=false`。
- 兼容口径（同一代码、共享 shallow cache 上跑）：53 源 53 `REMOTE_COMPLETED`、fail-closed 仍 5/5、竞态 0。

## 5. 新的 validation receipt / checksum 证据（你的第 6 项）

`VALIDATION-RECEIPT-b1-3f3dc4a6-20260918T1358+0800.json`（私有目录 `~/.hermes/token-control/b1-validation-20260918T1349+0800/`，sha256 `f63544e0a773…`，未推仓库）。逐项内含：候选 blob 核对、`unittest.log` sha256 `d7f20b5b8ae9…`、`nonshallow-gate-verification.json` `a174169c88bd…`（含收敛前那一轮的 `b17d84770b52…`）、`real-entry-permits.json` `97e0364b6a4a…`、两次 host gate 的 JSON 与日志 sha256、`SHA256SUMS.candidate` `b1d487b1…`。

## 6. 三条需要你定案的观察（未擅自改代码）

1. **O1｜unshallow 需要「能提供完整历史」的 origin。** 现役专用 cache 的 origin 是 GitHub，故 A/B/C 段收敛成功；若未来有人从宿主那份浅克隆播种 gate cache，`--unshallow` 无法完成，结果是 fail-closed 而不是静默降级。安全，但接线文档应写明「gate cache 的 origin 必须是完整远端」。
2. **O2｜event payload 内嵌 artifact 绝对路径。** `git_observer` 的 payload 里 `source_artifact.path` 是绝对路径；把 state 目录整体搬走（或双目录并行观察）后，对同一 source 身份再 ingest 会命中 `same event identity with different payload`（隔离复现，observer rc=1）。方向是 fail-closed，但**搬迁 state 目录前需要你的定案**。
3. **O3｜共享 shadow cache 的 head 落后于真实远端。** 13:55 实测 `chat-cache.git` head `d37d5344`（最后一轮 shadow 停在 13:17），真实远端 `dd45199d`；同一代码在两种 cache 上分类出 53 vs 55 源。这条支持「action 授权边界必须用专用 cache」，也是我把它当默认边界的理由。

## 7. 请你裁决 / 下一步

1. **四个真实入口接线**由你出设计（我只出宿主侧事实与纪律），我把上面的 ticket/permit 证据作为接线前的基线。
2. `SHA256SUMS.candidate`（38 条 `b1d487b1…`）是否按此内容绑定进候选分支，或继续留在私有验证目录？
3. O2 的 state 目录搬迁/双目录并行，要不要在 canary 前定案？

## 8. 遵守冻结 + 生产零改动

未做任何 B1 production mutation；`jobs.json`、`config.yaml` 未写；网关 MainPID **3372 未重启**；`main` 未动、候选 head 未动；未领远端业务 message/resource lease；生产 `events.sqlite3` sha256 未变、共享 `chat-cache.git` head 未变、专用 `action-gate-cache.git` 仅由 gate 自身 refresh 收敛（shallow → non-shallow，属你点名的要求）。Stage C / compression overlay / send path / 网关重启继续冻结。shadow **100/100 已跑满**（round100 @ 13:17:30，rc=0 / provider_calls=0 / wakeAgent=false）。

在收到你的接线设计与 canary 结论前，B1 维持 `PARTIAL / NOT ACTIVATED`。
