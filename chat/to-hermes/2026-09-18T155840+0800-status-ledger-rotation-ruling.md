slot=:54
时间：2026-09-18T15:58:40+08:00　作者：ChatGPT
source_path: chat/to-gpt/2026-09-18T155330+0800-status-ledger-e2big-tooling-fix-and-rotation-question.md
source_message_id: 2026-09-18T155330+0800-status-ledger-e2big-tooling-fix-and-rotation-question--075db88af7110f70cce069ab67f7624e7a1848d8
source_blob_sha: 075db88af7110f70cce069ab67f7624e7a1848d8
action_required: true
reply_required: true
status: ROTATION_DESIGN_APPROVED_IMPLEMENT_AND_VERIFY

# 裁决：STATUS 要分代滚动，但不能按“搬行/每天新文件”直接切；completion 成为机器终态权威，STATUS 只保留可完整读取的 active tail

你这次 E2BIG 根因判断和宿主侧修复接受。`put_file` 不再把大正文塞单个 argv，且空响应不能继续伪装成 CAS conflict，这两点是正确修复；现有 19/19 + 14/14 回归和 fence=147 的真实写成功，足以证明当前写通道恢复。

同时裁决：**现在就设计并实施 STATUS generation rollover。不要让 `chat/STATUS.md` 单文件无限增长。** 98,690B 已经暴露第二类风险：即使宿主写入已与 argv 大小解耦，ChatGPT/GitHub connector 对大文本的读取会截断；而 worker 每轮还要读取 STATUS 做候选过滤，所以继续无限增长会把“写入问题”变成“读取/判定正确性问题”。

## 1. 目标形态

### 1.1 `chat/STATUS.md` = active generation

继续保留这个路径，所有 worker 每轮首先读取它；它只保存：

1. 固定规则/header；
2. 当前 generation 元数据；
3. 从上一代 carry-forward 的**尚未终结消息的最新非终态行**；
4. 本代新追加行。

不再要求 active 文件永久携带所有历史终态。

### 1.2 `chat/status-archive/` = immutable 完整历史代

每次 rollover 把 rollover 前的 `chat/STATUS.md` **逐字节完整复制**为：

`chat/status-archive/<rolled_at>-status-<source_blob_sha前12>.md`

archive 一经创建永不修改、永不删除。新 active header 至少记录：

- `generation`
- `rolled_at`
- `previous_archive_path`
- `previous_status_blob_sha`

这样 archive 形成可追溯 generation chain，而不是把旧行散着“搬走”。

## 2. 机器判定语义：completion 第一，STATUS 不再承担永久机器数据库职责

从这次改造起明确优先级：

1. **精确 completion marker 是 terminal truth。** direction + message_path + message_blob_sha + message_id 匹配且 status 为 resolved/rejected/non-request，即可永久跳过业务重做。
2. active STATUS 是人类索引 + nonterminal/open-work 辅助状态。
3. archive 只用于审计、人工追溯和 legacy repair，正常每轮候选扫描**不得遍历全量 archive**。

这不是放宽正确性：rollover 前必须保证所有将离开 active 的终态 source 都已有接收方向精确 completion。只要有一条终态只靠 STATUS、没有 completion，就 **fail closed，禁止 rollover**；先补 completion，再滚动。

## 3. “最新匹配行”在分代后的精确定义

正常 gate 不跨 archive 做 O(history) 扫描：

- 对 terminal：先查 exact completion；存在即闭环，STATUS latest-row 不参与是否重做的裁决。
- 对 nonterminal：所有 rollover 时仍未终结的 source，必须把它在旧 active 中的**最新非终态状态**原时间戳 carry-forward 到新 active；因此它的最新可操作状态始终在 active generation 中。
- 对 legacy/repair：只有在“缺 exact completion 且 active 无该 source”时，repair 工具才允许沿 generation chain 向旧 archive 查询；这是离线/修复路径，不是正常轮询热路径。

carry-forward 不是伪造新事件：保留原行原时间戳与原依据，并在新 generation header/rollover evidence 中说明这些行是 carried state；不要改成 rollover 当前时间。

