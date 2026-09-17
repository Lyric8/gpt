# v3 扩展契约

## 目录与修改入口

| 内容 | 唯一维护入口 | 验证 |
|---|---|---|
| 新菜、材料、步骤、分量、分类、套餐 | `data/recipes.json` | Schema、`npm run validate`、引擎回归 |
| 工具的名称、兼容能力与条件 | `data/equipment.json` | `tests/pantry.test.mjs` |
| 实拍照片及署名 | `assets/photos/*.webp`、`data/photos.json` | 构建硬门禁、浏览器解码 |
| 库存、分类范围、缺项 | `src/core/pantry.mjs` | 纯函数单元测试 |
| 组合排序、操作预算与解释 | `src/core/recommendations.mjs` | 纯函数单元测试 |
| 浏览、库存、菜单/备料、操作卡、管理 | `src/ui/*.mjs` | Chromium 交互回归 |
| 配色、字号、间距 | `src/styles/tokens.css` | 手机与桌面截图 |
| 布局、卡片、库存、操作卡 | `src/styles/{base,catalog,inventory,workflows}.css` | 七种视口回归 |
| 数量、备料合并、进度失效、旧版迁移 | `src/engine.mjs` | 原105项引擎测试，保持独立 |

`src/app.mjs` 只负责事件路由、状态协调和本地持久化；不要重新把视图或匹配规则塞回入口。新增分类自动从菜谱派生，不需要修改视图条件分支。

## 新增一道菜

以一条现有完整菜谱作为结构起点，按 `recipes.schema.json` 填写全部必填字段。使用稳定、唯一 ID；现有 ID 不因中文名称调整而重命名。每条 ingredient 引用材料字典中的规范 ID，`form` 说明原始状态；生虾与熟虾、鲜草与干草不是同一种库存，不能合并为别名。分量、缩放规则、批次和最低安全要求由数量引擎校验，不允许通过 UI 隐藏必需材料。

新分类直接写 `recipe.category`。浏览页展示该分类；库存候选由选中分类内全部菜的原料与工具并集生成。没有库存预选，盐、油、饮用水也不例外。`pantryHint` 只用于阅读提示与卡片摘要，绝不是“自动拥有”。

为新菜增加 `photos.json` 的同 ID 条目和本地 WebP。每条必须具备 `src, alt, author, source, license, licenseUrl, note`；图片来源与许可链接使用 HTTPS。新菜没有署名或图片、孤儿照片元数据、错误图片格式都使构建失败。自定义库在浏览器导入新增菜时没有随库上传照片；会明确显示“暂无实拍”，不得拿另一道菜随机顶替。内置库发版要求完整照片覆盖。

完成修改后运行本文最后的全部命令，不编辑 `index.html`。

## 工具：能力与 AND / OR

`tools` 中每个实体工具有唯一 `id`、显示 `name`、`group`、`provides` 能力数组及 `note`。工具默认提供自己的 ID，再提供显式声明的能力。能力不做名称模糊猜测，也不做隐蔽传递推导：大带盖锅需要明确列出其支持的小锅/带盖锅能力。

`requirements` 的键是菜谱 `equipment` 中的完整原文。值的外层数组为 **AND**，内层为 **OR**。`[["tongs","spatula"]]` 表示夹子或铲子任一即可；`[["raw-tongs"],["cooked-tongs"]]` 表示生食夹与熟食夹均需具备。单夹不能冒充两夹，单杯不能满足两杯，任意一只锅盖不能默认适配另一口锅。

内置工具目录结构缺失、重复 ID、空条件或未知能力在索引建立时失败。用户导入自定义菜谱而没有对应工具规则时，以 `custom:<原文>` 生成精确候选，必须显式勾选，不默认为满足。

冷冻是独立硬条件：`needsFreezer` 菜谱只有用户明确确认持续 ≤ -18℃ 冷冻条件才进入“完全具备”。冷藏车载冰箱与保冷箱不自动满足它。库存仅检查品类和这些工具条件；燃料、火源、合法用火、冷链和总存量仍由备料与操作卡确认。

## 库存、范围与组合

库存保存在 `campfire-kitchen-pantry-v1`；菜单沿用 `campfire-kitchen-state-v2`，旧库沿用 `campfire-kitchen-library-v2`。更换分类只改变候选与结果，不清空范围外已拥有内容。多分类是并集；空分类数组代表全部。搜索内“本组全选”只选择当前查询中可见的候选。损坏原值在覆盖前保留到 recovery 键；保存失败必须展示提醒。

完整备份保留既有 `backupVersion: 2`，新增可选 `inventory` 字段；旧备份无此字段时保留当前仍有效的库存。数据升级不是把备份号和目录号随意一起加一。

推荐只接受当前范围内 `ready=true` 的菜。三种方向为“换着口味吃”“少忙一点”“一起动手吃”；有确定性排序、主动操作预算、菜数上限、主料去重和多样性理由。它是受限启发式选择，不是营养配餐优化，也不承诺库存数量足够。加入组合重新计算可做池、确认替换现有菜单，并把每道份数重置为1，避免继承上一顿隐藏的半份/四份设置。真正的合计用量由备料引擎产生。

## 模块和离线构建

源文件为原生 `.mjs` 模块，可直接被 Node 测试。标准库打包器为本项目固定语法提供隔离作用域，不是通用 JavaScript 编译器：仅接受显式相对路径的静态具名 import，以及顶层 export function / async function / const / class。具名导入支持 `as`；每条 export 仅一个声明。不要添加循环依赖、默认导出、转导出、动态 import、可变 live binding、顶层 await、import assertion、远程包或副作用导入。需要超出此契约时，应明确引入并固定成熟构建工具及锁文件，不能扩大正则去猜任意 JS 语义。

CSS 从 `src/styles.css` 按顺序引用本地文件；不加载远端字体、CSS、脚本或图片。JSON 对 script 结束标签和 Unicode 分隔符转义；图片构建时读真实字节、检查 WebP 头与尺寸，再内嵌。发布仍是一个 HTML，因此断网打开不依赖 CDN，既有单文件部署与 SHA256 回滚契约不变。HTML 是生成物，不是源码维护入口。

## 完整验收命令

```bash
npm run validate
npm test
python -m pip install -r tests/requirements.txt
python -m unittest discover -s tests -p '*_test.py'
python tests/release_checks.py
python tools/build.py
python -m playwright install --with-deps chromium
python tests/browser_smoke.py --mode http
```

浏览器报告必须说明模式。`--mode http` 才验证真实 origin、真实 localStorage 与浏览器 reload。仅在环境禁止导航时使用 `--mode content`；该模式显式使用 Storage 接口替身，不能替代发版前的 HTTP CI。浏览器测试检查 Blob 内容，不把操作系统下载对话框算作已测。视口模拟覆盖 Chromium，不宣称已实测 iOS Safari 或所有 Android 厂商内核。

## 发布

版本必须在 `package.json` 和 `data/recipes.json` 同步；目标提交先通过 Quality，再进入 `main`。发布非预发布 Release `campfire-kitchen-vX.Y.Z`，由现有 Release workflow 构建两次、上传不可变产物、下载原产物部署、比对线上 SHA256。普通 push 不部署，禁止手动上传一个与 Release 不同的 HTML 去“修线上”。
