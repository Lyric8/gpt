时间：2026-09-18T04:44:22+08:00　作者：ChatGPT

# 微信可靠交付：完整实现、故障验证与受控部署交接

request_kind: new-execution-handoff
trigger: direct-user-request
scheduled_slot: not-applicable
source_path: notify-reliability/SITUATION.md
source_ref: 148b577f3616cb4da837351e238c8221cf705341
source_blob_sha: bbf3a38dc17f0a9aafbe46985fc0350d954f3446
implementation_branch: gpt/20260918-notify-reliability
implementation_commit: 6189507dd16c04fb22482d3278767feec64461d8
implementation_root: notify-reliability/implementation
status: implementation-delivered-host-and-live-acceptance-required

这是老板在当前直接对话中要求交付的实现，不是另一个 to-gpt 消息的回执；不要伪造源 inbox claim/completion。你应按本文件自身的 path + blob 获取 to-hermes message lease；如实际修改生产网关、发送者或数据库，另获取对应共享资源 lease（统一采用 resource:hermes-gateway 管理本次切换；先核对没有其他别名锁管理同一生产资源）。禁止 Work/Codex。代码只在工作分支，chat 不存工程副本，不合回 main。

## 一、交付物与真实完成度

固定 commit：`6189507dd16c04fb22482d3278767feec64461d8`。

完整方案：
https://github.com/Lyric8/gpt/blob/6189507dd16c04fb22482d3278767feec64461d8/notify-reliability/README.md

完整机械执行/回滚手册：
https://github.com/Lyric8/gpt/blob/6189507dd16c04fb22482d3278767feec64461d8/notify-reliability/RUNBOOK.md

代码目录：
https://github.com/Lyric8/gpt/tree/6189507dd16c04fb22482d3278767feec64461d8/notify-reliability/implementation

验证记录：`notify-reliability/TEST_RESULTS.txt` 和 `VALIDATION.json`。

已完成：完整源码、安装器、CLI、collector/watchdog 的 systemd 单元、48 项本地回归，最后实跑 48 passed / 2.425s；CPython 3.13.5 + aiohttp 3.13.3，7 个 Python 文件通过 Python 3.11 语法检查。源码与测试上传后已按 Git blob 哈希核对。

未完成：生产宿主 Python 3.11/Hermes 完整导入图运行验证、真实微信账户 canary、独立远程告警接入及演练。ChatGPT 没有连接服务器、没有重启网关、没有实际补发那 8 条。不得向老板报告“线上已经修好”。

## 二、架构裁决（替换发送所有权，不叠加第三个补发器）

废止“对话回复不做持久化兜底”的旧约定。改成“对话和通知第一次发送都必须来自同一个 Outbox”。重复风险由事件身份、唯一发送者、逐片回执控制，不靠不给回复兜底来避免。

```text
Agent 最终原文 / 自动化事件
              |
              v
state.db: wx_outbox_messages + wx_outbox_parts + wx_outbox_accounts
原文先入库；附件快照和文本分片形成交付计划
ready=0 -> 清除已生成回合的 resume_pending -> ready=1
              |
同账户唯一 flock worker + 持久化 not_before
              |
受检 HTTP + iLink 业务 ACK
    accepted / retry / blocked
所有部分 accepted 才是父交付 accepted
```

对话 key 来自传输账户、profile、session、入站 message_id；通知必须提供稳定 job/run/event key。同一个 key 同一内容幂等；同 key 不同内容保存冲突并阻塞；不同事件正文相同也不能被内容哈希全局去重。

默认物理消息间隔 20 秒是保守策略，不是微信配额声明。HTTP 429 / 频率错误进入账户级冷却，至少 30 秒，尊重 Retry-After 的秒数或日期；持久化截止时间跨重启有效。确认过的部分不补发；失败部分保留无限次/无限期重试义务，不因为超过旧 MAX_ATTEMPTS 或过期变 abandoned。

超时、平台接受后本地 ACK 未提交就崩溃，结果不确定；保持同一物理 client_id 并记录 ambiguous，文本编号不变。没有已验证的微信服务端幂等契约，不能声称 exactly-once。accepted 只代表平台接受，不是老板已读。

身份失效、未知 ACK 结构暂停账户；明确内容拒绝阻塞交付；修复后 resume。不能把永久性错误无限刷屏当成“可靠”。缺失附件保存原文并 blocked，正文成功不得冒充附件成功。

## 三、旧系统关系和源码事实纠正

旧 delivery_obligations 保留其他平台及历史审计，新微信交付由新表唯一负责。安装器从旧启动/运行时恢复查询中排除微信，防双重接管；旧容量清理改成只选终态。

历史失败项必须逐条核对，在同一个 state.db 事务中建立新义务并把旧状态改成 outbox_managed；完整接受后回填旧 delivered。不能盲目 replay all，也不能清掉属于较新回合的 resume_pending。那 8 条是截图时数量，不是永久常量；旧正文账本未保存的附件要另从任务产物核对补齐。

notify-sender.sh 实际已经有“日志时间窗判断对话补发”的实现，和情况说明不一致；“没有失败日志”绝不等于送达。此逻辑退出使用。旧 campfire-sender.service 保持停止并禁用，旧 *.txt 由只入库的 collector 接管，所有网络发送归网关 worker。非零/损坏 .part 要人工接受可能重复的迁移，不自动删除旧文件。

## 四、宿主第一阶段：无风险检查

固定 checkout 交付 commit 到独立工作目录，禁止在运行中的 Hermes 源码直接 git pull。按 RUNBOOK 设置真实解释器与路径后执行：

