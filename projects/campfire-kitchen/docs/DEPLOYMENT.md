# campfire-kitchen 线上部署

本文档记录本项目**已上线**的部署形态与发布流程，供后续接手者（人或 Agent）直接照做。

## 线上地址

| 项 | 值 |
|---|---|
| 站点 | `http://124.223.114.109/` |
| 主机 | 腾讯云 CVM，内网 `10.0.0.9` |
| Web 服务 | Caddy 2.11.4，systemd 服务 `caddy`，监听 `:80` |
| 发布产物 | `/var/www/campfire-kitchen/index.html`（root:root 644） |
| 服务配置 | `/etc/caddy/Caddyfile` |
| 首次上线 | 2026-09-17，源码 commit `e801583e` |

站点只托管 **`index.html` 这一个文件**。本项目是离线优先的单文件应用，`data/`、`src/`、`tests/` 等目录不对外暴露。

## 发布流程

在项目根目录执行：

```bash
./deploy/release.sh --dry-run   # 只校验：目录完整性 + 测试 + 构建 + 哈希闸门
./deploy/release.sh             # 校验通过后发布到线上并实测
```

脚本内部按顺序做五件事：

1. **项目完整性**：确认 `data/recipes.json`、`src/engine.mjs`、`src/app.mjs`、`src/styles.css`、`tests/engine.test.mjs` 都在（对应仓库根 README 规则 6：关键文件缺失视为源码同步未完成，不部署残缺版本）。
2. **数据与引擎测试**：`node tools/check_catalog.mjs` + `node --test tests/engine.test.mjs`。任何一项失败即中止。
3. **构建**：`python tools/build.py` 生成 `index.html`。
4. **哈希闸门**：本机构建出的 `index.html` 哈希必须等于 `SHA256SUMS.txt` 里登记的值，否则停止发布——防止发出去的和登记的不是同一份东西。发新版本时需同步更新 `SHA256SUMS.txt`。
5. **发布与实测**：安装产物 → `systemctl reload caddy` → 拉一次线上返回体比对哈希 → 校验 `X-Content-Type-Options: nosniff` → 确认 `/docs/` 不开放目录列表。

要求：Node.js 20+、Python 3.10+、对本机的免密 `sudo`（仅第 5 步需要）。

## 服务配置

`deploy/Caddyfile` 是线上配置的副本，要点：

- `root * /var/www/campfire-kitchen`，`file_server` 默认不开放目录列表
- `encode zstd gzip`：单文件应用 306 KB → 传输约 81 KB
- `X-Content-Type-Options: nosniff`：与 `tests/release_checks.py` 的发布契约一致
- `Cache-Control: no-cache`：单文件应用，避免浏览器缓存住旧版本

改配置的规矩：先备份 `cp -a /etc/caddy/Caddyfile /etc/caddy/Caddyfile.bak-$(date +%Y%m%d-%H%M%S)`，改完 `caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile`，再 `systemctl reload caddy`。

## 回滚

站点只有静态文件与一个配置，回滚成本极低：

```bash
# 回滚服务配置
sudo cp /etc/caddy/Caddyfile.bak-<时间戳> /etc/caddy/Caddyfile && sudo systemctl reload caddy

# 回滚到某个历史版本
git checkout <commit> -- index.html
sudo install -o root -g root -m 644 index.html /var/www/campfire-kitchen/index.html && sudo systemctl reload caddy
```

## 当前未解决项

`SHA256SUMS.txt` 登记了 7 张浏览器测试截图（`test-results/desktop-*.png`、`mobile-*.png`），但文件尚未提交进仓库，因此对该清单执行 `sha256sum -c` 会报 7 行 `could not be read`，其余全部 `OK`。这属于仓库侧的登记与文件不同步，**不影响发布**（发布闸门只看 `index.html`）。处理方式二选一：补交截图，或从 `SHA256SUMS.txt` 中删除这 7 行。
