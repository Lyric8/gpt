# GitHub chat 告警推送适配契约

时间：2026-09-18T05:40:00+08:00　作者：ChatGPT

本文件覆盖 `RUNBOOK.md` D.1 / D.2 中把 `wx_outbox_alert.py` 直接指向宿主 `chat-push.sh` 的旧配置。宿主实测接口只有 `chat-push.sh "<提交说明>"` / `chat-push.sh --no-commit "<提交说明>"`；它不接受目标 path、payload 文件或 stdin，因此不能直接作为 `CHAT_PUSH_SCRIPT` 的 `path-file/file-path/stdin-path` 后端。

## 裁决

不把宿主 Git 工作树、commit-message-only 脚本和远端验证语义塞进 `wx_outbox_alert.py`，也不新增一个与宿主细节绑定的第四个 `CHAT_PUSH_STYLE`。保留 alert sender 已有、稳定的 `path-file` 抽象接口，并新增一层专用 adapter：

```text
wx_outbox_alert.py
  CHAT_PUSH_STYLE=path-file
      |
      v
chat_push_path_file_adapter.py <chat-relative-path> <payload-file>
      |
      +-- 原子 materialize 到 /home/ubuntu/src/gpt/chat/to-gpt/...
      +-- chat-push.sh "<commit message>"
      +-- git fetch origin chat
      +-- git show refs/remotes/origin/chat:<path>
      +-- 与 payload 逐字节校验
```

这样业务层只知道“path + payload -> 成功/失败”；Git 工作树、宿主脚本特殊签名、Git 远端证明都留在 adapter 边界。未来宿主 `chat-push.sh` 再变更，只替换 adapter，不改告警状态机。

## 安装

在启用 alert sender 前执行：

```bash
install -m 700 \
  "$DELIVERY/implementation/ops/chat_push_path_file_adapter.py" \
  "$HERMES_HOME/scripts/chat-push-path-file-adapter.py"
```

`$HERMES_HOME/reliable-weixin-ops.env` 使用：

```text
CHAT_PUSH_SCRIPT=/home/ubuntu/.hermes/scripts/chat-push-path-file-adapter.py
CHAT_PUSH_STYLE=path-file
CHAT_PUSH_BACKEND=/home/ubuntu/.hermes/scripts/chat-push.sh
CHAT_REPO_ROOT=/home/ubuntu/src/gpt
CHAT_PUSH_REMOTE=origin
CHAT_PUSH_BRANCH=chat
```

其余已有 `HERMES_HOME/HERMES_ROOT/HERMES_PYTHON/WX_*` 配置不变。adapter 不接收、不读取、不拼接任何 token；Git 凭证仍由宿主现有 repo / `chat-push.sh` 自己的 Git 凭据链管理。

## 成功语义

adapter 的 `0` 不等于“后端进程返回 0”。只有同时满足以下条件才返回 0：

1. 目标必须是 `chat/to-gpt/*.md`，拒绝绝对路径、`..`、其他目录和非 Markdown；
2. `CHAT_REPO_ROOT` 当前 checkout 必须是配置的 `chat` 分支；
3. payload 为普通文件，大小 `1..1 MiB`；
4. 目标不存在时，以同目录临时文件 + `fsync` + hard-link no-clobber 原子落位；目标已存在时只有内容逐字节一致才允许收敛，内容不同直接冲突，绝不覆盖；
5. 调用宿主 backend 时 argv 只有：`chat-push.sh "chat: deliver <subject>"`，绝不把 payload/path 塞进提交说明参数槽位；
6. backend 返回 0 后，adapter 再执行 `git fetch --quiet <remote> <branch>`；
7. 从 `refs/remotes/<remote>/<branch>:<path>` 读取远端文件，必须与 payload **逐字节一致**。

因此宿主 `chat-push.sh` 的“无改动也 rc=0”不会再造成假成功。若网络断开、backend 失败、fetch 失败、远端文件缺失或内容不一致，adapter 返回非 0，`wx_outbox_alert.py::drain()` 会保留原 JSON 于 `pending/`，下一次 timer 重试。

## 退出码

```text
0   VERIFIED：远端 chat 分支指定 path 与 payload 逐字节一致
20  CONFIG：backend/repo/branch/remote 配置或 checkout 不满足前置条件
21  INPUT：参数、目标 path 或 payload 非法
22  MATERIALIZE：本地原子落位 I/O 失败
23  CONFLICT：目标 path 已存在但内容不同，禁止覆盖
24  BACKEND：宿主 chat-push.sh 返回非 0 或无法执行
25  VERIFY：backend rc=0，但无法证明远端 exact payload
```

告警 sender 只需要把 `0` 视为成功、任何非 0 视为失败并保留 pending；退出码用于宿主诊断，不改变 spool 状态机。

## 并发与恢复

adapter 不替代宿主 `chat-push.sh` 自己的 flock。它只用原子 no-clobber 创建本次独占的新消息文件，不修改既有 chat 文件。若 backend 已经提交但 push/响应阶段不确定，本地目标文件保留；下一次重试会先收敛到相同内容，再调用 backend，最后以远端 exact-byte 校验决定是否归档。不得因为本地 commit 存在或 backend rc=0 就把事件从 `pending/` 移走。

宿主共享 checkout 仍要求所有写入方都采用“完整文件先在临时路径写完，再原子落位”的纪律；`chat-push.sh` 的 `git add -A chat` 可能把同时存在的其他完整 chat 文件收进同一个 commit，但这不改变各文件的消息身份。任何半写文件都不得暴露在共享 checkout 中。

## 测试与宿主门

本交付新增 `tests/test_chat_push_adapter.py`，覆盖：

- backend rc=0 + 远端 exact payload 才成功；
- backend rc=0 但远端缺失仍失败；
- backend 非 0 不进入远端成功判定；
- 本地同 path 不同内容 fail closed 且不覆盖；
- 只能写 `chat/to-gpt/*.md`。

宿主集成时至少执行：

```bash
cd "$DELIVERY/implementation"
"$PY" -m unittest tests.test_chat_push_adapter -v
"$PY" -m unittest discover -s tests -v
```

随后再跑 `RUNBOOK.md` 的四项真实 remote_alert 门。GitHub 断网门必须看到事件继续留在 `pending/`；恢复网络后必须证明同一 `alert_id` 对应的远端文件真实存在且内容与本地 render 一致，再进入 `sent/`。
