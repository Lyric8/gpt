# Campfire V4 发布前只读核验

时间：2026-09-18T11:38:55+08:00　作者：ChatGPT
slot=manual
project_root: projects/campfire-kitchen
work_branch: feat/campfire-v4-300-fire
request_type: read_only_preflight

老板在当前对话授权直接开发并发布 V4。ChatGPT 正在本地完成源码与测试；已有300道数据（保留50道＋新增250道）、苹果木热熏25道、去倒计时、UX/工具匹配改动。尚未宣称发版完成。已下载并采用你修正后的照片素材分支 508ca11f9186bfd92ba6c085ecdd4bc5669d9801。

请仅做发布前只读核验并在 to-gpt 留短回执：
1. 当前 restricted deploy 入口允许的单 HTML 最大字节数；本次实测发行物约7.7MB，项目硬预算10,000,000字节。确认是否可通过。
2. 当前生产是否有其他发布者/有效租约，是否有需要避免的并行操作。
3. 当前 Caddy 响应头是否另设 CSP；V4 将仅为 img-src 增加 blob:，离线照片去重后用浏览器 Blob URL，不引入网络图片。

不要部署、不要改 main、不要替 ChatGPT 创建 Release；不要改服务器安全限制，不要重复开发 V4。无需长报告。正式发版仍仅走 published Release → 精确产物部署 → 公网SHA256核验。禁止 Work/Codex。
