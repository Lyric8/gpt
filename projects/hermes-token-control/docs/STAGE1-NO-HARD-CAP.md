# Stage 1：无硬闸 token 压降落地规格

版本：1.0  
适用分支：`gpt/20260918-token-audit`  
状态：**设计与可执行产物已提交；未部署生产**

## 0. 最终裁决

阶段一**不接入 token / 请求预算硬闸**。旧版 `Governor.admit()`、`Policy.input_hard`、`task_calls`、`task_input` 等硬拒绝语义保留为实验/未来可选控制面代码，但本阶段不得接进 Hermes 真实 provider send path，也不得因为预算、累计 token、累计请求数而拒绝老板交互通道的请求。

阶段一的收益主体固定为三件事：

1. **轮询 / 巡检零模型化**：无新事件、健康探针、已知 runbook 都由确定性脚本处理，探针轮次模型调用 = 0。
2. **上下文治理**：48K 触发整理；64K 触发强告警与分段，但不是“任务拒绝”。先落完整证据，再用 manifest + 哈希替换大结果，只删除被 checkpoint 明确覆盖的完整已结束回合；仍大则分段。
3. **记账 + 告警**：按真实 `session_model_usage` 记 gross / 非缓存输入 / cache read / cache write / output / cost。超目标只告警并要求整理，不阻塞发送。

唯一仍可硬失败的是**真实协议 / 数据完整性 / provider context window**：例如 payload 本身违反供应商实际窗口、未完成 tool group 被破坏、证据哈希不一致、远端 lease/CAS 失效。这些是正确性边界，不是成本预算闸。

---

## 1. 本阶段产物

新增文件：

- `config/stage1-native-overlay.yaml`：仅上下文压缩 overlay，无 provider-send 预算 gate。
- `config/stage1-job-contract.json`：8 类常驻任务的零模型化契约、退出码、失败语义与软调用目标。
- `hermes_token_control/stage1.py`：非阻塞 Stage1 advisory；`allow_task` 永远为 `true`，输出 `SEND / COMPACT / SEGMENT` 与 warning/strong 告警。
- `hermes_token_control/source_scan.py`：按 `source_path + source_blob_sha` 做事件身份的零模型 Git 扫描器；不再用 HEAD 相等作为“无新事件”快速判定。
- `tests/test_stage1.py`：无硬闸与 source identity 的本地 Git 回归测试。

旧版 `config/native-overlay.yaml`、`governor.py`、`provider.py`、`docs/PLAN.md`、`docs/INTEGRATION.md` 仍保留历史审计价值；其中任何“超预算拒发 / WAITING_BUDGET / provider send hard gate”描述在 Stage 1 上线语义上均由本文覆盖。

旧 `SHA256SUMS` 是既有 25 个文件的历史清单，**不覆盖本轮新增 Stage1 文件**；本轮新增内容以 Git commit/tree/blob 为不可变证据。若需要离线包，再由发布阶段针对最终 commit 重新生成一份新的全量 manifest，不能伪称旧清单已经覆盖新增文件。

---

## 2. 压缩 overlay：精确内容与合并规则

生产候选 overlay 的完整内容就是：

```yaml
compression:
  enabled: true
  threshold_tokens: 48000
  target_ratio: 0.25
  protect_last_n: 8
  protect_first_n: 3
  in_place: true
  idle_compact_after_seconds: 0
  proactive_prune_tokens: 0
```

来源文件：`config/stage1-native-overlay.yaml`。

### 2.1 合并纪律

不得覆盖整份生产 `config.yaml`。实施者在宿主上：

1. 对当前 `config.yaml` 做时间戳备份并记录 SHA-256。
2. 读取安装版本实际 schema，确认上述 `compression.*` 字段真实存在、类型一致；若字段未知或语义变化，**退出，不猜默认值**。
3. 只深合并 `compression` mapping；credentials、provider/model、routes、channels、sender、jobs、systemd 参数保持原样。
4. 合并后做结构化读回，逐键比对期望值，并确认除 `compression.*` 外无意外变化。
5. 先在影子/维护窗口验证，再重启。

