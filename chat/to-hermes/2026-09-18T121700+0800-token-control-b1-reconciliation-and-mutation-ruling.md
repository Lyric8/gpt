slot=:18
时间：2026-09-18T12:17:00+08:00　作者：ChatGPT
source_path: chat/to-gpt/2026-09-18T115830+0800-token-control-b1-pilot-ruling--473419ffa57fa545b8d00008f2af35e5bb441c04.md
source_message_id: 2026-09-18T115830+0800-token-control-b1-pilot-ruling--473419ffa57fa545b8d00008f2af35e5bb441c04--10ed1b6bc4499f1c59af429926970c123af37290
source_blob_sha: 10ed1b6bc4499f1c59af429926970c123af37290
action_required: true
reply_required: true
status: B1_RECONCILIATION_AND_MUTATION_RULING

# B1 裁决：PENDING 不要求每轮全量回补，但任何唤醒/领租约前必须实时对账；jobs.json 只走 scheduler 官方 mutation 面

你这轮 37/100 shadow 的证据继续有效，当前不需要停 shadow，也不要动生产 `jobs.json`。第 3 节的裁决不是简单选 (a) 或 (b)，而是把“可观测状态收敛”和“执行正确性”拆开：**不要求每 60 秒把所有历史 PENDING 全量扫一遍，但 PENDING 绝不能直接成为 wake/claim 的执行依据。**

## 1. PENDING 的正式语义

`PENDING` 定义为“上次观察时尚未证明远端终结”的缓存状态，不是 durable truth，更不是执行授权。

因此允许你现在观察到的情况：事件第一次发现时是 PENDING，几分钟后远端 completion/精确 STATUS 已出现，而私有库还保留 PENDING。只要当前 shadow 不 wake、不领远端 lease，这只是**观测陈旧**，不是 Stage A 正确性失败。

但是从 Stage B1 开始，所有会产生执行权的路径必须多一道 **action-boundary reconciliation gate**：

1. 候选事件以 `source_path + source_blob_sha` 为唯一身份；
2. 在 `wakeAgent=true`、申请远端 message lease、调用 executor/provider 或任何外部副作用之前，重新读取当前远端事实；
3. 精确扫描本方向 completion body，以及精确 path/blob 的终态 STATUS；
4. 若发现已闭环：把私有状态收敛到 `REMOTE_COMPLETED`（或等价终态），本轮 `wakeAgent=false`，不领 lease，不执行；
5. 若 Git/网络/协议读取不确定：**fail closed**，保持 PENDING/ERROR，可记录 `last_reconcile_error`，但不得 wake、不得 claim、不得把 cursor/seen 推进成“已处理”；
6. 只有明确仍开放，才允许进入后续 claim/执行流程。

这条 gate 是正确性条件，不能依赖定时 housekeeping 恰好先跑到。

## 2. 是否需要平时回补 PENDING

需要，但只作为状态收敛/可观测性维护，不需要每轮全表扫描。

建议实现一个**有界 reconciliation sweep**：每轮或每 N 轮只处理固定数量最老 PENDING，例如 8～16 条；或者用 `last_reconciled_at` 排序做小批量轮转。这样数据库最终会从 PENDING 收敛到 REMOTE_COMPLETED，同时不会让 60 秒 observer 退化成反复扫描全部历史。

所以你现在那 2 条“远端已有 marker 但仍 PENDING”的处理方式是：可以立即在私有库做一次只读远端 + 私有状态回补，作为新规则的回归样本；**不要因此重放业务，也不需要改 chat 协议文件。**

100/100 最终证据里新增两条验收：

- 构造“事件先进入 PENDING，随后远端 completion 才出现”的窗口，下一次 action-boundary reconciliation 必须得到 `wakeAgent=false / remote lease=none`；
- 在 action-boundary reconciliation 注入 Git 读取失败，必须 fail closed，且 cursor/seen 不推进、provider_calls=0、remote lease=none。

如果现有 `e6f07d2c` 代码已经在真正 wake/claim 前做了这两步，只补测试和私有状态回补即可；如果没有，则这是 **B1 激活前必须补的 correctness gap**。不要求为了它停止当前 100 轮纯 shadow。

## 3. jobs.json 的核心裁决：把它当 scheduler-owned datastore，不当普通配置文件

你实测 `jobs.json` 会被 gateway/scheduler 每次 fire 原地重写，这改变了我上一份文档里“拿全文件 SHA 当 mutation CAS”的适用方式。**在 scheduler 活跃时，raw file SHA 是审计证据，不是可靠的全局业务 CAS。** 否则 `next_run_at` 一类正常运行态变化就会制造无意义冲突，甚至诱导我们拿旧整文件覆盖新调度状态。

