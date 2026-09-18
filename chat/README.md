# chat —— 跨执行者交接频道

时间：2026-09-17T17:12:30+08:00　作者：ChatGPT
修订：2026-09-18T00:12:15+08:00　作者：ChatGPT

本目录只存在于 `chat` 分支，用于 ChatGPT、Hermes 与老板之间的文字交接；不要把 `chat` 分支合回 `main`。

## 目录

| 路径 | 用途 |
|---|---|
| `chat/to-gpt/` | Hermes / 老板交给 ChatGPT 的消息 |
| `chat/to-hermes/` | ChatGPT / 老板交给 Hermes 的消息 |
| `chat/claims/to-gpt/` | ChatGPT worker 的 message lease 记录 |
| `chat/claims/to-hermes/` | Hermes worker 的 message lease 记录 |
| `chat/completed/to-gpt/` | ChatGPT 已完成消息的机器去重记录 |
| `chat/completed/to-hermes/` | Hermes 已完成消息的机器去重记录 |
| `chat/resource-leases/` | 双方共享资源的 resource lease 记录 |
| `chat/LEASE_PROTOCOL.md` | 消息 Claim / lease / takeover / 幂等完成协议 |
| `chat/RESOURCE_LEASE_PROTOCOL.md` | 共享资源锁、TTL、fence、死锁规避协议 |
| `chat/QUEUE_BASELINE.md` | to-gpt 队列启用前的历史 activation baseline |
| `chat/STATUS.md` | 人类可读状态账本 |

## 文档与文件名纪律

协议 v3 起，人类可见的新文件不再把 message_id / blob SHA / 派生链塞进文件名。

新请求与回复统一：

```text
YYYY-MM-DDTHHMMSS+0800-<subject>.md
```

其中：

- 时间戳到秒，文件名中使用 `+0800`，避免 Windows 路径冒号；
- subject 是简短业务主旨，建议 ≤ 56 字符；
- 流转关系写正文里的 `source_path` / `source_message_id` / `source_blob_sha`；
- 新文档正文头部时间仍写 `时间：YYYY-MM-DDTHH:MM:SS+08:00　作者：<谁>`；
- 文档 immutable，需要更正就新增文件，禁止原地改写对方消息。

claim / completion 也使用短文件名，但原子 claim 有一个关键约束：

```text
claim:      <source-stable-timestamp>-claim-<subject>.json
completion: <created-timestamp>-completed-<subject>.json
```

claim 的时间戳必须来自 source message 的稳定时间，而不是“当前尝试 claim 的时间”。这样同一 source 的竞争 worker 才会命中同一个 create-file 路径，保留原子冲突裁决。详细规则以 `chat/LEASE_PROTOCOL.md` v3 为准。

历史 v2 的 SHA 链文件不要求全量重命名；新 worker 必须兼容旧路径，并通过正文稳定键索引新 marker / reply。

## 两层 lease：消息所有权 vs 资源所有权

两层 lease 不可互换：

- `chat/LEASE_PROTOCOL.md`：决定谁有权处理某条 inbox 消息；
- `chat/RESOURCE_LEASE_PROTOCOL.md`：决定当前处理者是否有权修改某个共享资源。

A/B 类只读、纯计算或创建本次独占新文件，不需要 resource lease。C/D 类修改既有共享文件、共享账本、部署状态、服务配置或执行高风险外部副作用时，必须同时满足 message lease 与对应 resource lease。

当前 canonical resource key：

```text
resource:chat/STATUS.md
resource:chat-branch
resource:production-site
resource:release-ledger
resource:caddy-config
```

多资源操作必须按 canonical key 字节序获取；任一 BUSY/ERROR 时，立即逆序释放本轮已获得的其他资源，不持部分锁等待。

## baseline、claim 与 completion

`QUEUE_BASELINE.md` 只处理 ChatGPT 侧启用 worker pool 时已经存在的历史消息，是一次性 migration watermark，不是长期状态库。

正常运行时：

1. source `path + blob SHA` 决定 message identity；
2. `message_id = <filename-without-.md>--<full-blob-sha>`，但 v3 起它写正文，不再强制写入文件名；
3. claim 决定 active owner；
4. completion + STATUS 表示逻辑处理已闭环；
5. reply / completion / claim 的关联关系通过正文 `message_id` / `message_blob_sha` / `source_message_id` 建索引；
6. completion 已存在的逻辑消息永不重新执行业务动作。

Hermes 侧协议 v2 接入前的历史 `to-hermes` 已补 completion，不另建 baseline。

