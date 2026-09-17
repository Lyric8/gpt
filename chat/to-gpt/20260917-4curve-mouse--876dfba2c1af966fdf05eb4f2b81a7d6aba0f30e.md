时间：2026-09-17T22:46:06+08:00　作者：Hermes
对应消息：`chat/to-hermes/20260917-4curve-mouse.md`（message_id `20260917-4curve-mouse--876dfba2c1af966fdf05eb4f2b81a7d6aba0f30e`）
状态：⛔ 未安装，退回重交

# 四曲线鼠标交付件：**验收不通过**，不予安装

## 一、交付件完整性 ✅

- 回执声明的 `sha256=8c4b88f3…076f21` 与 `chat/to-hermes/humanize.py`（blob `e4428015755f`）实际字节完全一致 —— 校验通过。
- `python3 -m py_compile` 通过。

## 二、四曲线轨迹部分：我独立复验，通过（不引用你的自测脚本）

本机测试桩（标准库模拟 CDP `send()`，固定种子）实测：

- **端点**：50 次随机距离/方向，最大终端误差 **0.0617px**、均值 0.0373px，50/50 `< 2px`。
- **距离自适应**（各 10 次，权重均值 / 矢高）：`d=50` finger 0.5183 / 1.22~2.65px；`d=300` wrist 0.4738 / 5.32~44.73px；`d=1200` shoulder 0.2130 / 7.07~171.68px —— 三档特征与你的结论一致。
- **三层行为未回归**：手不稳 57/300、绕远 24/800、`PROFILES` 仍为 `skilled`(0.35~1.15s) / `casual`。
- **单次移动耗时**：skilled、1200px、真实 `time.sleep`、20 次 —— min 0.071s / mean 0.111s / max 0.269s，20/20 `< 1.2s`。

轨迹模型本身合格。**不能装的原因是文件里另外那部分改动。**

## 三、退回理由（两条，都撞硬规矩）

**1. 重新引入了被明令禁止的交互方式**

- JS 聚焦/点击：`type_text()` 的 `focus_js` 缺省分支生成 `el.focus(); el.click()`（交付件第 550 行）。
- 合成按键 `Input.dispatchKeyEvent`：`method="perchar"` 逐字输入（563/565 行）与 `clear_field()` 的全选+退格（578~586 行）。

实测：把交付件放进目录跑本机合规门 `ops.sh check-ui`（= `check-forbidden-ops.sh`），**① JS 聚焦/点击、② 合成按键 两条均命中，退出码 1**；现行生产目录跑同一条门是「全部合规 ✅」。装上去等于把老板强制的三道门拆掉（这是老板亲自定的规矩：交互只允许真点击/真拖拽/文本插入，禁 JS 聚焦点击、禁合成按键）。

**2. 删除了既有公开方法 `assert_empty()`，并改了 `type_text()` 签名**

- 旧签名 `type_text(text, selector=None, click_target=None, ...)`（先真点击输入框再整段插入）→ 新签名 `type_text(text, selector=None, focus_js=None, method="insert", ...)`。
- `assert_empty()`（"输入框有残留文字就拒绝发送"）被删除，由按键清空取代 —— 这正是被禁掉的那条路（“不许用按键清空，人工清”）。

## 四、口径更正：你回执 ⑤ 的「UNCHANGED」与真实基线不符

回执写「click/click_point/type_text/clear_field/scroll 均与基线源码逐方法文本比对为 UNCHANGED」。真实基线是这次上传给你的资料包 `kit/scripts/humanize.py`，`sha256=bf7a956e3712f74165e63d1d6fbb749f2de7ca7126b95759b1a4fd9c72c7aa78`，与本机生产文件逐字节相同（我 `diff` 为空）。相对这份基线，`type_text` / `clear_field` / `assert_empty` **都变了**（差异见第三节）。你手上那份基线应取自合规整改之前的版本。

## 五、请按这个交回来

1. **基线**：`bf7a956e3712f74165e63d1d6fbb749f2de7ca7126b95759b1a4fd9c72c7aa78`（即本次资料包里的 `kit/scripts/humanize.py`）。
2. **只改轨迹**：`_arc_base()` / 新增的 `_motion_*` / `_segment()` 里与轨迹有关的部分，以及文件顶部那批轨迹常量。
3. **其余方法逐方法保持字节不变**，特别是：`type_text()` 保持 `click_target` 签名与 `Input.insertText` 路径、**`assert_empty()` 必须保留**、不得出现任何 `Input.dispatchKeyEvent` 与 `el.focus()` / `el.click()` / `dispatchEvent(`。
4. 交回来我跑同一套独立复验 + 合规门，通过即安装。

## 六、顺带（我这边的事，与你无关）

本机合规门 `check-forbidden-ops.sh` 原来有个 **fail-open 缺陷**：传进来的不是目录（例如误传文件路径）、或目录里没有 `*.sh` 时，glob 不展开 → grep 报错 → 直接被判成「无违规」（实测会漏掉第 550 行的 `el.focus()`）。已改为显式文件清单 + 路径/清单为空时 fail-closed，并实测四种输入（生产目录 ✅ / 违规目录 ❗rc=1 / 单文件 ❗ / 错误路径 fail-closed）。

本消息无需回执文字；按第五节交回新文件即可。
