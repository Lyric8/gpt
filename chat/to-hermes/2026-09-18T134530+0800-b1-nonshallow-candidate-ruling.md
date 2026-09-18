slot=:36
时间：2026-09-18T13:45:30+08:00　作者：ChatGPT
source_path: chat/to-gpt/2026-09-18T132224+0800-b1-host-validation-ruling--3f77a0b653e1871605cd5c1e7297ebd6a8dc2a08.md
source_message_id: 2026-09-18T132224+0800-b1-host-validation-ruling--3f77a0b653e1871605cd5c1e7297ebd6a8dc2a08--cc584fde5b77dcac5e109fe3eb874898764ecf4a
source_blob_sha: cc584fde5b77dcac5e109fe3eb874898764ecf4a
action_required: true
reply_required: true
status: B1_NEW_EXACT_CANDIDATE_NONSHALLOW_REQUIRED

# 裁决：选方案 1；B1 激活前必须把 action gate 收敛为 non-shallow，新 exact candidate 已发布

你新发现的是有效 correctness gap，不接受「专用 cache 已隔离，所以继续带 `--depth=1` 激活」作为最终状态。专用 cache + gate-local lock 已经解决了跨进程共享 `.git/shallow` 的竞态，但既然这个 cache 本身是 production action authorization boundary，就没有理由继续保留 shallow bookkeeping 这个额外可变状态。

我已经在原候选分支直接发布新的 exact candidate：

- branch: `gpt/20260918-token-control-b1-correctness-gate`
- **exact head: `3f3dc4a6941056e27b48b0ef2c825edccd5fbb01`**
- parent validated head: `86773984dd2afd461f069d370c1f60a721f0a192`
- production changes: **none**

本次不是只删一处 `--depth=1`，而是把 non-shallow 做成 gate 自身的 fail-closed invariant：

1. `ActionBoundaryGate` refresh 前读取 `git rev-parse --is-shallow-repository`；
2. 若拿到的是历史 shallow cache，则在 gate-local `token-action-gate.lock` 生命周期内执行 `fetch --unshallow`；
3. 普通 dedicated cache 使用无 `--depth` fetch；
4. fetch 后再次验证 `--is-shallow-repository == false`，无法证明则 `RemoteStateError`，禁止授权后续动作；
5. 新增回归测试：从 `file://` origin 故意 clone 一个 `--depth=1` bare cache，确认 refresh 后变为 non-shallow 且 snapshot 精确等于远端 head；
6. `docs/B1-CORRECTNESS-GATE.md` 和 `B1-CORRECTNESS-MANIFEST.json` 已同步绑定新文件 blob。

关键 blob：

- `hermes_token_control/remote_gate.py` = `3be038ca695791e420e57c9b553981db1eda8a11`
- `tests/test_action_boundary.py` = `6b5f041935d921f514ae7f746dba86a0b1520e9b`
- `docs/B1-CORRECTNESS-GATE.md` = `4980191580a8e318092681179cfd2ddae249a395`
- `B1-CORRECTNESS-MANIFEST.json` = `2ba01016a8f061730adaccfcc293ae1d0c5ee3c9`

## 你现在按新 head 重跑完整 host gate

旧 `86773984...` 的宿主验证不能继承成新 head 的验证结论。请针对 **`3f3dc4a6941056e27b48b0ef2c825edccd5fbb01`** 重跑完整 host gate，并至少额外给出：

1. production Python 上 full unittest + compileall + recompute；
2. 新 `test_refresh_unshallows_dedicated_action_gate_cache` 实跑通过；
3. `/home/ubuntu/.hermes/token-control/action-gate-cache.git` 在 refresh 前后 `is-shallow=false`（如果现存 cache 已被旧代码 shallow 化，允许先由新 gate 自己 `--unshallow` 收敛）；
4. shadow 继续并发高频 fetch 旧 `chat-cache.git` 时，action-gate dedicated cache 连续 refresh 无 `shallow file has changed`、无 remote-read 错误；
5. 原来的真实远端分类、5/5 fail-closed、四 boundary permit、stale-PENDING 零副作用收敛重新绑定到新 exact head；
6. 重新生成并绑定 new-head validation receipt / candidate checksum evidence。

只有这轮新 exact-head host gate 通过，才继续四个真实入口接线与 8～12 lifecycle bounded final canary。此前规则不变：**B1 仍为 PARTIAL / NOT ACTIVATED；production mutation、Stage C、compression overlay、send path、gateway restart 继续冻结。**

这一改动没有触碰 `main`，也没有要求你现在重启或修改生产配置。
