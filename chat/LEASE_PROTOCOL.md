# ChatGPT 轮询队列：Claim / Lease 协议

时间：2026-09-17T17:12:30+08:00　作者：ChatGPT

协议版本：`1`

## 目的

ChatGPT 侧现在由 10 个彼此独立的 Scheduled Tasks 错峰轮询 `chat/to-gpt/`。它们分别在每小时 `:00/:06/:12/:18/:24/:30/:36/:42/:48/:54` 触发，因此整体约每 6 分钟检查一次。

这些 task 是独立 worker。**发现同一条新消息不等于可以直接执行**；任何实际处理前都必须先取得该消息的独占租约（lease），否则 6 分钟以上的工作会被下一 task 重复执行。

本协议提供：

- 同一消息同一时刻最多一个 active owner；
- worker 异常退出后可在租约过期后接管；
- deterministic reply / completion marker，降低重复回执与重复副作用；
- GitHub Contents API 的 create/update + blob SHA 作为乐观并发控制（CAS）。

> 本协议保证的是 **at-most-one active owner**。对仓库外或其他不可事务化副作用，恢复执行时仍必须先核对实际状态，不能假定 exactly-once。

## 目录

- `chat/to-gpt/`：Hermes / 老板写给 ChatGPT 的消息。
- `chat/claims/`：ChatGPT worker 的租约记录，只认 `*.json`。
- `chat/completed/`：已逻辑完成的消息记录，只认 `*.json`。
- `chat/to-hermes/`：ChatGPT 发给 Hermes 的请求 / 回执。
- `chat/QUEUE_BASELINE.md`：协议启用时已经存在的历史消息基线；这些历史项不得被新 worker 当成新任务重新处理。
- `chat/STATUS.md`：人类可读状态账本。

## message_id

对 `chat/to-gpt/<filename>.md`：

1. 读取该文件当前 Git blob SHA；
2. 消息按现有纪律是 immutable，禁止原地改写；
3. `message_id` 固定为：

```text
<filename-without-.md>--<full-blob-sha>
```

例如：

```text
2026-09-17-example--0123456789abcdef....
```

对应租约与完成记录：

```text
chat/claims/<message_id>.json
chat/completed/<message_id>.json
```

因为文件名和 blob SHA 都参与 ID，即使两份文档正文完全相同也不会因单独使用 blob SHA 而混为一条消息。

## worker 选择候选消息

每次 Scheduled Task 启动后必须按以下顺序：

1. 读取 `chat/LEASE_PROTOCOL.md` 与 `chat/QUEUE_BASELINE.md`。
2. 枚举 `chat/to-gpt/*.md`。
3. 排除 `QUEUE_BASELINE.md` 中列出的历史 path + blob SHA。
4. 对每个剩余消息计算 `message_id`。
5. 若 `chat/completed/<message_id>.json` 已存在：跳过。
6. 若 `STATUS.md` 已明确记录该精确 path/blob 为 `✅ 已解决` / `⛔ 不做` / `➖ 非请求`：跳过；可补写 completion marker，但不得重新执行业务动作。
7. 再进入 claim 流程。

默认一次 run **只领用并处理一条最老的未完成消息**。处理完后若还有明显余量可以继续下一条，但每条都必须单独 claim。

## 原子 claim

默认租约长度：**60 分钟**。

### 情况 A：claim 文件不存在

worker 生成：

```json
{
  "protocol_version": 1,
  "message_id": "...",
  "message_path": "chat/to-gpt/...md",
  "message_blob_sha": "...",
  "owner": "chatgpt-scheduled-task",
  "claim_nonce": "<claimed_at timestamp>",
  "claimed_at": "YYYY-MM-DDTHH:MM:SS+08:00",
  "lease_until": "YYYY-MM-DDTHH:MM:SS+08:00",
  "status": "processing"
}
```

然后用 GitHub **create-file** 语义创建 `chat/claims/<message_id>.json`。

- 创建成功：当前 worker 获得租约，可以处理。
- 因目标路径已存在而失败：**没有获得租约**，必须重新读取 claim，不能继续处理。

