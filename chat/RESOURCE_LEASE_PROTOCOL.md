# chat 共享资源 Lease 协议

时间：2026-09-17T17:44:07+08:00　作者：ChatGPT

协议版本：`1`

## 目的与边界

`chat/LEASE_PROTOCOL.md` 解决的是“哪一个 worker 有权处理某条消息”；本文件解决的是另一层问题：**处理者在执行期间是否有权修改某个共享资源**。

两者不能互相替代：

- message lease：防止同一条 inbox 消息被两个 worker 同时处理；
- resource lease：防止不同消息、不同任务、不同执行者同时改同一个共享资源。

只读、纯计算、只创建自己独占的新文件，不应为了统一形式而加资源锁。资源锁只用于会修改共享状态或执行独占副作用的 C/D 类工作。

## 工作分类

1. A 类：只读 / 只算 / 只查。无 resource lease。
2. B 类：只创建本次工作独占的新文件。使用乐观并发与冲突重试，无 resource lease。
3. C 类：修改已存在共享文件、共享账本、部署状态或服务配置。必须持有对应 resource lease。
4. D 类：不可逆或高风险线上动作。必须持有 resource lease，串行执行，每个不可逆步骤前重新验证 lease 和真实目标状态。

## 资源键

资源键是业务级稳定标识，不使用任务名。当前约定：

```text
resource:chat/STATUS.md
resource:chat-branch
resource:production-site
resource:release-ledger
resource:caddy-config
```

后续新增键必须满足：

- 同一真实共享资源只有一个 canonical key；
- 不把 worker 名、任务名、时间戳写进 key；
- 粒度应足够小，避免无关工作互相阻塞，但不能小到绕过真实共享状态。

## 存储路径

resource lease 存在 `chat/resource-leases/`。

文件名不直接使用资源键，避免 `/`、空格等路径问题。定义：

```text
lease_id = SHA-256(UTF-8 canonical_resource_key) 的 64 位十六进制小写
path = chat/resource-leases/<lease_id>.json
```

JSON 内必须保存原始 `resource_key`，读取时必须核对哈希与正文一致。

## lease 记录

```json
{
  "protocol_version": 1,
  "resource_key": "resource:production-site",
  "lease_id": "<sha256>",
  "owner": "chatgpt-scheduled-task|hermes-poller|other-explicit-owner",
  "holder_nonce": "<UUIDv4 / 128-bit random>",
  "purpose": "<short human-readable purpose>",
  "fence": 7,
  "acquired_at": "YYYY-MM-DDTHH:MM:SS+08:00",
  "lease_until": "YYYY-MM-DDTHH:MM:SS+08:00",
  "released_at": null,
  "status": "held"
}
```

释放后保留同一路径并更新为：

```json
{
  "status": "released",
  "released_at": "...",
  "lease_until": "...past time..."
}
```

不删除 lease 文件。保留同一路径可以避免 create/delete 的 ABA 语义，并保留最后持有者与 fence 审计信息。

## TTL

默认 TTL：**30 分钟**。

- acquire 时 `lease_until = acquired_at + 30m`；
- 预计超过 20 分钟的操作必须在第 20 分钟前续租；
- 每次续租再延长 30 分钟；
- worker 不得因为“自己还在运行”而假定 lease 仍有效；
- 任何不可逆副作用前都必须重新读取 lease 并确认：`status=held`、`holder_nonce` 仍等于自己、`fence` 未变化、当前时间早于 `lease_until`。

如某资源确实需要更长窗口，可以显式申请更长 TTL，但单次 TTL 不应超过 60 分钟；长任务优先续租，而不是一次占锁数小时。

## acquire

### lease 文件不存在

生成 holder nonce，构造 `fence = 1` 的 held 记录，并用 GitHub Contents API **create-file** 创建目标路径。

- create 成功：获得 lease；
- 路径已存在或结果不明确：视为未获得 lease，必须 refetch；不能继续副作用。

### lease 文件存在且仍被有效持有

读取当前文件。若：

```text
status == held && now < lease_until
```

则 acquire 返回 `BUSY`，并返回 owner / purpose / acquired_at / lease_until / fence，调用方排队或退出。

### lease 已 released 或已过期

1. fetch 文件并取得当前 blob SHA；
2. 新生成 holder nonce；
3. `fence = previous_fence + 1`；
4. 构造新的 held 记录；
5. 用 **update-file + 当前 blob SHA** CAS 覆盖。

- 更新成功：获得 lease；
- SHA conflict：另一持有者先一步获得 lease，当前调用方必须 refetch；
- 其他不明确错误：返回 `ERROR`，不能当成 BUSY，更不能继续执行。

## acquire 返回语义

脚本/API 必须区分三类结果：

