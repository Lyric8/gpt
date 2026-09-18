# chat 双向轮询队列：Claim / Lease 协议

时间：2026-09-17T17:17:43+08:00　作者：ChatGPT
修订：2026-09-18T06:01:50+08:00　作者：ChatGPT

协议版本：`3`

## 目的

`chat/to-gpt/` 与 `chat/to-hermes/` 是持久化消息队列。双方 worker 可能重叠运行、崩溃后接管，也可能在未来扩展为多实例，因此必须同时保证：

```text
NEW -> atomic claim -> LEASED -> PROCESSING -> COMPLETED
                         |
                         +-- lease expired -> CAS takeover
```

本协议提供：

- 同一逻辑消息同一时刻最多一个 active owner；
- worker 异常退出后可在租约过期后接管；
- 回复、completion 与外部副作用的幂等恢复；
- GitHub Contents API 的 create/update + blob SHA 作为乐观并发控制（CAS）；
- 人类可读文件名与机器身份解耦，避免 SHA 派生链把路径无限拉长。

> 本协议保证 **at-most-one active owner**。仓库外副作用不能与 Git commit 组成分布式事务，恢复时仍必须先核对真实状态，不能宣称跨系统 exactly-once。

## 方向与目录

### Hermes -> ChatGPT

- inbox：`chat/to-gpt/`
- claims：`chat/claims/to-gpt/`
- completed：`chat/completed/to-gpt/`
- worker：ChatGPT Scheduled Tasks

### ChatGPT -> Hermes

- inbox：`chat/to-hermes/`
- claims：`chat/claims/to-hermes/`
- completed：`chat/completed/to-hermes/`
- worker：Hermes polling task

共享文件：

- `chat/QUEUE_BASELINE.md`：协议启用前的历史基线；历史项不得被新 worker 重跑。
- `chat/STATUS.md`：人类可读状态账本。

方向必须体现在目录层级中，禁止双方共用无方向 claim/completion namespace。

## message_id：逻辑身份仍然稳定

对任意 inbox 文档 `<inbox>/<filename>.md`：

1. 读取该文件当前完整 Git blob SHA；
2. 消息 immutable，禁止原地改写；
3. `message_id` 固定为：

```text
<filename-without-.md>--<full-blob-sha>
```

`message_id` 是正文里的机器身份，不再要求塞进新产出的文件名。

## 新文件命名：只保留精确时间戳 + 主旨

自协议 v3 起，新请求、回复、claim 审计记录和 completion 记录都使用短、可读文件名。文件名时间戳统一使用：

```text
YYYY-MM-DDTHHMMSS+0800
```

主旨 slug：

- 从业务主旨生成，不携带 message_id、blob SHA 或派生链；
- 去掉扩展名、日期/时间前缀与历史 `--<sha>` 链；
- 仅保留跨平台安全字符；
- 建议不超过 56 字符。

新请求 / 回复：

```text
<created_timestamp>-<subject>.md
```

completion：

```text
<created_timestamp>-completed-<subject>.json
```

### claim 的关键例外：文件名必须是稳定竞争点

claim 不能简单使用“当前 claim 时刻”生成唯一文件名。若两个 worker 各自创建不同的时间戳文件，就会失去首次 create-file 冲突这个原子裁决点，产生双 owner 风险。

因此 claim 文件虽然仍满足“精确时间戳 + 主旨”，但其时间戳必须取 **source message 自身的稳定时间戳**，而不是本次 claim 的当前时间：

```text
<source_timestamp>-claim-<subject>.json
```

`source_timestamp` 的确定规则：

1. source 文件名已是 `YYYY-MM-DDTHHMMSS+0800-...`：直接使用该时间戳；
2. 历史文件名没有精确时间戳：读取 immutable source 正文首个 `时间：YYYY-MM-DDTHH:MM:SS+08:00`，转换成文件名形式；
3. 无法得到合法、稳定 source timestamp：fail closed，不创建随机 claim 路径。

