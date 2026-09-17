# v3 验收记录

本地源码产物：3.0.0，50道菜，112材料，6分类。最后本地构建：3,426,552字节；SHA256 `cd4bc1ce8ccc8bf2866927a426f838646162dbda663cd3fe21d7496de4f8b915`。

| 项目 | 已实跑结果 |
|---|---|
| Node数量/备料/迁移及库存/组合/存储 | 177 passed，0 failed，0 skipped；含原105项 |
| Python模块/CSS/图片/版本/原子构建边界 | 14 passed |
| Release检查 | 6项通过：Schema、语义、双构建、全模块语法、真实HTTP字节与nosniff、禁目录列表 |
| 本地Chromium场景 | 43组通过，无JS异常；明确为content模式 |
| 响应式 | 320/360/390/430/768/1024/1440px，五个视图无横向溢出 |
| 图片 | 50个菜谱图片引用全部离线解码，逐菜有署名及许可链接 |

浏览器覆盖：搜索与组合筛选、鲜干及材料形态、人数/份量与批次、采购合计和勾选失效、步骤进度和笔记、前台计时、套餐与顺序、历史筛选、分装、Markdown/CSV/JSON与打印、旧v1备份迁移、坏库拒绝与HTML转义、内置恢复、存储拒绝与损坏救援、冷冻门禁、库存范围并集、可见组选择、焦点恢复、全50道匹配、组合应用、含库存备份、弹窗Tab/Escape和手机结果跳转。

## 环境与证据边界

本地环境禁止 Chromium 的 file/localhost 导航，因此本地 `--mode content` 使用精确HTML的 `set_content` 与Storage接口替身；不是“真实localStorage刷新已测”。本地独立HTTP服务字节测试正常，不等于浏览器导航获准。

仓库 Quality workflow **必须另跑 `--mode http`**，使用真实origin、原生localStorage和浏览器reload；任一步失败不得发布。该run的 artifact `campfire-source-<commit SHA>` 包含 `test-results/browser-v3-report.json`、`release-v3-report.json`、截图及该提交构建出的HTML。报告写入实际运行模式、产物SHA256和字节数，供发布前按精确提交核对；这里不预先宣称尚未返回的CI通过。

发行Release另做双构建字节一致、不可变资产和线上SHA256对比。源仓库的历史v2报告保留为历史证据，不用于替代v3验收。不宣称在iOS Safari、实际Android手机、系统下载弹窗或野外烹饪中完成了实机验收。