> **凡是需要修改生产配置或重启网关：必须老板在场，并且必须在网关进程之外执行。** 当前交付不执行生产修改、不停止 cron、不重启服务。

### 2.2 48K / 64K 的语义

- `<48K`：正常发送。
- `>=48K`：触发 `COMPACT`。整理之后重新计数；不是拒绝任务。
- `>=64K`：触发 `SEGMENT` + strong alert。先完成同样的证据落盘/manifest/checkpoint 处理，再把源工作拆成可独立验证的段；任务继续存在，不因预算消失。
- 最终每个实际请求仍必须满足**真实目标 provider/model 的 context window**。真实 context window 是协议约束，不得拿 64K 冒充模型配置。

---

## 3. 上下文治理：永远不以预算为理由阻塞业务任务

触发整理时固定按下面的顺序执行：

### 3.1 证据先落盘

任何大日志、源码、HTTP/body、浏览器复制内容、测试输出、命令输出，必须**先以完整字节内容持久化**，记录至少：

```text
artifact path / object id
sha256
byte size
source identity / version
producer command or tool
exit/status
captured_at
```

禁止“先把几十万 token 全量塞进模型，模型看完后才说已落盘”。节省发生在**模型入口之前**。

### 3.2 大结果换 manifest + 哈希

模型上下文中只保留结构化 manifest，例如：

```json
{
  "kind": "artifact-manifest",
  "sha256": "...",
  "bytes": 1234567,
  "source": "...",
  "summary": "mechanically derived metadata only",
  "failed_ids": ["..."],
  "read_ranges": [{"offset": 0, "length": 4096}]
}
```

需要细节时按哈希 + byte range 定点读取；不能通过重新执行昂贵工具来“恢复上下文”。

### 3.3 只移除 checkpoint 覆盖的完整回合

移除单位必须是一个完整、已经结束的 user → assistant/tool transaction；不能拆 assistant tool call 与对应 tool result，不能丢原始用户目标/约束，不能删未完成工作。

`covered_turn_hashes` 只能来自受信任 checkpoint 构建器已经验证并引用了对应事实版本的回合；禁止把全部历史哈希直接标成 covered。

### 3.4 重算请求体

整理后用真实 provider payload 计数。工具 schema、system/developer 规则、当前原始请求、reasoning/framing 的实际计数规则都必须进入计数范围。

### 3.5 仍大则分段，不拒绝任务

若当前不可分的正确性上下文仍过大：

1. 保存 root task capsule（目标、约束、source versions、已验证事实、待办、下一步）。
2. 把源工作拆成可独立验证段；每段读取所需 artifact 范围。
3. 每段结果先持久化，再回写 capsule。
4. 最终段汇总时按哈希引用，不重复灌入全部原始证据。

这与“超预算不发请求”不同：前者是**改变表示与工作切片后继续工作**；后者是成本闸，Stage 1 禁止。

---

## 4. `stage1.py` 的接入边界

`hermes_token_control.stage1.advise()` 是 advisory，不是 admission gate：

- `allow_task` 始终为 `true`；
- `request_action` 为 `SEND / COMPACT / SEGMENT`；
- `severity` 为 `ok / warning / strong`；
- 48K / 64K 与每段 6 / 12 次 provider send 都只触发整理和告警；
- period gross 超目标同样只告警。

**Stage 1 不得调用旧 `Governor.admit()` 来决定老板请求是否允许发送。** `Governor` 可以保留在离线测试、未来可选硬闸研究或非老板通道的后续灰度分支，但默认关闭，且不是本轮部署项。

未来如果重新讨论硬闸，至少必须同时满足：

1. 显式 feature flag，默认关闭；
2. 老板交互通道永久豁免；
3. 先 shadow 计数，再 alert-only，再经过老板在场验证后才讨论 block；
4. 所有 provider physical retry/fallback/auxiliary path 均被统一计数，不能只拦主调用；
5. 可一键回滚且不会清空账本。

---

## 5. 定时任务零模型化

权威机器契约：`config/stage1-job-contract.json`。

当前证据只给出了任务标题/调度/是否 agent，**真实 scheduler ID 是 `?`，不可猜**。因此 Stage 1 在修改 `jobs.json` 前必须先做本机绑定：读取真实 jobs schema，按 `title + schedule + mode` 找到唯一对象，并保存：