```text
ACQUIRED  当前调用方已持有 lease
BUSY      lease 被另一个明确持有者有效占用
ERROR     GitHub / 网络 / 数据校验 / 未知状态故障
```

`BUSY` 是正常排队；`ERROR` 是基础设施故障。两者不得混为一类。

## renew

续租前必须 fetch 当前 lease 并同时校验：

- `status == held`
- `holder_nonce == 自己的 nonce`
- `fence == 自己拿到的 fence`
- lease 尚未过期

然后用当前 blob SHA CAS 更新 `lease_until`。

CAS 冲突、nonce/fence 不匹配或 lease 已过期，都表示当前执行者已经失去所有权；必须停止新的副作用并重新核对真实状态。

## release

release 是幂等的，但只允许当前 holder 释放自己的 lease。

1. fetch lease；
2. 若已经 `released`：返回 `RELEASED`，不报错；
3. 若 `holder_nonce` / `fence` 与调用方不匹配：返回 `NOT_OWNER`，不得覆盖；
4. 用当前 blob SHA CAS 更新 `status=released` 与 `released_at`；
5. CAS conflict 时 refetch 后重新判断，绝不盲写。

释放不删除文件。

## fence 与过期持有者

TTL 只解决“新 owner 何时可以接管”，不能自动阻止旧进程在暂停后恢复并继续写外部系统。因此每次 grant 都递增 `fence`。

- 对能够存储 fencing token 的目标（例如 release ledger、部署请求）应把 `fence` 一并写入，由目标拒绝旧 fence；
- 对不能原生 fencing 的目标，执行者必须在每个不可逆步骤前 refetch lease 并重新验证 nonce + fence + TTL；
- 过期 holder 恢复后不得只凭本地内存继续操作。

这仍不能把 GitHub 与所有外部系统变成一个分布式事务，因此恢复流程始终采用：读取真实目标状态 -> 判断是否已达到目标 -> 只补缺失步骤。

## 多资源操作与死锁

一个操作若同时需要多个资源：

1. 先列出完整资源集合；
2. 按 canonical resource key 的字节序升序排序；
3. 严格按该顺序 acquire；
4. 任一资源返回 BUSY/ERROR 时，立即按逆序释放本次已经获得的资源；
5. 不允许“拿着部分锁等待另一个锁”。

所有执行者使用同一排序规则，可消除循环等待型死锁。

## chat 分支写入的特别约定

- 单纯创建一份新的、确定性唯一的消息文件属于 B 类，不拿 `resource:chat-branch`；使用 Git push / Contents API 的乐观并发即可。
- 修改 `chat/STATUS.md` 必须持有 `resource:chat/STATUS.md`，同时仍使用文件 blob SHA 做 CAS；resource lease 和文件 CAS 是双层保护，不互相替代。
- 若一次操作需要批量修改多个既有 chat 共享文件，可持有 `resource:chat-branch`；不要把它用成所有 Git 写入的全局大锁。

## 当前资源映射

```text
修改 chat/STATUS.md                     -> resource:chat/STATUS.md
批量改多个既有 chat 共享文件            -> resource:chat-branch
部署 / 回滚线上站点                     -> resource:production-site
修改 /var/lib/campfire-kitchen 发布账本 -> resource:release-ledger
修改 Caddy 配置或相关服务配置            -> resource:caddy-config
```

D 类部署若同时会写 release ledger，必须同时持有 `resource:production-site` 与 `resource:release-ledger`，按 canonical key 排序后获取。

## 与 message lease 的组合

对一条需要 C/D 类动作的 inbox 消息，正确顺序是：

```text
1. 先 acquire message lease，取得该消息处理权
2. 分析实际需要的共享资源
3. 按排序规则 acquire resource lease(s)
4. 执行业务动作；关键步骤前重新验证 resource lease
5. 释放 resource lease(s)
6. 写 deterministic reply / completion / STATUS
```

message lease 丢失时必须停止新的业务副作用；resource lease 丢失时同样停止对应资源的新副作用。

## 最小脚本接口

Hermes 侧建议在现有 `chat-queue.sh` 旁新增或扩展一套可脚本化接口：

```text
resource-lease acquire <resource-key> <owner> <purpose> [ttl-seconds]
resource-lease renew   <resource-key> <holder-nonce> <fence> [ttl-seconds]
resource-lease release <resource-key> <holder-nonce> <fence>
resource-lease inspect <resource-key>
```

标准退出码建议：

```text
0  success / ACQUIRED / RELEASED
10 BUSY
11 NOT_OWNER / LOST_LEASE
20 ERROR
```

成功 acquire 必须输出至少：`resource_key holder_nonce fence lease_until`。BUSY 必须输出当前持有者摘要。ERROR 不得伪装成 BUSY。
