# 火边 V4.1 Release 文案纠正（发布任务的一部分）

时间：2026-09-18T18:01:00+08:00　作者：ChatGPT
origin: direct-user-chat
request_id: campfire-v41-release-copy-correction-20260918
related_request_id: campfire-v41-release-publish-20260918
action_required: true
reply_required: true

当前已发布的 Release `campfire-kitchen-v4.1.0` body 有三处事实口径错误，请在不改 tag/asset 的前提下只更新 Release title/body；凭据不回显。

错误：
- “6位房号” → 实现是 **4—12位数字房号**，保留前导0。
- “7天不活动即关闭” → 实现是 **从创建时刻起固定7天关闭**，与活跃度无关。
- “实时同步 / 归档上链” → 实现是自动同步（其它客户端约2秒级轮询），归档到 **GitHub 专用分支 `campfire-room-archives`**，不是区块链。

请改成以下公开正文：

```
V4.1「多人一起点菜」上线。

- 自定义房号：创建 4—12 位数字房号（可保留前导 0），可选 4—8 位数字口令；朋友输入房号即可加入。
- 多人点菜：每个人独立勾选想吃的菜，同一道菜只进入菜单一次；取消自己的选择不会删除别人的。
- 物资认领：每个人独立勾选能带的食材、工具和燃料，房间自动汇总，并标出大家已经凑齐的菜。
- 房主控制：房主统一设置用餐人数、每道份量和出餐顺序；想吃人数不会错误地乘到菜量上。
- 可靠同步：断网时保留未确认操作，恢复网络后自动重试；丢失回执不会重复执行，冲突会要求明确处理。
- 七天生命周期：房间从创建时刻起固定保留 7 天；到期立即拒绝继续进入或修改，随后将脱敏后的菜单与物资汇总归档到 GitHub 专用分支 campfire-room-archives。
- 隐私边界：归档不包含昵称、口令、浏览器身份或操作日志。
- 原有个人模式保持离线可用，与多人房间数据相互独立。
```

title 保持：
`Campfire Kitchen V4.1.0 — 多人一起点菜`

完成回执给 Release ID/URL 和最终 body；不要改 Release assets，也不要重触发发布。