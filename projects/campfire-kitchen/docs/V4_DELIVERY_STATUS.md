# 火边 V4 本次交付状态

## 当前结论

**开发交付完成；本次未发布、未上线。** 本文不作为任何 Release 或部署成功回执。

完整源码、可离线打开的 HTML、图片与署名元数据、测试和证据一起交付。源码来自主线基线 `f970c7b3ca6caf9d57a1c11edeefa51564b1639f`，V4 实现位于本包 `projects/campfire-kitchen/`。本包不包括其他项目或仓库级 `.github/workflows/` 配置；项目自身构建与测试的所有输入均已包含。

## GitHub 与上线阻塞

正常批量源码写入有部分 Git 对象创建成功；后续 `src/styles/workflows.css` 和 `tools/build.py` 写入连续两次被工具拒绝，返回：

> 因 OpenAI 无法确定请求的安全状态，已拦截此工具调用。

首次检查后修正了请求中构建脚本的一个复制括号错误，正常重试一次仍被拒绝。返回未给出更具体原因；不能推断是凭据过期、仓库权限不足或源代码运行失败。随后停止该写入，没有换通道或编码规避拦截。

本次**没有**形成完整可用的 V4 GitHub 提交，没有更新主线，没有发布 V4 Release，没有部署或验证线上 V4 字节。部分已写入对象不可当作完整源码或可发布分支；本交付 ZIP 才是完整本地实现，不要求从部分 Git 对象拼回。

## 交付物字节

- 程序：`campfire-kitchen-v4.0.0.html`，与项目 `index.html` 字节一致。
- HTML 大小：7,492,813 字节。
- HTML SHA256：`97e85084999a0ebe9e73cd28a93b45328308babc1d41a0b766f14f91de2595fc`。
- 全部源码、资料和证据的独立 SHA256 列在压缩包根目录 `SOURCE_MANIFEST.sha256`。
- 688 项 Node 测试、14 项 Python 构建测试、6 项发版检查通过。
- 浏览器报告为 49 项检查通过，包括遍历 300 道做法、109 张照片解码、分页、库存、菜单、导入导出、焦点、视口与首页文本检查。

## 验证范围与尚未完成项

浏览器报告的 `mode` 为 `content`：真实 Chromium 执行页面与交互，存储为明确的接口替身。运行环境禁止浏览器 HTTP/file 导航，所以这份报告**不证明真实 HTTP 来源、原生 localStorage 持久化或原生刷新**。Python 标准库服务的 HTTP 返回和响应头另经测试，但不能代替上述浏览器门禁。

首页实际计算文本通过已实现的 AA 对比度阈值检查，不能外推为全站 WCAG 认证。320、360、390、430、768、1024、1440 像素的六视图布局检查与截图属于界面回归，并不等于真实用户可用性研究。

正式上线仍须在允许的正常环境中通过完整源码提交、Quality 的 HTTP 浏览器测试、published Release、不可变资产回验与生产部署哈希验证；本次未完成这些步骤。

## 菜谱与照片边界

300 项包含 15 项饮品、19 项甜品和冷菜/蘸酱，并非 300 项肉类烧烤。每项配方为明确编写的食材、准备、烹饪和吃法，不是调味料笛卡尔积自动拼凑。配方未逐项在用户实际炉具上实做验证。

照片池包含 109 张独立实拍参考图，296 项有照片引用，不宣称 300 张本配方成品实拍。苹果木坚果、苹果木鸡蛋、荷兰豆、小红萝卜四项明确缺图。许可、来源、图片处理说明随数据交付。

## 回滚边界

本次未变更线上，因此无线上回滚操作。未来正式发布后的回滚，应重放前一份已发布、SHA256 验证成功的 Release 资产；源码用独立 revert 提交，不强推主线、不覆盖已有 Release 资产。任何需人工执行的线上发布或回滚：**必须老板在场、网关进程外执行**，不能修改网关、密钥或无关项目。

## 复算命令

在包内 `projects/campfire-kitchen/` 执行：

```bash
npm run validate
npm test
python -m unittest discover -s tests -p '*_test.py'
python tests/release_checks.py
python tools/build.py
```

测试依赖见 `tests/requirements.txt`。允许浏览器 HTTP 导航的环境使用：

```bash
python -m pip install -r tests/requirements.txt
python -m playwright install --with-deps chromium
python tests/browser_smoke.py --mode http
```

HTML 校验（Python 标准库）：

```bash
python -c "import hashlib,pathlib; print(hashlib.sha256(pathlib.Path('index.html').read_bytes()).hexdigest())"
```
