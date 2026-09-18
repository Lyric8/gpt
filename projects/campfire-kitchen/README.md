# 火边 · 露营厨房 V4

300 道露营菜谱，按串烤、大肉、海鲜、苹果木烟熏、蔬菜、豆类与菌菇、主食、一锅与煎盘、冷菜与蘸酱、甜品、饮品分类。

> **本次交付状态：V4 已完成本地开发与下述验证，但本次没有发布 Release，也没有上线。GitHub 源码批量写入连续两次被安全状态检查拦截；没有更新主线或部署站点。** 既有生产地址为 https://furrypant.com/ ，它不是本包已上线的证明。详细状态见 [V4_DELIVERY_STATUS.md](docs/V4_DELIVERY_STATUS.md)。

## 使用

**看菜谱**：搜索菜名、食材或玩法，按分类浏览，每页24道。卡片只显示照片参考、菜名、分类、现场时间估计和加入菜单按钮。做法页依次展示火区、用量、准备、上火步骤、完成标准与吃法；不再提供逐菜倒计时。

**我有这些**：先选菜谱分类，再勾选食材、工具与燃料。候选只来自所选范围；分类变化保留库存。盐、油、木炭与冷冻条件不默认拥有。竹炭可满足烧烤炭要求，苹果木不能替代燃料；烟熏需要带盖双区炉、炉温计、探针温度计和苹果木。

**菜单与备料**：按人数和每菜份量合计采购，调整出餐顺序，核对净用量、预制和分装；导出 Markdown、CSV 或完整 JSON 备份。库存“拥有”不等于数量足够，称量备好后再勾选采购完成。

**炭火指南**：竹炭供热、苹果木增香；双区火、加盖间接烤、薄烟、两种温度计与安全收火分别说明。只做热烟熏熟食，不做冷熏或常温保藏。

数据只保存在当前浏览器。发行HTML内置数据、照片、脚本与样式；打开后不请求外部字体、图片或API，可离线使用。浏览器禁用存储时提示导出，不假装保存成功。

## 源码

```text
data/
  recipes.json                 # V4目录清单：版本、源文件、精确数量
  catalog/classics.json         # 原50道完整数据，稳定ID与数量保留
  catalog/ingredients.tsv       # 新原料定义（竖线分隔）
  catalog/{skewers,...}.tsv     # 十个分类，各25道明确编写的配方
  equipment.json               # 工具、能力、AND/OR要求
  photos.json                  # 既有照片来源与许可
  photos-v4.json               # 新照片来源、许可、参考边界
  photos-v4-provenance.json     # 素材检索与校对记录
assets/photos/                 # 本地WebP
src/
  app.mjs                      # 状态、路由、事件协调
  engine.mjs                   # 数量、备料、进度、备份兼容
  core/                        # 库存、推荐、存储、分页
  ui/                          # 浏览、库存、菜单、做法、炭火指南、资料
  styles/                      # 设计变量与各视图样式
  index.template.html          # 发行HTML模板
 tools/catalog.py              # 严格编译目录；不生成调料排列组合
 tools/build.py                # 确定性离线打包；照片池去重
 tests/                        # 数据、引擎、构建、浏览器与发版测试
```

`.tsv` 文件沿用工程文件名，实际分隔符为 `|`，不是制表符。每道配方包含名称、材料与克数、准备、烹饪、吃法、照片引用、时间估计、明确的烹饪模式及额外工具。构建验证路径、数量、唯一名称、原料、照片与工具引用。不是从“若干肉类×若干调料”自动乘出300道。

运行时和备份仍使用 `schemaVersion=2` 的完整数据库。`tools/catalog.py` 将源码清单编译成完整数据库，旧版自定义菜谱库仍可导入；导入的自定义库不会被悄悄替换。资料页提供明确确认后的“恢复内置菜谱”。旧版计时状态清空，旧菜单稳定ID、笔记、库存与数量语义保留。

维护多文件源码，不手改生成的 `index.html`。页面内照片共享一个内嵌资源池，不为同一参考照片重复保存几份Base64。

## 构建与验收

Node.js20以上、Python3.10以上。运行和构建无第三方npm依赖；浏览器测试依赖固定在 `tests/requirements.txt`。

```bash
cd projects/campfire-kitchen
npm run validate
npm test
python tools/build.py
python -m pip install -r tests/requirements.txt
python -m unittest discover -s tests -p '*_test.py'
python tests/release_checks.py
python -m playwright install --with-deps chromium
python tests/browser_smoke.py --mode http
```

`tools/serve.py --no-browser --port 8080` 提供本地HTTP预览。编译完整数据库：

```bash
python tools/catalog.py --output /tmp/campfire-catalog.json
```

浏览器验收逐一打开全部300道、遍历13页，检查搜索、库存、组合、采购、导入、防脚本注入、焦点、刷新恢复、照片解码、实际文本对比度与320—1440像素布局。只有 `--mode http` 验证真实HTTP来源与原生存储；受限环境 `--mode content` 使用显式存储替身，报告会说明，不能代替上线门禁。

## 发布与回滚

保留现有 **published Release → build → immutable assets → exact-asset deploy → public SHA256 verification** 流水线。代码push不部署。

版本必须同时匹配 `package.json` 与 `data/recipes.json`。源码通过Quality并进入main后，发布非预发布Release，标签格式 `campfire-kitchen-v4.0.0`。流水线验证main祖先关系、两次构建字节一致、Release资产不可变、下载回验、受限SSH部署、线上字节哈希与响应头。发布完成以部署回执为准，不以提交或创建标签为准。

回滚按 [RELEASE_PIPELINE.md](docs/RELEASE_PIPELINE.md) 使用已发布且校验成功的旧版资产，保留旧版Release，不覆盖不同字节的已发布文件。不会修改网关进程、凭据或其他项目。

## 内容边界

配方是基于烹饪和食品安全原则编写的两人分享配方，未逐道在你的炉具上实做。分钟用于安排用餐，不替代中心温度与完成标准。数量随人数调整，炉面面积、批次、腌制、冷却与升温时间需另行安排。

照片是有署名和许可的实拍参考，不是本配方逐道复刻照片；食材照片明确标注。暂无匹配图片时显示缺图，不用无关照片冒充。版权、食安来源在做法和资料页可查看。