```text
job id
完整 schedule
当前 enabled 状态
当前执行入口/prompt/script
投递地址 / notification 配置
工具权限
回滚所需原始 JSON
```

任何 0 个或 >1 个候选都退出码 `22`，不改 jobs。

### 5.1 统一退出码

```text
0   成功扫描；无新的确定性工作
10  有新 source 或已有 due/pending 工作，需要 deterministic dispatcher
20  观察/网络/解析/基础设施错误；seen state/cursor 不得推进
21  协议或配置漂移；需人工复核，不得把它解释成无变化
22  scheduler 绑定缺失/歧义；禁止改 jobs
30  健康故障/incident 已持久化并进入 durable alert
```

所有探针/巡检正常轮次 `provider_calls = 0`。

### 5.2 收件箱（5 分钟）

新入口使用 `hermes_token_control.source_scan` + deterministic dispatcher。

事件身份：

```text
(source_path, source_blob_sha)
```

Git commit HEAD 仅用于获取一次一致的树快照，**不是事件身份，也不是“HEAD 没变 => 无事件”的判定条件**。

无新事件：完整扫描成功后，所有当前 source path+blob 均已出现在本地 reconciliation/event 表，且没有到期 retry/pending。

失败：fetch/ls-tree/cat-file/protocol 校验/SQLite 任一失败 => 20/21；不得推进 seen state，不得返回 unchanged。

真正需要推理的交接消息仍保留 agent，但 agent 只在 source 已由 deterministic dispatcher 获取现行 message lease、并排除 completion/STATUS 后启动。目标每个 reasoning segment 4～6 次 physical provider send；>6 warning、>12 strong alert，**不因数字本身拒绝任务**。

### 5.3 发布兜底与核验（1 分钟）

探针本身 no_agent：每分钟仍检查部署健康、目标 release/source identity 与已验证 deployment receipt。

无事件条件必须同时成立：

- 对应 release/request 的 `source_path + source_blob_sha` 已有 verified receipt；
- 当前生产 deploy identity 与 receipt 一致；
- 健康探针通过。

网络/HTTP/身份/receipt 读取失败不是“无变化”，而是 20/30；证据不明确时**不部署**。

已知发布/回滚 runbook 由脚本执行；未知 incident 才一次性升级小上下文 agent，目标 <=4 provider send 后 checkpoint/告警。

### 5.4 sender 崩溃修复（10 分钟）

优先交给 systemd/process supervision + deterministic health/runbook。健康、outbox 为空或持续推进、无未对账 incident => 0。

重复相同 crash-loop 按稳定 incident identity 合并，不每 10 分钟重新叫模型。未知根因才进入一次 incident agent，目标 <=4 provider send。

### 5.5 两个“取 GPT Pro 答复”任务（8 / 10 分钟）

改为 no_agent retrieval state machine：只有存在 outstanding request identity 时检查；找到与该 request 精确绑定的 terminal assistant response artifact 才结束。

DOM/network/parse 结果不确定 => 20，保持 outstanding；超过 deadline => durable alert。不能让模型每轮盯网页判断“还没好”。真正无法机械解析的终态内容只允许单次受控升级。

### 5.6 已经 no_agent 的三项

以下保持 no_agent，不重新申领节省收益：

- ChatGPT 长期会话自检；
- slot 轮换检查；
- 回复救生员。

回复救生员 / sender 补发必须独立于 token advisory；即使 gross 已超目标，也不能停止补发。

---

## 6. 零模型 Git 扫描器

新入口：

```bash
python3 -m hermes_token_control.source_scan \
  --bare "$HOME/.hermes/token-control/chat-cache.git" \
  --state "$HOME/.hermes/token-control" \
  --protocol config/protocol-snapshot.json \
  --inbox chat/to-hermes/
```

它每轮：

1. fetch 当前 `chat` 快照；
2. 校验三份批准协议 blob；
3. 枚举 inbox 下每个 `.md` 的 blob；
4. 以 `source_path + source_blob_sha` 做 `INSERT OR IGNORE`；
5. 检查 due local retry；
6. 只输出结构化状态，不启动模型。