## 时间戳规矩

正文和 STATUS：

```text
YYYY-MM-DDTHH:MM:SS+08:00
```

文件名：

```text
YYYY-MM-DDTHHMMSS+0800
```

统一使用 UTC+8 / `+08:00` 语义，不使用城市名代替时区。

## 自动轮询

Hermes 约每 5～6 分钟检查 `chat/to-hermes/`。

ChatGPT 使用 10 个彼此独立的普通 Scheduled Tasks，在每小时：

`00 / 06 / 12 / 18 / 24 / 30 / 36 / 42 / 48 / 54`

触发，整体约每 6 分钟检查一次 `chat/to-gpt/`。

双方都把 inbox 当成 durable Git-backed queue。每轮必须：

1. 重新读取最新 `LEASE_PROTOCOL.md`、`RESOURCE_LEASE_PROTOCOL.md`、`QUEUE_BASELINE.md`、`STATUS.md`；
2. 枚举本方向 inbox 并排除 baseline / completion / STATUS 已终结项；
3. 计算 source message_id；
4. 按 `LEASE_PROTOCOL.md` 获取有效 message lease；
5. 没拿到 lease 就 fail closed；
6. 只有 lease owner 可以继续业务判断；
7. 若修改 C/D 类共享资源，再取得 resource lease；
8. 回复前按正文 source identity 查重；
9. 完成后写 completion，并在持有 `resource:chat/STATUS.md` 时用当前 blob SHA CAS 追加 STATUS；
10. 过期接管前先核对 reply、completion、STATUS 与真实外部副作用，只补缺失步骤。

## STATUS

每处理完一份交接消息，在 `chat/STATUS.md` 追加一行。只追加，不覆盖历史。

修改 STATUS 属于 C 类共享写：

- 必须持有 `resource:chat/STATUS.md`；
- 同时必须基于 STATUS 当前 blob SHA 做 CAS；
- resource lease 与文件 CAS 是双层保护，不互相替代。

状态固定使用：`⏳ 待处理` / `🔧 处理中` / `✅ 已解决` / `⛔ 不做` / `➖ 非请求`。

## ChatGPT 资源边界

relay 只允许普通 ChatGPT Scheduled Tasks 与 GitHub connector。禁止升级到 ChatGPT Work、Codex、Codex automations/CLI、delegated agents、Workspace Agents 或其他会计入 Work/Codex 共享 agentic allowance 的路径。


## STATUS 账本分代（generation）与 generation0 legacy attestation

时间：2026-09-18T16:33:52+08:00　作者：Hermes

`chat/STATUS.md` 是**分代滚动**的账本：active 只保留固定 header + 本代元数据 + carry-forward 的未终结行 + 本代新增行；
每次滚动把滚动前的整份 STATUS **逐字节**复制进 `chat/status-archive/<rolled_at>-status-<源blob前12>.md`（不可变、永不删除）。

- 入口只有 `chat-queue.sh status-rollover [--check] [--force]`（两阶段：Phase A 写 archive → Phase B 以 S0 blob CAS 重写 active；
  Phase A 后 active 变了就保留 orphaned-prepared-snapshot 并安全中止，绝不覆盖别人的新行）。
- 资源集合 `{resource:chat-branch, resource:chat/STATUS.md}` 按 canonical key 升序获取、逆序释放。
- 机器终态权威是**接收方向精确 completion marker**；archive 只用于审计与 legacy repair，正常轮询不遍历。
- **64KiB hard ceiling 按 generation 判定**：generation 0 越线只 warn/CRITICAL（bootstrap grace，硬拦会锁死控制面并明确要求 rollover）；
  generation >= 1 越线 = 协议内在硬约束 → `status-append` 返回 `NEEDS_ROLLOVER`（rc=8）且**不写**，先 rollover 再重试。
- **新账本行的 blob 列一律写完整 40 位 Git blob SHA**；解析器兼容历史 `—` / 12 位 / 40 位三种，12 位仅 legacy/repair 路径按 prefix 解析且必须唯一命中。
- **legacy 豁免只允许 generation 0 -> 1 一次**，且只认 `chat/status-legacy/2026-09-18-generation0-bootstrap.json` 里**逐行枚举的 exact `row_sha256`**
  （不是“早于某日就算 legacy”的通用 cutoff，也没有环境变量放行口）。首次滚动成功后，generation 1 header 记录该 manifest 的 path + blob SHA；
  generation >= 1 出现缺 completion 的终态行一律 blocker。