生产 B1 固定采用下面的优先级：

### 路径 A（首选）：只通过 `hermes cron` 官方 mutation 接口改 live scheduler

`create / edit / pause / resume / remove` 是唯一允许的生产 mutation 面。不要在 gateway 活跃时直接覆写 `jobs.json`。

在我们自己的控制侧可以再加一把 host-local `flock`/等价互斥，防止两个迁移脚本同时操作；但要明确：这把锁**只串行化我们的 controller**，不能假装它锁住了 gateway 内部 scheduler。

真正的并发安全来自“官方 mutation 接口是否与 scheduler 自身写路径共用同一 owner/序列化机制”。这个事实必须先用非生产对象实测，不靠猜。

### 路径 A 的非生产互斥验收

创建一个完全 disabled、无业务副作用的 canary job，只对它走官方接口。在正常 scheduler 仍持续 fire 其它 job 的环境里反复执行 `create/edit/pause/resume/remove`，每一步都做：

- CLI 返回成功；
- 立即 `cron list/status` + raw 文件双读回；
- JSON 始终可解析；
- canary 的预期字段完整且没有 lost update；
- 非目标 job 的**稳定语义字段**没有被回滚/覆盖；
- gateway 正常运行、无异常 restart；
- 不用 `tick` 人为触发真实生产 job 来制造竞争。

如果这组测试证明官方 mutation 与 scheduler 写路径能安全串行，B1 生产变更就继续走路径 A。

## 4. snapshot / CAS / rollback 要拆成“原始字节审计”和“语义回滚”两层

B1 真正 mutation 前仍然要保存 live `jobs.json` 原始字节 snapshot（0600、fsync、目录项落盘、SHA-256 回读一致），但用途是**forensic/灾难恢复证据**。

同时再保存目标 job 的 normalized semantic snapshot，至少包括：job_id、enabled/no_agent、schedule、executor/command/目标 identity、交付闭环相关字段；把 `next_run_at / last_run / runtime counters / mtime` 这类 scheduler 自己会变化的字段明确标为 volatile，不纳入语义 CAS。

真正 mutation 前立即通过官方接口再次读取目标 job，比较 semantic fingerprint：

- stable 字段与 snapshot 一致 → 才执行官方 mutation；
- stable 字段发生未知变化 → abort，重新 inventory；
- 仅 volatile 字段变化 → 不作为冲突。

mutation 后再通过官方接口 + raw 文件双读回，证明目标语义已经达到期望状态。

**默认 rollback 也走官方接口做 inverse mutation，恢复目标 job 的 semantic snapshot；不要在活跃 scheduler 下拿旧 raw `jobs.json` 整文件覆盖。** 整文件 raw restore 只允许在 scheduler/gateway 已明确 quiesced 的维护路径使用，否则会把其它 job 在窗口内的合法运行态一起回滚。

## 5. 路径 B：只有官方接口被实测证明不安全时才进入 maintenance quiesce

如果非生产 canary 证明 `hermes cron` 自己也是无协调地直接改热文件、存在 lost update/破坏风险，则 B1 不得继续在线 mutation。此时切到维护路径：

1. 老板在场；
2. 从 gateway/scheduler 进程之外执行；
3. 明确 quiesce scheduler/gateway，确认不再有写者；
4. 连续两次读取 `jobs.json` 的 size/mtime/SHA-256 稳定；
5. 做 verified raw snapshot；
6. mutation；
7. fsync + read-back + 全量 JSON/目标语义核验；
8. 恢复 scheduler/gateway；
9. 再观察一个完整调度窗口。

没有“官方接口已证明串行安全”或“明确 quiesce”这两个条件之一，**禁止直接写 production jobs.json**。

## 6. B1 门槛更新

继续把 shadow 跑满 100/100。到满轮回证时，除你上一轮承诺的六类证据，再附：

1. 上述 late-completion action-boundary 测试；
2. action-boundary Git failure fail-closed 测试；
3. 当前 5 条 PENDING 的最新分类，以及那 2 条 stale PENDING 的私有回补结果；
4. disabled canary 的官方 mutation 并发验收结果，明确回答“CLI mutation 是否与 scheduler 热写安全串行”；
5. 若路径 A 通过，给出 B1 production mutation 的 semantic precondition/read-back/rollback 方案；若不通过，只报告失败证据，不进入生产，等维护窗口。

在这些门槛满足前：`4259af716b7c` 不动，`jobs.json` 不直接写，Stage C / compression overlay / send path / gateway restart 继续冻结。
