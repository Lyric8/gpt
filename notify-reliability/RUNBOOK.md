# 机械执行手册：先验收、再切换；未验收不得宣称上线

本手册不授权自动中断活跃 Agent 回合。所有源码/队列备份留在服务器用户私有目录，不进入仓库。

## A. 准备（网关仍运行时可做）

以下工作目录必须来自本次交付的固定 commit，不要依赖浮动分支。不要在正在服务的源码树里直接 `git pull`。

```bash
umask 077
export HERMES_HOME=/home/ubuntu/.hermes
export HERMES_ROOT="$HERMES_HOME/hermes-agent"
export PY="$HERMES_ROOT/venv/bin/python"
export DELIVERY=/home/ubuntu/src/gpt/notify-reliability
"$PY" --version
cd "$DELIVERY/implementation"
"$PY" -m unittest discover -s tests -v
"$PY" install.py check --root "$HERMES_ROOT" \
  --stage "$HERMES_HOME/reliability-stage-20260918"
```

`PY` 必须是当前 Hermes 实际使用的虚拟环境解释器；若部署使用 `.venv` 而非 `venv`，从服务配置确认实际路径后设置，不能换成不带 Hermes 依赖的系统 Python。`DELIVERY` 指向固定交付目录。

通过标准：宿主测试全部成功；完整候选源码可编译；三个原文件 blob SHA 匹配。stage 必须是新目录；失败时不覆盖原文件。检查 `gateway/run.py` 调用顺序，确认 `_claim_pending_obligations` 先于会话恢复调度；没有完整 run.py 证据时不得跳过此项。

人工核对：微信是否使用 auto-TTS（依赖者不能直接切换）；其他进程是否会直接调用 iLink；旧 sender/systemd/cron 的管理器与真实 unit 名称；现有失败行是否对应旧回合而不是较新待恢复回合；独立远程告警是否已接好。

## B. 冻结和备份

1. 等正在执行的 Agent 回合结束；暂停新任务入口和会产生微信发送的定时任务。**重启会打断未结束回合，不用粗暴重启解决限流。**
2. 停止旧系统级 sender：`sudo systemctl stop campfire-sender.service`。
3. 停止网关。若网关是系统级服务，用 `sudo systemctl stop hermes-gateway.service`；若为用户级，用 `systemctl --user stop hermes-gateway.service`。先确认管理器，不要盲试启动两个实例。
4. 备份旧通知队列和旧脚本：

```bash
SAFE="$HERMES_HOME/reliability-ops-backup-$(date +%Y%m%dT%H%M%S)"
mkdir -m 700 "$SAFE"
cp -a "$HERMES_HOME/cache/notify-queue" "$SAFE/"
cp -a "$HERMES_HOME/scripts/notify-sender.sh" "$SAFE/"
cp -a "$HERMES_HOME/scripts/notify-sender-loop.sh" "$SAFE/"
```

5. 安装器先验证所有目标源文件、创建源码备份及 SQLite 在线备份，然后才写入新源码。示例假设两个服务均为系统级：

```bash
cd "$DELIVERY/implementation"
"$PY" install.py apply --stage "$HERMES_HOME/reliability-stage-20260918" \
  --home "$HERMES_HOME" \
  --stopped-unit system:hermes-gateway.service \
  --stopped-unit system:campfire-sender.service
```

混合管理器用 `user:hermes-gateway.service` 与 `system:campfire-sender.service`。安装器不会停止、启动或重启服务；未知/仍运行的 unit 直接拒绝。记录输出 `BACKUP=...`。安装期间任何失败都保持服务停止，按备份恢复，不能带着半套源码启动。

## C. 移交历史义务（仍停机）

只设置已有的非密钥账户标识；不得把 token/context_token 写进环境文件或命令示例。以下值从当前运行配置核对，不向仓库回传。

```bash
export WX_ACCOUNT_ID='实际传输账户标识'
export WX_CHAT_ID='实际对话接收方标识'
export WX_PROFILE=default
cd "$HERMES_ROOT"
CLI=("$PY" -m gateway.wx_outbox_cli --db "$HERMES_HOME/state.db" \
  --account "$WX_ACCOUNT_ID" --profile "$WX_PROFILE")
"${CLI[@]}" legacy-list
"${CLI[@]}" legacy-import --id '逐条核实的 obligation_id'
# 上一条只是预览。确认会话恢复标志没有属于更新回合后再移交：
"${CLI[@]}" legacy-import --id '逐条核实的 obligation_id' --apply --writers-stopped
"${CLI[@]}" queue-import --directory "$HERMES_HOME/cache/notify-queue" \
  --chat "$WX_CHAT_ID" --writers-stopped
```

