# 紧急：撤销 b15b... 的生产部署授权

时间：2026-09-18T17:47:00+08:00　作者：ChatGPT
origin: direct-user-chat
request_id: campfire-v41-backend-deploy-supersede-20260918
supersedes: campfire-v41-backend-deploy-20260918
action_required: true
reply_required: true

**不要部署**旧候选 `b15b2a8204d734db38ef7e8e2b65e2e5afa4e773`，即使它的 CI 已绿。

上线前复核发现：生产 Caddy 同时服务 `furrypant.com` 与 `www.furrypant.com`，旧 API 的 exact-origin guard 只允许 apex host/origin，直接上线会导致 www 站点的房间请求被 403。

GPT 正在修正为显式双 origin 白名单并新增回归门禁。旧 GO 立即作废。如果已经开始 staging，只保留不可变 staging 目录，不启用 unit、不改 Caddy；若已产生任何生产副作用，立刻按旧消息回滚段恢复并回报。

新的 exact SHA + green run + GO 会单独发送。