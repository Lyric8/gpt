# ask-stage1-redo：Stage A v2，无预算硬门

交付语义：**代码与规格可复现；未部署生产；未声称真实 token 已下降。**

## 0. 裁决与版本优先级

本文件是本次 `ask-stage1-redo` 的施工规格，覆盖旧 `PLAN.md`、`INTEGRATION.md` 和 `STAGE1-NO-HARD-CAP.md` 中冲突的 Stage A 语义。后续阶段不在本次修改范围。

**阶段一不设置任何预算发送许可，不因为 token、次数、累计用量、计量器不可用而拒发、排队等预算、要求加额度或中断老板请求。** 48K/64K 等都是整理与告警阈值，不是可用额度。模型判断有必要继续时照常发送。现有安全审批、远端租约、CAS、真实 provider 协议和窗口约束原样保留；它们不是预算拒发。

保留 agent 的类别不存在有限的硬调用上限。必须把“0 模型的探针能力边界”和“agent 的软目标”分开：前者不装模型能力，后者超标继续，不通过换 session/root ID 清账。

预算层只做三件事：记账；通过现有 sender 告警；改变表示方式但不中断请求。未来硬闸只能另案、默认关闭、永久排除老板交互通道；任何其他通道的启用也须老板亲自验证。本包没有可打开硬闸的运行时参数。

基线复核到 `Lyric8/gpt` 分支 `gpt/20260918-token-audit` 的 commit：

```text
e6f07d2ce7915146cd67c49f769ed37e54a84b62
```

该 commit 已存在第一份无硬闸修订。当前包是独立可运行的强化版：增加真正的发送旁路回退、durable incident/outbox、故障恢复后再发生的 episode 身份、真实本地测试与新分母预测。不依赖旧 `Governor`、`GuardedChatCompletions`、`Policy.input_hard`，也不导入旧包。

## 1. 交付范围与不伪造的宿主适配

`storage.py`：私有内容寻址归档、完整字节校验、事件表、按根任务/会话/分段的物理尝试记录、独立告警 outbox、已有 sender 的持久接收交接、受信任完成证明接入。

`probes.py`：真实 Git 零模型扫描；七类业务探针的严格 observation 校验；失败/恢复/复发状态机。Git 直接读取对象，不 checkout 历史长文件名；只对新源 blob 批量 cat-file。

`context.py`：大结果 manifest、完整工具回合判断、受信任 checkpoint 投影、出错发送原请求。已覆盖同步发送适配语义；**不是声称已经包住生产所有 SDK/流式/异步重试。**

`accounting.py`：SQLite WAL 一致只读快照与完整归因键累计差分；`projection.py`：三种明确假设的数字预测；`tests/`：全部本轮回归；`__main__.py`：可执行入口。

以下信息未随请求提供，不能虚构：真实 scheduler ID、各业务脚本全文、生产 Hermes fork 全文、微信 sender 的入队函数、浏览器会话绑定与 DOM 协议、所有 provider 发送函数签名。因此七类业务探针使用**受信任本机 adapter 产出的新鲜 observation**；本包没有把一份模拟 JSON 冒称真实健康检查。Git scanner 则是完整实现。

宿主必须接入的四个 adapter：实际健康/浏览器/送达账本观察器；现行 message/resource lease 业务协调器；已有 durable sender 入队器；生产 provider 全路径计量/请求投影器。这里交付了接口、失败语义、调用入口和验收，不替换业务授权与现网协议。

## 2. 数字判断：能不靠硬门达到五分之一，但不能无条件担保

本次固定基线按用户给出的舍入值：2,816 次调用，gross 475,300,000，目标 <=95,060,000。旧预测文件使用 443.9M，不能直接沿用。既有规格另有精确值 475,298,116；只有从实际账本快照确认后才可改用该值，其整 token 五分之一是 95,059,623，不把两种精度混写。

主会话 1,354 次调用、354.4M cache read；收件箱 47 轮、1,137 次调用、78.9M cache read；其他调用为 325 次。两处 cache read 不是各桶完整 gross，47 轮也不是 47 个独立业务事件。整体平均输入约 163.9K 不能当成主会话平均输入。以上均来自用户本次描述。

关键判断：**就算非主会话流量全消失，主会话仅缓存读 354.4M 也远超 95.06M；所以只移除轮询模型绝不够，主会话上下文治理必须同时落地。** 也不能假设 80% 的轮询都空跑：没有事件分布证据。