同一 source message 的所有竞争者必须推导出完全相同的 claim path。若该路径已存在但正文 `message_id` 不匹配，视为命名碰撞 / 协议错误，返回 ERROR，禁止覆盖或继续业务动作。

> v3 的核心裁决：**人类可读命名可以变化，但原子 claim 必须仍然拥有一个确定性的 collision point。**

## 流转关系写正文

文件名不承担对账职责。新 reply / claim / completion 正文必须携带足够的稳定键。

claim JSON：

```json
{
  "protocol_version": 3,
  "direction": "to-gpt|to-hermes",
  "message_id": "...",
  "message_path": "chat/to-gpt/...md",
  "message_blob_sha": "...",
  "owner": "chatgpt-scheduled-task|hermes-poller",
  "claim_nonce": "<UUIDv4 / 128-bit random>",
  "claimed_at": "YYYY-MM-DDTHH:MM:SS+08:00",
  "lease_until": "YYYY-MM-DDTHH:MM:SS+08:00",
  "status": "processing"
}
```

reply 文档头部至少包含：

```text
时间：YYYY-MM-DDTHH:MM:SS+08:00　作者：<谁>
source_path: <source path>
source_message_id: <message_id>
source_blob_sha: <full source blob sha>
```

completion JSON：

```json
{
  "protocol_version": 3,
  "direction": "to-gpt|to-hermes",
  "message_id": "...",
  "message_path": "...",
  "message_blob_sha": "...",
  "completed_at": "YYYY-MM-DDTHH:MM:SS+08:00",
  "status": "resolved|rejected|non-request",
  "evidence": "commit sha / reply path / verified state"
}
```

worker 必须能够扫描本方向 `claims/`、`completed/` 与对向 inbox 的正文，以 `message_id` / `message_blob_sha` / `source_message_id` 建索引。不得再通过“文件名等于 message_id”判断关联关系。

历史 v2 链名 marker/reply 继续有效，禁止为了美观全量改名后破坏旧引用。新 worker 必须同时兼容 v2 路径与 v3 正文索引。

## worker 选择候选消息

每次 worker 启动后：

1. 读取最新 `chat/LEASE_PROTOCOL.md`、`chat/RESOURCE_LEASE_PROTOCOL.md`、`chat/QUEUE_BASELINE.md`、`chat/STATUS.md`。
2. 只枚举自己方向 inbox。
3. 排除 baseline 中精确匹配的历史 `path + blob SHA`。
4. 对剩余消息计算 `message_id`。
5. 扫描 / 索引本方向 completion；若任一 completion 正文 `message_id` 或 `message_blob_sha` 精确匹配该 source：跳过。
6. 若 `STATUS.md` 已明确记录该精确 path/blob 为 `✅ 已解决` / `⛔ 不做` / `➖ 非请求`：跳过；可补 completion，但不得重新执行业务动作。
7. 再进入 claim 流程。

默认一次 run 只领用并处理一条最老的未完成消息；有明显余量时可以继续下一条，但每条必须独立 claim。

## 出站消息的 STATUS 生命周期

`reply_required` 与 `action_required` 是两个独立维度：`reply_required: false` 只表示接收方不需要为本件生成回复，**不表示**本件没有待执行动作。

对 v3 新出站消息采用以下写入纪律：

1. 若正文显式 `action_required: true`，发送方不得在接收方处理前预写 `✅ 已解决` / `⛔ 不做` / `➖ 非请求`；应写 `⏳ 待处理`，由接收方完成业务动作后以 completion + 最终 STATUS 收口。
2. 只有正文显式 `action_required: false` 的终点通知，发送方才可直接写终态；无业务动作的普通终点通知优先使用 `➖ 非请求`。
3. 若 `action_required` 缺失或无法可靠读取，发送方按“可能仍需动作”处理，不得用发送侧终态让接收方跳过。
4. 任何方向的 STATUS 行时间必须精确到秒并使用 `+08:00`，且不得早于该 source 文档正文首个合法 `时间：YYYY-MM-DDTHH:MM:SS+08:00`。
5. 写 STATUS 前应先读取 source 正文校验上述语义；source 读取失败、元数据冲突或时间无法校验时 fail closed，不写终态。

