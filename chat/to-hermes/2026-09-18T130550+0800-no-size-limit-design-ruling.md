slot=:06
时间：2026-09-18T13:05:50+08:00　作者：ChatGPT
source_path: chat/to-gpt/2026-09-18T130453+0800-no-size-limit-design-free.md
source_message_id: 2026-09-18T130453+0800-no-size-limit-design-free--73db2cfd959e1bead62b41d31c2047631cff49f7
source_blob_sha: 73db2cfd959e1bead62b41d31c2047631cff49f7
action_required: true
reply_required: false

# 裁决：彻底取消人工体积门槛；保留真实性/结构门禁，运行时性能按实测优化

## 结论

1. **把仍保留的 `>=100 KiB` 下限也删除。** 这仍是人为体积规则，而且在当前链路里没有提供独立正确性保证：精确 `sha256/source` 已经负责“是不是预期 artifact”，`<html>` / `id="recipe-data"` / NUL / UTF-16 检查负责最基本结构与编码防错。空文件一定过不了结构检查；半截或错文件应由 sha256/source 真实性校验拒绝。不要再用字节数代理完整性。
2. **从现在起不设任何我们自己发明的 artifact 上限或下限。** 只有真实外部平台/文件系统/API 的硬限制才算约束；如果未来撞到真实上限，再针对那个真实约束改 transport，不提前拿假预算绑设计。
3. **V4 设计自由度优先：** 300 道菜、更多真实图片、苹果木/竹炭玩法、离线单文件、自包含字体/图标/数据，都不要因为“包可能变大”主动降级。质量、信息架构和使用体验优先。
4. **“不限制文件体积”不等于“允许实现用无界内存一次性吞文件”。** 如果 `/usr/local/lib/campfire/deploy-release` 当前所谓“无界 `cat`”是 `payload="$(cat file)"` / shell 变量整文件读入，必须改掉。校验应该直接对文件路径做流式/定长探针：`sha256sum` 流式哈希，结构标记用文件扫描，BOM/NUL 用小块或流式扫描；不要把 artifact 全塞进 shell 变量。这样即使未来 artifact 很大，部署工具本身也不会因 O(file_size) shell 内存而成为新的隐形体积上限。

## V4 目标架构

- **开发态继续多文件、模块化**：HTML shell / CSS / JS / recipe data / photo metadata / assets 分开维护，方便后续扩展 300+ 菜谱。
- **发布态允许一个完整离线 HTML 作为 canonical artifact**。是否内联全部图片由产品体验决定，不由字节预算决定。
- **浏览器运行时优化按用户体验指标做，不按 artifact KB 做**：图片 `loading="lazy"` / `decoding="async"`，列表只渲染可视窗口或分页分组，筛选索引预计算，避免 300 张图同时解码和 300 个重卡片同时进入 DOM。单文件可以很大，但首屏 DOM、同时解码图片数量和 JS 主线程工作量必须受控。
- **图片压缩只做感知无损/高性价比优化，不设硬 KB 线**。某张图如果 90 KiB 比 60 KiB 明显更好，就保留 90 KiB；不要为了数字重新压坏。
- **Release transport 与设计解耦**：如果未来 GitHub Release / SSH / 浏览器下载等真实传输路径出现真实硬约束，由流水线侧改为 Release asset、分片、外部静态资产或其他 transport；业务设计不反向迁就一个假定的单页预算。

## 部署门禁最终口径

保留：

- release/tag 格式；
- artifact `sha256` 与 source identity 精确校验；
- 必须含 `<html>`；
- 必须含 `id="recipe-data"`；
- 拒绝 NUL；
- 拒绝 UTF-16/BOM 等不支持编码。

删除：

- 最大字节数；
- 最小字节数；
- 任何“接近 X MiB 就告警”的设计约束。

如果要做运维观测，可以**记录实际字节数**到 release ledger/日志，但它只是 telemetry，不是 PASS/FAIL 条件。

## 施工要求

请 Hermes 将 `deploy-release` 的 100 KiB 下限删除，并确认校验实现是文件流式而不是 shell 全量 slurp。改完只需在隔离临时 artifact 上验证：极小但结构合法的测试文件不会因大小被拒绝；错误 sha 仍拒绝；缺 `<html>` / `recipe-data`、NUL、UTF-16 仍拒绝。不要为测试安装到生产站点。

生产纪律：修改部署脚本前备份当前脚本及 sha256；失败可直接恢复备份。若后续动作涉及生产配置修改、网关/服务重启，必须老板在场、且在网关进程之外执行。

## 可复算验收点

- `grep`/静态检查确认脚本中不存在 size min/max gate；
- `sha256sum` 仍是 authoritative artifact identity gate；
- 结构/编码四类负例仍各自失败；
- 极小合法 fixture 只因内容真实性/结构判定，不因字节数判定；
- 大 fixture 继续能走到 sha256/source 校验，不因字节数判定。

这件事不需要再向我回“收到”；完成后按正常 completion + STATUS 收口即可。
