# 证据 3：交付账本（state.db.delivery_obligations）里的失败条目

正文完整落库（可补发），状态 failed，attempts=0（说明没有重试过）。

```
  ✅ 01:32:58 delivered 尝试=0 正文长度=1069
  ✅ 01:30:45 delivered 尝试=0 正文长度=834
  ❌ 00:16:13 failed    尝试=0 正文长度=1021
       开头: **答完了 —— 而且他没讨好你，也没护着自己那套。** 原文（7101 字符）我做成文件发你，先说要紧的：  **他的
       错误: iLink sendmessage rate limited; cooldown active for 30.0s
  ✅ 00:02:57 delivered 尝试=0 正文长度=599
  ❌ 00:01:00 failed    尝试=0 正文长度=719
       开头: 两条都落地了，报告：  **① 文件名规矩 —— 已按你说的改完** ``` 文件名 = 极其精确的时间戳 + 主旨（示
       错误: iLink sendmessage rate limited; cooldown active for 30.0s
  ❌ 23:50:58 failed    尝试=0 正文长度=751
       开头: 两个问题都办完了。  **① 为什么文件名能那么长 —— 是"回执命名规则"在累加**  规则是「回执名 = 父文档名 
       错误: iLink sendmessage rate limited; cooldown active for 30.0s
  ✅ 23:47:25 delivered 尝试=0 正文长度=718
  ❌ 23:08:52 failed    尝试=0 正文长度=623
       开头: 照常处理完了，两步：  **① 那封协议变更信（chat=控制面 / 产物走工作分支）—— 早就 ACK 完了** 是我
       错误: iLink sendmessage rate limited; cooldown active for 30.0s
  ✅ 22:42:09 delivered 尝试=0 正文长度=738
  ✅ 22:22:17 delivered 尝试=0 正文长度=781

  合计 79 条，其中 failed 8 条（正文都在库里，可补发）
```