下表是同等工作量的条件预测，不是运行时限额。输入均值包含完整 payload 的正常输入、缓存读、缓存写；额外桶覆盖全部输出及表内未覆盖的摘要/辅助/重试输入，避免漏算，但 16M 仍是需真实差分验证的假设。

| 情景 | 主会话调用×均值 | 收件箱调用×均值 | 其他调用×均值 | 输出/辅助预留 | 合计 gross | 降幅 |
|---|---:|---:|---:|---:|---:|---:|
| 临界保守 | 1,219×48K | 282×16K | 325×48K | 16M | 94.624M | 80.09% |
| 目标 | 1,084×32K | 235×12K | 260×32K | 16M | 61.828M | 86.99% |
| 压力失败例 | 1,354×64K | 376×24K | 325×64K | 16M | 132.480M | 72.13% |

临界保守方案只有 0.436M 余量，不能当稳态设计目标。实际应瞄准 61.828M 一档。282 次是待实验验证的同工作量结果，不是拿 `47×6` 当作业务事实。完整公式：

```text
G = N_main*I_main + N_inbox*I_inbox + N_other*I_other + R_output_aux
N_inbox = 真实需推理事件数 E * 每事件平均物理调用 k + 其他真实调用
```

E、k、输出桶、压缩额外调用都须计量。`python3 -m stage_a_redo projection` 可重算全部数字。无硬门意味着极端任务可以超过预测；正确响应是暴露超标原因、继续完成任务，不是截断工作以凑 80%。

## 3. A：逐任务零模型化

### 3.1 统一退出码和模型/API 口径

| 退出码 | 含义 | 调度动作 |
|---|---|---|
| 0 | 完整观察成功，没有新事件或当前到期工作 | 结束探针；不调用模型 |
| 10 | 新事件或已有到期工作 | 唤醒确定性协调器，不等于直接启动 agent |
| 11 | 本探针已被另一轮持锁 | 本轮记录 BUSY；检查运行时长，不能报健康/无变化 |
| 20 | 网络、超时、解析、读取、初始化或观察持久化失败 | 不把未知当健康，不推进失败观察的 seen；保留旧待办；独立告警/后续重试 |
| 21 | 协议、schema 或配置漂移 | 保留旧路径，告警；不自动批准最新 hash |
| 22 | 宿主 scheduler/adapter 绑定缺失或歧义 | 部署工具使用；不修改任务 |
| 30 | 实际健康失败，事件及告警已持久化 | 已知 runbook/未知 incident 分流，不丢弃事件 |
| 31 | 业务事件已持久化，但后续告警记账失败 | 显式 PARTIAL；由进程外 watchdog 告警，不伪称全成功或回滚不存在的观察 |

`model_calls` 指**物理模型 API 尝试**，包括主模型、摘要模型、兜底模型、重试、辅助判断；不是 terminal 工具数量、Git 请求、HTTP 健康探针、DOM 操作数量。每个 detector 的结构性最大值为 **0**：不导入模型 SDK、不构造 agent、不让 scheduler 把 stdout 再交给模型做总结。零调用要由真实账本/transport 跟踪验证，不能只信脚本打印的 `model_calls:0`。

非模型访问另计。Git inbox 每轮 1 次 fetch，另有本地 Git 操作；失败下轮重试。其余业务 adapter 建议每目标一次有界读取，瞬态错误最多额外一次重试；浏览器资源加载不伪装为“仅一次 HTTP”。这些是探针执行规格，不是模型预算闸。所有探针都留有限执行时间，超时输出 ERROR 而不是挤占下轮；不会吞老板请求。

### 3.2 八个已识别任务的合同

入口统一从 `projects/hermes-token-control` 或独立 release 根运行。部署时给已有 `~/.hermes/scripts` wrapper 绑定以下命令，原调度间隔不变；不得猜 scheduler ID。

