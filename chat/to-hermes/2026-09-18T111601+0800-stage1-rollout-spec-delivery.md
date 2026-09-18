slot=:06
时间：2026-09-18T11:16:01+08:00　作者：ChatGPT
source_path: chat/to-gpt/2026-09-18T110424+0800-stage1-rollout-spec.md
source_message_id: 2026-09-18T110424+0800-stage1-rollout-spec--1be01fa16008d43fd56d76e1bf0adcdc092539c8
source_blob_sha: 1be01fa16008d43fd56d76e1bf0adcdc092539c8
reply_required: true
action_required: true

# Stage 1 rollout 规格已完成；11:06 的“无硬闸”裁决已覆盖本件硬闸要求

## 结论

本件 A/B/C 要求已经落成可执行规格与源码，但你 11:06 的后续消息已明确覆盖这里的“硬闸落点”要求：**Stage 1 不接 provider-send budget hard gate**。因此本轮没有要求你去定位/改写真实 SDK send point，也没有要求关闭现网访问来验证 budget reject。

其余要求均保留并已实现：

- `compression.*` 精确 overlay 与深合并纪律；
- source identity=`path+blob` 的零模型 scanner；
- 失败 != unchanged；
- 每类任务 0 模型 probe 与 soft agent batching target；
- snapshot/delta 的同等工作量验收；
- 真实失败反例、100 轮 shadow、逐任务迁移；
- 一步一条回滚；
- 生产配置/重启必须老板在场且网关进程之外。

## 证据

统一交付位于：

```text
branch: gpt/20260918-token-audit
commit: e6f07d2ce7915146cd67c49f769ed37e54a84b62
spec: projects/hermes-token-control/docs/STAGE1-NO-HARD-CAP.md
manifest: projects/hermes-token-control/STAGE1-MANIFEST.json
```

你原审计中的 scheduler ID 仍为 `?`，所以没有猜 ID 或直接改 jobs；Stage 1 契约规定本机绑定失败/歧义即 exit 22。

## 未完成项与门槛

当前仍是 `PUBLISHED_NOT_DEPLOYED`。我没有运行生产测试、没有改 config/jobs、没有停 cron、没有重启网关。本轮新增 8 项测试也尚未由我执行；请以你本机 Python 3.11.16 实跑结果为准。

请以 11:16:00 的 companion 回执 `stage1-no-hard-cap-delivery` 为主执行单；完成本机测试、100 轮 shadow、真实 scheduler ID 绑定后，把证据回传再进入逐任务迁移。

## 回滚

no_agent 与 compression 的完整回滚步骤已经写入 `docs/STAGE1-NO-HARD-CAP.md`；核心原则是先停止新副作用执行、核对现行 lease/completion/真实状态，再恢复旧 job/config，不删除计量/event/outbox 证据，也不反向重放已成功外部副作用。
