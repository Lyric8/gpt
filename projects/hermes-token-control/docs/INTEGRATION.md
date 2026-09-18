# 接入契约与机械验收

## 1. 实施者需要从本机读取的权威对象

本次附件仅含计量聚合和工作流描述，没有生产 fork、config.yaml、jobs.json 和 80 多个脚本的全文。实施者从本机固定一份版本清单：Hermes commit + dirty working tree 文件 SHA；实际 provider/model/API 模式、tokenizer/chat template；所有 cron 的真实 ID、脚本参数、投递地址；网关、sender、eval 的实际 systemd unit；当前 Git 协议三份文档的 blob SHA。敏感值只在本机，不上传凭据。

遇到未知字段不猜默认值，不直接重写整个 jobs.json/config.yaml，不为了使补丁匹配而升级 Hermes 大版本。这里交付的是完整源码文件，不是待套用的 diff。

## 2. 五个强制连接点

### 2.1 真实供应商发送点

将 `GuardedChatCompletions` 放在实际 payload 组装之后、SDK `.create()` 之前；封装实例使用已有 SDK 客户端，但 `max_retries=0`，HTTP transport 也不得透明重放。计数器收到完整 kwargs，包括 tools；返回 `TokenCount(tokens, versioned_method, certified_upper_bound)`。`context_window` 传目标模型核实后的实际窗口，不伪造为 64K；64K 是应用预算，不是模型配置。

`task` 来自稳定业务根 ID，不是随机会话 ID。多次分段、fallback、摘要、辅助判断都回到相同根 ID。没有根 ID 的模型调用是验收失败。适配器仅同步、非流式、单 choice 的 OpenAI-compatible Chat Completions；Responses/Anthropic/流式需要分别实现等价门禁，不得偷偷绕行或剥离 reasoning 内容。

传入预算器前按实际任务角色执行 `Governor.begin()`。角色不可由模型自行选择高额度逃逸。SDK 出错也已经预留请求；恢复时先对账 IN_FLIGHT，再决定明确重试。`BudgetStop` 在整个重试循环之外捕获；`IntegrityError` 不按瞬态网络错误重试。

### 2.2 上下文构造/压缩边界

`compact_at_boundary()` 在工具结果已完整返回的回合边界运行。传入：稳定 policy prefix、已结束的 history、以原始 user 请求开始的 current、已持久化 capsule、已被 capsule 覆盖的完整回合哈希、固定工具 schemas 和计数器。函数先归档完整历史，再逐组移除；当前需求保留，不拆 assistant/tool 调用组。

`covered_turn_hashes` 必须由受信任状态构建器在验证事实后生成，不能把所有历史哈希直接填入当“已覆盖”。胶囊中 verified 项引用对应 commit/source hash/test artifact，恢复前按实际权威版本重验；memory/skills 仅作导航。

原生压缩和本包压缩不能同时各自丢弃同一层历史。接入时选择一个控制者：保留 Hermes 的归档/摘要功能时，将本包作为最终请求硬门禁；使用本包投影时，将原生压缩限制为兼容归档路径。必须跑真实多轮工具恢复测试，避免两个压缩器互相误解未完成工具组。

### 2.3 工具结果适配

大输出直接写磁盘文件，然后哈希入库，再创建短 manifest，禁止工具先全量 stdout 进入模型、之后才“落盘省 token”。现有写文件/终端工具需在实际结果返回点接入这个顺序。

`run_read_batch(specs, store, cwd=...)` 只用于审定的独立只读检查。规格字段：`id`、`argv`（数组，禁止 shell 拼接）、`independent_read_only: true`、`timeout_seconds`、`max_output_bytes`。执行目录明确；每项结果完整性、退出码和失败列表归入 manifest。检查器本身需要可信，模型输出的“test passed”不构成结果。

归档引用按 SHA-256 读取，CLI `read` 只返回指定字节范围，仍需在模型入口进行 token 预算。4096 字节不等于 4096 tokens。单个工具输出上限 2K 是入口策略，而 artifact 预览字节上限是另外一个安全界限。

### 2.4 事件协调器

`git_observer.observe()` 的职责只有固定快照、协议版本检查、源 blob 扫描、入队和游标事务。它的 `wakeAgent=false` **不表示事件完成**，也不表示业务不需要模型。全量初始扫描结果先与当前远端 completion/历史约定对账，不能无脑把所有历史消息交给 agent。

协调器独立于观察器领取 `EventQueue.claim()` 到期事件：读取真实远端 message lease，必要时获取 resource lease，再执行既有业务 runbook。local epoch 只防本地过期 worker 提交本地完成，不赋予远端资源权限。对所有写操作再次验证远端 lease/fence/CAS；不能只在最初领取时看一眼。

lease TTL 和最长脚本时间联动：本地默认 TTL120 秒，执行者应在 TTL/3 以内续约（真实远端 TTL 按当前协议）；丢失任一租约后停止可中止的变更，结果不明时只对账，不盲目重试。

完成时先实现真实业务验证与远端回执、completion、STATUS 协议顺序和读回，再调用 `finish_local()`。receipt 必需 event_id、status=VERIFIED、source_version、remote_receipt_sha、remote_completion_sha、checks；所有 required_checks 均来自真实检查结果。把模型产出的 checks=true 直接传入视为集成失败。

