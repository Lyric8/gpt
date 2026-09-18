# 证据来源、范围与复现

## 用户提供的仓库证据

- https://github.com/Lyric8/gpt/tree/hermes/20260918-token-audit/token-audit
- `evidence/token-detail.txt`：2,689 请求，4.33M 非缓存输入，436.90M 缓存读，2.67M 输出，估算 $2.5337。原文件聚合已按 M/K 舍入，本包不把它称为逐请求原始数据。
- `evidence/per-turn.txt` blob `3bede0fa439646498920b1bb0fe0b87683f08d08`：85 条 gateway response-ready 记录。`recompute.py` 转录其调用数字重算。
- `evidence/workflow-map.md` blob `fcd3e2877e6c5c8437db85c1a7ac0eae0039bb28`：实际工具/进程角色说明。
- `evidence/cron-jobs.md`：5 个 agent 条目；两个取答复任务没有变更检测。

未获得本机 state.db、账单明细、全部请求 payload、完整本地 Hermes fork、80 多个脚本、jobs.json/config.yaml、浏览器和实际服务访问权限。不能从本报告推断这些对象已被端到端审查。

## 当前交接协议

https://github.com/Lyric8/gpt/blob/chat/chat/README.md

实际读取 README blob `d6eb5e1740d6a4f128fcce94c0d1ef528c9906f0`，其中描述 v3 短文件名、source identity、消息/资源两层租约与 CAS。目录枚举中 `LEASE_PROTOCOL.md` blob `c8f8be77457bdbfe478af37230de60cb19f63cf2`、`RESOURCE_LEASE_PROTOCOL.md` blob `469ac4cb1286a0c3f35e7ca1ae1ac22463bffb41` 用作当前批准快照检查；本包没有重写两份协议的完整执行器。上线实施者必须读取两份完整协议并验证现有 adapter。

## Hermes 核对源码

使用用户历史报告中的上游 commit `693641aa` 读取以下文件；这不证明用户本机分叉毫无改动：

- https://github.com/NousResearch/hermes-agent/blob/693641aa/agent/usage_pricing.py ：CanonicalUsage 的非缓存/缓存读/写分离口径，reasoning 不重复加到 total。
- https://github.com/NousResearch/hermes-agent/blob/693641aa/hermes_state_usage.py ：session_model_usage 按完整 route key 累加，含延迟写入与 estimated/actual 区分。
- https://github.com/NousResearch/hermes-agent/blob/693641aa/agent/api_request_hooks.py ：生命周期 hook payload 有裁剪和清洗，不是完整请求硬预算的可靠入口。
- https://github.com/NousResearch/hermes-agent/blob/693641aa/run_agent.py ：入口与上下文/迭代/生命周期组合；本次没有改写该完整文件。

## 官方资料

- https://hermes-agent.nousresearch.com/docs/user-guide/configuration/ ：压缩、in-place、阈值、保留尾部、工具输出与重试配置。在线版本可能新于本机，必须核对本机 schema。
- https://hermes-agent.nousresearch.com/docs/user-guide/features/cron/ ：no_agent 和 pre-script wakeAgent gate。已有 gate 的收益不重复计入。
- https://api-docs.deepseek.com/guides/kv_cache/ ：前缀缓存和 hit/miss 口径，命中率不是 SLA。
- https://api-docs.deepseek.com/api/create-chat-completion/ ：Chat Completions usage、输出限制和 finish reason。

未核验用户实际费率，不使用上游硬编码报价冒充供应商真实账单。

## 本包复算

```bash
python3 evidence/recompute.py
python3 -m unittest discover -s tests -v
```

`projection.json` 是显式假设的流量测算，**不是跑了生产优化方案产生的 benchmark**。所有原始主要输出保留，其他小任务保留，另加5M辅助开销储备。67 项测试是机制测试，不是可靠性不退化或线上 token 五倍压降的证据。
