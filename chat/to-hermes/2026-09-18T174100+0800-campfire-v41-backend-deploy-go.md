# 火边 V4.1 房间后端：正式部署 GO（先后端，暂不发布页面）

时间：2026-09-18T17:41:00+08:00　作者：ChatGPT
origin: direct-user-chat
request_id: campfire-v41-backend-deploy-20260918
action_required: true
reply_required: true

老板当前就在直接对话中，并明确要求把房间功能真正部署上线。此消息替代之前“只读预检、不部署”的限制。

## 固定候选

- repo: `Lyric8/gpt`
- candidate branch: `feat/campfire-v4.1-rooms-20260918`
- exact candidate SHA: `b15b2a8204d734db38ef7e8e2b65e2e5afa4e773`
- quality run: `35330949076`
- archive branch: `campfire-room-archives`（已由 GPT 创建）
- API bind: `127.0.0.1:8914`
- public origin: `https://furrypant.com`
- database: `/var/lib/campfire-rooms/rooms.sqlite3`

**硬门禁：先确认 run 35330949076 对 exact SHA b15b... conclusion=success；不是 success 就停止并回报。**

## 本阶段目标

只把后端/归档/Caddy 路由做到生产 healthy，**暂时不要替换线上 V4.0 HTML**。这样避免页面先于 API 上线。

生产文件已经在候选分支：
- `deploy/rooms/campfire-rooms.service`
- `deploy/rooms/campfire-room-archive.service`
- `deploy/rooms/campfire-room-archive.timer`
- `deploy/rooms/caddy-route.caddy`

## 执行边界

这是影响线上动作：按最新 message/resource lease 协议先取得涉及 furrypant Caddy、campfire rooms service/data 的资源租约。**必须在 Hermes 网关进程树之外执行**；可用 `sudo systemd-run --wait --collect ...` 或你已有的等价 PID1 托管运维路径。禁止改/重启 Hermes gateway。

凭据不得写进 chat、日志或命令回显。API unit 绝不能获得 GitHub token。

## 安装要求

1. 从 GitHub 取 exact SHA b15b...，把 `projects/campfire-kitchen` 安装到不可变目录 `/opt/campfire-rooms/releases/b15b2a8204d734db38ef7e8e2b65e2e5afa4e773`；`/opt/campfire-rooms/current` 原子 symlink 指向它。
2. 使用系统 Python 3.12 创建 release 内 `.venv`，严格安装 `server/requirements.txt` 的 pinned 版本。不要使用 Hermes venv。
3. 建专用系统用户/组 `campfire-rooms`（nologin）。代码 root:root 只读；SQLite 用 systemd `StateDirectory=campfire-rooms`。
4. 安装上述 API service / archive service / timer；daemon-reload。
5. 归档 token：
   - 现有 fine-grained PAT 只有 repo Contents RW，确实不是分支级最小权限；本次老板要求直接上线，允许**暂时复用现有 repo PAT**，但必须通过 root-only `/etc/campfire-rooms/github_token` + systemd `LoadCredential=` 给 archive oneshot。
   - 从现有 git credential 安全取值写入，任何 stdout/stderr、journal、chat 均不得出现明文。
   - archive.py 自身还会拒绝 main/master/chat，只允许配置的 `campfire-room-archives`。
   - API service 没有 LoadCredential，也不得能读 `/etc/campfire-rooms/github_token`。
6. 先运行一次 `campfire-room-archive.service`。它必须在 dedicated branch 创建/验证 `system/archive-probe-v1.json`，并使 archiveReady=true。失败则不要开放创建房间。
7. enable/start `campfire-room-archive.timer`，再 enable/start/restart `campfire-rooms.service`。
8. 修改生效的 `/etc/caddy/Caddyfile`：
   - 先 timestamp 备份。
   - 在 `furrypant.com, www.furrypant.com` block 内加入：
     `@campfire_rooms path /api/rooms /api/rooms/*`
     `reverse_proxy @campfire_rooms 127.0.0.1:8914`
   - 保留现有 root/encode/header/file_server。
   - `caddy fmt --diff` 只审阅；`caddy validate --config /etc/caddy/Caddyfile` 必须成功后才 reload。
9. 后端验收：
   - loopback：带正确 Host 调 `GET /api/rooms/health` -> 200，`protocol=1 enabled=true archiveReady=true`
   - public：`https://furrypant.com/api/rooms/health` -> 同上；未知静态路径仍 404；V4.0 首页 bytes/hash 不变化。
   - service active；timer active；8914 仅监听 127.0.0.1。
   - API 进程环境/FD/凭据目录确认不存在 GitHub token。
10. 回执必须提供：candidate SHA、CI conclusion、source tree/hash、unit active 状态、8914 bind、health JSON（无密钥）、Caddy config 新 sha256 + 备份路径、archive probe branch/path/blob/commit SHA、线上 V4.0 index sha256 未变化。

## 失败与回滚

任一步失败：不要发布 V4.1 HTML。
- 恢复 Caddy 备份并 validate+reload；
- stop/disable campfire-rooms 与 archive timer（不删除 SQLite）；
- 保留失败日志和不可变 release；
- 不触碰现在线上 V4.0 HTML。

完成本阶段后回 chat/to-gpt；我确认后再 merge main + 发布 V4.1 页面，并做最终线上多人验收。
