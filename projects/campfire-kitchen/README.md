# 火边 · 露营风味厨房 v3

离线优先的露营菜谱、现有食材匹配和一顿饭规划工具。内置50道定稿菜谱、112种规范材料、6类菜与8套现成菜单。正式站点：<https://furrypant.com/>。

## 三个入口

**看菜谱**：实拍参考图卡片、分类、中文搜索、主动操作时间和核心食材直接可见。完整做法在操作卡中；照片有来源与许可。八套现成菜单放在可展开区域，不挤占浏览主线。

**我有这些**：先多选想做的菜谱类别，再按组勾选已有食材和工具；候选来自范围内菜谱，不摆出无关物品。勾选实时更新“完全具备 / 缺食材 / 缺工具或冷冻 / 全部”；换分类保留库存，搜索状态只选择可见候选。符合条件的菜可组成有理由的组合，不把盐、油或冰箱能力默认算有。

**这顿菜单**：按人数、每菜份数和出餐顺序计算；接着进入“备料与分装”，查看合计采购、按菜分配、预制任务、操作进度、Markdown/CSV与完整JSON备份。已有一种食材不代表数量足够或已经称量装车。

库存、菜单、笔记与记录仅保存在浏览器，不上传服务器。页面打开后不请求外部图片、字体、脚本或API。下载发行HTML后可离线打开；浏览器拒绝本地存储时明确提示先导出备份。

## 源码结构

```text
data/
  recipes.json              # 定稿菜谱、材料、分类、菜单、来源
  recipes.schema.json       # 结构契约
  equipment.json            # 工具实体、能力、AND/OR要求
  photos.json               # 每菜照片、署名、许可、参考边界
assets/photos/              # 本地实拍WebP
src/
  app.mjs                   # 状态、事件、存储和视图协调
  engine.mjs                # 数量/备料/进度/备份迁移引擎
  core/
    pantry.mjs              # 分类范围、候选并集、精确可做判断
    recommendations.mjs     # 有约束的组合选择与解释
    storage.mjs             # 可失败的存储适配
  ui/
    components.mjs          # 安全转义、照片、图卡、分类组件
    browse.mjs              # 看菜谱
    pantry.mjs              # 我有这些
    planning.mjs            # 这顿菜单与备料
    recipe.mjs              # 操作卡
    settings.mjs            # 资料、导入与管理
  styles.css                # 本地样式入口
  styles/                   # 设计变量、基础、卡片、库存、操作布局
  index.template.html       # 极小HTML壳
 tools/                     # 确定性离线打包、校验、可选HTTP服务
 tests/                     # 引擎/库存/构建/浏览器/发版回归
```

维护的是多文件源码；`index.html` 是自动打包出的离线发行物，已gitignore，不应手改。新增菜谱/分类不需要修改渲染分支。详细扩展入口、库存语义、工具规则、构建语法与发布边界见 [EXTENDING_V3.md](docs/EXTENDING_V3.md)。

## 本地运行与测试

Node.js 20以上，Python 3.10以上；运行时与构建无npm第三方依赖。测试依赖单独固定在 `tests/requirements.txt`。

```bash
cd projects/campfire-kitchen
npm run validate
npm test
python tools/build.py
python tools/serve.py --no-browser --port 8080
```

浏览器访问本地8080端口。完整验证：

```bash
python -m pip install -r tests/requirements.txt
python -m unittest discover -s tests -p '*_test.py'
python tests/release_checks.py
python -m playwright install --with-deps chromium
python tests/browser_smoke.py --mode http
```

Quality workflow 在独立分支/PR运行这些测试并保留源码、报告与截图artifact；**它不部署**。报告区分真实HTTP与受限沙箱content模式，不能拿模拟存储替代真实浏览器刷新验收。

## 发版与回滚

只保留既有 **published Release → build → immutable assets → exact-asset deploy → public SHA256 verification** 流水线。代码push不部署。

版本同步修改 `package.json` 与 `data/recipes.json`，提交通过Quality并进入main，再创建非prerelease `campfire-kitchen-vX.Y.Z`。正式流水线会验证版本与main祖先关系、两次构建字节一致、Release产物下载校验、受限SSH部署、线上字节哈希与安全响应头。禁止覆盖已发布的不同字节产物。部署/回滚细节见 [RELEASE_PIPELINE.md](docs/RELEASE_PIPELINE.md)。

## 设计与内容边界

[UX_V3_PLAN.md](docs/UX_V3_PLAN.md) 记录信息架构与研究依据；[PHOTO_POLICY_V3.md](docs/PHOTO_POLICY_V3.md) 记录真实照片引用、参考差异和署名要求。照片并非本配方复刻成果，不依据照片替换原材料。

原105项数量引擎回归保留。v3新增库存、工具、组合、焦点/范围/存储恢复与构建边界测试。受控测试不等同于野外实测烹饪；安全、冷链、禁火规定和真实熟度仍按操作卡与现场要求确认。主动操作时间是配方估计，不是实测保证。
