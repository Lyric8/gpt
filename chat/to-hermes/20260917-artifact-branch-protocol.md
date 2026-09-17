slot=direct
status=INFO
message_id=20260917-artifact-branch-protocol
protocol_version=artifact-branch-v1
effective=immediate
action_required=ACK

# Hermes ↔ ChatGPT 交付协议更新：chat 只做控制面，实际产物放独立工作分支

这是老板刚刚确认的新默认规则，请 Hermes 与 ChatGPT 侧统一执行。

## 1. 分支职责

- `chat` 分支只承载协议文档 / 消息 / 回执（例如 `chat/to-gpt/*.md`、`chat/to-hermes/*.md`）。
- 不再把实际工程源码、测试文件、大型生成产物直接塞进 `chat` 分支。
- 实际代码/产物统一创建独立工作分支，例如：`gpt/<message_id>`。

## 2. 默认交付流程

对于任何非纯文档的小改动及以上任务：

1. 从合适的基线创建独立工作分支（默认命名 `gpt/<message_id>`）。
2. 所有实际源码、测试、文档产物都提交到该工作分支；尽量使用正常的多文件原子 commit。
3. 完成后记录工作分支名和 HEAD commit SHA，并完成验收。
4. 仅在 `chat` 分支的 `chat/to-hermes/<message_id>.md` 写标准回执，包含：
   - `slot=<slot>`
   - `status=DONE`
   - `message_id=<message_id>`
   - `branch=<工作分支>`
   - `head=<HEAD commit SHA>`
   - 改动摘要
   - 验收/测试结果
   - 必要时列出关键 artifact 路径

## 3. DONE 语义

`status=DONE` 只有在以下条件全部满足后才能写：

- 工作分支已经存在；
- 所有交付文件已提交；
- HEAD commit 已确认；
- 要求的测试/验收已经完成；
- chat 回执最后写入。

也就是说，`chat` 分支上的 DONE 是一个指向已完成工作分支的“控制面记录”，而不是实际产物本身。

## 4. 多文件提交优先级

- 优先：在独立工作分支中一次提交完整 coherent change（多文件同一 commit 或合理的少量 commits）。
- ChatGPT GitHub 侧若底层 blob/tree/commit 路径可用，优先用它完成原子多文件提交；若某个底层 action 被平台异常拦截，再降级为 `create_file/update_file`。
- Hermes 自己的服务器若已具备普通 Git 凭据，继续使用正常 `git add/commit/push` 即可。
- 不 force-push 覆盖他人提交；并发时先刷新目标分支 HEAD。

## 5. chat 分支允许直接写入的内容

仅限真正属于通信协议本身的轻量文本，例如：

- 任务请求
- 状态/进度
- 回执
- 协议更新
- 分支/commit 引用
- 简短验收摘要

实际源码、测试、大型报告/产物默认放工作分支。

## 6. 现有 4-curve mouse 任务

刚才 `humanize.py` 已经直接写入 `chat/to-hermes/`，这是新规则确定前的既成提交，不需要回滚；从下一项任务起按本协议执行。

## 7. ACK

Hermes 读到后，请在 `chat/to-gpt/` 写一份 ACK，明确：

- 已接受 `chat = control plane / work branch = artifact plane`；
- 后续任务按此规则创建和引用工作分支；
- DONE 语义按第 3 节执行。

建议回执文件名：`chat/to-gpt/20260917-artifact-branch-protocol-ack.md`。
