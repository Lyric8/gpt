# 火边 V4.1 房间后端：FINAL GO

时间：2026-09-18T17:52:00+08:00　作者：ChatGPT
origin: direct-user-chat
request_id: campfire-v41-final-backend-deploy-20260918
supersedes: campfire-v41-backend-deploy-supersede-20260918
action_required: true
reply_required: true

老板当前就在直接对话中并明确要求实际部署。旧候选 b15b... 永久作废；**只允许以下最终版本**。

## 最终候选与门禁

- main merge SHA: `9ea66b6bbd499a2c1c71aa5d244e7fa0b52ba29a`
- exact source tree: `3efe674627e7b1a6ca9ceec24f1fad9b0a653f89`
- verified branch SHA: `914b9643f08c5d53c9bcc535dc4d798322f8fc49`
- branch SHA 的 tree 同为 `3efe674627e7b1a6ca9ceec24f1fad9b0a653f89`
- final quality run: `35331452282` = **completed / success**
- PR #2 已 merge；main 当前应包含最终 tree
- archive branch: `campfire-room-archives` 已存在

执行前再次只读确认 main == 9ea66b... 且 tree == 3efe...；不一致则停止。

## 本阶段：先后端健康，线上 HTML 暂不切

按你之前预检确认的生产事实执行。影响线上动作必须取得最新 resource lease，并在 Hermes gateway 进程树之外（例如 PID1/systemd-run）执行，不重启/修改 gateway。

### 1. 安装 exact main source

将 `projects/campfire-kitchen` from exact main SHA 安装到：
`/opt/campfire-rooms/releases/9ea66b6bbd499a2c1c71aa5d244e7fa0b52ba29a`

- 专用系统用户/组：`campfire-rooms`，nologin
- release 源码 root:root 只读
- release 内 Python 3.12 `.venv`
- 严格安装 `server/requirements.txt`
- `/opt/campfire-rooms/current` 原子 symlink
- DB 由 systemd `StateDirectory=campfire-rooms` 管理，实际 `/var/lib/campfire-rooms/rooms.sqlite3`

安装 repo 中：
- `deploy/rooms/campfire-rooms.service`
- `deploy/rooms/campfire-room-archive.service`
- `deploy/rooms/campfire-room-archive.timer`

API service 的 `ROOMS_ORIGINS` 必须是：
`https://furrypant.com,https://www.furrypant.com`

### 2. 归档凭据隔离

本次老板要求直接上线，允许暂时复用现有 Lyric8/gpt fine-grained PAT，但：
- 不得输出/记录明文
- 安全写 root-only `/etc/campfire-rooms/github_token`
- 只通过 archive oneshot 的 `LoadCredential=` 注入
- API unit 无 LoadCredential，且验证 API 进程不能读取 token
- archive.py 仍强制拒绝 main/master/chat，只配置 `campfire-room-archives`

### 3. 先做真实 GitHub archive probe

运行一次 `campfire-room-archive.service`。
必须成功创建或逐字节验证：
`campfire-room-archives:system/archive-probe-v1.json`

随后：
- archiveReady=true
- enable/start archive timer
- enable/start API service
- 8914 仅 `127.0.0.1` 监听

### 4. Caddy 使用最终的互斥 handle 结构

不要简单在旧全局 header 下插一个 reverse_proxy，因为旧 `Cache-Control: no-cache` 会污染多人 API 的隐私缓存策略。

以 repo `deploy/rooms/caddy-route.caddy` 为目标结构，只替换现有 `furrypant.com, www.furrypant.com` site block；保留文件顶部 ACLI import 与其它 site block。

核心要求：
- `@campfire_rooms path /api/rooms /api/rooms/*`
- API handle -> `reverse_proxy 127.0.0.1:8914`
- API `Cache-Control "no-store"`
- 静态 handle -> 原 webroot/file_server
- 静态 `Cache-Control "no-cache"`
- 两边保留 nosniff/referrer-policy
- 修改前 timestamp 备份
- `caddy fmt --diff` 审阅
- `caddy validate --config /etc/caddy/Caddyfile` 成功后 reload

### 5. 本阶段验收

必须全部成立：
- loopback Host=furrypant.com health 200, protocol=1 enabled=true archiveReady=true
- public apex health 同上
- public www health 同上
- API health `Cache-Control: no-store`
- 首页仍为 V4.0 bytes/hash（本阶段禁止换 HTML）
- 未知静态路径仍 404
- API service active，archive timer active
- 8914 only loopback
- GitHub archive probe 返回 commit SHA + blob SHA
- API 进程无 GitHub credential exposure

回执带：main SHA/tree、release path、pip pinned versions、unit/timer状态、监听地址、3组 health、Caddy 新 sha256+备份路径、archive probe commit/blob SHA、当前线上 V4.0 index sha256。

失败则恢复 Caddy 备份、停止新 service/timer（SQLite不删），保持 V4.0 页面，并回报。

完成后我会立即发布 V4.1 HTML，再做真实创建/加入双客户端 smoke。