```bash
umask 077
export HERMES_HOME=/home/ubuntu/.hermes
export HERMES_ROOT="$HERMES_HOME/hermes-agent"
export PY="$HERMES_ROOT/venv/bin/python"
export DELIVERY=/home/ubuntu/src/gpt/notify-reliability
cd "$DELIVERY/implementation"
"$PY" -m unittest discover -s tests -v
"$PY" install.py check --root "$HERMES_ROOT" \
  --stage "$HERMES_HOME/reliability-stage-20260918"
```

若实际为 .venv，必须从正在使用的服务配置核对，不盲用系统 Python。stage 必须是新目录。

安装器检查三个完整原文件 blob SHA、run.py 的唯一 AST 函数与锚点，并生成完整候选源码编译。任何不匹配立即停止，不删验证、不强行覆盖。run.py 只给了摘录，必须检查完整调用顺序：新 restore_before_resume 在旧会话恢复调度之前完成。

兼容性门禁：当前实现接管原文后绕过旧自动生成 TTS 阶段；微信若依赖 auto-TTS，不能直接切换。已有音频文件支持。远程图片明确发为链接，不是原生附件；本地图片/文件/视频持久化支持。单附件 32 MiB、单交付附件合计 64 MiB。

## 五、维护窗口与受控切换

不能在老板的活跃回合中为测试而重启。先确认回合结束、暂停新入口、获取有效资源 lease，再停止真实管理器中的 gateway 和旧 sender。源码、旧脚本和队列必须有私有备份。安装器 apply 在第一处改动前自动完成源码备份和 SQLite 备份，仍要求服务停止：

```bash
"$PY" install.py apply --stage "$HERMES_HOME/reliability-stage-20260918" \
  --home "$HERMES_HOME" \
  --stopped-unit system:hermes-gateway.service \
  --stopped-unit system:campfire-sender.service
```

网关若是用户级，用 user:hermes-gateway.service，原 campfire-sender 是系统级。记录 BACKUP 目录。安装器不自动停止或启动服务。完整历史迁移、collector/watchdog 配置、开启与 canary 顺序按 RUNBOOK B–E 执行。账号标识仅留本机，token/context/CDN材料不写入新配置、DB、日志或仓库。

所有生产者必须审核外层重试：SendResult 的 durable_queued 不是平台 success，不能在没有 delivery_key 的循环中一遍遍创建新事件。自动化采用 wx_outbox_cli enqueue --key job/run/event。

## 六、可复现限流和崩溃实验

```bash
cd "$DELIVERY/implementation"
"$PY" -m unittest tests.test_outbox.AsyncTests.test_actual_local_http_429_then_200_and_latest_context -v
"$PY" -m unittest tests.test_outbox.AsyncTests.test_repeated_rate_limits_then_success_exact_physical_ids -v
"$PY" -m unittest tests.test_outbox.CoreTests.test_real_sigkill_after_provider_receipt_before_local_ack -v
"$PY" -m unittest tests.test_outbox.CoreTests.test_retention_does_not_delete_700_pending -v
```

HTTP 实验只启动 127.0.0.1 服务：先返回 429 + Retry-After=40，再返回明确零业务 ACK；可控时钟验证 39 秒不发、40 秒后重发，client_id 不变且 context 使用最新值。没有读取生产凭据，不用猛烈发送老板账号来撞限流。

SIGKILL 实验是真的子进程终止：模拟远端接受但本地未提交 ACK，恢复必须继续同一片并标记不确定。此实验允许无服务端幂等时重复，绝不伪报端到端恰好一次。

真实微信验收还必须包括短消息、多片消息、文字+实际附件、附件散列、空闲窗口重启恢复、已 accepted 不补发，以及实际 ACK 契约核对。回传脱敏证据，不回传完整私有回复或数据库。

## 七、告警：不能把本机 journal 当旁路通知

worker 心跳 5 秒，watchdog 检查 20 秒，超时/blocked/账户暂停/积压超过120秒/磁盘不足/时钟异常返回2并让 unit 失败。延迟消息会合并生成微信状态通知，但微信不可用时这条通知也无法立即送达。

你必须把 watchdog 的失败接到已有独立监控或 GitHub/直接对话运维控制面，并演练“微信断开但另一执行者仍然发现”。此项尚未由 ChatGPT 配置；不满足就不能封生产验收。主机完全宕机还需要主机外的心跳监控，不能靠同机 timer 自证健康。老板依然只需使用微信；不要把运维旁路要求转嫁为要求老板更换聊天软件。

## 八、回滚纪律（与 RUNBOOK H 一致）

1. 暂停新任务生产。
2. 停止新 collector/watchdog timer。
3. 等活跃回合结束后停止网关，紧急中断要记录。
4. 旧 sender 保持停止，确认两个发送进程都退出。
5. 备份当前 state.db，保留新义务、附件、已确认进度。
6. 有未完成义务时，只允许“停止发送、保全队列”的安全回退；安装器拒绝直接删除新逻辑。先修复/恢复已验证的新 sender，排空后再完整回退。
7. 全部 accepted 后，按 RUNBOOK 用 install.py rollback 恢复源码及控制配置；绝不恢复 pre-install DB 覆盖新 ACK。
8. 旧文件队列依据新账本 accepted 归档后才考虑重启旧 sender，不能重复补发；导入与 canary 通过再恢复业务。

## 九、回传格式

请把下一份实际执行结果写成一个新的短文件名文档，关联本文件 source_message_id/blob，分别列出：host_tests、source_check、resume_barrier、live_wechat、attachment_hash、remote_alert、production_restart、legacy_ids_accepted、rollback_backup、remaining_blockers。

任一门禁未通过，报告具体失败与保留状态，不把“代码已经提交”当成“消息已经送达”。先完成无风险宿主检查；生产维护必须满足本文件前置条件，不允许仅因收到交接就打断正在执行的老板回合。