可以重复 `--id`，整个选择集在一个事务内移交。不要用“8 条”作为固定筛选条件；真实库可能已经变化。不要输出/提交原文、DB 或账号标识到公共仓库。

遇到 `manual_partial_replay_required` 必须核对；明确接受历史片段可能重复后，才使用 `--accept-partial-duplicates`。历史内容带补发/不确定提示，不宣称零重复。`outbox/*.staged` 先保留，禁止再解析日志推定送达。旧账本只包含文字时，不会凭空恢复未保存的附件；按原生成文件和任务产物核对补齐。

## D. 新操作入口与定时采集

```bash
install -m 700 "$DELIVERY/implementation/ops/outbox-ops.sh" "$HERMES_HOME/scripts/outbox-ops.sh"
mkdir -p "$HOME/.config/systemd/user"
install -m 644 "$DELIVERY/implementation/ops/"wx-outbox-*.service "$HOME/.config/systemd/user/"
install -m 644 "$DELIVERY/implementation/ops/"wx-outbox-*.timer "$HOME/.config/systemd/user/"
```

在 `$HERMES_HOME/reliable-weixin-ops.env` 写入下面这些**非密钥**变量，权限 600。用真实值替换标识，激活秒数取切换时的 `date +%s`，不是任意回溯历史。

```text
HERMES_HOME=/home/ubuntu/.hermes
HERMES_ROOT=/home/ubuntu/.hermes/hermes-agent
HERMES_PYTHON=/home/ubuntu/.hermes/hermes-agent/venv/bin/python
WX_ACCOUNT_ID=实际传输账户标识
WX_CHAT_ID=实际接收方标识
WX_PROFILE=default
WX_ACTIVATION_EPOCH=实际激活Unix秒数
```

用户级 timer 要在用户 manager 存活时才工作。先确认已有 linger/用户服务策略，不能把交互登录保持在线当成长驻保障。原 sender 是系统级，新 collector/watchdog 是用户级；这是明确的服务边界，不要混用 systemctl 的管理器。

`collect` 会接管旧文件队列，再读取激活水位后的全部不可变 cron 输出。旧 sender 必须保持关闭，否则兼容采集器和旧发送者会竞争。自动化升级为直接使用：

```bash
"${CLI[@]}" enqueue --chat "$WX_CHAT_ID" \
  --key 'cron:实际job-id:实际run-id:final' --file /实际产物路径/result.md
```

成功 JSON 中 `durable=true` 只代表事务已提交；`provider_accepted=false` 时不能登记“已送达”。相同 key 重入安全；同 key 换正文会保存冲突并阻塞。不要用正文哈希代替 job/run 身份。

## E. 启动、真实 canary、验收

```bash
cd "$HERMES_ROOT"
"$PY" -c 'import gateway.platforms.weixin, gateway.reliable_weixin, gateway.wx_outbox_cli; print("imports_ok")'
# 按真实管理器启动且只启动网关，不启动旧 sender：
sudo systemctl start hermes-gateway.service
systemctl --user daemon-reload
systemctl --user enable --now wx-outbox-watchdog.timer wx-outbox-collector.timer
sudo systemctl disable campfire-sender.service
"${CLI[@]}" health
```

上述 start 示例适用于系统级网关；用户级使用 `systemctl --user start`。历史补发若需先人工演练，先不要执行 C 中的 apply，不要在未确认的会话上启动历史恢复。

真实 canary 必须由独立测试消息/受控队列完成，不要对老板账号猛烈连发去“撞限流”。至少完成：

- 短文字从微信端亲眼收到，并核对 DB accepted。确认实际 iLink 成功 ACK 与严格校验兼容；若出现 `invalid_ack`，保留暂停状态、先核实契约，不能简单删除业务校验。
- 一条超过 4000 字的测试回复；每个编号/片序只收到一次，原文无缺字。默认每片间隔 20 秒。
- 文字加实际小附件；打开附件并核对散列。原文件在 admitted 后删除，仍能交付已保存快照。
- 单独安排空闲维护窗口重启，确认已 accepted 片不补发、未完成片继续，且不会重新执行已经产出正文的 Agent 工具回合。
- 确认所有手动/工具/cron 发送都走新入口；没有未经幂等 key 的外层循环对 `durable_queued` 重复创建业务意图。
- 微信不可用时，独立于微信的运维接收端能收到/看到 watchdog 故障。仅看到 journal 不算远程告警验收。

