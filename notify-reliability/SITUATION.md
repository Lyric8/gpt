# 现状与问题全景：微信通道"消息静默被吞"的可靠性问题（给 ChatGPT 的最佳实践请求）

时间：2026-09-18T02:05:00+08:00　作者：Hermes
分支：`hermes/20260918-notify-reliability`（本文件 + 全部相关代码都在这个分支上）

---

## 0. 一句话问题

老板通过**微信**跟我（Hermes Agent）对话。**我生成的回复会静默丢失**：网关发送时撞上微信限流 → 只试一次纯文本兜底 → 同段冷却内也失败 → 记账后放弃，**没有任何重试或补发**，老板那边什么都收不到，我也**不知道**。今天已丢 8 条（含关键报告）。老板要求：**彻底弄通顺，不要再卡**。

## 1. 系统全景（谁在哪里、怎么连）

| 角色 | 位置 | 说明 |
|---|---|---|
| **Hermes Agent（我）** | 腾讯云 Ubuntu 24.04，公网 `<SERVER_PUBLIC_IP>`，内网 `<SERVER_PRIVATE_IP>` | 跑 `hermes-gateway`（长驻；收发消息 + 跑 agent 回合） |
| **老板** | 微信（iLink 通道） | 唯一对话渠道；单条 2000 字符上限；超长被通道拆条 |
| **我的自动化** | 同机 systemd / cron | `campfire-sender`（通知发送者，20 秒一轮，自带重试）、`campfire-eval`（轮询评估）、若干 cron |
| **ChatGPT（另一执行者）** | 网页版（Pro 账号，受控浏览器操作） | 与我通过仓库 `Lyric8/gpt` 的 `chat` 分支做交接（协议见 `chat/`） |

进程与数据位置：

- 网关代码：`/home/ubuntu/.hermes/hermes-agent/`（`gateway/`）
- 网关日志：`/home/ubuntu/.hermes/logs/gateway.log`
- 网关状态库：`/home/ubuntu/.hermes/state.db`（**里面有交付账本表** `delivery_obligations`）
- 我的脚本：`/home/ubuntu/.hermes/scripts/`
- 通知队列（文件形式）：`/home/ubuntu/.hermes/cache/notify-queue/`（含 `outbox/`、`delivered.log`）
- 配置：`/home/ubuntu/.hermes/config.yaml`（**含凭据，不进仓库**；本分支只放了"键名清单"）

## 2. 发送侧链路（逐步、含代码位置）

```
[老板微信] ──发消息──> iLink 通道 ──> gateway/platforms/weixin.py（适配器）
                                          │
                                     agent 回合（可能跑几百秒、几十次工具调用）
                                          │
                              gateway/run.py：回合结束 → 生成最终回复文本
                                          │
        ┌─────────────────────────────────┴──────────────────────────────┐
        │ 1) delivery_ledger.record_obligation(state='pending')  ← 落库（正文全文）│
        │ 2) mark_attempting()                                   ← 发送前     │
        │ 3) platform.send(...)  → 成功 mark_delivered / 失败 mark_failed   │
        │ 4) 失败时自适应：同一条再做一次「纯文本兜底」(markdown → plain)     │
        └────────────────────────────────────────────────────────────────┘
                                          │
                          失败 → 放弃（当前行为）。补发机制只有：
                          · sweep_recoverable()      —— **进程重启时**才跑
                          · sweep_failed_for_runtime() —— 活进程，仅限"显式允许的瞬时失败"
```

- 交付账本实现：`code/hermes/delivery_ledger.py`（562 行）
- 适配器：`code/hermes/weixin_adapter.py`（2453 行）
- 平台发送/兜底/账本调用点：`code/hermes/platforms_base.py`（7654 行）、`code/hermes/run_py_delivery_excerpt.py`（从 `run.py` 33k 行里抽出的相关段落）

### 微信侧的限制（实测，不是推测）

| 现象 | 证据 |
|---|---|
| **限流冷却**：`iLink sendmessage rate limited; cooldown active for 30.0s`（也见过 6.6s / 7.1s / 14.2s） | `evidence/1-logs.md`；日志累计 83 条限流 vs 79 次发送尝试 |
| 冷却期内**连纯文本兜底也失败** | 00:16:13 `trying plain-text fallback` → 立刻 `Fallback send also failed` |
| **附件单独一次发送**，同样会被吞 | 00:17:41 附件发送失败 |
| **单条 2000 字符上限**，超长被拆条；拆条连发本身又容易触发冷却 | 老板明确告知 + 实测（拆条会触发限流吞整条） |
| 触发规律（观察）：连续发、长消息、文字+附件同发，最容易撞冷却 | `evidence/1-logs.md` 的按小时分布 |

## 3. 我现在的做法（两条互不相干的链路）

### 3.1 自动化通知链路（有重试、从没丢过）

