# 我的工作流（谁触发谁、谁写谁读）

```
老板(微信) ──发消息──> iLink ──> Hermes 网关 ──> agent 回合 ──> 网关直发回复
                                    │                        └─ 失败即丢（现已加"回复救生员"扫账本补发）
                                    │
       ┌────────────────────────────┴─────────────────────────────┐
       │  我用的工具/通道                                          │
       │  · terminal / python / 文件读写（状态落盘）                │
       │  · GitHub 仓库 Lyric8/gpt（分支 chat = 与 ChatGPT 交接）   │
       │  · 受控浏览器（Chrome+Xvfb，只许点击/复制/粘贴）与 ChatGPT │
       │  · 本机脚本库 ~/.hermes/scripts（80+ 脚本）                │
       └───────────────────────────────────────────────────────────┘

定时任务（cron，均投递 local 或 origin）
  f0297666a04f 每5分钟  agent  收件箱：chat/to-hermes 有变更才醒 → 领租约 → 干活 → 回执+标记+账本+通知
  c73de63b1c2d 每1分钟  agent  发布兜底：Release/部署异常才醒
  1c32ede5bb5f 每10分钟 agent  取回 GPT Pro 答复（只读浏览器）
  4259af716b7c 每10分钟 agent  发送者崩溃自修
  fbd636c77d16 每30分钟 脚本   slot 轮换检查
  781c5e76e52e 每2分钟  脚本   回复救生员（扫交付账本的 failed 行补发）

systemd
  campfire-sender  每20秒  读通知队列 → 发微信（成功才出队、自拆片、断点续传、失败熔断）
  campfire-eval.timer 每60秒 轮询评估

成本结构
  成本 ≈ 每次 API 调用的上下文体积 × 调用次数
  主会话上下文 ~250K tokens；每个工具调用迭代都要重发一次（cache read 计价）
  定时任务把 agent 当脚本用：收件箱每次运行 24~86 次 API 调用
```
