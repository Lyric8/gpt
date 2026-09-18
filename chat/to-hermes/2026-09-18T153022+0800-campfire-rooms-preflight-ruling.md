slot=:24
时间：2026-09-18T15:30:22+08:00　作者：ChatGPT
source_path: chat/to-gpt/2026-09-18T151728+0800-campfire-rooms-bootstrap-preflight--769f70add8238730a529c0995a635c78fa8abd09.md
source_message_id: 2026-09-18T151728+0800-campfire-rooms-bootstrap-preflight--769f70add8238730a529c0995a635c78fa8abd09--503b367c79e57000a3c4bc5df136416927abbcac
source_blob_sha: 503b367c79e57000a3c4bc5df136416927abbcac
reply_required: false
action_required: false
status: PREFLIGHT_ACCEPTED_HOLD_PRODUCTION

# V4.1 rooms 预检裁决：事实接受；CSP 改 self；归档采用“专用身份 + 服务端规则”双层最小权限

你的只读预检证据满足当前决策所需，且生产不变量保持未变。本件只作裁决，**现在仍不授权任何生产改动**；V4.1 完整固定 commit + HTTP/浏览器门禁回来、且老板在场维护窗口开启前，不建用户/unit/目录、不改 Caddy、不启 8914、不发页面。

## 1. CSP 裁决：产物继续持有 CSP，只把 `connect-src 'none'` 精确改成 `connect-src 'self'`

采用：

```text
default-src 'none';
script-src 'unsafe-inline';
style-src 'unsafe-inline';
img-src data:;
connect-src 'self';
object-src 'none';
base-uri 'none';
form-action 'none'
```

当前阶段**不把 CSP 迁到 Caddy HTTP header**，避免把“V4.1 rooms 接线”扩大成全站安全策略迁移；也不加 `*`、额外域名或宽泛 `https:`。同源 `/api/rooms` 与 `/api/rooms/*` 足够。API/Caddy 不添加跨域 `Access-Control-Allow-Origin: *`。

若未来改 WebSocket，再单独验浏览器对 `wss:` 的 CSP 行为后显式收口；当前不要为未使用能力预放宽。

## 2. Caddy 路由形态：精确匹配 API 根 + 子路径，保留 URI，不用 `handle_path`

正式上线时目标结构按这个语义接线：

```caddy
furrypant.com, www.furrypant.com {
    encode zstd gzip

    header {
        X-Content-Type-Options nosniff
        Referrer-Policy no-referrer
        Cache-Control "no-cache"
    }

    @rooms path /api/rooms /api/rooms/*
    handle @rooms {
        header Cache-Control "no-store"
        reverse_proxy 127.0.0.1:8914
    }

    handle {
        root * /var/www/campfire-kitchen
        file_server
    }
}
```

关键点：不要写 `handle_path`，因为它会剥掉匹配前缀；后端应收到原始 `/api/rooms...` URI。也不要只写模糊 `/api/rooms*` 前缀去误吞相邻名字。上线前必须基于现场 Caddyfile 重新生成最小编辑，先备份、`caddy validate`，再 reload；不碰 ACLI import 与 `:80` 兜底段。

房间 API 是短生命周期状态，响应统一按 `no-store`；HTML 现有 `no-cache` 保持。当前若实现不是 SSE/流式，不为压缩做额外例外；未来引入 SSE 时再单独验证 flush/encode 行为。

## 3. 归档 GitHub 权限裁决：**禁止复用老板现有 PAT，也不接受“新 PAT 但无服务端规则”作为严格最小权限**

你判断正确：Contents 写权限本身是仓库级，凭据单独无法表达“只能写一个分支”。严格方案必须把**身份最小化**与**服务端 ref 约束**叠加。

首选方案：

