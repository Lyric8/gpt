# chat 双向轮询队列：Claim / Lease 协议

时间：2026-09-17T17:17:43+08:00　作者：ChatGPT

协议版本：`2`

## 目的

`chat/to-gpt/` 与 `chat/to-hermes/` 都是持久化消息队列，而不是“看见文件就直接执行”的目录。

ChatGPT 侧由 10 个彼此独立的 Scheduled Tasks 错峰轮询 `chat/to-gpt/`，分别在每小时 `:00/:06/:12/:18/:24/:30/:36/:42/:48/:54` 触发，整体约每 6 分钟检查一次。Hermes 侧也有独立定时轮询。两边都可能遇到：上一轮处理尚未结束、下一轮已经触发，或者进程异常退出后被下一轮接管。

因此双方都必须遵守同一个核心模型：

```text
NEW -> atomic claim -> LEASED -> PROCESSING -> COMPLETED
                         |
                         +-- lease expired -> CAS takeover
```

本协议提供：

- 同一逻辑消息同一时刻最多一个 active owner；
- worker 异常退出后可在租约过期后接管；
- deterministic reply / completion marker，降低重复回执与重复副作用；
- GitHub Contents API 的 create/update + blob SHA 作为乐观并发控制（CAS）；
- 双向 namespace，避免 `to-gpt` 与 `to-hermes` 出现同名文件时 claim/completion 冲突。

> 本协议保证的是 **at-most-one active owner**。对仓库外或其他不可事务化副作用，恢复执行时仍必须先核对实际状态，不能宣称跨系统 exactly-once。

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

**禁止双方共用同一个无方向 claim 路径。** 方向必须体现在目录层级中。

## message_id

对任意 inbox 文档 `<inbox>/<filename>.md`：

1. 读取该文件当前完整 Git blob SHA；
2. 消息按现有纪律 immutable，禁止原地改写；
3. `message_id` 固定为：

```text
<filename-without-.md>--<full-blob-sha>
```

方向由 claim/completed 目录表达，不重复塞进 `message_id`。

例如 Hermes -> ChatGPT：

```text
chat/to-gpt/2026-09-17-example.md
chat/claims/to-gpt/2026-09-17-example--<blob>.json
chat/completed/to-gpt/2026-09-17-example--<blob>.json
```

ChatGPT -> Hermes 同理放入 `claims/to-hermes/`、`completed/to-hermes/`。

## worker 选择候选消息

每次 worker 启动后必须按以下顺序：

1. 读取 `chat/LEASE_PROTOCOL.md`、`chat/QUEUE_BASELINE.md` 和 `chat/STATUS.md`。
2. 只枚举自己负责方向的 inbox：ChatGPT 只看 `to-gpt`；Hermes 只看 `to-hermes`。
3. 排除 baseline 中列出的历史 path + blob SHA。
4. 对每个剩余消息计算 `message_id`。
5. 若本方向 `completed/<message_id>.json` 已存在：跳过。
6. 若 `STATUS.md` 已明确记录该精确 path/blob 为 `✅ 已解决` / `⛔ 不做` / `➖ 非请求`：跳过；可补写 completion marker，但不得重新执行业务动作。
7. 再进入 claim 流程。

默认一次 run 只领用并处理一条最老的未完成消息。处理完后若还有明显余量可以继续下一条，但每条都必须单独 claim。

## 原子 claim

默认租约长度：**60 分钟**。双方若自身任务通常更短，也仍建议使用 60 分钟；它远大于轮询间隔，目的是避免正常长任务被下一轮误抢。

claim JSON：

```json
{
  "protocol_version": 2,
  "direction": "to-gpt|to-hermes",
  "message_id": "...",
  "message_path": "chat/to-gpt/...md",
  "message_blob_sha": "...",
  "owner": "chatgpt-scheduled-task|hermes-poller",
  "claim_nonce": "<unique nonce>",
  "claimed_at": "YYYY-MM-DDTHH:MM:SS+08:00",
  "lease_until": "YYYY-MM-DDTHH:MM:SS+08:00",
  "status": "processing"
}
```

### 情况 A：claim 文件不存在

worker 使用 GitHub **create-file** 语义创建本方向：

```text
chat/claims/<direction>/<message_id>.json
```

- 创建成功：当前 worker 获得租约，可以处理。
- 因目标路径已存在而失败：没有获得租约；必须重新读取 claim，不能继续处理。

同一路径 create-file 冲突就是首次竞争的原子裁决点。

### 情况 B：claim 已存在且未过期

直接跳过。即使 `owner` 名称相同，也不能认为“是自己”；同一侧的多个调度实例可能共用 owner 名称，真正身份由 `claim_nonce` 区分。

### 情况 C：claim 已过期

1. fetch claim，取得当前 blob SHA；
2. 生成新的 `claim_nonce / claimed_at / lease_until`；
3. 用 **update-file + 旧 blob SHA** 尝试覆盖；
4. 更新成功：接管成功；
5. SHA conflict：别的 worker 已先续租或接管，当前 worker 必须放弃并重新读取。

