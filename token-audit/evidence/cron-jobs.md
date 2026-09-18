# 常驻任务（cron jobs.json 摘要）

```
?              {'kind': 'interval', 'minutes': 1, 'display': 'every 1m'} agent            有变更检测        campfire-kitchen 发布兜底与核验
?              {'kind': 'interval', 'minutes': 5, 'display': 'every 5m'} agent            有变更检测        campfire-kitchen 交接受件箱
?              {'kind': 'interval', 'minutes': 10, 'display': 'every 10m'} agent            有变更检测        发送者崩溃自动修复
?              {'kind': 'cron', 'expr': '0 9 * * 1', 'display': 'every monday 9am'} 脚本(no_agent)     无变更检测        ChatGPT 长期会话自检
?              {'kind': 'interval', 'minutes': 30, 'display': 'every 30m'} 脚本(no_agent)     无变更检测        slot 轮换检查
?              {'kind': 'interval', 'minutes': 8, 'display': 'every 8m'} agent            无变更检测        取回 GPT Pro 可靠性方案
?              {'kind': 'interval', 'minutes': 10, 'display': 'every 10m'} agent            无变更检测        取回 GPT Pro 答复（6aac476f）
?              {'kind': 'interval', 'minutes': 2, 'display': 'every 2m'} 脚本(no_agent)     无变更检测        回复救生员（补发被限流吞掉的回复）
```

## systemd 常驻

```
Fri 2026-09-18 10:20:40 CST       36s Fri 2026-09-18 10:19:40 CST      23s ago campfire-eval.timer            campfire-eval.service
active
active
```
