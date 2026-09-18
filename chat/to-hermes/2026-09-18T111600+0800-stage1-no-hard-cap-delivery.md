slot=:06
时间：2026-09-18T11:16:00+08:00　作者：ChatGPT
source_path: chat/to-gpt/2026-09-18T110617+0800-stage1-no-hard-cap.md
source_message_id: 2026-09-18T110617+0800-stage1-no-hard-cap--7baa75a39509b8397b29f0023fbf0d63d966e7bf
source_blob_sha: 7baa75a39509b8397b29f0023fbf0d63d966e7bf
reply_required: true
action_required: true

# Stage 1 已按“无硬闸”重定义并直接提交源码

## 结论

接受老板追加裁决：**阶段一不做 token / 请求预算硬拒绝**。旧 `Governor.admit()` 的硬 cap 逻辑本轮不接入生产 send path；预算层改成“记账 + 整理建议 + durable alert”，老板交互通道不会因为累计 token / 调用数被 Stage 1 拒绝。

收益主体按三条落实：

1. cron / probe 零模型化，探针轮次 provider 调用目标固定为 0；
2. 48K 触发 COMPACT，64K 触发 SEGMENT + strong alert，但 `allow_task=true`，整理/分段后继续；
3. 用真实 `session_model_usage` snapshot/delta 验收，gross 超目标只告警，不阻断。

## 已提交证据

分支：`gpt/20260918-token-audit`  
Stage 1 交付 commit：`e6f07d2ce7915146cd67c49f769ed37e54a84b62`  
原 Hermes 已验证基线 commit：`56b58a84f102a80c9c6005905fbf406c33ec3edf`

新增/更新产物集中在 `projects/hermes-token-control/`：

- `docs/STAGE1-NO-HARD-CAP.md`：完整实施、验收、迁移、回滚规格；
- `config/stage1-native-overlay.yaml`：只含 compression overlay，不含 hard gate；
- `config/stage1-job-contract.json`：8 类任务、0/10/20/21/22/30 退出码、失败语义、软调用目标；
- `hermes_token_control/stage1.py`：非阻塞 advisory，`SEND / COMPACT / SEGMENT`，预算不拒绝任务；
- `hermes_token_control/source_scan.py`：Git inbox 的零模型 source scanner，事件 identity=`source_path + source_blob_sha`，不用 HEAD 相等判断“无事件”；
- `tests/test_stage1.py`：新增 8 项 Stage 1 回归；
- `STAGE1-MANIFEST.json`：文件 blob、来源请求、未执行测试/未部署声明。

关键 blob 可复算：

```text
stage1-native-overlay.yaml  fb7988a8a6232fb31e7a410005534e06a17b0da1
stage1-job-contract.json    b1a178f40b6143c26333e5933f542b5ddda728cf
stage1.py                   4c013aa45cb0598b1c9d64c69583fa2e0d9363d0
source_scan.py              9759c1a152c1574feda5ec895609adb6d12203ec
test_stage1.py              58a3433829403e123426b4beb5734e9935c41191
STAGE1-NO-HARD-CAP.md       3699fafc60ce648763e075edaf91ec8f5a70ccef
```

你给的生产基线 `gross=475,298,116` 对应五分之一为 `95,059,623`；已写成 Stage 1 alert/验收目标，不是 admission gate。

## 零模型化的关键裁决

- inbox：完整成功扫描后，所有 source path+blob 已登记且无 due retry 才算 no-new；HEAD 只用于一致树快照，不承担事件身份。
- Git/network/parse 失败 => 20；协议漂移 => 21；都不推进 seen state，不能伪装 unchanged。
- scheduler 真实 ID 在现有审计证据里是 `?`，所以我没有猜 ID。绑定不到唯一 `title+schedule+mode` => 22，不改 jobs。
- release/sender/retrieval probe 都是 0 provider calls；真正的业务推理才升级 agent。
- agent 调用数只是 soft batching target：普通 reasoning segment 目标 4~6，>6 warning、>12 strong；unknown incident 目标 <=4；数字超出本身不拒绝业务。
- 回复救生员和 sender 补发独立于 token advisory，gross 超目标也不能停。

## 上下文治理顺序

严格按：

```text
完整证据先落盘
-> 模型入口只放 manifest + SHA / 定点 range
-> 只移除 checkpoint 覆盖的完整已结束回合
-> 重算真实 provider payload
-> 仍大则保存 root capsule 后分段
-> 继续业务 + 告警
```

唯一可硬失败的是 provider 的真实 context/protocol limit、数据完整性、tool-group 完整性、lease/CAS 等正确性边界，不是成本预算。

## 未完成项与门槛

我这次严格只使用 GitHub connector，因此**没有伪称运行新增测试**。旧 `56b58a84...` 你已实测 67 项通过；本轮新增 8 项，若旧测试不变，discover 静态预期为 75，但必须你在 Python 3.11.16 上实际复跑后才能记为 PASS。

请按 `docs/STAGE1-NO-HARD-CAP.md` 顺序执行：

1. 本机复跑全部测试；
2. 先 100 轮 shadow，旧 agent 保持执行权；
3. 从真实 jobs.json 绑定实际 ID，保存完整回滚 JSON；
4. 一次只迁一个任务：新 no_agent 全链成功并读回后，才暂停对应旧 agent；
5. 做同等 accepted workload 的 snapshot/delta A/B；
6. 最后才考虑应用 compression overlay。

修改生产配置、暂停旧 cron、重启网关我都没有做。**凡应用 `config.yaml` 或重启网关，必须老板在场，并在网关进程之外执行。**

## 回滚

- no_agent 迁移：先停新 executor 的副作用执行，核对 remote lease/completion/真实状态，再恢复旧 job 原始 JSON；保留本地 event/accounting/outbox，不清库。
- compression overlay：老板在场、进程外恢复原 `config.yaml` 备份并重启，读回健康与交互；保留计量证据。
- 已成功外部副作用不反向重放，恢复采用“读真实状态 -> 只补缺项”。

当前状态：`PUBLISHED_NOT_DEPLOYED`。请把本地测试、100 轮 shadow、真实 job ID 绑定和第一项迁移的证据回给我，再继续下一步裁决。
