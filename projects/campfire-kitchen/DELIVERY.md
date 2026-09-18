# 火边 V4 交付包

**本次已完成本地实现与验证，未发布 Release，未上线。** GitHub 批量源码写入两次被工具的安全状态检查拒绝，随后停止；未更改生产站点。完整说明：`projects/campfire-kitchen/docs/V4_DELIVERY_STATUS.md`。

## 打开

可直接用浏览器打开 `projects/campfire-kitchen/index.html`。全部图片、菜谱、脚本和样式都已内置，不依赖外部网络。单独交付的 `campfire-kitchen-v4.0.0.html` 与它字节一致。

源码位于 `projects/campfire-kitchen/`，包含项目构建、测试及图片输入。仓库级 `.github/workflows/` 配置和无关项目不在本包内。

## 验证

```bash
cd projects/campfire-kitchen
npm run validate
npm test
python tools/build.py
```

300项分类、名称和稳定ID见 `docs/V4_CATALOG_INDEX.md`。完整构建、浏览器验收、发布前条件见项目 README。

`evidence/` 包含原始日志、49项浏览器检查报告、数据/图片/对比度报告以及桌面和手机截图。浏览器模式为 `content`，有明确存储替身；未验证正式 HTTP 浏览器持久化，不冒充上线门禁。

## 完整性

压缩包根目录 `SOURCE_MANIFEST.sha256` 覆盖包内每份源码、资料、HTML和证据（清单本身除外）。HTML SHA256：

```
97e85084999a0ebe9e73cd28a93b45328308babc1d41a0b766f14f91de2595fc
```

注意：300项包括15项饮品，并非全部肉类烧烤。图片为109张去重实拍参考，296项有图、4项明示缺图；配方没有逐项在用户实际炉具上实做。
