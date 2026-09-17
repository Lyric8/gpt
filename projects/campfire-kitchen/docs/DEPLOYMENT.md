# campfire-kitchen 线上部署

## 线上形态

| 项 | 值 |
|---|---|
| 站点 | `http://124.223.114.109/` |
| 主机 | 腾讯云 CVM，内网 `10.0.0.9` |
| Web 服务 | Caddy 2.11.4，监听 `:80` |
| 对外文件 | `/var/www/campfire-kitchen/index.html` |
| 项目根 | `projects/campfire-kitchen` |
| 受限部署用户 | `campfire-deploy` |

站点只对外服务一个单文件应用。`data/`、`src/`、`tests/` 不部署到 Web root。

## 正常发布：只认 GitHub Release

普通 `push main` **不会部署**。正式版本流程是：

1. 修改源码与数据。
2. 同时把 `package.json.version` 与 `data/recipes.json.version` 更新为同一个稳定 SemVer，例如 `2.1.0`。
3. 合入 `main`，确认要发布的 commit 在 `main` 上。
4. 创建 tag：`campfire-kitchen-v2.1.0`，指向该 commit。
5. 在 GitHub 发布这个 Release（不是 prerelease）。
6. `.github/workflows/campfire-kitchen-release.yml` 自动：测试 → 双构建 → 挂 Release 成品 → 从 Release 重新下载同一成品 → 经受限 SSH stdin 推送 → 线上哈希实测。

Release 最终包含：

```text
campfire-kitchen-v2.1.0.html
campfire-kitchen-v2.1.0.sha256
campfire-kitchen-v2.1.0.manifest.json
campfire-kitchen-v2.1.0.deployment.json   # 首次成功生产部署后出现
```

`index.html` **不再提交进 Git**。源码 checkout 后需要 `python tools/build.py` 才会生成；最终用户应下载 Release HTML。

## 服务器侧受限部署契约

服务器侧已经由 Hermes 落地并实测，不由本项目 workflow 重建。权威事实见 `chat` 分支：

```text
chat/to-gpt/2026-09-17-deploy-boundary.md
```

外部唯一允许的线上动作：

```bash
ssh -i <部署私钥> -p 22 campfire-deploy@124.223.114.109 deploy < 数据流
```

数据流：

```text
version=1 tag=v2.1.0 sha256=<该HTML的64位小写sha256>
<从第二行开始是完整HTML字节>
```

该 SSH 身份没有交互 shell、不能任意执行命令、不能直接写站点目录、不能改 Caddy、不能任意 sudo。服务器入口负责请求校验、哈希校验、原子替换、Caddy reload、真实返回体比对和失败自动回滚。

GitHub Actions 在服务器完成后还会从公网再次 GET，要求线上返回体与 Release HTML 的 SHA-256 逐字节一致。

## GitHub Environment

生产 workflow 使用：

```text
campfire-kitchen-production
```

需要配置：

```text
CAMPFIRE_DEPLOY_SSH_KEY
CAMPFIRE_DEPLOY_KNOWN_HOSTS
```

私钥永不进入仓库。`known_hosts` 使用固定的真实服务器 host key，不在运行时盲信 `ssh-keyscan`。

## 回滚

使用 Actions 页面中的：

```text
Campfire Kitchen Rollback
```

输入一个已有正式 Release tag，例如：

```text
campfire-kitchen-v2.0.0
```

rollback workflow **不重新构建**，而是下载该 Release 已经发布的 HTML、checksum 和 manifest，互相校验后把这份原始字节重新推给同一个受限服务器入口。

这样回滚的含义明确：生产重新变成某个历史正式 Release 的原始成品，而不是从今天的源码“重新猜一次旧版本”。

## 人工兜底发布

Actions 故障时，在完整项目 checkout 中：

```bash
./deploy/release.sh --dry-run
```

要实际走 break-glass 部署，显式准备私钥和 pinned known_hosts：

```bash
DEPLOY_KEY_FILE=/secure/path/key \
DEPLOY_KNOWN_HOSTS_FILE=/secure/path/known_hosts \
./deploy/release.sh --deploy
```

它运行相同的数据/引擎检查和确定性双构建，然后走 Hermes 同一个受限 stdin SSH 通道。正常发版不得把这个入口当成 push 后的日常部署脚本。

## Caddy 配置

`deploy/Caddyfile` 是线上配置副本。配置变化仍归 Hermes；流水线不会获得修改 Caddyfile 或任意 root shell 的能力。

## 发布与回滚设计

详见 [`RELEASE_PIPELINE.md`](RELEASE_PIPELINE.md)。
