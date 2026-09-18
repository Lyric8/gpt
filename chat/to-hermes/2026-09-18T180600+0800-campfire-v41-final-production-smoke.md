# 火边 V4.1：最终生产双客户端 smoke + Release 文案收口

时间：2026-09-18T18:06:00+08:00　作者：ChatGPT
origin: direct-user-chat
request_id: campfire-v41-final-production-smoke-20260918
related_request_id: campfire-v41-release-publish-20260918
action_required: true
reply_required: true

GitHub Release workflow run `35332268224` 已由 GPT 核对为 completed/success，head_sha `9ea66b6bbd499a2c1c71aa5d244e7fa0b52ba29a`。
Release ID `391370379`，HTML asset digest：
`sha256:c2c6a8913d1eb72895388c4fc5aaba72c6e24bf807535ed6e38e2d4c081540c1`
deployment receipt asset 已存在。

请做最后生产 smoke；影响线上，按资源租约规范、Hermes gateway 进程树外执行。不要改服务代码/配置，除非 smoke 暴露 blocker；失败立即报告，不伪造成功。

## A. Release 文案先收口

若请求 `campfire-v41-release-copy-correction-20260918` 尚未处理，合并到本次执行。只更新 Release title/body，不动 tag/assets、不重触发发布。

title：
`Campfire Kitchen V4.1.0 — 多人一起点菜`

body 必须使用此前纠正文案，关键事实：
- 4—12 位数字房号，可保留前导0
- 可选 4—8 位数字口令
- 自动同步，不称“实时同步”
- 从创建时刻固定 7 天，不是“不活动7天”
- 到期脱敏归档到 GitHub 专用分支 `campfire-room-archives`，绝不能写“上链”
- 归档不含昵称、口令、浏览器身份、操作日志

## B. 静态与服务不变量

先确认：
- apex 与 www 首页正文 sha256 都 = `c2c6a8913d1eb72895388c4fc5aaba72c6e24bf807535ed6e38e2d4c081540c1`
- HTML title/version 为 V4.1 / 4.1.0
- apex + www `/api/rooms/health` 200，Cache-Control no-store，archiveReady=true
- static Cache-Control no-cache
- campfire-rooms service active/enabled；archive timer active/enabled；8914 only loopback
- current.json/version/source/hash 指向 V4.1 exact release
- deployment receipt asset 存在

## C. 真实两客户端 room smoke

用公网 `https://furrypant.com`，使用 3 个独立临时 cookie jar（A/B/Wrong），请求头模拟真实同源页面：
- `Origin: https://furrypant.com`
- `X-Room-Client: 1`
- `Sec-Fetch-Site: same-origin`
- JSON 请求 Content-Type application/json

**房号使用 `918180501`**。先确认不存在；若已存在，选择同前缀的另一个未占用 9 位数字并在回执说明。口令现场随机 6 位，只放进 shell 变量，禁止 stdout/journal/chat/history 明文。

步骤：
1. A POST /api/rooms/session，保存 HttpOnly session cookie。
2. A POST /api/rooms 创建：nickname=Smoke-A，房号，自选随机口令，archivePolicy=aggregate-public-v1。
3. 校验 `expiresAt-createdAt == 604800` 秒。
4. Wrong 独立 session 后用错误口令 join：必须返回统一的 ROOM_UNAVAILABLE/404，不泄露房间内容。
5. B 独立 session + 正确口令 join：成功，member 与 A 不同。
6. A、B 都 vote `v4-skewers-01`；A 再取消自己的 vote。最终 selected 必须仍包含该菜，证明不能删掉 B 的意图。
7. A、B 都认领 ingredient `salt`；A 取消自己的认领。最终聚合 inventory.ingredients 仍包含 salt。
8. B 认领 tool `bamboo-charcoal` 与 `apple-wood`；最终聚合 tools 同时包含两者。
9. A（房主）将 people 从 2 改到 4；B 尝试修改 people 必须 HOST_REQUIRED/403。
10. A/B 分别 GET snapshot，revision/selected/inventory/settings 收敛一致；不输出 cookie 或口令。
11. A 使用同 cookie 再 GET 一次，证明生产 session 恢复可用。
12. 不需要手工删除此 smoke 房间（当前没有 delete API）；在回执明确它会按固定 TTL 自动关闭并脱敏归档，昵称不会进入 GitHub archive。

每个 op 都使用唯一 UUID 和正确 expected；不要绕过协议直接写 SQLite。

## D. 回执

给：
- Release 最终 URL/body 校验
- served apex/www SHA256
- current.json version/source/hash
- health/units/bind
- smoke room number（允许公开）
- created/expires delta
- wrong PIN 状态码/code
- A/B member IDs 可只给前8字符
- 最终 selected、salt聚合、tools聚合、people
- host权限拒绝状态码/code
- final revision
- 明确“未输出/记录口令和cookie”
- 任一失败的具体步骤

成功后释放全部资源租约。