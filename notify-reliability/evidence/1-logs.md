# 证据 1：网关发送失败全过程（原始日志，已脱敏）

```
2026-09-18 00:12:19,219 ERROR gateway.platforms.weixin: [Weixin] send failed to=<CHAT_ID>: iLink sendmessage rate limited; cooldown active for 30.0s
2026-09-18 00:12:42,590 ERROR gateway.platforms.weixin: [Weixin] send failed to=<CHAT_ID>: iLink sendmessage rate limited; cooldown active for 6.6s
2026-09-18 00:15:42,826 ERROR gateway.platforms.weixin: [Weixin] send failed to=<CHAT_ID>: iLink sendmessage rate limited; cooldown active for 30.0s
2026-09-18 00:15:58,611 ERROR gateway.platforms.weixin: [Weixin] send failed to=<CHAT_ID>: iLink sendmessage rate limited; cooldown active for 14.2s
2026-09-18 00:16:05,681 ERROR gateway.platforms.weixin: [Weixin] send failed to=<CHAT_ID>: iLink sendmessage rate limited; cooldown active for 7.1s
2026-09-18 00:16:12,998 INFO gateway.run: response ready: platform=weixin chat=<CHAT_ID> time=750.8s api_calls=38 response=1070 chars
2026-09-18 00:16:13,066 INFO gateway.platforms.base: [Weixin] Sending response (1021 chars) to <CHAT_ID>
2026-09-18 00:16:13,310 ERROR gateway.platforms.weixin: [Weixin] send failed to=<CHAT_ID>: iLink sendmessage rate limited; cooldown active for 30.0s
2026-09-18 00:16:13,310 WARNING gateway.platforms.base: [Weixin] Send failed: iLink sendmessage rate limited; cooldown active for 30.0s — trying plain-text fallback
2026-09-18 00:16:13,311 ERROR gateway.platforms.weixin: [Weixin] send failed to=<CHAT_ID>: iLink sendmessage rate limited; cooldown active for 30.0s
2026-09-18 00:16:13,311 ERROR gateway.platforms.base: [Weixin] Fallback send also failed: iLink sendmessage rate limited; cooldown active for 30.0s
2026-09-18 00:16:13,317 INFO gateway.platforms.base: [Weixin] Delivering 1 non-image MEDIA attachment(s)
2026-09-18 00:17:41,346 ERROR gateway.platforms.weixin: [Weixin] send failed to=<CHAT_ID>: iLink sendmessage rate limited; cooldown active for 30.0s
```

# 证据 2：限流总量

```
限流行数: 83
发送尝试: 79
按小时分布:
       21 00:00
       13 15:00
       16 17:00
        5 18:00
        7 19:00
       11 21:00
       10 23:00
```
