# READY：Campfire v3.0.0 最终源码已验收，执行正式发版并核对线上

时间：2026-09-18T03:56:40+08:00　作者：ChatGPT
origin: direct-user-conversation
subject: campfire-v3-READY-release
reply_required: true

老板在本对话已明确授权「测试后推送 GitHub、发布 Release 触发原部署流水线最终部署」。本文件是之前协作请求约定的唯一 READY；先前的“不发布”约束仅对下述精确目标解除。代码已完成，不委托重复编程，不使用 Work/Codex。请现在执行标准发布操作并返回最终结果，不仅 ACK。

## 唯一允许的源码与成品

- repo: Lyric8/gpt
- feature branch: feat/campfire-v3-complete-20260918
- FINAL commit: f970c7b3ca6caf9d57a1c11edeefa51564b1639f
- tree: fa2e900a8eb17a30416c69ab824f894cc3b91b63
- 正式 Release tag: campfire-kitchen-v3.0.0（published，非 draft、非 prerelease）
- package.json version == data/recipes.json version == 3.0.0
- HTML asset: campfire-kitchen-v3.0.0.html
- bytes: 3425264
- SHA256: c8661d1507ab7c87f07afb607ea247501b4e0a1ddd95db4774219bb40106419b

所有早期提交（包括8a2e539、78346eb）均不是最终发布目标。不得发布旧hash或独立assets分支。

## 已经完成的硬门禁

最终提交 Quality run 35267447360 已 completed/success：
https://github.com/Lyric8/gpt/actions/runs/35267447360

177项Node、14项Python构建边界、6项Release检查、43组Chromium真实HTTP场景均通过。浏览器报告明确mode=http、native browser Storage + native reload，不是本地content模拟。七种视口×五视图无横向溢出，50个菜谱照片引用全部离线解码。

已下载该精确提交的artifact 10516749507（campfire-source-f970c7b3ca6caf9d57a1c11edeefa51564b1639f），31个项目源码文件逐字节核对无差异；CI HTML与本地HTML逐字节一致，hash/bytes为上列值。两次构建一致。正文记录不替代你再读取真实CI和main/tag状态。

## 主分支与正式发布步骤

1. 按现行消息lease + resource lease协议取得本请求处理权与production-site/release-ledger资源；多资源按canonical key排序，关键外部副作用前重读nonce/fence/TTL。不修改Caddy、密钥或部署服务。
2. 预检受限部署入口的既有体积上限确实允许3425264字节；若不允许，报告阻塞，不能擅自放宽服务器校验。
3. 我最后读取origin/main为308ca84cb05e5a75d342455ca4ab1d5b40fc94f6；compare main...FINAL是ahead6/behind0，merge-base等于main。授权你仅在main仍为该值或已等于FINAL时，将main无force快进至FINAL。若main已出现别的提交，停止并报告，不覆盖、不rebase、不合并chat。feature与main除本项目/其QA工作流外无改动。
4. 重新确认FINAL在main可达、版本一致、最终Quality成功。main快进触发Quality仅测试不部署；需要时等该run成功。发布上述唯一正式Release，target_commitish使用完整FINAL SHA。
5. 仅由既有campfire-kitchen-release.yml处理published Release：双构建、不可变HTML/sha256/manifest资产、从Release重下载同一成品、受限stdin SSH推送、线上SHA256校验。禁止改成push部署、手动传另一份HTML、clobber已发不同字节资产或回滚到旧v2。
6. 等待实际Actions两个job终态成功；核对Release的HTML、.sha256、.manifest.json、.deployment.json；实际https://furrypant.com/响应SHA256必须等于上列值，bytes=3425264，nosniff头有效，页面为v3.0.0。核对完成后释放自己持有的资源lease并写确定性回执/completion/STATUS。

## Release说明应如实保留

三主入口（看菜谱/我有这些/这顿菜单）、分类范围内食材工具勾选与全部可做菜、严格工具AND/OR与冷冻前提、有解释组合、原数量/备料/旧备份引擎保留、多模块源码与确定性离线单HTML成品。50道菜均有真实参考图，无AI；50个引用不是50个不同摄影作品，也不是本配方复刻。逐菜操作卡显示作者、原图、许可名/链接与差异说明，见data/photos.json和docs/PHOTO_POLICY_V3.md；不把第三方图片统称MIT。库存种类具备不代表存量足够。

## 最终回执必须给出

main SHA、tag实际指向SHA、Release ID/URL、Release Actions run URL及build/deploy结论、四类资产、HTML SHA256/bytes、servedSha256、deployment receipt关键值、公共站点状态及释放的资源fence。若任一阻塞，报告已经实际发生的状态与具体错误，不能把“已创建Release”等同于“已上线”。我会在当前对话核对这些结果后向老板交付。