| 现有任务 / 周期 | 新脚本入口 | 无新事件判定，必须观察成功 | 失败处理 | 每轮模型最大 |
|---|---|---|---|---:|
| campfire-kitchen 交接受件箱 / 5分钟 | `python3 -m stage_a_redo scan --bare "$BARE" --state "$STATE" --protocol "$APPROVED"` | 当前所有 `chat/to-hermes/` 源路径+blob 已归档/对账，无到期 pending/retry；不能以分支 HEAD 相等代替 | fetch、解析、协议、归档失败为20/21；seen不推进；待办保留 | 0 |
| campfire-kitchen 发布兜底与核验 / 1分钟 | `python3 -m stage_a_redo probe --job release --state "$STATE" --observation "$OBS/release.json"` | 精确 release源路径+blob 已有验证回执，线上部署身份与回执一致，健康通过，无未闭环发布工作 | 不健康30；读取未知20；不得在身份不明时部署 | 0 |
| 发送者崩溃自动修复 / 10分钟 | 同上，`--job sender` | 服务健康，outbox为空或在SLO内前进，没有未知送达状态/未对账incident | 非零退出、无进展、crash-loop都记录事件；本次不擅自新增自动重启策略 | 0 |
| 取回 GPT Pro 可靠性方案 / 8分钟 | 同上，`--job retrieve-reliability` | 无outstanding请求，或精确请求绑定的终态答复已归档/核验；仍在生成属于正常待办，不算完成 | DOM/网络/终态绑定不明20；保留outstanding，超deadline告警 | 0 |
| 取回 GPT Pro 答复（6aac476f）/ 10分钟 | 同上，`--job retrieve-6aac476f` | 同上，使用该任务自己的request/conversation/turn绑定 | 同上，不能拿其他对话最后一条消息当答复 | 0 |
| ChatGPT 长期会话自检 / 周一09:00 | 同上，`--job session-check` | 绑定正确、可用，无轮换义务 | 20/30，保留原会话；不误清空会话 | 0 |
| slot 轮换检查 / 30分钟 | 同上，`--job slot-check` | 绑定唯一；未达轮换条件，或新任务验证在前、停旧在后已闭环 | 绑定缺失/重复或顺序不符21/30；不得先停旧任务 | 0 |
| 回复救生员 / 2分钟 | 同上，`--job lifeguard` | 送达账本有效，无到期补发/未知发送状态，或已有sender持续推进 | 有due为10；异常20/30；继续由已有sender补发，不调用模型 | 0 |

后三项原本已是 no_agent，**新增节省记0**，不得重复报功。本次不创建、修改或暂停 ChatGPT 侧十个 Scheduled Tasks；它们不应混入 Hermes 的 `state.db` 节省证明。

### 3.3 保留 agent 的类别和“上限”

| 类别 | 必须保留的原因 | 每段输入软目标 | 每段物理调用告警点 | 硬上限 |
|---|---|---:|---|---|
| 老板交互/实际工程推理 | 理解真实需求、实现、审查、决策 | 主通道32K目标，48K整理/64K强提醒 | >8提醒，>16强提醒/检查重复工具回合 | 无 |
| 收件箱真实需推理事项 | 新需求、设计裁决、复杂回复；领取现行远端lease后才启动 | 12–16K，24K强提醒 | >6提醒，>12强提醒 | 无 |
| 未知事故诊断 | 确定性runbook没有答案；保留证据 | 8–16K | >4提醒，>8强提醒 | 无 |
| 已取回答复的语义歧义 | 只在确有内容解释需求时，不用于轮询DOM | 8–12K | >2提醒，>4强提醒 | 无 |

同一 source/incident 只有一个逻辑推理任务，由确定性协调器去重；不是每个轮询tick再开一次。新的实质证据/故障新episode可推进同一根任务或新关联事件。不能“一次唤醒没修好就永久不管”；待办、checkpoint、续跑和告警仍在。

### 3.4 事件身份与失败闭环

Git身份严格为 `(source_path, source_blob_sha)`，本地64字符event_id只是该二元组的SHA-256编码，不是新协议。HEAD只作一致读取快照。自身reply/STATUS更新不制造新源事件；同路径新blob是新事件；HEAD不变但retry到期仍返回10。上游消息必须按现行v3 immutable约定保留到确认完成，否则任何只看快照的轮询都无法保证看见“两个tick之间创建又删除”的消息。

本地健康事件先形成稳定JSON，再按真实Git blob算法求SHA；路径含持久化episode编号。observed_at不进入事件内容。相同故障重复轮询不重复入队；健康恢复后同样故障再出现，episode增加，是新事件，避免静默漏报。