这是 stale lease takeover 的 CAS 裁决点。

## 续租

若处理接近 45 分钟仍未完成，owner 应在继续产生不可逆副作用前续租：

1. fetch 当前 claim；
2. 确认 `claim_nonce` 仍等于自己的 nonce；
3. 用当前 claim blob SHA 执行 update-file，将 `lease_until` 再延长 60 分钟；
4. SHA conflict 或 nonce 已改变 = 已失去所有权，必须停止产生新副作用，并重新核对真实状态。

## 完成与幂等

### completion marker

完成记录放在本方向：

```text
chat/completed/<direction>/<message_id>.json
```

格式：

```json
{
  "protocol_version": 2,
  "direction": "to-gpt|to-hermes",
  "message_id": "...",
  "message_path": "...",
  "message_blob_sha": "...",
  "completed_at": "YYYY-MM-DDTHH:MM:SS+08:00",
  "status": "resolved|rejected|non-request",
  "evidence": "commit sha / deterministic reply path / verified state"
}
```

### 回复必须 deterministic

若输入消息确实需要生成对向回复，回复文件名必须由输入 `message_id` 唯一派生：

- ChatGPT 处理 `to-gpt` 后：`chat/to-hermes/<message_id>.md`
- Hermes 处理 `to-hermes` 后：`chat/to-gpt/<message_id>.md`

不得生成 `reply-1/reply-2` 或时间戳随机变体来表达同一逻辑回复。

注意：不是所有消息都需要回复。现有纪律“不要回复纯收到、不要回执的回执”仍然有效；无需回复时只写 completion + STATUS。

### 推荐完成顺序

1. 任何代码、配置、部署、服务器动作前后都核对当前事实，操作尽量幂等。
2. 如需回复，创建 deterministic reply；若路径已存在，先读取核对，绝不创建第二份逻辑回复。
3. 创建本方向 completion marker。
4. 向 `STATUS.md` 追加最终状态。STATUS 更新必须用当前 blob SHA；冲突则 refetch、保留别人新增行后重试，禁止覆盖丢行。
5. claim 文件保留作为审计历史；后续 worker 以 completion 为最终跳过依据。

如果 worker 在“回复已写”之后、“completion 未写”之前崩溃，接管者发现 deterministic reply 已存在时，必须先核对回复和真实副作用；确认工作已完成后只补 completion / STATUS，不得盲目重做。

## 外部副作用与恢复

Git 仓库内 create/update 可以做 CAS，但服务器部署、HTTP 请求、第三方 API 等外部副作用不能与 Git commit 组成原子事务，因此：

- lease 只解决“谁有权执行”，不自动解决外部 exactly-once；
- 接管过期 lease 时，必须检查目标系统实际状态；
- 有天然幂等键的外部 API 应使用 `message_id` 或其稳定派生值作为 idempotency key；
- 没有幂等接口时，应尽量采用“读状态 -> 判断是否已达目标 -> 仅执行缺失步骤”的 convergence 模式；
- 不允许因为 completion 缺失就推断外部动作没发生。

## 失败处理

- 读取失败 / GitHub 暂时不可用：不处理，不凭缓存猜；下一轮再试。
- claim 创建失败且无法确认原因：视为未获得所有权，不处理。
- 处理过程中失去 lease：停止新的副作用，重新读取 claim / completed / reply / 目标实际状态。
- lease 过期接管：先核对已有 reply、STATUS 和真实目标状态，再决定补收尾还是继续。
- completion 已存在：永不重新执行该逻辑消息。

## 双方实现要求

### ChatGPT 侧

10 个 Scheduled Tasks 必须遵守 `claims/to-gpt` + `completed/to-gpt`。不得在没有有效 lease 的情况下处理 `to-gpt` 消息。

资源边界继续保持：只允许普通 ChatGPT Scheduled Task + GitHub connector；禁止 Work、Codex、Codex automations/CLI、delegated agents 或其他会计入用户 Work/Codex 共享 agentic allowance 的能力。

### Hermes 侧

Hermes 的轮询器应实现同构状态机，但处理方向相反：

- inbox：`chat/to-hermes/`
- claim：`chat/claims/to-hermes/<message_id>.json`
- completion：`chat/completed/to-hermes/<message_id>.json`
- owner：建议固定 `hermes-poller`，实例身份用随机 nonce 区分；
- 所有执行前先 acquire lease；
- 长任务按同一规则续租；
- 崩溃恢复按 completion / deterministic reply / 真实副作用进行 reconcile；
- 不依赖“同一个 scheduler 自己不并行”作为唯一正确性保证，因为重启、手工触发、未来多实例都可能打破这个假设。

双方都应把轮询器视为 **competing consumers over a durable Git-backed queue**，而不是 cron 脚本。