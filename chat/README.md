# chat —— 跨执行者交接频道

这个目录**不是代码**，是留话的地方。

> **本目录只存在于 `chat` 分支，不会合并进 `main`。** 交接内容与代码开发是两回事，混在同一个分支里会互相干扰：写代码的人不该被迫看见一堆留言，读留言的人也不该被代码变动刷屏。
>
> **怎么读写：**
>
> - GitHub 网页：切到 `chat` 分支即可阅读，也可以直接在网页上编辑并提交，不需要本地环境
> - 本地：
>
> ```bash
> git fetch origin chat
> git switch chat        # 首次可用 git switch -c chat origin/chat
> # ……写留言、提交……
> git push origin chat
> ```
>
> 需要同步代码进展时，在 `chat` 分支上 `git merge origin/main`（或 `git rebase origin/main`）即可，方向是**从 main 往 chat 拿**，不要把 chat 合回 main。

同一个仓库上可能有多个执行者（ChatGPT、Hermes、其他自动化工具），彼此看不到对方的会话，只能通过仓库里的文字交接。所有交接都写在这里，不写进代码、不写进 commit message、不靠口头转述。

## 目录约定

| 目录 | 谁写 | 谁读 | 放什么 |
|---|---|---|---|
| `to-gpt/` | 老板 / Hermes | ChatGPT | 交给 ChatGPT 的任务书、要它拍板的决策、它必须遵守的约束 |
| `to-hermes/` | 老板 / ChatGPT | Hermes | 交给 Hermes 的服务器侧请求、要它执行或确认的事 |

Hermes 负责线上发布与服务器运维，不参与本项目的代码开发；ChatGPT 负责代码与流水线设计。需要对方做的事，写进对方的目录。

## 写法要求

1. **文件名带日期**：`YYYY-MM-DD-一句话题目.md`，按名字排序就是时间顺序。
2. **一份文档一件事**，写完不再改。要修正就新写一份，并写明它替代了哪一份。
3. **不要在这里放密钥、token、密码。** 这是公开仓库的一部分。要凭据就只说「需要哪种凭据、要什么权限」。
4. **完成方回执写在对方的目录里**，形成闭环；不要原地修改别人的文档。
5. 这里是**需求与证据**，不是教程。写清楚「要达成什么、怎么算完成、什么不许动」，具体怎么做留给接手方决定。

## 当前

- 给 ChatGPT：
  - `to-gpt/2026-09-17-release-pipeline.md` —— 任务书：把发布改成「发版才部署」
  - `to-gpt/2026-09-17-server-side-facts.md` —— 配套材料：服务器实情与通道选项（任务书写目标，这份补事实；其通道/安全部分已被下一份取代）
  - `to-gpt/2026-09-17-deploy-boundary.md` —— **部署通道的受限边界（已落地实测）**：能做/不能做的完整清单、线上契约、需要它提供的公钥
  - `to-gpt/2026-09-17-deploy-channel-ready.md` —— **通道已接通**：它的安装器已按位置装好（pin 到 cd9992df）、它 workflow 的传输方式需要改的地方、需要建的 secrets、公钥请求
  - `to-gpt/2026-09-17-deploy-key-installed.md` —— **回执**：公钥已装且端到端实测通过、host key 材料、线上哈希与「装钥匙前后未变」的证据；另含两处必须让它知道的事实（登录 shell 的改动、线上请求行的确切格式）
  - `to-gpt/2026-09-17-domain-live-and-two-workflow-fixes.md` —— **汇报**：域名已上线（用它做公网校验）、它的 workflow 有两处要改（请求行、PUBLIC_URL）、回执行已兼容、兜底已上线
- 给 Hermes：
  - `to-hermes/2026-09-17-release-pipeline-key-and-readiness.md` —— **已回应**，见上面那份回执
