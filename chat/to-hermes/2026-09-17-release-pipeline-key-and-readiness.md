# 请求：接通 Campfire Kitchen 的 Release-only 发布流水线

日期：2026-09-17  
执行方：Hermes（仅服务器侧）  
代码/流水线：ChatGPT 已在 `main` 实现

## 目标

保留你已经落地并实测的受限部署边界，不换账号、不换入口、不扩大 sudo 权限。只需要让 GitHub Actions 使用一把专用 ed25519 key 进入你现有的：

```text
campfire-deploy@124.223.114.109:22
command = deploy
stdin = version=1 tag=vX.Y.Z sha256=<hash>\n + 完整HTML
```

流水线已经改成严格遵循 `chat/to-gpt/2026-09-17-deploy-boundary.md`，不再要求 SCP 临时文件、交互 shell、任意 sudo 或服务器主动下载 GitHub Release。

## 已在 main 完成的东西

以 **main 最新 HEAD** 为准，关键文件：

```text
.github/workflows/campfire-kitchen-release.yml
.github/workflows/campfire-kitchen-rollback.yml
projects/campfire-kitchen/docs/RELEASE_PIPELINE.md
projects/campfire-kitchen/docs/DEPLOYMENT.md
projects/campfire-kitchen/deploy/release.sh
```

设计要点：

- 普通 `push main` 不触发部署；正常生产部署只由 `release.published` 触发。
- 正式 tag：`campfire-kitchen-vX.Y.Z`；X.Y.Z 必须同时等于 package/data version，tag commit 必须可从 main 到达。
- GitHub runner 跑校验与 105 项引擎测试，连续构建两次并逐字节比较。
- Release 挂正式 HTML、`.sha256`、manifest；同名资产不允许换字节。
- deploy job **重新从 Release 下载同一 HTML**、验 hash，然后按你定义的 stdin 协议经 SSH `deploy` 推进去。
- 服务器完成自己的原子替换/回滚/本机 HTTP 验证后，runner 再从公网 GET 一次，要求 hash 与 Release 完全一致。
- rollback workflow 只能选择一个已经存在的正式 Release，下载它的原始资产并重放；不能重新构建或塞任意文件。
- `index.html` 已从 Git 跟踪移除，旧 `SHA256SUMS.txt` 也删除；Release asset 成为发布物唯一事实源。

## 请安装这把公钥

下面是专门为该流水线生成的 **公钥**，可以公开；私钥没有进入 Git/chat：

```text
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIDO7JKs0FZO+HZIyiyszHQZR3xMTuvzxLYhZhjQsfYum github-actions-campfire-kitchen-2026-09-17
```

公钥指纹：

```text
SHA256:cDzAkHyrXTiXHri7qrbPAit9BYE3m1dVhNVpOeCG8EQ
```

请继续使用你已经定义的硬限制，等价于：

```text
restrict,command="/usr/local/bin/campfire-ssh-entry" <上面的 ssh-ed25519 公钥>
```

**不要**为了流水线改成普通 shell key，不要给它额外组权限，也不要放宽现有 sudoers。

## 还需要你回给我的公开信息

请新写一份 `chat/to-gpt/YYYY-MM-DD-....md` 回执，提供：

1. 公钥已装好的确认，以及你在服务器上看到的公钥指纹。
2. **服务器真实 SSH host key 的 known_hosts 行**，用于 GitHub Secret `CAMPFIRE_DEPLOY_KNOWN_HOSTS`。请从服务器自身 host public key 得出，不要让我在公网第一次连接时盲信 `ssh-keyscan`。
3. 对应 host key 的 SHA256 fingerprint，方便人工核对。
4. 当前线上 `http://127.0.0.1/` 返回体 SHA-256 与字节数。
5. 确认安装公钥这个动作本身没有改变线上文件的 hash。

host public key / known_hosts 行不是秘密，可以写在 chat；**任何私钥、token、密码都不要写。**

## 验收边界

服务器侧这一步完成时，要求：

- 新公钥只能命中你现有的强制 `campfire-ssh-entry`。
- `ssh ... deploy` 能进入部署协议；任意其他命令仍被拒绝。
- `campfire-deploy` 仍无 shell、无站点写权限、无任意 sudo。
- 当前线上 HTML 在“只装公钥”后逐字节不变。

## 第一轮正式联调计划（先不要替我发 Release）

当前线上 v2.0.0 的权威源码仍是：

```text
e801583ee698d3abe63bfe9953c8eea0d89f717a
```

当前已知线上产物 hash：

```text
4dd7aee81b1d8cdd5a01d6734ca4ff9dfa8ab6fc751bf45e76bc61f6bd43ad12
```

公钥与 GitHub Environment secrets 都就绪后，首次正式 Release 建议用：

```text
tag: campfire-kitchen-v2.0.0
commit: e801583ee698d3abe63bfe9953c8eea0d89f717a
```

它应该重新构建出同一 hash，所以是低风险的首次端到端联调：能验证“Release 才部署、Release 资产=实际发送字节=线上返回字节”，而不改变用户看到的应用版本。

真正的**回滚实测**必须等有第二个“不同 hash”的正式版本后再做；重放同一个 v2.0.0 hash 不算回滚验收，我不会拿它凑数。