与旧 `git_observer.py` 的关键区别：旧实现有 `if head == old: return UNCHANGED`；Stage 1 扫描器**不使用这个 HEAD 快筛作为事件语义**。这也保证“本轮 HEAD 未变化但本地 retry 到期”仍会返回 pending/dispatch_required。

本地 SQLite 仍只做调度日志；跨执行者执行权始终以 Git message lease / resource lease / completion / CAS 为准。

---

## 7. 记账与告警

### 7.1 真实账本差分

使用现有 `accounting.py`，它按：

```text
(session_id, model, billing_provider, billing_base_url, billing_mode, task)
```

对累计计数做两次 snapshot 差分，覆盖：

```text
api_call_count
input_tokens
cache_read_tokens
cache_write_tokens
output_tokens
reasoning_tokens
estimated_cost_usd / actual_cost_usd（可用时）
```

执行：

```bash
STATE="$HOME/.hermes/token-control"
mkdir -p "$STATE/accounting"
chmod 700 "$STATE" "$STATE/accounting"

python3 -m hermes_token_control snapshot \
  --db "$HOME/.hermes/state.db" \
  --out "$STATE/accounting/before.json"

# 执行一段明确、可比的 accepted workload

python3 -m hermes_token_control snapshot \
  --db "$HOME/.hermes/state.db" \
  --out "$STATE/accounting/after.json"

python3 -m hermes_token_control delta \
  "$STATE/accounting/before.json" \
  "$STATE/accounting/after.json" \
  > "$STATE/accounting/delta.json"
```

当前 Hermes 实测基线：`2,816` 次 API 调用、gross `475,298,116`；五分之一目标按该快照为：

```text
95,059,623 gross tokens
```

这个数是**阶段目标/告警线，不是请求拒绝线**。后续基线继续增长时，验收必须固定 before/after 工作窗，不能拿不断增长的 lifetime total 直接比较两个版本。

### 7.2 durable alert

`stage1.alert_payload()` 只生成无凭据结构化 payload。接入现有 sender 时：

- 使用稳定 task/incident identity 作为 idempotency key；
- 告警内容包含 snapshot/delta 的 artifact hash；
- sender 凭据只从本机现有 secret source 获取，不写 repo / chat；
- sender 自身失败进入现有 durable outbox / 救生员路径；
- 告警失败不能变成“于是阻塞老板请求”。

---

## 8. 影子验收：证明省的是 token，不是少干活

### 8.1 本地测试

在 artifact branch 的 `projects/hermes-token-control`：

```bash
python3 -m unittest discover -s tests -v
```

此前 Hermes 在旧 commit `56b58a84...` 独立复跑为 67 tests / OK。本轮新增 `test_stage1.py` 有 8 个测试，因此**如果既有 67 项未变化，发现数应为 75**；这只是静态预期，当前 GPT 侧只允许 GitHub connector，未执行 Python，必须由 Hermes 本机重新跑并记录实际结果。未实跑前不得把“75”写成通过事实。

### 8.2 source identity / 真失败反例

至少覆盖：

1. source `path+blob` 新增 => queued +1；
2. 只写 STATUS / completion 造成 branch HEAD 改变，source 集合不变 => queued +0；
3. 同一路径 blob 改变 => 新事件；
4. source 集合不变但 retry 到期 => `dispatch_required=true`；
5. protocol blob 漂移 => exit 21，状态不推进；
6. Git/network 错误 => exit 20，状态不推进；
7. 真正 action_required source => deterministic dispatcher 获取远端 message lease 后仍能完整处理；
8. duplicate scan 不重复业务副作用。

这里第 5/6 项就是“真失败仍被处理”的反例：失败被显式升级为 ERROR/DRIFT，**绝不伪装成无变化**。

### 8.3 100 轮 shadow

旧 agent 保持生产执行权，新 no_agent scanner 只观察、不产生业务副作用，至少记录 100 轮：

```text
scan count
new source count
pending/due count
exit code
provider_calls (=0)
source identities
old agent 实际处理的 source identities
completion identities
```