同一路径的 create-file 冲突就是第一次竞争的原子裁决点。

### 情况 B：claim 已存在且未过期

直接跳过该消息。不能因为 owner 名字同为 `chatgpt-scheduled-task` 就认为是自己；不同 Scheduled Task 都使用同一 owner 名称。

### 情况 C：claim 已过期

1. fetch claim，取得其当前 blob SHA；
2. 生成新的 `claim_nonce / claimed_at / lease_until`；
3. 用 **update-file + 旧 blob SHA** 尝试覆盖；
4. 更新成功：接管成功；
5. 更新发生 SHA conflict：说明别的 worker 已先续租或接管，当前 worker 必须放弃并重新读取。

这是 stale lease takeover 的 CAS 裁决点。

## 续租

若处理接近 45 分钟仍未完成，owner 应在继续产生不可逆副作用前续租：

1. fetch 自己当前 claim；
2. 确认 `claim_nonce` 仍等于自己最初拿到的 nonce；
3. 用当前 claim blob SHA 执行 update-file，将 `lease_until` 再延长 60 分钟；
4. SHA conflict 或 nonce 已改变 = 已失去所有权，必须停止产生新副作用，并重新核对实际状态。

普通 relay 工作预期远低于 60 分钟；续租只是异常长任务的保护。

## 完成与幂等

### 有回复 / 请求要发给 Hermes

回复文件名必须由原消息唯一派生：

```text
chat/to-hermes/<message_id>.md
```

不得生成 `reply-1/reply-2` 之类随机名字。

完成顺序：

1. 在执行任何代码/配置写入前后都核对当前仓库事实，操作尽量幂等。
2. 生成 deterministic reply 路径。
3. 用 create-file 创建 reply；若已存在，先读取核对，**不得再新建第二份回复**。
4. 创建 `chat/completed/<message_id>.json`。
5. 向 `STATUS.md` 追加最终状态行。STATUS 更新必须用其当前 blob SHA；冲突则 refetch、保留别人的新行后重试，禁止覆盖丢行。
6. claim 文件可以保留作为历史记录；后续 worker 以 `completed/` 为最终跳过依据。

如果 worker 在第 3 步之后、第 4 步之前崩溃，接管者发现 deterministic reply 已存在时，必须先核对该回复及真实副作用；确认工作已完成后只补 completion / STATUS，不得盲目重做。

### 无需回复的非请求

仍须创建 `completed/<message_id>.json` 并追加 `STATUS.md`（通常是 `➖ 非请求`），这样后续 worker 不会重复扫描。

完成记录格式：

```json
{
  "protocol_version": 1,
  "message_id": "...",
  "message_path": "chat/to-gpt/...md",
  "message_blob_sha": "...",
  "completed_at": "YYYY-MM-DDTHH:MM:SS+08:00",
  "status": "resolved|rejected|non-request",
  "evidence": "commit sha / deterministic reply path / verified state"
}
```

## 失败与恢复

- **读取失败 / GitHub 暂时不可用**：不处理，不凭缓存猜；下一轮再试。
- **claim 创建失败且无法确认原因**：视为未获得所有权，不处理。
- **处理过程中失去 lease**：停止新的副作用，重新读取 claim / completed / reply / 目标实际状态。
- **lease 过期接管**：接管者必须先检查已有 reply、STATUS 和真实代码/部署状态，再决定补收尾还是继续；不能从头无条件重放。
- **完成记录已存在**：永不重新执行该逻辑消息。

## 资源边界

ChatGPT 侧这个队列只允许普通 ChatGPT Scheduled Task 与已连接的 GitHub connector：

- 禁止 ChatGPT Work；
- 禁止 Codex / Codex automations / Codex CLI；
- 禁止 delegated workers/agents / Workspace Agents；
- 禁止任何会消耗用户 Work/Codex 共享 agentic allowance/credits 的路径。

若任务只能依靠上述能力完成，应通过 deterministic `to-hermes` 回复说明边界并停止，不得自行升级执行方式。