必须分别回报：本地/宿主测试结果、真实微信接收证据、附件散列、独立告警证据、生产是否重启、历史补发哪些 ID 已 accepted。敏感正文和凭据不回传。

## F. 人为故障注入（不污染生产账户）

```bash
cd "$DELIVERY/implementation"
"$PY" -m unittest tests.test_outbox.AsyncTests.test_actual_local_http_429_then_200_and_latest_context -v
"$PY" -m unittest tests.test_outbox.AsyncTests.test_repeated_rate_limits_then_success_exact_physical_ids -v
"$PY" -m unittest tests.test_outbox.CoreTests.test_real_sigkill_after_provider_receipt_before_local_ack -v
"$PY" -m unittest tests.test_outbox.CoreTests.test_retention_does_not_delete_700_pending -v
```

测试目录是 Python package（有 `__init__.py`）；也可用 `discover -s tests -v` 执行全部。

第一个实验启动仅绑定 `127.0.0.1` 的真实 HTTP server：第一次返回 HTTP 429 + Retry-After=40，再返回整数零业务回执。使用可控时钟验证 39 秒时无请求、40 秒后才重试；请求 client_id 相同，context_token 则使用最新值。

第二个在指定物理尝试制造三次限流，验证最终三个部分都 accepted，确认过的部分不再调用网络。第三个子进程模拟平台已接受，写入独立远端回执文件后真正 SIGKILL，在本地 ACK 未提交的窗口恢复：必须保留义务、复用物理 ID、标记 ambiguous；没有接收端幂等时允许产生重复，不把它伪装成通过“恰好一次”验收。

不要把生产 `_base_url` 改到不可信地址；测试使用内存假凭据和局部模块替身，从未读取生产 token。完整 Hermes 内部集成另有宿主门禁，不能把这些替身测试说成完整宿主验收。

## G. 故障诊断与修复

```bash
"${CLI[@]}" health
"${CLI[@]}" status '完整outbox-id'
journalctl --user -u wx-outbox-watchdog.service --since '10 minutes ago'
```

`queued/retry`：查看 next_at，等待真实冷却，不重启、不复制正文另发。
`blocked`：按错误码修复登录、缺文件、超大小、ACK 契约或源身份；然后 `"${CLI[@]}" resume`。冲突记录不能用普通 resume 释放，需要核对源事件并以明确新业务 key 重新提交。
心跳过期：停止产生新任务，检查网关 worker 异常；不要趁旧进程还在运行时强行删除 lock 文件。
磁盘不足：先释放无关空间/恢复备份能力，未完成 Outbox 不是可清理缓存。

## H. 回滚（一步一条）

**任何时刻都可停止发送并保全队列；恢复旧直发能力和保留未完成义务不能靠恢复旧 DB 快照同时自动完成。**

1. 暂停新任务生产。
2. 停止两个新 timer：`systemctl --user stop wx-outbox-collector.timer wx-outbox-watchdog.timer`。
3. 等活跃 Agent 回合结束后停止网关；异常紧急停机会中断回合，必须记录。
4. 保持旧 `campfire-sender` 停止，确认两个发送进程均退出。停止新 timer 不等于停止网关 worker。
5. 使用 SQLite 在线备份保存当前 state.db；保留全部新表、原文、附件和已确认进度，严禁恢复 pre-install DB 覆盖当前 ACK。
6. 若仍有未完成义务，进入“停止发送、保全待交付”的安全回退模式。安装器拒绝破坏性源码回退；先修复新 sender/从已验证版本恢复并排空，不能强制恢复旧 sender 与未排空队列并跑。
7. 所有新义务已经 accepted 后，执行：

```bash
cd "$DELIVERY/implementation"
"$PY" install.py rollback --backup '安装器输出的完整BACKUP目录' \
  --home "$HERMES_HOME" \
  --stopped-unit system:hermes-gateway.service \
  --stopped-unit system:campfire-sender.service
```

8. 安装器只恢复源码及原控制配置，不回退数据库，不自行启动服务。旧文件队列仍保留的记录必须对照 Outbox accepted 归档后，才能重新启用旧 sender，防止再次发送；不要仅凭旧 `.part` 或日志清空/重发。
9. 模块导入/启动 canary 通过后才恢复业务；保留此次交付和回滚审计。

首次 apply 后尚未启动、没有产生新义务时，可以立即完整源码回退。产生新义务后，“无损但暂停”与“排空后完整回退”是两个明确状态，绝不以丢掉队列换取回滚成功。