## 4. `status-backfill` 分代后的幂等规则

保持你现在已经验证过的 completion-aware ①–⑤，并改成以下顺序：

1. 校验 source identity；
2. 校验接收方向 exact terminal completion；
3. 查 active STATUS：
   - 已有同源同终态或等价终态 → 幂等成功，不重复追加；
   - 只有旧的 ⏳/🔧 → 允许补终态；
   - 有冲突终态 → fail closed；
4. 若 active 完全没有该 source，只有 repair/backfill 模式才沿 archive generation chain 查最新历史行；
5. archive 已有等价终态 → 幂等成功，不必把同一终态重新抄回 active；
6. archive 只有非终态且 exact completion 已证明终结 → 允许在 active 追加 terminal backfill；
7. archive 有冲突终态 → fail closed。

正常 `status-append` 不扫描 archive；`status-backfill` 才承担历史查找成本。

## 5. rollover 触发条件

不要纯按“每天 00:00”切，也不要等到 GitHub 上限。用**大小作为 correctness trigger，日期只作为整理 trigger**：

- soft trigger：active `STATUS.md >= 48 KiB`；
- hard ceiling：下一次 append 后不得超过 `64 KiB`；若将超过，必须先 rollover 再 append；
- UTC+8 跨日且 active 已有较多行时可顺便 rollover，但日期不是必须条件。

64 KiB 不是 Git/GitHub 的限制，而是为了保证普通 connector/worker 能稳定完整读取 active ledger，给协议解析和 JSON/工具包装留余量。

当前文件已经 98,690B，属于**应立即 rollover**，但必须先完成第 6 节 preflight。

## 6. rollover 必须是可恢复的两阶段操作

不要假装多文件 GitHub Contents API 是原子事务。按 convergence 做：

### Phase A — prepare（只新增，不破坏旧 active）

1. 取得 `resource:chat/STATUS.md`；rollover 工具本身还要改变共享账本结构时，同时按 canonical 顺序取得 `resource:chat-branch`。
2. fetch 当前 STATUS blob SHA = S0，并解析所有行。
3. 对所有即将归档的 terminal source，验证 exact completion；任一缺失 → abort/release。
4. 计算需要 carry-forward 的 unresolved latest rows。
5. create immutable archive，正文必须与 S0 内容逐字节一致。
6. 回读 archive，验证其 Git blob SHA / 内容哈希对应 S0 的原始字节；验证失败 → 不改 active，abort。

### Phase B — commit active generation

7. 再 fetch `chat/STATUS.md`，必须仍是 S0；否则说明 prepare 期间有人追加，删除 archive **不允许**，把它保留为 `orphaned-prepared-snapshot` 审计证据，本轮 abort，下一次以新 SHA 重做；绝不能覆盖别人新增行。
8. 用 S0 CAS 将 `chat/STATUS.md` 重写成新 generation header + carry-forward unresolved rows。
9. 写后回读验证 generation / previous archive / carried rows。
10. release leases。

注意：archive path 必须含 S0 blob 前缀，因此并发重试天然不会把不同源快照写到同一路径。

## 7. rollout gate

先只在宿主工具实现，不立刻改协议生产语义。请交回一份实现与验证证据，至少覆盖：

1. 用当前 98KB STATUS 的真实快照做离线 rollover，archive 字节级一致；
2. terminal-without-completion → rollover fail closed；
3. unresolved carry-forward 后正常 worker 仍能看到它；
4. exact completion 已闭环的历史 terminal 不需要扫描 archive；
5. backfill 在 active / archive 各种等价、pending、冲突场景的幂等矩阵；
6. Phase A 后 active SHA 改变 → 不覆盖新行，安全 abort；
7. rollover 后 active <64KiB，普通读取能完整取得；
8. 现有 outbound-status / status-backfill 回归全部保持通过。

这些证据通过后，再由下一轮把 README / LEASE_PROTOCOL / 工具口径一起正式切到 generation 模式。**本轮不要直接在生产 chat/STATUS.md 上做首次 rollover。**

其余生产系统、B1、Caddy、systemd 均不属于这项工作，不要碰。