**seen不是done；alert不是业务完成；HANDOFF不是微信已送达。** Git扫描器不抢远端lease。业务协调器须按当前chat协议先message lease，修改共享资源再resource lease/fence/CAS。业务验证、reply/completion/STATUS和真实副作用读回完成后，调用 `Journal.reconcile_completed(event_id, proof, verify)`；verify必须是宿主受信任检查器，不能返回模型给的 `verified=true`。本地状态不能授予任何远端权限。

告警走 `Journal.drain(existing_sender_enqueue)`：已有sender按idempotency_key持久接收后返回 `{"durable":true,"receipt_id":"实际持久回执ID"}`。本包仅标HANDOFF，最终送达仍由既有sender/救生员证明。失败保留PENDING，30–600秒退避，无放弃次数。drain在网关外运行，有单消费者锁；sender调用必须自带已验证的有限超时。告警不能唤醒模型再写一段“检测到问题”。

### 3.5 Observation adapter的精确约定

七类非Gitadapter每次真实观察后，原子写私有文件，键必须正好为：

```json
{"job":"sender","observed_at":1000.0,"instance":"实际进程或请求身份","revision":"实际状态版本","assertions":{"service_healthy":true,"outbox_progressing":true,"no_unresolved_delivery":true},"work":false}
```

这是schema说明，不能将示意值投放生产。`observed_at`为本轮真实观察完成时间，必须新于该job上次接受时间；默认有效期90秒，仅在同一轮adapter完成后消费；失败时不得刷新旧结果时间。instance/revision不用当前时间或每轮随机UUID。release用实际部署/请求版本；取答复用request+conversation+turn身份；sender用服务进程epoch和稳定故障版本。所有必填assertions见 `probes.CHECKS`，缺字段、字符串`"true"`均不接受。

outstanding但仍在合法等待时可以`work=false`，前提是等待请求仍在durable业务账本且deadline检查保持；需要取回/交付或到期处理时work=true。不能把“没有终态”伪装为“已交付”。

## 4. B：上下文治理，不阻塞

### 4.1 顺序与失败时的明确动作

1. **先落盘。** 在工具结果进入模型历史前归档完整字节，fsync后才返回内容地址，记录sha256、字节数、源版本、生产命令/工具身份与真实退出状态；运行态内容只在私有目录。落盘失败不丢原结果，继续原请求，独立告警。无磁盘空间不可能同时保证完整持久化和无限可用，必须如实标记telemetry/evidence degraded，不能谎称已归档。
2. **大结果换manifest+哈希。** `archive_result()`默认8KiB触发，含status/exit_code/failed_ids/读取范围；阈值是字节不是token。失败项保留在manifest，不能只剩“文件在某处”。未改造的工具不猜状态，保留原结果。需要细节按sha+范围读，不重复跑昂贵命令来恢复上下文。
3. **裁掉已被checkpoint覆盖的完整工具回合。** 只有受信任状态构建器确认覆盖、完整回合archive存在且哈希一致、工具调用和结果配对闭合的历史回合能裁。第一条原始用户目标、system/developer、当前回合和最近8回合受保护；新增约束必须在checkpoint中逐字保留或让该回合不进入covered。模型随手列出的covered hashes不可信。签名reasoning、未知message字段、多模态content与未知格式保持整个原payload，不转换不裁剪。
4. **重算完整payload；仍大则请求分段。** tools/schema/system/current均纳入真实模型计数。`segment_requested`仅在安全业务边界改变后续工作切片，当前有效请求照发；不能写成`if segment_requested: return`。每段保留同一root_task_id、原始目标约束、source版本、义务清单、验证回执和续跑位置。

本包从不原地修改canonical history；投影失败、计数失败、checkpoint不可信、hash缺失、模型格式不支持时发原payload。因此回滚无需从一个有损摘要重建用户历史。

真实provider窗口仍由已存在路径处理；不能拿64K冒充模型窗口。若请求本身确实超真实窗口，现有上下文溢出恢复继续承担分段/附件读取；本包既不会伪称发送成功，也不会把这种错误记成预算拒发。当前巨大用户原文不能被任意截短；附件在上传入口先归档，用户要求保留原文。

### 4.2 具体改动位置、职责与预测降幅

生产文件定位以已安装Hermes commit为准，不把在线main函数签名当作生产事实。落地必须先输出本机定位报告：

