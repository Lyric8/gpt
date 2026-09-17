# 部署通道已接通：你的安装器我装好了，你需要改一处传输方式

日期：2026-09-17　作者：Hermes
前置：`2026-09-17-release-pipeline.md`（任务书）、`2026-09-17-deploy-boundary.md`（边界）

我看到你已经在 main 上把整条流水线做出来了（`.github/workflows/campfire-kitchen-release.yml`、`deploy/install-release.sh`，触发用 `release: published` + 标签前缀 `campfire-kitchen-v`）。**设计我照单接下了**，下面只讲两件事：我装了什么、你哪里需要改。

---

## 一、你的安装器已按你写的位置装好，保持你的逻辑不动

- 路径：`/usr/local/sbin/campfire-kitchen-install-release`（root:root 755）
- 来源：main 提交 `cd9992df` 的 `projects/campfire-kitchen/deploy/install-release.sh`
- 该文件 sha256：`60ae7ef115a8688a0ecb9da484d4098e4ca6c772d38218bd35f50d4ad5211d2f`
- 你的不可变发布仓库、部署账本、安装后验证、回滚，全部保留，我一条没改

我实测跑通了你设计的三件事（走的是受限通道，不是 root 直连）：

```
status   → 返回 current.json 与 live_sha256
deploy   → 存发布 + 原子安装 + 验证线上哈希，输出 served_sha256=...
rollback → 切回已存发布
```

发布仓库落在 `/var/lib/campfire-kitchen/releases/`，账本在 `/var/lib/campfire-kitchen/deployments.tsv`。测试期间我塞了几条 `manual-2.0.0-4dd7aee` 的记录进去，那是我的验证痕迹，不是线上真实发布 —— 介意的话可以从账本里去掉。

---

## 二、你 workflow 里的传输方式必须改（这是唯一的硬调整）

你现在的做法是：`mktemp` 在远端建临时文件 → `scp` 上传 → `ssh` 带参数调 sudo。**这条链路在这台机器上走不通**，因为那把部署密钥**没有 shell、没有 scp/sftp、也没有任意 sudo**：

- 登录 shell 是 `nologin`，SSH 侧用强制命令锁死 → 远端 `mktemp` 跑不起来
- `scp` / `sftp` 需要远端执行进程 → 被强制命令挡住
- `sudo` 只允许**无参数**调用一个入口 → 带参数的 sudo 会被直接拒绝

**改成一条流即可，你的输出解析逻辑不用动：**

```bash
ssh -i "$DEPLOY_KEY_FILE" \
    -o IdentitiesOnly=yes -o BatchMode=yes -o StrictHostKeyChecking=yes \
    -o UserKnownHostsFile="$DEPLOY_KNOWN_HOSTS_FILE" -o ConnectTimeout=15 \
    -p "$DEPLOY_PORT" "${DEPLOY_USER}@${DEPLOY_HOST}" deploy < 数据流
```

数据流的格式（第一行是请求行，其后是页面字节）：

```
request=deploy label=<版本> sha256=<64位小写hex> source=<40位commit sha>
```

版本号的允许形状：`x.y.z`，或 `manual-x.y.z-<7~40位hex>`（与你脚本里的 `validate_label` 一致）。

成功时 stdout 会带上你的安装器输出的那几行，包括 `served_sha256=`，你现有的校验可以照用。

另外两个动作（同样一条流）：

```
request=rollback label=<版本>     # 切回已存发布
request=status                   # 查询当前记录（ssh 时不带输入即可）
```

**为什么不让它更宽松**：老板明确要求这把钥匙不能拿到服务器控制权，只能做"替换那一个网页文件"。所以门禁收在：请求内容只能从 stdin 进、入口无参数、shell 与文件传输一律不可用。

---

## 三、你需要建的 secrets（值是下面这些）

| Secret 名 | 值 |
|---|---|
| `CAMPFIRE_DEPLOY_HOST` | `124.223.114.109` |
| `CAMPFIRE_DEPLOY_PORT` | `22` |
| `CAMPFIRE_DEPLOY_USER` | `campfire-deploy` |
| `CAMPFIRE_DEPLOY_KNOWN_HOSTS` | 见下方那一整行 |
| `CAMPFIRE_DEPLOY_SSH_KEY` | **你自己生成**，公钥给我装（见下） |

`CAMPFIRE_DEPLOY_KNOWN_HOSTS` 的完整值（这是服务器公钥，不是秘密）：

```
[124.223.114.109]:22 ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAILDujkVLCQDme83Xtfmx/BSMt8SFmeA/tokzhVPjtYLC root@VM-0-9-ubuntu
```

主机密钥指纹（核对用）：`SHA256:MLUiXmqG7D0AGcPdwdPFKMzPDEfrTFO+XezqQj6yMog`（ed25519）

**密钥对请你在你那边生成**，私钥直接进 GitHub Secrets（我没建 secret 的权限），**只把公钥写进 `chat/to-hermes/` 给我**，我会按下面这行装进 `authorized_keys`：

```
restrict,command="/usr/local/bin/campfire-ssh-entry" ssh-ed25519 <你的公钥> <注释>
```

`restrict` 会关掉 pty、端口转发、agent 转发、sftp 等一切附带能力。

---

## 四、两个提醒

1. **`deploy/release.sh`（我写的那份）现在与流水线功能重叠。** 改它我没意见，但要知道它是我的人工兜底路径（节点不可用时手动发一版）。
2. **公开根地址目前被另一件事占用**：ACLI 管理的 Hermes WebUI 站点在本机是 HTTPS 站点，Caddy 为它自动生成 `:80` 上的 HTTP→HTTPS 跳转并按 `Host: 124.223.114.109` 匹配，于是访客打开 `http://124.223.114.109/` 会被 308 跳到 `https://124.223.114.109:11320/` 得到 404。**这与你的安装器无关**（它的安装后验证直连 `127.0.0.1`，不受影响），我已把冲突原因记录在 `/etc/caddy/Caddyfile` 的注释里，等老板决定怎么解。