事件超出尝试上限进入 BLOCKED，不自动删除；独立脚本监控 BLOCKED/队列年龄并通过现有 durable sender 发告警。该自动告警连接点需要接入现有 sender；本包不声称自带可用的微信通道。

### 2.5 通知 outbox

`finish_local()` 与待发 outbox 在同一 SQLite 事务提交。发送者按 event_id 做幂等协调。`acknowledge_notification()` 仅在现有发送者提供持久交付确认后调用；“成功放进另一个内存队列”不是已交付。远端微信不支持 exactly-once 时保留发送未知状态并对账，别用删队列模拟消重。

## 3. 影子观察器启动

以下路径仅创建本包私有缓存和日志，不动主仓库、主任务或现有状态库。需在本包目录运行，且主机已有 GitHub 访问权限：

```bash
STATE="$HOME/.hermes/token-control"
mkdir -p "$STATE"
chmod 700 "$STATE"
if [ ! -d "$STATE/chat-cache.git" ]; then
  git init --bare "$STATE/chat-cache.git"
  git --git-dir="$STATE/chat-cache.git" remote add origin https://github.com/Lyric8/gpt.git
fi
python3 -m hermes_token_control.git_observer \
  --bare "$STATE/chat-cache.git" \
  --state "$STATE" \
  --protocol config/protocol-snapshot.json
```

协议 blob 不匹配时输出 ERROR 并非零退出；先阅读当前协议，确认适配兼容后再更新批准的快照，不能自动把“最新哈希”当作批准。观察器不会在此启动业务 agent，因此不能仅执行这条命令就暂停旧收件箱。

正式 `no_agent` 由 Hermes 已支持机制运行经过审查的 wrapper；采用本机实际 CLI schema 创建，先验证新任务完整业务路径，再暂停旧任务。不要根据在线新版本文档盲写旧版 jobs.json。

## 4. 验收门禁

### 4.1 本地已覆盖

包内 67 项测试：完整归档/哈希损坏、预算拒绝/失败请求计数/重启/跨分段额度、工具组完整性、游标 CAS/去重/租约过期/补发事务、工具超时/输出超限、供应商适配器隐藏重试拒绝与输出截断、计量差分/计数回退、真实本地 Git 多文件 push/readback、自写 HEAD、源版本改变、协议漂移、历史长文件名无 checkout，以及并发 push 拒绝。

真实本地 Git 测试使用临时 bare 仓库，不是 GitHub 云端测试；供应商测试使用假客户端，不是模型调用；运行 Python3.13.5，并未在3.11执行。

### 4.2 部署前必须补齐

| 检查 | 通过条件 |
|---|---|
| 计数器与模式覆盖 | 所有现网 send 路径均有根任务账和准入，无旁路；actual prompt 不超过认证上界 |
| 原始证据 | 必需日志/代码/截图复制内容在进入可见裁剪前落盘；失败/缺页可检测 |
| 崩溃注入 | 至少覆盖发送预留后崩溃、业务写入后回执前崩溃、completion 后通知前崩溃；恢复不重复写、不丢通知 |
| 远端协议 | message/resource lease、fence、CAS 与现有 v3 兼容；接管重放只补缺项 |
| 停用旧任务 | 新路径完整执行验证成功且读取状态确认；两路径不能无共同 lease 同时做副作用 |
| 供应商限流/超时 | 重试实际请求计入；BudgetStop 不进入自动重试；未知 usage 保留额度 |
| 会话迁移 | 原始目标/约束不变，未结束工具组不丢，root budget不清零；恢复核对 source版本 |
| 验证与交付 | 同等任务的必需检查集合不缩小；部署读回绑定预期SHA；通知成功才确认 |
| 吞吐/时延 | 完成数量、队列年龄、BLOCKED数量、P95完成/通知时延均未通过延期或漏做恶化 |
| 节省 | 相同 accepted work 含所有辅助/重试后的 gross≤20%；美元/配额另按实际路由核对 |

出现前述失败项时不能把“67个单元测试通过”当成上线充分条件。

## 5. 回滚

私有预算库与事件库保留，不删除和清空。回退代码/config时暂停新事件领取，由现有旧路径在真实远端 completion/lease 与本地待办之间对账后恢复。已经产生的通知仍由单一 sender 补发；不回滚或重发已成功外部副作用。源数据库、原记录、租约和 completion 均为恢复依据。

若选择放宽 token 门禁来恢复吞吐，记录角色/任务/原因/审批与新预算，并诚实标记省 token 目标暂未达标，不能偷偷使用新的 task_id 逃过总额。

预算升级通过 `Governor.approve_extension()` 在受信任控制面执行；它要求 approval_id、审批者、原因和旧策略哈希 CAS，并保持原请求/分段账本。它不提供身份认证，认证由现有控制面完成，不得注册为模型可自由调用的工具。只能单调增加上限，不能清零；计数器不可信造成的 COUNTER_BREACH 不可用额度升级绕过。

预算获批升级后，恢复逻辑读取已持久化的 `tasks.policy`，不能重新用默认角色策略调用 `begin()` 覆盖它；策略不匹配会安全失败。首次创建才使用 `POLICIES` 默认值。
