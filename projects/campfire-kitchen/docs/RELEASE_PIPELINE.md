# Campfire Kitchen 发布流水线设计

## 发布契约

生产环境只接受 **GitHub Release** 触发的正式发布：普通 `push`、PR、手工运行测试都不会部署线上。

本项目位于 monorepo 的 `projects/campfire-kitchen/`。正式 Release tag 必须使用：

```text
campfire-kitchen-vX.Y.Z
```

其中 `X.Y.Z` 必须同时等于：

- `projects/campfire-kitchen/package.json` 的 `version`
- `projects/campfire-kitchen/data/recipes.json` 的 `version`

Tag 指向的 commit 必须可从 `main` 到达。GitHub prerelease 不部署；其他项目的 Release tag 不触发本项目 job。

## 五个设计决定

### 1. `index.html` 不再提交进 Git

`index.html` 是由 `data/recipes.json + src/* + tools/build.py` 确定生成的发布物，不是源码。继续提交会形成第二份事实源，并要求开发者每次同时更新源码、生成物和静态哈希清单。

从本流水线开始：

- `index.html` 被 `.gitignore` 排除；
- `SHA256SUMS.txt` 删除；旧清单中不存在的浏览器截图行也随之消失；
- 发布时在 GitHub runner 上**连续构建两次并逐字节比较**，以证明构建确定性；
- Release 上的 HTML + `.sha256` + manifest 才是版本对应的正式成品。

Windows 的 `打开程序.cmd` 会先从源码构建，再打开本地生成的 `index.html`。

### 2. 构建发生在 GitHub runner，不在生产服务器

本项目的正式构建只需要 Node.js 20+、Python 3.10+，没有 npm runtime dependency；因此 runner 可以在无需访问中国第三方包源的情况下完成核心校验与构建。

流水线先执行数据语义校验、105 项引擎测试、JS 语法检查，再构建两次。生产服务器永远不从 Git checkout 临场构建正式 Release。

### 3. 部署的是“从 Release 再下载回来”的那一个文件

build job 将三份不可变资产挂到 Release：

```text
campfire-kitchen-vX.Y.Z.html
campfire-kitchen-vX.Y.Z.sha256
campfire-kitchen-vX.Y.Z.manifest.json
```

随后 deploy job **重新从 GitHub Release 下载 HTML**、复核 SHA-256，再通过 SSH 发送到服务器。这样“用户可下载的成品”和“线上安装的成品”天然是同一份字节流，而不是两个分别构建的文件。

同版本同名 Release asset 已存在时，只允许字节完全相同；不允许用 `--clobber` 覆盖一个已经发布的版本。

### 4. 生产切换由受限的 root installer 完成

GitHub runner 不直接获得任意 sudo shell。Hermes 在服务器安装仓库中的 `deploy/install-release.sh` 为：

```text
/usr/local/sbin/campfire-kitchen-install-release
```

部署用户只需要：

- SSH 登录；
- 写自己的 `/tmp/campfire-kitchen.*.html`；
- 通过 sudo 运行这一条固定 installer。

installer 只写固定的站点文件与 `/var/lib/campfire-kitchen/` 状态目录，做 SHA-256 校验、不可变版本存档、原子替换和上线后本机 HTTP 实测。任何后置校验失败，会立即恢复切换前的 `index.html`。

静态内容更新**不 reload Caddy**：Caddy 配置没有变化，只替换它读取的静态文件。配置变更仍由 Hermes 单独验证和 reload。

### 5. 保留人工兜底，但明确是 break-glass 通道

`deploy/release.sh` 保留：

```bash
./deploy/release.sh --dry-run
./deploy/release.sh --deploy
```

它不再依赖仓库里的生成产物或静态 `SHA256SUMS.txt`，而是测试后连续构建两次、校验逐字节一致，再通过同一个 server installer 发布。`--deploy` 会留下 `manual-<version>-<commit>` 记录。

正常发布不得用这个通道绕过 GitHub Release；它只用于 Actions 故障或紧急恢复。

## GitHub workflow

文件：`.github/workflows/campfire-kitchen-release.yml`

唯一触发器：

```yaml
on:
  release:
    types: [published]
```

两个 job：

1. **Build immutable Release asset**：校验 tag/version/main → 测试 → 双构建 → 上传不可变资产。
2. **Deploy exact Release asset**：从 Release 下载成品 → SHA 校验 → SSH → server installer → 上传 deployment receipt。

生产 job 使用 GitHub Environment：`campfire-kitchen-production`。Environment 本身形成 GitHub deployment history；成功后 Release 还会增加：

```text
campfire-kitchen-vX.Y.Z.deployment.json
```

服务器同时追加 `/var/lib/campfire-kitchen/deployments.tsv`。

## GitHub Environment / Secrets

由仓库所有者或 Hermes 协助配置，凭据本身不得提交：

| 名称 | 内容 |
|---|---|
| `CAMPFIRE_DEPLOY_HOST` | SSH 主机/IP |
| `CAMPFIRE_DEPLOY_PORT` | SSH 端口，纯数字 |
| `CAMPFIRE_DEPLOY_USER` | 专用部署用户 |
| `CAMPFIRE_DEPLOY_SSH_KEY` | 只供该用户使用的私钥 |
| `CAMPFIRE_DEPLOY_KNOWN_HOSTS` | 可信服务器 SSH host key 行；workflow 强制 StrictHostKeyChecking |

建议把它们放到 `campfire-kitchen-production` Environment，而不是仓库文件。

## 失败边界

- tag/version/source 校验失败：没有 Release asset，没有 SSH。
- 测试或构建失败：没有 Release asset，没有 SSH。
- 同名 Release asset 与当前构建不一致：拒绝覆盖，没有 SSH。
- Release 下载哈希失败：没有 SSH。
- SSH/SCP 失败：线上文件没有切换。
- server installer 在切换前发现哈希/版本冲突：线上文件没有切换。
- server installer 切换后 HTTP/响应头/目录暴露检查失败：自动恢复切换前文件，然后返回失败。

因此红色 workflow 不应留下“失败但线上已经静默变成未知字节”的状态。

## 回滚

每个成功进入 server installer 的版本都永久存放在：

```text
/var/lib/campfire-kitchen/releases/<version>/index.html
```

Hermes 可执行：

```bash
sudo /usr/local/sbin/campfire-kitchen-install-release rollback X.Y.Z
```

回滚也走原子替换和同一套线上哈希/响应头检查，并写 deployment log。回滚不会移动 Git tag、不会修改 GitHub Release；它只改变当前生产指向的已发布字节。
