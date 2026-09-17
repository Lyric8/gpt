# Campfire Kitchen 发布流水线设计

## 发布契约

生产环境的**新版本发布**只接受 GitHub Release：普通 `push`、PR、测试运行都不会触碰线上。唯一例外是显式的“回滚到已有正式 Release”，它只能重放一个已经发布、带完整哈希与 manifest 的旧成品，不能构建或上传任意新内容。

本项目位于 monorepo 的 `projects/campfire-kitchen/`。正式 Release tag 必须使用：

```text
campfire-kitchen-vX.Y.Z
```

其中 `X.Y.Z` 必须同时等于：

- `projects/campfire-kitchen/package.json` 的 `version`
- `projects/campfire-kitchen/data/recipes.json` 的 `version`

Tag 指向的 commit 必须可从 `main` 到达。GitHub prerelease 不部署；其他项目的 Release tag 不触发本项目 job。

## 设计决定

### 1. `index.html` 不再提交进 Git

`index.html` 是由 `data/recipes.json + src/* + tools/build.py` 确定生成的发布物，不是源码。继续提交会形成第二份事实源。

从本流水线开始：

- `index.html` 被 `.gitignore` 排除；
- 旧 `SHA256SUMS.txt` 删除；那份清单里指向未提交 PNG 的陈旧条目也一起消失；
- 发布时在 GitHub runner 上**连续构建两次并逐字节比较**；
- Release 上的 HTML + `.sha256` + manifest 才是版本对应的正式成品。

Windows 的 `打开程序.cmd` 会先从源码构建，再打开本地生成的 `index.html`。

### 2. 构建发生在 GitHub runner，不在生产服务器

正式构建只需要 Node.js 20+ 与 Python 3.10+；核心校验没有 npm runtime dependency。流水线先执行数据语义校验、105 项引擎测试、JS 语法检查，再构建两次。

生产服务器不 checkout Git、不装构建依赖，也**不从 GitHub 拉 Release 附件**。Hermes 已实测这台服务器下载 GitHub Release 资产会超时，因此采用推式部署。

### 3. 部署的是“从 Release 再下载回来”的同一个文件

build job 将三份不可变资产挂到 Release：

```text
campfire-kitchen-vX.Y.Z.html
campfire-kitchen-vX.Y.Z.sha256
campfire-kitchen-vX.Y.Z.manifest.json
```

随后 deploy job 在 GitHub runner 上**重新从 GitHub Release 下载 HTML**并复核 SHA-256，再把这一个文件经 Hermes 已落地的受限 SSH 通道流式送到服务器。

因此：

```text
源码构建出的字节
  = Release 可下载 HTML
  = Actions 实际发送的 HTML
  = 线上 Caddy 返回的 HTML
```

同版本同名 Release asset 已存在时，只允许字节完全相同；流水线不会用 `--clobber` 改写已经发布的版本。

### 4. 完全复用 Hermes 已安装并实测的受限部署入口

服务器侧事实以 `chat` 分支的 `chat/to-gpt/2026-09-17-deploy-boundary.md` 为准。流水线**不要求 Hermes 换掉它，也不在服务器新增 root installer**。

已落地边界：

- SSH 用户：`campfire-deploy`
- SSH 端口：`22`
- 服务器：`124.223.114.109`
- authorized_keys 使用 `restrict,command="/usr/local/bin/campfire-ssh-entry"`
- 用户 shell 为 `nologin`
- 唯一允许的远端命令是字面量 `deploy`
- 部署数据从 stdin 输入；服务器账号不能写站点、不能拿 shell、不能改 Caddy、不能任意 sudo

Actions 发出的数据流严格是：

```text
version=1 tag=vX.Y.Z sha256=<64位小写sha256>\n
<完整 index.html 字节>
```

即：

```bash
{ printf 'version=1 tag=v%s sha256=%s\n' "$version" "$sha"; cat artifact.html; } |
  ssh campfire-deploy@124.223.114.109 deploy
```

服务器入口已经负责：格式/体积/HTML身份/哈希检查 → 备份当前版本 → 原子替换 → reload Caddy → 实际 HTTP 返回体哈希检查 → 失败自动回滚。

Actions 还会从公网再 GET 一次站点，要求返回体 SHA-256 与 Release 一致，并检查 `X-Content-Type-Options: nosniff`。

### 5. Release 资产与版本完全绑定

Release tag 用项目名前缀避免 monorepo 冲突：

