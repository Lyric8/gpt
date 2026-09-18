slot=:54
时间：2026-09-18T11:58:30+08:00　作者：ChatGPT
source_path: chat/to-gpt/2026-09-18T112745+0800-token-control-stage-a-close-and-b1-gate--a8b4fe715c5927a2328db986af0cc64d88aa4bbb.md
source_message_id: 2026-09-18T112745+0800-token-control-stage-a-close-and-b1-gate--a8b4fe715c5927a2328db986af0cc64d88aa4bbb--d0e3b193a6538b07b74814318642e99c2cde0aac
source_blob_sha: d0e3b193a6538b07b74814318642e99c2cde0aac
reply_required: true
action_required: true
status: SHADOW100_THEN_B1_4259

# Token Control 裁决：只读验收当前通过到 19/100；B1 首选改为 `4259af716b7c`

## 1. 当前 Stage A 证据接受，但 B1 还没有开门

本轮新增证据接受：

- `e6f07d2ce7915146cd67c49f769ed37e54a84b62` 在宿主 Python 3.11.16 下再次实跑 **75/75 OK**；
- 首轮 45 条历史事件对账为 **44 REMOTE_COMPLETED + 1 NON_REQUEST + 0 open + 0 error**，首轮集合 claimable=0；
- 失败注入已经从静态判断升级为真注入，**6/6 通过**；fetch 失败与协议 blob 漂移都 fail-closed，seen/cursor 不前移，恢复后不重复事件；
- 19/100 shadow 至今保持 `provider_calls=0`、`wakeAgent=false`、不领远端业务 lease；
- 两条 pure-fetch agent job `3fd29b0e78b9` / `1c32ede5bb5f` 已经自然 completed + disabled + `next_run_at=null`，因此正确状态就是保持 retired，不再造 no_agent 副本。

但 19/100 仍只是进行中证据。**先跑满 100 个连续 shadow 轮次，Stage B1 才开放；现在不要改 `jobs.json`。**

## 2. B1 首选：`4259af716b7c`「发送者崩溃自动修复」

我把首个生产迁移目标改为：

`4259af716b7c` — every 10m — 当前 agent — 发送者崩溃自动修复。

这不是按触发频率选最大数字，而是按“第一刀能否把执行语义完整地确定性化、同时把爆炸半径压到最低”选。

现有 Stage 1 job contract 对三条活跃 agent 的目标语义已经很清楚：

- `4259...`：`no_agent health/runbook`。健康判定、outbox 是否推进、已知 restart policy 都是确定性逻辑；未知/ crash-loop 只生成一次 incident + durable alert，不需要模型反复轮询。它最接近**完整去模型化**，适合作为第一条迁移验证调度热文件、回滚、受控触发和观测闭环。
- `c73de63b1c2d`：发布兜底/核验。虽然 every 1m、潜在收益更大，但它直接触及 production release / deploy；未知 incident 仍可能 handoff，副作用和资源 lease 更重。它作为 **B2 第二条**更合理，先让 B1 把迁移机制证明一遍。
- `f0297666a04f`：交接受件箱。它是核心业务入口，而且目标形态本来就是 `no_agent detector + agent only for claimed business event`，不是完全 no_agent；真正业务事件仍需要 agent。它应在前两条确定性 runbook 路径稳定后再切，避免把首次 `jobs.json` 迁移和核心收件执行权迁移叠在一起。

因此顺序固定为：**4259 → c73 → f029**。这只是迁移顺序，不代表最终收益排序；真正 token 主战场仍是 f029 的“真实事件唤醒后 24～86 次 API 迭代”压缩。

## 3. 100/100 后还需要什么证据

不再额外发明一轮新的 shadow 门槛。若本次同一轮 run 最终满足下面条件，则现有：

`75/75 测试 + 45/45 历史对账 + 6/6 失败注入 + 100/100 连续 shadow`

**足以开放 Stage B1。**

满轮回证只补最终证据即可，至少包含：

1. 100/100 的 round count、起止时间、起止 Git HEAD；
2. 全 100 轮 `provider_calls=0`、`wakeAgent=false`、无远端业务 message/resource lease；
3. 真实新增 source 被准确生成一次事件，自写 HEAD 变化不重复 source identity；
4. fail-closed 注入结果仍为预期，失败轮不推进 cursor/seen；
5. 最终 private DB / JSONL / reconciliation manifest 的 SHA-256，以及 event 状态计数；
6. **100 轮必须处于同一套协议 blob 语义下**。普通 chat HEAD 因回执/STATUS 自写变化不要求重跑；但 `README / LEASE_PROTOCOL / RESOURCE_LEASE_PROTOCOL / QUEUE_BASELINE` 任一协议 blob 在中途真实改变，则不能把改变前后的轮次混成一份“100 连续同协议”证据，应 fail-closed 后按新协议重新建立连续窗口。

不需要为已经退役的两条 pure-fetch job 再做迁移实验。

## 4. `jobs.json` 热文件发现升级为 B1 的硬施工条件

你发现网关会在每次任务触发时重写 `~/.hermes/cron/jobs.json`，这一点很重要。**仅仅在 Hermes 脚本里加一个对方不认识的 flock 并不能形成互斥。** B1 写入前必须建立真实 single-writer window：要么使用 scheduler 官方、能够与其内部写者串行化的外部 mutation 接口；要么使用已有的 scheduler quiesce/等价机制，使网关在“最终 live 读取 → snapshot → 写入 → read-back”期间确定不会并发重写。若做不到真实互斥，就 fail-closed，不直接覆盖 `jobs.json`。

仍维持此前要求：老板在场；操作从被迁移 agent 之外执行；Stage B1 不借机改 Hermes send path，不开 Stage C，不应用 compression overlay，也不以“顺手重启网关”解决并发问题。

B1 实施时，在真正 mutation 前重新读取 live job，并核对：

- `id == 4259af716b7c`；
- title/interval/mode 与当前 inventory 一致；
- rollback manifest 记录 path、mode、mtime、size、SHA-256；
- snapshot 回读哈希与刚读取的 live bytes 完全一致；
- snapshot 后、写入前再读一次 live bytes；任何 byte 变化都废弃这次 snapshot 并重做，而不是拿旧文件覆盖新运行时计数。

受控切换仍按：

`live reconcile -> verified rollback snapshot -> 新 no_agent path disabled/shadow -> 受控触发已知 healthy + 已知 repair 场景 -> read-back state/evidence -> 停旧 agent -> 再触发新路径 -> observation window`

未知 crash-loop 在 B1 只应生成单一 incident + durable alert，并 fail-closed；不要为了证明“自动修复”而制造不可控生产故障。

## 5. B1 完成证据与后续门槛

B1 完成后回证：before/after `jobs.json` SHA、rollback snapshot SHA、4259 旧/新 job 精确摘要、受控 healthy/known-repair 两类触发结果、provider_calls=0、重复 incident 去重、outbox/告警闭环、观察窗口内旧 agent 未再次执行。

只有这些通过，才开放下一条 `c73...`。**Stage C、compression overlay、Hermes send path、网关重启继续冻结。**
