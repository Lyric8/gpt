# campfire-kitchen 线上部署

## 线上形态

| 项 | 值 |
|---|---|
| 站点 | `http://124.223.114.109/` |
| 主机 | 腾讯云 CVM，内网 `10.0.0.9` |
| Web 服务 | Caddy 2.11.4，监听 `:80` |
| 对外文件 | `/var/www/campfire-kitchen/index.html` |
| Release 状态 | `/var/lib/campfire-kitchen/` |
| 项目根 | `projects/campfire-kitchen` |

站点只对外服务一个单文件应用。`data/`、`src/`、`tests/` 不部署到 Web root。

## 正常发布：只认 GitHub Release

普通 `push main` **不会部署**。正式版本流程是：

1. 修改源码与数据。
2. 同时把 `package.json.version` 与 `data/recipes.json.version` 更新为同一个稳定 SemVer，例如 `2.1.0`。
3. 合入 `main`，确认要发布的 commit 在 `main` 上。
4. 创建 tag：`campfire-kitchen-v2.1.0`，指向该 commit。
5. 在 GitHub 发布这个 Release（不是 prerelease）。
6. `.github/workflows/campfire-kitchen-release.yml` 自动：测试 → 双构建 → 挂 Release 成品 → 从 Release 重新下载 → SSH 安装 → 线上哈希实测。

Release 最终包含：

```text
campfire-kitchen-v2.1.0.html
campfire-kitchen-v2.1.0.sha256
campfire-kitchen-v2.1.0.manifest.json
campfire-kitchen-v2.1.0.deployment.json   # 首次成功生产部署后出现
```

`index.html` **不再提交进 Git**。源码 checkout 后需要 `python tools/build.py` 才会生成；最终用户应下载 Release HTML。

## 生产服务器 installer

仓库提供 `deploy/install-release.sh`，由 Hermes 以 root 身份安装为：

```text
/usr/local/sbin/campfire-kitchen-install-release
```

正常 workflow 调用：

```text
sudo /usr/local/sbin/campfire-kitchen-install-release deploy <tmp-html> <version> <sha256> <source-sha>
```

installer 的行为：

- 校验参数、临时文件路径和 SHA-256；
- 将版本保存到 `/var/lib/campfire-kitchen/releases/<version>/`，同版本禁止换字节；
- 备份当前线上文件；
- 原子替换 `/var/www/campfire-kitchen/index.html`；
- 从服务器本机请求 Caddy，要求返回体 SHA-256 与 Release 相同；
- 要求 `X-Content-Type-Options: nosniff` 且 `/docs/` 返回 404；
- 后置检查失败则自动恢复切换前文件；
- 成功后更新 `/var/lib/campfire-kitchen/current.json` 并追加 `deployments.tsv`。

静态文件发布不 reload Caddy；只有 Caddy 配置本身改变时才需要 reload。

查看当前状态：

```bash
sudo /usr/local/sbin/campfire-kitchen-install-release status
```

## 回滚

服务器保留已经接收过的不可变 Release。回滚到 `2.0.0`：

```bash
sudo /usr/local/sbin/campfire-kitchen-install-release rollback 2.0.0
```

回滚本身也会验证线上哈希和安全响应头，并写入部署历史。

## 人工兜底发布

Actions 不可用或紧急恢复时，在完整项目 checkout 中：

```bash
./deploy/release.sh --dry-run
./deploy/release.sh --deploy
```

`--deploy` 是 **break-glass** 通道：它会跑数据/引擎测试、连续构建两次并比对，再调用相同 server installer。它会以 `manual-<version>-<commit>` 留痕，但不会伪造 GitHub Release。

正常开发与发布不得把这个通道当成“push 后顺手上线”。

## Caddy 配置

`deploy/Caddyfile` 是线上配置副本。配置变化仍归 Hermes：备份 → `caddy validate` → 安装 → reload。发布 HTML 不触碰 Caddy 配置。

## 凭据

SSH 私钥与 trusted known_hosts 只存在于 GitHub `campfire-kitchen-production` Environment secrets / 服务器侧，绝不提交仓库。具体 Secret 名与发布设计见 `docs/RELEASE_PIPELINE.md`。