```text
campfire-kitchen-v2.1.0
```

服务器协议中的 `tag` 按 Hermes 已实现的格式使用：

```text
v2.1.0
```

manifest 记录：Release ID、正式 tag、版本、源码 commit、成品文件名、SHA-256、字节数和发布时间。

生产部署成功后，再给 Release 增加：

```text
campfire-kitchen-vX.Y.Z.deployment.json
```

它记录同一成品的 hash、源码 SHA、Actions run URL 和部署时间。GitHub Environment `campfire-kitchen-production` 同时保留 deployment history。

### 6. 保留人工兜底，但它不是日常发布

`deploy/release.sh` 保留：

```bash
./deploy/release.sh --dry-run
./deploy/release.sh --deploy
```

`--dry-run` 只做完整性、测试、JS 语法和双构建一致性检查。

`--deploy` 是 break-glass 通道，需要本机显式提供：

```text
DEPLOY_KEY_FILE
DEPLOY_KNOWN_HOSTS_FILE
```

然后通过**同一个 Hermes 受限 stdin SSH 入口**推送构建产物。它不会获得服务器 shell 或 sudo。正常发版不得用这个通道绕开 GitHub Release。

## GitHub workflows

### 正常发版

文件：`.github/workflows/campfire-kitchen-release.yml`

唯一触发器：

```yaml
on:
  release:
    types: [published]
```

两个 job：

1. **Build immutable Release asset**：校验 tag/version/main → 测试 → 双构建 → Release 不可变资产。
2. **Deploy exact Release asset**：从 Release 下载成品 → SHA 校验 → stdin SSH 推送 → 公网再次验 hash → deployment receipt。

### 回滚

文件：`.github/workflows/campfire-kitchen-rollback.yml`

这是显式 `workflow_dispatch`，输入一个**已经存在的正式 Release tag**。它：

1. 不 checkout 源码，不重新构建；
2. 只允许 `campfire-kitchen-vX.Y.Z` 的正式、非 prerelease Release；
3. 要求 HTML、`.sha256`、manifest 三个正式资产都存在；
4. 三者互相校验；
5. 把这个旧 Release 的原始 HTML 通过同一受限 SSH 通道重新部署；
6. 再验证公网返回体 hash。

因此回滚不会制造“一个旧 tag 对应新字节”的情况，也不能借 rollback workflow 部署任意文件。

## GitHub Environment / Secrets

生产 job 使用 Environment：

```text
campfire-kitchen-production
```

流水线只需要两项私有配置：

| 名称 | 内容 |
|---|---|
| `CAMPFIRE_DEPLOY_SSH_KEY` | 对应 `campfire-deploy` authorized_keys 公钥的 ed25519 私钥 |
| `CAMPFIRE_DEPLOY_KNOWN_HOSTS` | 固定服务器 SSH host key 的完整 known_hosts 行 |

主机、端口、用户名本身不是秘密，直接作为 workflow 配置写明，以减少秘密配置面。

workflow 强制 `StrictHostKeyChecking=yes`、`BatchMode=yes`、`IdentitiesOnly=yes`，不会动态 `ssh-keyscan` 后无条件信任。

## 失败边界

- 普通 push：workflow 根本不触发生产发布。
- tag/version/source 校验失败：没有 Release asset，没有 SSH。
- 测试或构建失败：没有 Release asset，没有 SSH。
- 两次构建不同：立即失败。
- 同名 Release asset 与当前构建不同：拒绝覆盖，没有 SSH。
- 从 Release 下载后的 checksum/哈希失败：没有 SSH。
- SSH 身份或 host key 不匹配：服务器没有收到有效部署请求。
- 数据流 header、体积、HTML身份或 SHA-256 不合格：Hermes 入口拒绝，线上不动。
- 服务器安装后的本机真实返回校验失败：Hermes 入口自动恢复上一版。
- GitHub runner 最后的公网 hash 检查失败：workflow 红灯并留下证据；服务器入口此前已经完成自己的本机校验。

## 回滚验收边界

代码层已经把回滚限制为“重放已有正式 Release 的不可变成品”。真正的**生产回滚演练**需要线上至少存在两个不同 hash 的正式 Release；在只有 v2.0.0 一个字节版本时，重放同一 hash 不能冒充有效回滚测试。第一次出现下一版实际内容变化后，应执行一次 rollback workflow，再重新发布当前版，记录两个方向的 hash 证据。
