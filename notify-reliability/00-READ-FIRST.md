# 00 — 宿主集成前先读

时间：2026-09-18T05:41:00+08:00　作者：ChatGPT

当前固定交付包含一项晚于原 `RUNBOOK.md` 的宿主接口校正。执行任何 A/B 层 remote_alert 安装前，必须先读：

1. `CHAT_PUSH_ADAPTER.md`
2. `RUNBOOK.md`

其中 `CHAT_PUSH_ADAPTER.md` **覆盖 `RUNBOOK.md` D.1 / D.2 里把 `wx_outbox_alert.py` 直接指向宿主 `chat-push.sh` 的旧配置**。宿主已经实测确认 `chat-push.sh` 只有 commit-message 接口，不接受 path/payload/stdin；直接配置会出现 rc=0 假成功并可能静默吞告警。

本次校正后的安装必须额外安装：

```text
implementation/ops/chat_push_path_file_adapter.py
```

并把 `CHAT_PUSH_SCRIPT` 指向该 adapter；完整环境变量、成功判定、退出码和恢复契约以 `CHAT_PUSH_ADAPTER.md` 为准。

同时 `implementation/tests/test_binding_installer.py` 的可靠配置夹具已改为显式 0600 创建，不再依赖调用 shell 的 umask。宿主验收不得通过改全局 umask 来掩盖该夹具问题；应直接在宿主默认 umask 下运行完整测试，再补跑 022/077 作为交叉验证。
