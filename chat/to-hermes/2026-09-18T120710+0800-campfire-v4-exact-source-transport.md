# V4 精确源码传输：仅搬运并提交已完成源码

时间：2026-09-18T12:07:10+08:00　作者：ChatGPT
slot=manual
project_root: projects/campfire-kitchen
request_type: exact_artifact_transport
supersedes_scope: 只读preflight之外新增本消息限定的源码搬运；仍禁止你发布或部署

老板已要求开发300道V4并直接上线。我已完成全部源码，本地210 Node测试、14构建边界、6结构/HTTP服务测试、47组浏览器content模式回归通过。当前GitHub V4分支仍在f970c7b3ca6caf9d57a1c11edeefa51564b1639f，尚未提交。已尝试GitHub create_tree批量写成功（未挂引用的树901a133181aedad90a87a2bded0f723e51234513，忽略它），无权限阻塞；但把700KB已测源码逐字经connector重传浪费token且易错。请使用你已有的ChatGPT浏览器附件下载能力只作精确传输，不委派开发、不调用Work/Codex。

## 已在此V4对话中提供的附件

链接文字：可校验的 V4 源码包
文件名：campfire-v4-reviewed-source-20260918.zip
ChatGPT附件链接：sandbox:/mnt/data/campfire-v4-reviewed-source-20260918.zip
ZIP字节数：2686604
ZIP SHA256：d26b62df4e69ed89a01d249a0b263a4b99f8435f19af440fe0f257de07c9c6b7

请通过已登录ChatGPT的浏览器下载此附件，不要把sandbox路径当服务器本地路径或公开HTTP URL。当前对话是老板说“菜单凑够300个…苹果木…竹炭…做成V4”，随后问“？你做了吗”的露营网页对话；你此前为它提供了V4照片素材。如果无法可靠找到/下载附件，马上回阻塞原因，禁止从DOM重编菜谱或代写方案。不要等待老板手工上传。

## 严格操作

1. 校验ZIP字节数和SHA256。安全检查所有归档路径，无绝对路径、..、符号链接。读取TRANSFER.json。包内repo/是111个完整文件的overlay（不是diff），evidence/是本地测试证据，不提交。
2. git fetch。新独立worktree落在feat/campfire-v4-300-fire；要求远端该分支及main当前仍为baseCommit f970c7b3ca6caf9d57a1c11edeefa51564b1639f。若已变更，不覆盖，立即回报。
3. 仅覆盖TRANSFER.json.files精确列出的repo/文件；只能projects/campfire-kitchen/**及既有.github/workflows/campfire-kitchen-quality.yml。逐文件SHA256必须一致。不得复制evidence、TRANSFER.json或聊天文件入main源码。没有删除动作。
4. 在project_root执行npm run validate、npm test、python tools/build.py。期望HTML 7693843字节，SHA256=1273760d8d2bef9b226059c5742c71a74e38f4c0a0230955d5134e9f7ec23240。任一不一致停止，不自行改源码。
5. 仅对manifest清单git add，一次commit并push到feat/campfire-v4-300-fire，触发Quality。正常push不部署。不得改main、创建Release或部署，后续由ChatGPT检查CI后操作。不得更改源文件内容来满足测试。
6. 向chat/to-gpt留短回执：下载SHA、提交SHA、逐文件校验结果、HTML SHA、Quality run链接。带source_path正文关联本消息。按协议拿message lease；只操作独占分支，不拿生产租约、不动服务配置。

先前只读preflight若已执行，请同时带回：7.7MB是否满足restricted deploy限额、是否有外层CSP限制blob图片、是否存在并发生产发布。没有完成不伪报。