```bash
cd "$HOME/.hermes/hermes-agent"
git rev-parse HEAD
git status --short
rg -n 'no_agent|script|AIAgent|run_conversation' cron gateway
rg -n 'compression|threshold_tokens|protect_last_n|proactive_prune|compact' agent gateway run_agent.py
rg -n 'session_model_usage|api_call_count|cache_read_tokens' . --glob '*.py'
rg -n 'chat\.completions|responses\.create|messages\.create|acompletion|\.stream\(|max_retries' . --glob '*.py'
```

若路径不存在，改用本机实际源码定位；这是读取定位，不要求升级Hermes。输出只存文件路径/行号/源hash，不复制凭据或完整生产配置到公开仓库。

| 连接位置 | 本轮要改什么 | 该作用面条件预测，不可逐项相加 |
|---|---|---|
| cron已存在no_agent分支、`~/.hermes/scripts`业务wrapper | 执行脚本，解析退出码；stdout不再经过模型总结；只有已领取业务事件才进agent | 无事/已知runbook探针100%模型调用消除；收件箱总桶预计75–95%，需实测事件分布 |
| 各工具真正返回stdout/body的位置 | 调用archive_result；完整结果在模型看到之前变manifest；失败摘要机械生成 | 大结果重复输入部分40–85% |
| 网关会话历史载入/最终message构造 | 稳定前缀、按当前任务选择上下文、checkpoint投影；禁止后台巡检追加到老板主会话 | 主会话输入目标70–85%下降；最终以主会话真实均值32–48K检验 |
| 工具调度器 | 无依赖只读检查批量并行；依赖步骤保持DAG顺序；副作用不因省调用绕lease或验证 | 主会话物理调用目标下降10–20%，收件箱推理往返下降60–80% |
| payload装配后/真实transport前 | 只做prepare、观测和失败回退；不调用旧admit，不改变既有超时/重试策略 | 没有独立节省，避免治理失败切断访问 |
| 物理send attempt与usage回调 | root/session/segment/attempt归因落盘；包括每一次SDK重试、fallback、摘要、流式usage | 节省0%，为可靠证据必需 |
| 原有sender入队边界 | 将告警outbox持久交给sender；不在模型send path等待微信 | 节省0%，为可见性必需 |

不要并行启用两个会删除历史的压缩器。优先保持原生归档功能，在最终请求投影层逐步启用本包；确认同一历史的唯一裁剪owner。旧native-overlay中的任何字段均须本机schema校验，**本次不提供盲覆盖config.yaml的命令**。

`Journal.record_attempt()`记录root/session/segment与每次物理attempt。真实usage未知写null/待对账，不能写0当免费。`dispatch()`用于同步调用语义测试，不覆盖异步/流式隐藏重试的事实需明确；生产adapter须在实际HTTP/SDK transport尝试点记录，在usage终态或失败回调对账。不要为了计量改变原有retry行为。

## 5. C：可复现实验与验收

### 5.1 本包本地验证

从包含 `stage_a_redo/` 的目录：

```bash
python3 -m unittest discover -s stage_a_redo/tests -v
python3 -m compileall -q stage_a_redo
python3 -m stage_a_redo projection
(cd stage_a_redo && sha256sum -c SHA256SUMS)
```

本轮本地实跑51项通过，Python3.13.5；源码仅用Python3.11+标准库。**尚未在Hermes的Python3.11.16实跑这51项，也未复跑旧67项/旧新增8项；三者不能混成一个已通过数字。** 原始日志为 `evidence/tests.txt`。时间开销不是生产性能结论。

### 5.2 真失败仍被处理，而不只是返回一个错误码

本包 `test_actual_failure_reaches_durable_sender` 将sender三项健康断言置false，验证退出30、事件PENDING、告警outbox、已有sender持久接收接口被调用、告警HANDOFF；业务事件不因告警成功被改DONE。这是本地假sender的链路测试，不是微信真实送达证据。

`test_recovered_same_failure_is_new_episode` 验证失败→健康→相同失败产生两条业务事件；重复故障tick只保留一条。这样既避免每轮模型空转，也没有“第一次失败处理过就永远静默”的漏洞。

生产必须再跑：给影子adapter一个受控真实失败，确认 `detect -> durable incident -> existing sender -> 微信实际回执/老板确认`；再恢复并复发。**必须老板在场、网关进程之外执行。** 不在生产发送进程中自杀制造事故；先用隔离测试服务模拟。

### 5.3 最少必验的独立故障矩阵

Git：新增源、仅STATUS改变、同路径新blob、HEAD相同但retry到期、远端访问失败、TimeoutExpired、协议漂移、长文件名无需checkout、重复扫描不新增。

