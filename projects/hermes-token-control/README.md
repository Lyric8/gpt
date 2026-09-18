# Hermes Token Control

用于 Hermes 工作流的 token 治理核心与部署裁决。Python 3.11+，运行时仅标准库；Git 观察/发布工具需要 Linux 和 Git。当前验证环境为 Python 3.13.5。**未在用户生产网关部署；没有声称真实 token 已减少。**

先读 **[完整实施方案](docs/PLAN.md)**、[接入契约](docs/INTEGRATION.md)。预测公式和原始证据来源见 `evidence/`。

## 直接执行

解压后进入本目录，先执行：

```bash
python3 -m unittest discover -s tests -v
python3 evidence/recompute.py
python3 -m compileall -q hermes_token_control bin tests
```

只读获取真实计量快照（不修改 Hermes 的 state.db，也不会调用模型）：

```bash
mkdir -p "$HOME/.hermes/token-control/accounting"
chmod 700 "$HOME/.hermes/token-control"
python3 -m hermes_token_control snapshot \
  --db "$HOME/.hermes/state.db" \
  --out "$HOME/.hermes/token-control/accounting/before.json"
```

在验收时间窗结束后获取第二份快照，生成差分：

```bash
python3 -m hermes_token_control snapshot \
  --db "$HOME/.hermes/state.db" \
  --out "$HOME/.hermes/token-control/accounting/after.json"
python3 -m hermes_token_control delta \
  "$HOME/.hermes/token-control/accounting/before.json" \
  "$HOME/.hermes/token-control/accounting/after.json"
```

快照保留当前路由分类和累计计数，用于观测；按任务成功数归一化仍需要实际业务账本，不能从 session 数推断完成任务数。

## 发布用户要求的两个分支

本包生成时无法向 GitHub 写入。下面命令由已有 GitHub 认证的 Hermes 服务器执行；不会使用 Work/Codex，不使用 force push，不改主工作区，不要求检出历史长文件名：

```bash
python3 bin/publish.py --repo /home/ubuntu/src/gpt
```

命令先运行全部测试，再把完整源码写入 `gpt/20260918-token-audit` 的 `projects/hermes-token-control/`，逐文件读回，然后向 `chat/to-hermes/` 写入 v3 短文件名的不可变完整方案。成功会输出代码 commit、交接 commit、路径和 blob。当 `chat` 协议变更或并发 push 冲突时安全失败，不覆盖他人更新。代码已经推送但交接失败时会打印 `CODE_PUBLISHED`，两者不能混称完成。

发布不等于部署。脚本不改生产配置、不操作现有 cron、不重启服务、不生成虚假的 completion。

## 文件职责

| 模块 | 已实现能力 |
|---|---|
| `governor.py` | 根任务/分段预算、发送前事务预留、失败记账、重启后不清零 |
| `provider.py` | 同步非流式 Chat Completions 明确接入；隐藏重试/未支持路径拒绝 |
| `artifacts.py` / `context.py` | 完整证据持久化、哈希校验、只移除已覆盖的完整工具回合 |
| `batch.py` | 独立只读检查批量执行；完整 stdout/stderr 与失败 manifest |
| `queue.py` | 观察游标 CAS、事件去重、local lease/epoch、验证后 outbox 事务 |
| `git_observer.py` | 只扫描收件方向的新源版本，不让自身回执写入重复触发 |
| `accounting.py` | 活跃 SQLite WAL 的只读快照与完整键累计差分 |
| `bin/publish.py` | 隔离 Git index 的多文件提交和远端逐文件读回，无 checkout |

## 不得误用

`certified_upper_bound` 不是“开关调为 true 就完成”的配置；必须接入与实际目标模型相符、包含工具和 framing 的计数器。本包没有假造 token/字符比例作为精确计数。

Git 观察器只入本地队列，**不执行业务、不领取远端租约、不自动启动模型**；先对接当前生产协调器，再把原 cron 改为 no_agent。`queue.py` 的本地租约不能替代远端消息/共享资源租约。完整接入前保留旧生产路径。

运行态 artifacts、prompt、SQLite 和原始业务日志一律放私有目录，不要提交到公开 GitHub 仓库。