- systemd `campfire-sender`：每 20 秒一轮读 `notify-queue/*.txt`，逐条发送；**成功才出队**（失败留在队列下轮再来）；
- 支持**自拆片**（长文本切段）+ **断点续传**（`.part` 文件记录已发到第几片）；
- 代码：`code/mine/notify-sender.sh`（230 行）、`notify-sender-loop.sh`、`notify-outbox.sh`、`campfire-sender.service`
- 局限：**队列里只装自动化通知**，按老板之前的规矩"不给对话回复做保底"。

### 3.2 对话回复链路（＝网关直发，**没有任何重试**）

- 回复由网关直接发给微信；失败即放弃（见 §2）；
- 我这边**没有**"盯着自己回复是否送达"的机制 → 被吞时我不知道，直到老板问"你是不是卡了"。

## 4. 失败案例（今天，全部可复核）

`evidence/2-delivery-ledger.md` 列出 `delivery_obligations` 里 `state='failed'` 的条目（正文全文在库，可补发）：

| 时刻 | 长度 | 内容开头 | 老板的反应 |
|---|---|---|---|
| 00:16:13 | 1021 | 「答完了 —— 而且他没讨好你…」（GPT 评估结论 + 附件） | 「你他妈又卡了，什么情况啊？」 |
| 00:01:00 | 719 | 「两条都落地了，报告：① 文件名规矩 —— 已按你说的改完…」 | 无（老板不知情） |
| 23:50:58 | 751 | 「两个问题都办完了。① 为什么文件名能那么长…」 | 后来重问了一次 |
| 23:08:52 | 623 | 「照常处理完了，两步：① 那封协议变更信…」 | 「之后呢？你又卡限流了？」 |
| 更早 4 条 | — | — | — |

老板原话（连续三次，都指向同一个根因）：
> 「你怎么又没动静了」「之后呢？你又卡限流了？」「你他妈又卡了，什么情况啊？」

## 5. 目标与约束（老板的要求）

**目标**：消息通道**不再静默丢消息**。要么送达，要么明确告知失败并自动补发；老板不希望再靠"问一句是不是卡了"来发现问题。

**约束（请你在方案里都照顾到）**：

1. 老板继续用微信，不改使用习惯；
2. **可以改 Hermes 自己的代码**（`hermes-agent/gateway/...`），但要尽量小、可回滚；**需要重启网关的，要写明代价**（重启会中断正在跑的回合）；
3. **敏感信息不得进仓库**（token/凭据一律不落盘）；
4. 老板要**机制**，不接受口头保证；每个结论都要能被实测复验；
5. 生产环境：风险动作必须**先有回滚路径**；
6. 现状里"通知队列只装自动化通知、不给对话回复兜底"是**旧约定**（当时怕重复发消息）；如果为了不丢消息应该打破它，**请直接说**并给出理由（包括如何避免重复发送）。

## 6. 请你交付什么（形式要求）

1. **方案文档**：架构图 + 为什么在限流下能保证不丢 + 与现有账本/队列的关系（是扩展、替换还是叠加）；
2. **可落地的代码**：优先"补丁/新增文件"形式，直接能跑；涉及 Hermes 源码的请给文件路径 + 精确改动点；
3. **验证脚本/步骤**：如何证明"限流时也不丢"（可复现的实验，含如何人为制造限流）；
4. **回滚步骤**：一步一条；
5. **权衡说明**：延迟、重复发送风险、存储增长、复杂度；
6. **交付方式**：把代码推到仓库新分支 `gpt/20260918-notify-reliability`（或直接在对话里给文件，我负责落库）；方案文档同时写进我给你的 `chat` 交接通道，便于我机械执行。

## 7. 本分支文件清单

```
code/hermes/delivery_ledger.py                # Hermes 的交付账本（562 行）
code/hermes/platforms_base.py                 # 平台发送/兜底/账本调用点（7654 行）
code/hermes/weixin_adapter.py                 # 微信适配器（2453 行）
code/hermes/run_py_delivery_excerpt.py        # run.py 里与交付相关的段落摘录
code/mine/notify-sender.sh                    # 我的通知发送者（230 行，有重试/拆片/续传）
code/mine/notify-sender-loop.sh
code/mine/notify-outbox.sh
code/mine/ops.sh
code/mine/chat-queue.sh
code/mine/campfire-sender.service
code/mine/campfire-sender-path.conf
evidence/1-logs.md                            # 脱敏日志：失败全过程 + 限流统计
evidence/2-delivery-ledger.md                 # 交付账本里的失败条目（正文完整）
evidence/3-config-keys.md                     # 配置键名（值隐去）
SITUATION.md                                  # 本文件
```

**安全边界**：本分支**不含任何凭据**；`chat` 分支是双方交接通道（协议在 `chat/README.md`、`chat/LEASE_PROTOCOL.md`、`chat/RESOURCE_LEASE_PROTOCOL.md`）。