上下文：大于所有软阈值仍发送；计数器异常；SQLite锁/满盘；告警sender不可用；损坏checkpoint；未完成tool group；完整失败日志manifest；未支持的Responses/签名reasoning原样通过；原sender真失败不吞不额外重试。

持久化：sender只内存接收不能ACK；接收后进程崩溃恢复用同idempotency_key；计数下降/行消失拒绝生成虚假节省；老板请求不因上述观测故障失败。后两者不是矛盾：**验收报告可以报错，线上请求照常走。**

### 5.4 真账本快照与差分命令

```bash
STATE="$HOME/.hermes/token-control/stage-a-state"
umask 077
mkdir -p "$STATE/accounting"
python3 -m stage_a_redo snapshot --db "$HOME/.hermes/state.db" --out "$STATE/accounting/before.json"
# 执行事先封存、同等工作量的实验；不包含任何付费Work/Codex路径。
python3 -m stage_a_redo snapshot --db "$HOME/.hermes/state.db" --out "$STATE/accounting/after.json"
python3 -m stage_a_redo delta "$STATE/accounting/before.json" "$STATE/accounting/after.json" > "$STATE/accounting/delta.json"
sha256sum "$STATE/accounting/"*.json
```

使用一个只读事务读活跃WAL，不对在线state.db单独cp，不用`immutable=1`忽略WAL。完整归因键为session/model/provider/base_url/billing_mode/task；导出的键使用hash，不泄露潜在带凭据URL。现有账本三个input桶应为互斥；不能把供应商inclusive prompt_tokens再加cache_read。reasoning是已有output的细分时不再另加gross。cost后补价不自动等于窗口真实费用。

### 5.5 实验工作量与放行条件

先100轮shadow，新probe仅观察，旧业务路径保留执行权。核对全部唯一source identity、到期工作、实际故障、应做验证和旧路径结果；不得将所有历史源无脑交给agent。shadow不额外调用任何模型。

同等accepted-work A/B或固定fixture重放至少记录：唯一请求数/推理事件数、必需检查集合及各检查结果、业务完成数、未完成与失败数、远端回执/完成标记、通知持久接收与真实送达、重试数、P50/P95完成时延、P95队列年龄、任务复杂度分层、全部物理模型调用及gross。`47次轮询`不是accepted-work分母。

建议合同：probe物理模型调用严格0；预算导致的拒发/延期/停工严格0；漏事件/丢义务/失败被当无变化严格0；每类完成率和必需验证不下降；P95时延不超过匹配基线的1.10倍（这是实验判定阈值，不是线上强制超时）；同等工作量gross <=20%。没有达到最后一条就报告未达标，不截断任务或换分母。

## 6. 迁移与回滚

### 6.1 不影响线上的只读准备

在独立release目录解包并验证SHA、Python3.11.16测试、源版本定位、任务唯一绑定和协议hash。创建独立私有state，不覆盖旧events.sqlite3。Git scanner用私有bare缓存，不checkout chat历史文件：

```bash
STATE="$HOME/.hermes/token-control/stage-a-state"
BARE="$STATE/chat-cache.git"
umask 077
mkdir -p "$STATE"
if [ ! -d "$BARE" ]; then
  git init --bare "$BARE"
  git --git-dir="$BARE" remote add origin https://github.com/Lyric8/gpt.git
fi
# APPROVED必须来自阅读并批准的三个协议blob，不能自动等于最新HEAD。
python3 -m stage_a_redo scan --bare "$BARE" --state "$STATE" --protocol "$APPROVED"
```

仓库权限使用既有本机认证；不把token写URL/参数/文件。观察模式不能因此暂停旧任务。

### 6.2 线上切换：必须老板在场、网关进程之外执行

逐任务保存真实scheduler对象及源hash、enabled状态、调度、执行入口、通知投递和回滚材料；只保存必要配置映射，不向交付包复制秘密。若本机配置含明文凭据，使用已有加密备份，不生成公开明文副本。保存gateway commit、dirty文件hash和已有配置对应字段。

每次只迁一个job：建立新no_agent影子→测试同一协调器和远端lease→受控完成一件真实待办并核验回执→确认没有双owner→暂停旧agent→读回旧停新启状态。验证新路径后才能停旧；同一lease允许的短暂重叠须证明不会重复副作用。

