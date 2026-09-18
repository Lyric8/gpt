# 火边 V4.1 多人房间：服务器部署预检

时间：2026-09-18T15:17:28+08:00　作者：ChatGPT
origin: direct-user-chat
request_id: campfire-rooms-v41-20260918

老板已部署 V4，并在当前直接对话授权下一功能：自定义数字房号创建/加入，多人选食材和点菜；创建后7天关闭，归档提交GitHub，网页不再查询或允许进入旧房。

我在 `feat/campfire-v4.1-rooms-20260918` 开发，基线main `54ab874e01b31852b3656ad98948d2efbf6aae98`。部分后端源码已用逐文件提交成功。**此分支尚未完整、尚未通过正式HTTP浏览器CI，当前禁止部署。** 后续会以新文档提供固定完成commit和门禁结果。

请先只读预检并回复：
1. 实际生产Caddy配置对应站点块、现有HTML发布方式、当前CSP是否connect-src none（不要回传任何凭据）。仓库 deploy/Caddyfile 是旧 :80 示例，不能覆盖实际HTTPS配置。
2. 新服务计划绑定127.0.0.1:8914，Caddy同源 `/api/rooms` 与 `/api/rooms/*` 反代；SQLite在 `/var/lib/campfire-rooms/rooms.sqlite3`，不进webroot。请确认端口、磁盘、Python和systemd可用。
3. 归档单独进程，GitHub令牌仅由systemd LoadCredential注入归档worker，API无令牌。目标仓库Lyric8/gpt，专用分支 `campfire-room-archives`，不向main/chat写房间数据。请确认现有授权是否有可供归档worker安全使用的最小仓库Contents写权限；没有则报告需老板授权，不索要或回传明文。
4. 老HTML发布SSH是受限入口，不能拿它执行后端bootstrap。请使用你现有合法服务器运维路径。

架构已实现：每成员独立认领与点菜，聚合并集；服务器固定604800秒TTL，各API逐请求检查；到期先事务封存脱敏outbox再删成员数据；GitHub故障退避重试但房间仍关闭；create-only提交＋读取字节校验＋提交SHA；只归档房号/菜谱/物资汇总，不含昵称/口令/身份。页面有公开归档告知。房号4—12位保留前导0，默认允许选填数字口令，已过期房号不可复用。

影响线上的动作必须老板在场、网关进程外执行，并按最新message/resource lease协议取得相应锁。不碰Hermes网关进程，不用Work/Codex/CLI代理/共享agent额度。本消息仅预检，不授权未验收代码上线。
