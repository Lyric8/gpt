# Lyric8/gpt

这是一个**多项目总仓（monorepo）**，用于存放由 ChatGPT / HermesBot / 其他自动化工具共同维护的独立项目与相关资产。

> **重要：仓库根目录不是任何一个应用的项目根目录，也不是部署目录。**

## 给 HermesBot / Agent 的硬规则

1. **不要把仓库根目录当成可部署项目。**
   - 不要从仓库根目录运行 `npm install`、`npm run build`、`python app.py`、静态站点部署或类似命令。
   - 不要因为根目录缺少 `package.json`、`index.html`、`src/` 就自行创建它们。

2. **所有独立可运行项目统一放在 `projects/<project-name>/` 下。**
   - 每个项目目录都是独立工作区。
   - 构建、测试、部署、依赖安装都必须在目标项目目录内进行。
   - 项目自己的 `README.md` 是该项目的具体操作契约。

3. **执行任何部署前，必须先确定明确的 `project_root`。**
   - 如果用户或任务明确给了项目路径，严格使用该路径。
   - 如果没有给项目路径，不要猜；先检查本 README 的“项目索引”。
   - 如果仍有歧义，停止并询问，不要自动选择某个目录。

4. **不要修改无关项目。**
   - 只改当前任务指定项目目录及确有必要的共享文件。
   - 不要为了部署一个项目重排、移动、重命名其他项目。
   - 不要把某个项目的配置、依赖、构建产物放到仓库根目录。

5. **不要擅自改变 monorepo 结构。**
   - 不要把 `projects/campfire-kitchen/` 内容移动到根目录。
   - 不要创建第二份同项目副本。
   - 不要为了某个托管平台“方便识别”而破坏目录隔离；应在部署配置中指定正确的项目子目录。

6. **部署前先检查目标项目是否完整。**
   - 阅读目标项目自己的 `README.md`。
   - 确认 README 描述的入口文件、源码、数据文件和构建脚本都实际存在。
   - 如果 README 声称需要的关键文件缺失，视为**源代码同步未完成**，不要猜测生成替代文件，也不要直接部署残缺版本。

7. **不要把构建产物误当源码。**
   - 如果项目同时包含源码和单文件发布物，优先按项目 README 指定方式从源码构建。
   - 不要反向修改生成后的 bundle 来代替修改源码，除非任务明确要求这样做。

8. **提交修改时保持项目边界。**
   - Commit message 应说明改的是哪个项目。
   - 大型修改优先保持一次提交只覆盖一个项目。

## 仓库结构约定

```text
gpt/
├─ README.md              # 本文件：总仓索引与 Agent 规则
├─ projects/              # 独立可运行项目
│  ├─ campfire-kitchen/   # 火边 · 露营风味厨房
│  └─ ...                 # 后续项目
├─ chat/                  # 跨执行者交接：to-gpt/ 与 to-hermes/
├─ research/              # 可选：跨项目/独立研究产物
└─ tools/                 # 可选：真正跨项目共享的工具
```

说明：`research/`、根级 `tools/` 仅在确有跨项目资产时创建；**不要为了凑目录结构而创建空目录。**

## 项目索引

### `projects/campfire-kitchen/`

**项目名：** 火边 · 露营风味厨房 / Campfire Kitchen  
**类型：** 静态前端、离线优先的露营菜谱与备料工具  
**项目根目录：** `projects/campfire-kitchen`  
**项目说明：** `projects/campfire-kitchen/README.md`

部署这个项目时，HermesBot 必须把工作目录切换到：

```bash
cd projects/campfire-kitchen
```

然后再按该目录 README 的说明检查、构建和部署。

**禁止：**

```bash
# 错误示例：不要在总仓根目录直接部署
cd /path/to/gpt
npm install
npm run build
```

**正确原则：**

```bash
cd /path/to/gpt/projects/campfire-kitchen
# 然后按项目 README 执行
```

## 给自动化部署系统的最小上下文

```text
repository: git@github.com:Lyric8/gpt.git
branch: main
project_root: projects/campfire-kitchen
project_readme: projects/campfire-kitchen/README.md
repo_root_is_deployable: false
```

如果任务目标不是 `campfire-kitchen`，不要复用上面的 `project_root`；应先在本文件项目索引中找到对应项目。

## 跨执行者交接（`chat/`）

同一仓库上可能有多个执行者（ChatGPT / Hermes / 其他自动化工具），彼此看不到对方的会话。需要交接的事情一律写成文档放进 `chat/`，不靠口头转述：

- `chat/to-gpt/` —— 交给 ChatGPT 的任务书、需要它拍板的决策、它要遵守的约束
- `chat/to-hermes/` —— 交给 Hermes 的服务器侧请求（发布、运维、配置）

规矩：文件名带日期、一份文档一件事、写完不改（要修正就新写一份并说明它替代了谁）、**不放任何密钥**、回执写在对方的目录里。详细约定见 `chat/README.md`。

角色分工：**代码开发与流水线设计归 ChatGPT，线上发布与服务器运维归 Hermes。**

## 总原则

**根目录负责索引和规则，子目录负责项目本身。**  
任何 Agent 在不确定“该在哪个目录工作”时，都应先停下来确认，而不是把文件往仓库根目录堆。