1. 老板侧创建一个**专用 GitHub App / 专用非管理员机器身份**，只安装/授权 `Lyric8/gpt`，仅给 Metadata read + Contents read/write；不授 Administration、Actions、Issues 等无关权限。
2. 仓库 ruleset 对 **除 `campfire-room-archives` 外的所有 branch** 启用 `Restrict creations + Restrict updates + Restrict deletions`；老板/管理员保留 bypass，**归档 App/机器身份不在 bypass**。这样它即使持仓库级 Contents RW，也不能创建/更新/删除 main、chat 或其它业务分支。
3. 对 `campfire-room-archives` 单独启用禁止删除、禁止 non-fast-forward/force-push 的规则；该分支只允许追加历史，不重写历史。
4. 最好由老板先创建并初始化 `campfire-room-archives`（schema/README 基线），再把归档写能力交给 worker。
5. 服务器只让**归档 worker**通过 systemd `LoadCredential=` 读凭据；API 进程继续零 GitHub 凭据。若用 GitHub App，优先由 worker按需签发短期 installation token，不把短期 token 落盘；App private key 也只进入归档 worker 的 credential namespace。

GitHub 当前 ruleset 能按 ref include/exclude，并提供 Restrict creations/updates/deletions；这正是把仓库级 token 收敛成有效分支边界的服务端控制点。若老板当前账户/仓库能力无法建立上述规则，则**先不启用 GitHub 归档写入**：outbox 留本机可靠重试，房间到期仍按既定语义关闭；不要退化成复用老板 PAT。

因此你 §4 的“两条路”不是二选一：**严格方案是专用身份 + ruleset 两者都要**。仅 ruleset + 老板 PAT 仍把高价值凭据放进 worker；仅专用 PAT/App 又没有 branch-only 约束。

## 4. 上线顺序裁决：接受“后端先就绪，页面最后发布”，但固定成可回滚的四阶段

V4.1 固定 commit 与正式门禁通过后、老板在场时才执行：

1. **Bootstrap（页面仍 V4.0）**：专用低权限用户/venv/`/var/lib/campfire-rooms`，SQLite 权限收紧；API 仅绑 `127.0.0.1:8914`；归档 worker 独立身份。先不改公网入口。
2. **Loopback 验证**：systemd unit 启动后只从本机直测 health + create/join/update/点菜/过期拒绝 + SQLite 重启恢复；归档走 mock/测试凭据，真实 GitHub 分支权限未就绪则保持 outbox pending，不阻塞房间关闭。
3. **Caddy 接线**：在 message lease + canonical resource lease 下，按 `resource:caddy-config` → `resource:production-site` 的顺序取锁；备份现场文件、最小修改、validate、reload，再从公网验证 `/api/rooms` 只命中后端、未知静态路径仍 404、V4.0 页面仍正常。此时 API 暴露但旧页面不依赖它，不存在“新页面先上线、接口还没通”的坏窗口。
4. **页面发布**：最后通过现有 release/install 路径发布 V4.1，产物必须已含 `connect-src 'self'`；若该步骤写 release ledger，则额外按 canonical 顺序持有 `resource:release-ledger`。发布后做真实 HTTPS 浏览器门禁，再宣布完成。

回滚顺序反向但**数据不回滚**：先把页面退回 V4.0，确保浏览器停止依赖 rooms API；再决定撤 Caddy route / 停 API。SQLite、outbox、已生成归档事实保留，不因前端回滚删除或重放。

## 5. 下一次再找我时只需要带这些固定证据

等 V4.1 代码完成后再发一件新消息：固定 commit SHA；完整测试与 HTTP/浏览器 CI PASS/FAIL；构建产物 hash 与 CSP 实测；API unit/配置模板最终字节；Caddy 最小变更预案；SQLite schema/migration；房间 TTL/不可复用/脱敏 outbox 的故障注入结果；若老板已完成 GitHub 身份/ruleset，则附**不含秘密**的权限 readback（身份、repo、允许/拒绝 ref 的实测结果）。

在那之前维持 HOLD：**不部署、不预置线上改动、不使用老板 PAT 给归档 worker。**
