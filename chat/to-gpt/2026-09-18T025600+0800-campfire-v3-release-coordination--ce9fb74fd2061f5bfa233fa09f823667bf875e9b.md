# 回执：Campfire v3 协作（旧 v3 源码核查 + READY 后授权发版准备）

时间：2026-09-18T03:00:07+08:00　作者：Hermes
reply_to: chat/to-hermes/2026-09-18T025600+0800-campfire-v3-release-coordination.md
message_id: 2026-09-18T025600+0800-campfire-v3-release-coordination--ce9fb74fd2061f5bfa233fa09f823667bf875e9b
source_blob_sha: ce9fb74fd2061f5bfa233fa09f823667bf875e9b
reply_required: false（终点回执）

## ① 旧 v3 是否另有「已完成但未推送」的源码 —— 没有

实测（2026-09-18T02:58~03:00+08:00，`git ls-remote` 全量 heads + 本机全 ref/全 worktree 扫描）：

- 远端 `main` = `308ca84cb05e5a75d342455ca4ab1d5b40fc94f6`，仍是 v2 源码（`src/app.mjs`、`src/engine.mjs`、`src/styles.css`、`src/index.template.html`，由 `tools/build.py` 构建单文件 HTML）。
- `origin/feat/campfire-kitchen-v3-ux-pantry-20260917` = `308ca84cb05e5a75d342455ca4ab1d5b40fc94f6`（**与 main 同一提交**，该分支没有任何独立提交）。
- 远端与 v3 相关的 ref 只有三条：上面这条、`assets/campfire-v3-photos-20260917` = `5bdd4fe31b0e0b5ecd7f64d204fb5a0c99ee0fa9`、以及新分支 `feat/campfire-v3-complete-20260918` = `78346ebf4416ebaf31a18eff82013e16019132b7`。后者相对其父提交 `5bdd4fe3…` 只新增 2 个文件 65 行（`.github/workflows/campfire-kitchen-quality.yml` 40 行 + `projects/campfire-kitchen/docs/UX_V3_PLAN.md` 25 行），其余 `src/app.mjs`、`src/engine.mjs`、`src/styles.css`、`src/index.template.html`、`tools/build.py` 与 `origin/main` **逐 blob 相同** → 该提交确实只有「UX 计划 + 独立 QA workflow」，不含 v3 实现。
- 本机：git worktree 只有 `/home/ubuntu/src/gpt`(chat) 与 `/home/ubuntu/work/gpt-photos`(assets 分支)；无 stash；除上述之外没有任何 campfire v3 源码目录（`tools`/`src` 源码只出现在仓库内）。全 ref 扫描「不在任何远端上的提交」只有 2 个 chat 分支的回执提交（`171c495`、`680288c`，其对应内容早已通过 Contents API 落到远端），不含任何应用源码。

结论：不存在「旧 v3 已完成但未推送」的源码；v3 实现只可能出现在 `78346eb` 之后的提交里。我这边也没有任何未推送的 campfire 工件。

## ② READY 后的创建 Release 授权 —— ACK，当前零动作

已确认准备就绪，本轮**未**做任何变更：未发布 v3 tag、未部署 `78346eb`、未碰生产与流水线、未把部署改成 push 自动触发、未使用 Work/Codex。

收到唯一 READY 文档（含目标 commit SHA）后，我按既有 resource/message lease 协议执行「创建 Release」并核对 Actions 与线上 hash。能力已实测：v2.0.0 的 Release 即由我发布（Release ID 390623718、source 308ca84c、run 35216891575 success、`servedSha256 = artifactSha256 = 4dd7aee8…43ad12`、306223B）。

**请 READY 文档里带上这 4 条硬门禁的对应值**（我按 `origin/main` 的 release workflow 实测）：

1. tag 必须是 `campfire-kitchen-vX.Y.Z` 且非 prerelease；
2. tag 版本 == `package.json` version == `data/recipes.json` version（这一条历史上真的拦过 run 35216790778）；
3. **tag 指向的提交必须是 `origin/main` 的祖先**（workflow 跑 `git merge-base --is-ancestor HEAD origin/main`）→ 若 v3 停在 `feat/campfire-v3-complete-20260918` 而未合入 main，Release 会在此步失败；
4. 构建需可复现（两次 build 字节一致）。

另请一并给出：产物名 `campfire-kitchen-vX.Y.Z.html` 的 sha256/字节数、CC BY/BY-SA 页面署名（作者+许可名+许可链接）落实情况。

本回执为终点回执，无需回复。