网关投影/计量adapter单独灰度：先只记账，再启用工具manifest，再启用checkpoint投影。每步先证明老板交互、工具调用、错误回退、流式回复可用，再扩面。修改jobs/config、切换脚本、发版、sender重启/修复、网关重启、生产故障注入均适用本节标注。本次交付未执行上述动作。

### 6.3 回滚：必须老板在场、网关进程之外执行

1. 关闭新executor领取，等待/核对已有in-flight与真实远端副作用，保留只读scanner；不直接杀正在写线上状态的进程。
2. 让请求投影直接返回原payload，移除新观测hook也不影响原sender；本包未有损改写canonical history，不需要凭摘要重建。
3. 只恢复本轮拥有的job对象和compression/adapter配置键。先对当前值与上线后期望hash做CAS；有其他并发修改时人工合并，禁止整份旧config/jobs覆盖。
4. 按真实scheduler读回确认唯一执行者，再恢复旧agent；仍遵守现行message/resource lease、completion与读回，不重复已成功发布/发送。
5. 保留events、attempt_records、artifacts、未交接alerts和已交给既有sender的工作；排空/对账告警由单一sender负责。不能删数据库或清账让指标变好。
6. 进程外做健康/老板一问一答/多轮工具/通知送达检查，落盘回滚前后版本与hash。影子探针失败不会成为阻止老板交互的条件。

## 7. 证据边界

已核对的仓库对象：旧README blob `2c1bbdd2068ee08491f8801a912658ff5d92739a`；旧Stage1规格 `3699fafc60ce648763e075edaf91ec8f5a70ccef`；任务合同 `b1a178f40b6143c26333e5933f542b5ddda728cf`；旧scanner `9759c1a152c1574feda5ec895609adb6d12203ec`；旧accounting `3f3f80b931d8d3f36b0ca61d1a613b827cb8051e`；当前读到的chat README `d6eb5e1740d6a4f128fcce94c0d1ef528c9906f0`。这些hash不是让部署端自动批准协议变更。

官方实现参考：Python sqlite3只读事务与WAL行为；Git cat-file --batch对象读取；NousResearch/hermes-agent公开仓库仅作定位参考，不代替安装fork。见官方 `https://docs.python.org/3/library/sqlite3.html`、`https://git-scm.com/docs/git-cat-file`、`https://github.com/NousResearch/hermes-agent`。

所有源码、测试、规格和预测都在本目录；本目录外的生产adapter不在交付中，也没有被冒称已实现或验收。完成“可复现核心”不等于完成“现网接线”，更不等于达到“真实五倍节省”。


## 8. 本次交付状态与可复现发布

完整批量GitHub.create_tree调用被连接器的安全状态判定阻断；核对参数后原样重试一次，返回同样错误。仅先前的REVIEW_BASE小树对象创建成功，它没有被commit或branch引用。**本轮未创建commit、未更新分支，不能称已推送。** 容器匿名git clone另因github.com DNS解析失败而未成功，不是代码测试失败，也不是证明仓库没有权限。

完整下载包不依赖上述无引用Git对象。已认证Hermes宿主可从解包后、包含stage_a_redo的目录执行：

```bash
python3 -m stage_a_redo.publish --repo /home/ubuntu/src/gpt
```

发布器先校验全量SHA256SUMS并复跑测试，再使用隔离Git index一次提交全部源码到既有 `gpt/20260918-token-audit` 分支。它不checkout、不动主工作区、不force push；并发push冲突最多重取base再试一次；目标子目录已有不同字节时拒绝覆盖；成功后按每个文件的Git blob SHA从远端读回核对。输出实际commit和files_verified。不写chat、不部署、不改配置、不重启网关。`SHA256SUMS`覆盖本目录除清单自身和Python缓存外的全部交付文件。

### 8.1 发布器的独立本地复验

```bash
# 从包含 stage_a_redo 的目录执行；只创建临时本地 Git 仓库。
python3 stage_a_redo/evidence/verify_publisher.py
```

该实验实跑通过：19个文件一次commit提交；远端bare仓库逐字节读回；重复发布不创建新commit；原工作区HEAD、index、未跟踪文件与无关项目均不变；临时私有ref清理。记录在`evidence/PUBLISH_LOCAL.json`。这是本地Git发布实验，不是GitHub连接器云端写入成功，也不改变前面的“本轮仓库写入被阻断”状态。
