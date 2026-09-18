# 火边 V4.1：发布 Release 并切生产 HTML — GO

时间：2026-09-18T17:57:00+08:00　作者：ChatGPT
origin: direct-user-chat
request_id: campfire-v41-release-publish-20260918
action_required: true
reply_required: true

后端阶段回执已验收通过：API/归档/Caddy healthy，archiveReady=true，apex+www 都 200，V4.0 HTML 尚未改变。老板仍在当前直接对话中并要求实际上线。

## 固定发布对象

- exact main SHA: `9ea66b6bbd499a2c1c71aa5d244e7fa0b52ba29a`
- exact tree: `3efe674627e7b1a6ca9ceec24f1fad9b0a653f89`
- package/data version: `4.1.0`
- release tag: `campfire-kitchen-v4.1.0`
- tag 当前不存在（GPT 已 GET refs/tags/... 得到 404）
- main CI:
  - Campfire Rooms Quality run `35331635857` = completed/success
  - Campfire Kitchen Quality run `35331635837` = completed/success

执行前重新确认 main exact SHA、tag 不存在、上述两个 run 都成功；不一致则停止。

## 发布方式

使用**现有 GitHub Release 正式流水线**，不要手工覆盖 webroot：

1. 按最新资源租约协议取得 `resource:release-ledger` 与 `resource:production-site`；触发线上发布属于生产动作，仍须在 Hermes gateway 进程树之外执行。
2. 使用现有合法 GitHub 凭据（不输出明文）创建并立即 publish GitHub Release：
   - tag: `campfire-kitchen-v4.1.0`
   - target: exact SHA `9ea66b6b...`
   - prerelease=false, draft=false
   - title: `Campfire Kitchen V4.1.0 — 多人一起点菜`
   - body 简述：数字房号、多人点菜/物资认领、断网恢复、7天关闭归档；个人离线菜单保留。
3. 由现有 `.github/workflows/campfire-kitchen-release.yml` 自动：
   - checkout released tag
   - validate version/source
   - tests + deterministic double build
   - attach immutable html/sha256/manifest
   - restricted SSH exact artifact deploy
   - public site byte hash verify
   - upload deployment receipt
4. 不修改 release 产物，不绕过 workflow。若 workflow 失败，保持/恢复 V4.0，并回报失败 job/step；不要手工“补成成功”。

## 发布后生产验收

流水线成功后实测并回执：
- Release URL / ID / workflow run ID / conclusion
- tag commit == 9ea66b...
- Release HTML sha256、served apex sha256、served www sha256 三者一致
- 页面 title/内置 version = 4.1.0
- apex + www `/api/rooms/health` 都 200 + no-store + archiveReady=true
- 首页静态 Cache-Control no-cache
- unknown path 404
- 后端 service/timer 仍 active，8914 only loopback
- 当前 production pointer/current.json version/source/hash
- deployment receipt asset 存在

本阶段成功后不要额外创建测试房间；先回 chat/to-gpt。我随后下发最终真实双客户端 create/join smoke，避免测试数据与正式发布动作混在一个审计步骤里。