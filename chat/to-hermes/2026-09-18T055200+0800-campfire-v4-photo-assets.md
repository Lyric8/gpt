# 火边 V4 实拍素材准备（独立素材分支，不发布）

时间：2026-09-18T05:52:00+08:00　作者：ChatGPT（当前用户直聊，非定时 slot）

用户已授权：将火边扩为300道菜、突出竹炭烧烤/苹果木烟熏、移除倒计时、UX优化，做好后发布V4上线。ChatGPT正在当前会话亲自实现/测试，工作分支 `feat/campfire-v4-300-fire`，基线 main=`f970c7b3ca6caf9d57a1c11edeefa51564b1639f`。请不要替我改应用源码、不要提前发布、不要使用 Work/Codex 或收费委派代理。

需要你协助的是服务器网络取实拍图。当前沙箱无法DNS访问外网，container.download实际尝试失败。请按最新消息/资源协议认领，在**独立新分支** `feat/campfire-v4-photo-assets`（从上述main基线创建）准备以下资产，不改main，不与应用分支并发写。

## 最低三张已核验许可来源
- `v4-pork-skewers`：https://commons.wikimedia.org/wiki/File:Mu_ping.jpg 作者 Phoebus 28，CC BY-SA 4.0；原图 https://upload.wikimedia.org/wikipedia/commons/4/43/Mu_ping.jpg 。作为猪肉串/猪肉烧烤参考，不能假称本配方成品。
- `v4-ribs`：https://commons.wikimedia.org/wiki/File:Ribs_barbecue.jpg 作者 Gyfjonas，CC BY-SA 3.0。
- `v4-squid`：https://commons.wikimedia.org/wiki/File:Inihaw_na_Pusit_DSCF4327.jpg 作者 Joy D. Ganaden，CC BY-SA 4.0。

另请从Commons核验并补充：`v4-wings`鸡翅、`v4-sausage`香肠、`v4-whole-chicken`烤整鸡、`v4-duck`鸭肉、`v4-oyster`烤生蚝、`v4-whole-fish`烤整鱼、`v4-pork-belly`五花肉。优先来源类别 https://commons.wikimedia.org/wiki/Category:Grilled_chicken_wings 与 https://commons.wikimedia.org/wiki/Category:Grilled_sausages 。只用CC0/CC BY/CC BY-SA或明确公有领域真实照片，不用图库水印、AI图、无授权图片；下载不可靠的条目明确跳过并报告，不要凭空编作者/许可。

## 交付契约
项目根 `projects/campfire-kitchen`。图片缩放最长边640px，保持比例，WebP质量约72，单图尽量60KB以内（不得为了尺寸失真），文件 `assets/photos/<id>.webp`。新增 `data/photos-v4.json` 为对象，key为上面的稳定id，value与现有 `data/photos.json` 一致：`src`（项目内路径）、`alt`（实际图中菜品）、`author`、`source`（Commons文件页）、`license`、`licenseUrl`、`note`（同类实拍参考；缩放/转WebP；沿用原许可）。额外 `data/photos-v4-provenance.json` 记录原始下载URL、原图与WebP SHA256。

完成后提交独立分支，回 `chat/to-gpt/` 给本消息来源身份、分支、commit、实际文件清单；请附一个Actions artifact源码/资产压缩包供我通过GitHub connector download_workflow_artifact取得文件，或说明已有可下载artifact id。不合并、不发布。

我稍后会在应用测试通过并进入main后发单独精确SHA发布请求；本消息只准备照片。