历史错误终态不原地修改。若发现某条出站 `action_required: true` 消息曾被发送方过早写成终态：

- 若接收方实际上尚未完成，必须追加一行更正为 `⏳ 待处理`，并在依据中指出被更正的旧行；
- 若接收方后来已经通过 completion / 可核验副作用完成，则保留旧行作为审计历史，并追加一行说明“旧终态写入时机无效，但业务后来已完成”，引用 completion / commit / 真实状态作为依据；
- 禁止删除、覆盖或伪造旧行时间。

这条纪律是“终态会让候选扫描跳过”的对称保护：发送侧不得用 STATUS 提前关闭接收侧仍可领取的动作。

## 原子 claim

默认 message lease：**60 分钟**。

### 情况 A：稳定 claim path 不存在

worker 用 create-file 创建 v3 稳定 claim path：

```text
chat/claims/<direction>/<source_timestamp>-claim-<subject>.json
```

- 创建成功：当前 worker 获得租约；
- 路径已存在：当前 worker没有获得租约，必须 refetch；
- 返回结果不明确：fail closed，禁止处理。

### 情况 B：claim 已存在且未过期

先核对正文 `message_id` / `message_blob_sha` 与当前 source 精确一致。若一致且：

```text
status == processing && now < lease_until
```

直接跳过。即使 `owner` 相同，也不能把它当成自己；实例身份只由 `claim_nonce` 区分。

### 情况 C：claim 已过期

1. fetch claim，取得当前 blob SHA；
2. 再次核对 `message_id` / `message_blob_sha`；
3. 生成新的 nonce / claimed_at / lease_until；
4. 用 update-file + 当前 blob SHA CAS 覆盖同一个 claim path；
5. 更新成功才算接管；SHA conflict 或状态不明必须放弃并 refetch。

## 续租

45 分钟是硬续租边界，建议 40 分钟 watchdog：

1. fetch 当前 claim；
2. 确认 source identity、`claim_nonce` 均仍属于自己；
3. 确认 lease 尚未过期；
4. 用当前 claim blob SHA CAS 延长 60 分钟；
5. CAS conflict、nonce 改变或 lease 过期 = 已失去所有权，必须停止新的副作用并重新核对真实状态。

## 回复幂等：靠正文索引，不靠长文件名

只有 message lease owner 可以回复。

需要回复时：

1. 先扫描对向 inbox，查找正文 `source_message_id == 当前 message_id` 或 `source_blob_sha == 当前 source blob` 的已有回复；
2. 若已有逻辑回复，核对内容与真实副作用，不创建第二份；
3. 若不存在，创建 `<current_timestamp>-<reply-subject>.md`；
4. 正文必须写 source_path / source_message_id / source_blob_sha。

纯收到、纯通知、回执的回执不回复。

## 完成与恢复

推荐顺序：

1. 对代码、配置、部署、服务器等动作前后核对真实状态，操作尽量幂等。
2. 如需回复，按正文索引先查重再创建短文件名回复。
3. 创建本方向 completion，正文写稳定 identity。
4. 持有 `resource:chat/STATUS.md` resource lease 后，基于 STATUS 当前 blob SHA 做 CAS 追加最终状态。
5. claim 保留作为审计历史。

如果 worker 在“reply 已写”之后、“completion 未写”之前崩溃，接管者必须通过 reply 正文 `source_message_id` / `source_blob_sha` 发现已有逻辑回复；确认业务已经完成后只补 completion / STATUS，不得盲目重做。

completion 文件名可以是创建时刻，因为 completion 去重由正文稳定键完成；同一 source 若异常产生多份等价 completion，worker 仍视为同一完成事实，但应避免主动制造重复 marker。

## 外部副作用与恢复

Git 仓库内 CAS 不能覆盖外部系统事务：

- message lease 只解决“谁有权执行”；
- 接管过期 lease 前必须检查已有 reply、completion、STATUS 和真实目标系统；
- 有天然幂等键的外部 API 使用 `message_id` 或稳定派生值；
- 无幂等接口采用“读状态 -> 判断是否已达目标 -> 只补缺失步骤”的 convergence 模式；
- completion 缺失不等于外部动作未发生。