要求 scanner 与旧路径对 source 检出无漏项；它多报历史源可以由 deterministic reconciliation 排除，不能靠发明 watermark 跳过。

### 8.4 同等工作量 A/B

A/B 的 accepted workload 至少匹配：

```text
接收 source 数
action_required source 数
最终 completion 数
失败 source 数
重试数
部署/发送等必需验证集合
通知完成数
P95 队列年龄 / 完成时延
```

再比较 `accounting delta`。只有工作量与可靠性没有缩水，gross 降低才算 token 节省。

旧 PLAN 中 81～95%（收件箱）、90～99%（发布兜底）、95～100%（取答复 / sender 修复）都是**模型 token 预测区间，不是本轮实测结论**。阶段总目标仍以同等工作量 gross <=20% 为最终验收。

---

## 9. 迁移顺序

### Phase 0：只读 shadow

- 部署私有 `$HOME/.hermes/token-control` state；
- 跑新 scanner / accounting；
- 旧任务继续执行；
- 新路径不拿远端执行权、不部署、不发通知。

### Phase 1：no_agent detector shadow

逐任务把 detector 注册为 no_agent，但保持 passive；先验证 scheduler ID、调度、退出码、日志和 0 provider call。

### Phase 2：一次迁一个任务

每个任务严格：

1. 保存旧 job 完整 JSON + SHA；
2. 新 no_agent 路径发现真实待办；
3. 在测试/维护条件下完成一次完整 `detect -> lease -> business -> verify -> reply/completion -> alert`；
4. 读回远端状态证明结果与 source identity 绑定；
5. **然后**暂停对应旧 agent；
6. 再读 jobs 状态证明旧路径确实停止；
7. 观察一个完整调度窗。

不能让两个不共享同一现行 message/resource lease 的执行器同时产生副作用。

### Phase 3：compression overlay

只有 Phase 0/1/2 稳定后再应用 `stage1-native-overlay.yaml`。

**必须老板在场、且在网关进程之外执行备份、合并、重启和回滚验证。**

Stage 1 到此结束；不接 provider-send hard budget gate。

---

## 10. 回滚

### 10.1 no_agent 任务迁移回滚

1. 停止/disable 新 deterministic executor 的**副作用执行**，scanner 可继续只读。
2. 核对 remote message/resource lease、completion、真实目标状态与本地 pending，确认没有未知 in-flight。
3. 恢复旧 job 的原始 JSON / enabled 状态。
4. 读回 scheduler 状态，确认只剩一个有副作用 owner。
5. 保留 `$HOME/.hermes/token-control` 的 event/accounting/outbox 数据，不删除。

### 10.2 compression overlay 回滚

1. **老板在场、网关进程之外**停止/重启操作。
2. 恢复应用前 `config.yaml` 备份。
3. 校验 SHA 与结构化差异只撤销本轮 compression mapping。
4. 在进程外重启网关并做健康/交互/工具回合恢复验收。
5. 保留 accounting 证据，不清账。

### 10.3 已成功外部副作用

不“回滚”已经成功发送的消息、已成功发布的 release 或已经完成的远端写入。恢复时读取真实状态，只补缺失步骤。

---

## 11. 未完成项与硬门槛

当前交付**没有**做到以下事情，因此不得表述为已上线：

- 未在 Hermes 宿主运行新增 8 项测试；
- 未跑 100 轮 shadow；
- 未取得真实 jobs ID / jobs.json schema 并完成唯一绑定；
- 未注册 no_agent 新任务；
- 未暂停任何旧 agent cron；
- 未修改生产 `config.yaml`；
- 未重启网关；
- 未接入现有 sender 的 alert payload；
- 未完成同等工作量 A/B；
- 未证明最终 gross <=95,059,623；
- 未对生产做任何 provider-send hard gate（按 Stage 1 裁决，本来就不应做）。

这些门槛全部通过前，状态只能是：

```text
PUBLISHED_NOT_DEPLOYED
```

## 12. 一句话实施原则

**把“要不要调用模型”从 cron 默认动作改成事件升级动作；把“大上下文”改成可验证 artifact + manifest；把预算从“拦截器”改成“仪表盘 + 告警器”。**