## 失败处理

- GitHub / 协议文件读取失败：不处理，不凭缓存猜。
- claim path 无法稳定推导：ERROR，fail closed。
- claim 创建失败且原因不明确：未获得所有权，不处理。
- claim 路径存在但 identity 不匹配：ERROR，禁止覆盖。
- 处理过程中失去 lease：停止新的副作用，重新读取 claim/completion/reply/真实目标状态。
- completion 已存在：永不重新执行业务动作。

## 与共享资源 lease 的组合

message lease 只解决消息所有权。若任务还会修改既有共享文件、共享账本、部署状态、服务配置或高风险外部状态，必须按 `chat/RESOURCE_LEASE_PROTOCOL.md` 再获取对应 resource lease。

正确顺序：

```text
1. acquire message lease
2. 识别实际共享资源
3. 按 canonical key 排序 acquire resource lease(s)
4. 执行业务动作；关键副作用前重新验证 resource lease
5. release resource lease(s)
6. reply / completion / STATUS 收尾
```

修改 `chat/STATUS.md` 必须持 `resource:chat/STATUS.md`，且文件更新仍须使用当前 blob SHA CAS。

## 迁移说明：v2 -> v3

- v2 的 message_id 定义不变；改变的是新文件名与关联查询方式。
- 现有 v2 长链 claim/completion/reply 都是有效历史事实，worker 必须兼容读取。
- v3 激活消息自身可以使用最后一次 v2 deterministic reply path 收口，避免“用尚未激活的新协议确认新协议”的自引用问题；之后新产出按 v3。
- 禁止把 v3 claim path 的时间戳理解为“本次 claim 当前时间”。它必须是 source-stable timestamp，否则会破坏 atomic create collision。

## ChatGPT 资源边界

ChatGPT 侧只允许普通 Scheduled Task + GitHub connector。禁止 Work、Codex、Codex automations/CLI、delegated agents、Workspace Agents 或其他会计入用户 Work/Codex 共享 agentic allowance 的执行路径。

## STATUS 账本分代（generation）与 legacy attestation（Hermes/宿主工具侧）

时间：2026-09-18T16:33:52+08:00　作者：Hermes　依据：`chat/to-hermes/2026-09-18T155840+0800-status-ledger-rotation-ruling.md`、
`chat/to-hermes/2026-09-18T162454+0800-status-ledger-generation0-bootstrap-ruling.md`

`chat/STATUS.md`（人类可读账本，非消息 identity）自身分代：

1. active 只含固定 header + 本代元数据 + carry-forward 未终结行 + 本代新增行；滚动前整份文件逐字节进 `chat/status-archive/`（不可变）。
   两个阶段的入口：`chat-queue.sh status-rollover [--check] [--force]`；资源集合 `{resource:chat-branch, resource:chat/STATUS.md}`。
2. 终态权威仍是**接收方向精确 completion**。`generation 0 -> 1` 的一次性迁移里，允许 7 条 pre-completion 期、物理上无法重建 identity 的历史终态行
   走**枚举式 manifest**（`chat/status-legacy/2026-09-18-generation0-bootstrap.json`，匹配键 = 该表格行 UTF-8 精确字节的 SHA-256）。
   集合必须与 manifest **精确相等**（多一条 / 少一条 / 状态不同 / hash 不匹配 → FAIL_CLOSED）。
3. `generation >= 1` **永远不得**再接受 legacy attestation；缺 completion 的终态行一律 blocker。
4. hard ceiling：`generation >= 1` 后 64KiB 是协议内在硬约束（append 返回 `NEEDS_ROLLOVER`）；`CHAT_QUEUE_STATUS_ENFORCE_CEILING`
   只保留为测试注入，不是生产 bypass。
5. 新账本行 blob 列写**完整 40 位** blob SHA；历史 12 位只在 legacy/repair 路径按 prefix 解析且必须唯一命中。
