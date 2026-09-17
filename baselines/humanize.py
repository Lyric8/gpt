#!/usr/bin/env python3
"""拟人化浏览器操作层（直连 CDP 版）。

原则（按老板要求）：
  1. **随机延迟**：**两次操作之间**默认隔 2~10 秒随机（老板定的规矩）——
     人类不会在半秒内连做两个输入动作。手势内部（移动步进、按下/抬起）仍是毫秒级。
  2. **随机漂移**：鼠标走多段带抖动的曲线，不瞬移；落点也有随机偏移。
  3. **点击前复核**：漂移到位后用 elementFromPoint 确认"指针下面还是那个按钮"，
     不是就重新定位（最多 3 次），确认后才按下。
  4. **逐字输入**：按字符节奏输入（含随机停顿），不一次性塞满。

为什么直连 CDP：工具自带的 cdp() 是"一次调用一次 IPC 往返"，鼠标轨迹要发几十个事件，
必超时。这里自己连 ws://127.0.0.1:9222 的页面目标，事件可以连续发（fire-and-forget）。

用法（browser_exec 内）：
    import sys; sys.path.insert(0, "/home/ubuntu/.hermes/scripts")
    from humanize import Human, attach
    h = Human(attach("chatgpt.com"), js=js)
    h.click_js(LOCATOR_BY_TEXT % '"New chat"', verify_js=VERIFY_BY_TEXT % ('"New chat"','"New chat"'), label="New chat")
    h.type_text("hello", selector="#prompt-textarea")
"""
import json
import math
import os
import random
import sys
import time

sys.path.insert(0, "/home/ubuntu/.hermes/scripts")
from cdpmini import DirectCDP, attach  # noqa: E402  （纯标准库 CDP 客户端）


HSTATE = os.environ.get("HUMANIZE_STATE", "/home/ubuntu/.hermes/cache/humanize-state.json")


def _load_hstate():
    try:
        with open(HSTATE) as f:
            return json.load(f)
    except Exception:
        return {}


def _save_hstate(st):
    try:
        os.makedirs(os.path.dirname(HSTATE), exist_ok=True)
        with open(HSTATE, "w") as f:
            json.dump(st, f)
    except Exception:
        pass


def _log(msg):
    print(f"    [human] {msg}")


class Human:
    # 节奏档位：skilled = 熟练的人（快但随机，不浪费 时间）；casual = 慢悠悠
    PROFILES = {
        "skilled": {"lo": 0.35, "hi": 1.15, "rare": 0.08, "rare_add": (0.5, 1.5),
                    "steps": (7, 16), "step_ms": (0.004, 0.013), "hold": (0.04, 0.11)},
        "casual": {"lo": 2.0, "hi": 10.0, "rare": 0.12, "rare_add": (0.8, 2.6),
                   "steps": (8, 24), "step_ms": (0.007, 0.022), "hold": (0.05, 0.14)},
    }

    def __init__(self, tab, js=None, verbose=True, pause_lo=None, pause_hi=None, profile="skilled"):
        self.tab = tab
        self._js = js or tab.evaluate
        self.verbose = verbose
        self.profile = self.PROFILES.get(profile, self.PROFILES["skilled"])
        self.pause_lo = self.profile["lo"] if pause_lo is None else pause_lo
        self.pause_hi = self.profile["hi"] if pause_hi is None else pause_hi
        try:
            vw = self._js("innerWidth") or 1280
            vh = self._js("innerHeight") or 800
        except Exception:
            vw, vh = 1280, 800
        self.x = random.uniform(vw * 0.2, vw * 0.8)
        self.y = random.uniform(vh * 0.2, vh * 0.8)

    # ── 延迟 ────────────────────────────────────────────────
    def pause(self, lo=None, hi=None, why=""):
        """**两次操作之间**的随机停顿（熟练档 0.35~1.15 秒；偶尔来一次略长的停顿）。

        手势内部的微调（移动步进、按下/抬起）是毫秒级 —— 那是同一个动作的连续过程。
        """
        d = random.uniform(self.pause_lo if lo is None else lo,
                           self.pause_hi if hi is None else hi)
        if random.random() < self.profile["rare"]:
            d += random.uniform(*self.profile["rare_add"])
        if self.verbose and why:
            _log(f"停顿 {d:.2f}s（{why}）")
        time.sleep(d)

    # ── 落点抖动 ────────────────────────────────────────────
    def jitter_point(self, x, y, w=None, h=None):
        """在元素内部随机取一个落点（不点正中；留 20% 边距避免点到边缘外）。"""
        w = w or 0
        h = h or 0
        dx = random.uniform(-0.30, 0.30) * (w * 0.5) if w else random.uniform(-2.0, 2.0)
        dy = random.uniform(-0.28, 0.28) * (h * 0.5) if h else random.uniform(-2.0, 2.0)
        return int(round(x + dx)), int(round(y + dy))

    def click_point(self, x, y, w=None, h=None, check_js=None, label="", retries=3):
        """落点抖动 + 只在**抖动后的点**上复核 + 真点击（check_js 用 __X__/__Y__ 占位）。"""
        for attempt in range(1, retries + 1):
            jx, jy = self.jitter_point(x, y, w, h)
            ok = True
            if check_js:
                try:
                    code = check_js.replace("__X__", str(jx)).replace("__Y__", str(jy))
                    ok = bool(self._js(code))
                except Exception:
                    ok = True
            if ok:
                if self.verbose:
                    _log(f"落点 ({jx},{jy}) ← 中心 ({x},{y})，抖动 {jx - x:+d},{jy - y:+d}")
                return self.click(jx, jy, verify_js=None, label=label)
            self.pause(why="复核没过，换个落点")
        _log(f"{label}: 三个抖动点复核都不过，放弃（不瞎点）")
        return False

    # ── 鼠标移动（连续发事件，不等回执）────────────────────
    @staticmethod
    def _ease(s):
        """尖锐一点的 smoothstep：两端近乎静止、中段快 —— 更像真实鼠标的启停。

        用 smootherstep（6s⁵-15s⁴+10s³），中段斜率比经典 smoothstep 更陡，
        起停段更"干脆"，正好是"熟练的人"那种果断移动。
        """
        s = min(max(s, 0.0), 1.0)
        return s * s * s * (s * (s * 6 - 15) + 10)

    def _arc_base(self, x0, y0, x1, y1, n):
        """手腕控制 → 轨迹是**圆弧**：先按弦长定矢高，再由矢高算圆半径。

        短距离（<40px）近似直线（手指微调不会画弧）；长距离弧度按 4%~15% 弦长。
        速度仍用尖锐 smoothstep（把缓动施加在**角度**上）。
        """
        dx, dy = x1 - x0, y1 - y0
        d = math.hypot(dx, dy)
        if d < 40:
            return [(x0 + dx * self._ease(i / n), y0 + dy * self._ease(i / n)) for i in range(1, n + 1)]
        sag = d * random.uniform(0.04, 0.15) * random.choice([-1, 1])   # 矢高（带方向）
        abs_s = abs(sag)
        R = (d * d) / (8 * abs_s) + abs_s / 2                          # 弦长 + 矢高 → 半径
        px, py = -dy / d, dx / d                                       # 弦的法向
        sgn = 1 if sag > 0 else -1
        cx = (x0 + x1) / 2 + px * sgn * (R - abs_s)                    # 圆心（在弦的另一侧）
        cy = (y0 + y1) / 2 + py * sgn * (R - abs_s)
        a0 = math.atan2(y0 - cy, x0 - cx)
        a1 = math.atan2(y1 - cy, x1 - cx)
        da = (a1 - a0 + math.pi) % (2 * math.pi) - math.pi             # 走短弧
        pts = []
        for i in range(1, n + 1):
            a = a0 + da * self._ease(i / n)
            pts.append((cx + R * math.cos(a), cy + R * math.sin(a)))
        return pts

    def _segment(self, x0, y0, x1, y1, profile_only=False):
        """走一段：圆弧轨迹 + 尖锐缓动 + 逐点小抖动 + 偶发启停。"""
        dx, dy = x1 - x0, y1 - y0
        dist = max((dx * dx + dy * dy) ** 0.5, 1.0)
        lo_s, hi_s = self.profile["steps"]
        lo_m, hi_m = self.profile["step_ms"]
        n = max(4, min(hi_s, int(dist / random.uniform(24, 46))))
        base = self._arc_base(x0, y0, x1, y1, n)
        prev = (x0, y0)
        for i, (bx, by) in enumerate(base, start=1):
            e = self._ease(i / n)
            # 逐点抖动：越接近终点越小（人类临近目标会收敛）
            amp = (1 - e) * 1.9
            jx = bx + random.uniform(-amp, amp)
            jy = by + random.uniform(-amp, amp)
            r = random.random()
            if i < n and r < 0.035:                # 启停：原地顿一下（速度突然为 0）
                time.sleep(random.uniform(0.02, 0.07))
                jx, jy = prev
            elif i < n and r < 0.055:              # 微回撤：像手抖过头再拉回来
                jx = bx - (bx - prev[0]) * random.uniform(0.15, 0.5)
                jy = by - (by - prev[1]) * random.uniform(0.15, 0.5)
            self.tab.send("Input.dispatchMouseEvent", wait=False, type="mouseMoved",
                          x=round(jx, 1), y=round(jy, 1), buttons=0)
            time.sleep(random.uniform(lo_m, hi_m) * (1.0 + 1.4 * (1 - e)))
            prev = (jx, jy)
        self.x, self.y = x1, y1

    # ── 移动不准：每 4~7 次来一次（先偏出去再修正）────────────
    def _imprecise_due(self):
        """本次移动是否"手不稳"：误差事件按随机间隔 4~7 次发生一次（持久计数）。"""
        st = _load_hstate()
        st["moves"] = st.get("moves", 0) + 1
        if "next_imprecise" not in st:
            st["next_imprecise"] = st["moves"] + random.randint(4, 7)
        due = st["moves"] >= st["next_imprecise"]
        if due:
            st["next_imprecise"] = st["moves"] + random.randint(4, 7)
            st["imprecise"] = st.get("imprecise", 0) + 1
        _save_hstate(st)
        return due

    def move_to(self, tx, ty, imprecise=None, detour=False, why=""):
        """带"手不稳"的移动：先落到偏 1/10~1/20 总路径的点，再修正回目标。"""
        if imprecise is None:
            imprecise = self._imprecise_due()
        if imprecise:
            sx, sy = self.x, self.y
            dist = max(((tx - sx) ** 2 + (ty - sy) ** 2) ** 0.5, 1.0)
            # 蒙特卡洛：以目标为圆心的**实心圆**内均匀取点
            #   圆半径上限 R = 总路径的 1/20~1/10；r = R·√U 才保证"圆内均匀"
            rmax = dist * random.uniform(1 / 20.0, 1 / 10.0)
            r = rmax * math.sqrt(random.random())
            theta = random.uniform(0.0, 2 * math.pi)
            ex = tx + r * math.cos(theta)
            ey = ty + r * math.sin(theta)
            try:
                vw = self._js("innerWidth") or 1920
                vh = self._js("innerHeight") or 1000
                ex = min(max(ex, 4), vw - 4)
                ey = min(max(ey, 4), vh - 4)
            except Exception:
                pass
            if self.verbose:
                _log(f"手不稳：实心圆内随机落点 半径 {r:.0f}px / 上限 {rmax:.0f}px（"
                     f"角度 {math.degrees(theta):.0f}°）→ ({int(ex)},{int(ey)})，再修正")
            self.move(ex, ey, detour=detour)
            self.pause(0.08, 0.30, "咦，偏了")
            self.move(tx, ty, steps=random.randint(2, 4), detour=False)
            if self.verbose:
                _log(f"修正回目标 ({tx},{ty})")
            return True
        self.move(tx, ty, detour=detour)
        return False
    def _detour_due(self):
        """计数本次是否该绕远（跨进程持久化，保证真实频率是 1/20~40）。"""
        st = _load_hstate()
        st["clicks"] = st.get("clicks", 0) + 1
        if "next_detour" not in st:
            st["next_detour"] = st["clicks"] + random.randint(20, 40)
        due = st["clicks"] >= st["next_detour"]
        if due:
            st["next_detour"] = st["clicks"] + random.randint(20, 40)
            st["detours"] = st.get("detours", 0) + 1
        _save_hstate(st)
        return due

    def move(self, x, y, steps=None, why="", detour=False):
        sx, sy = self.x, self.y
        pts = [(x, y)]
        if detour:
            try:
                vw = self._js("innerWidth") or 1920
                vh = self._js("innerHeight") or 1000
            except Exception:
                vw, vh = 1920, 1000
            wps = []
            for _ in range(random.randint(1, 2)):
                ang = random.uniform(0, 6.28318)
                dist = random.uniform(140, 430)
                wps.append((min(max(sx + dist * random.uniform(-1, 1), 20), vw - 20),
                            min(max(sy + dist * random.uniform(-1, 1), 20), vh - 20)))
            pts = wps + [(x, y)]
            if self.verbose:
                _log(f"绕远：经过 {[ (int(a), int(b)) for a, b in wps ]} 再回目标 ({x},{y})")
        cur = (sx, sy)
        for tp in pts:
            self._segment(cur[0], cur[1], tp[0], tp[1])
            cur = tp
        try:
            self.tab.ws.drain()
        except Exception:
            pass
        if self.verbose and why:
            _log(f"移动到 ({round(x)},{round(y)}) {why}")

    def verify(self, verify_js):
        try:
            return bool(self._js(f"(() => {{ const el = document.elementFromPoint({round(self.x)}, {round(self.y)}); {verify_js} }})()"))
        except Exception as e:
            _log(f"复核异常: {e}")
            return False

    # ── 点击：漂移 → 复核 → 按下 ───────────────────────────
    def click(self, x, y, verify_js=None, locator_js=None, label="", retries=3):
        lo_h, hi_h = self.profile["hold"]
        due = self._detour_due()          # 每"一次点击"只抽一次绕远
        imp = self._imprecise_due()       # 每"一次点击"只抽一次手不稳
        for attempt in range(1, retries + 1):
            self.pause(why=f"准备点击 {label}" if label else "")
            self.move_to(x + random.uniform(-6, 6), y + random.uniform(-5, 5),
                         imprecise=(imp if attempt == 1 else False),
                         detour=(due if attempt == 1 else False))
            self.pause(0.08, 0.28)
            self.move(x + random.uniform(-2, 2), y + random.uniform(-1.5, 1.5), steps=random.randint(2, 4))
            if (not verify_js) or self.verify(verify_js):
                time.sleep(random.uniform(0.03, 0.11))
                self.tab.send("Input.dispatchMouseEvent", type="mousePressed",
                              x=round(self.x), y=round(self.y), button="left", clickCount=1, buttons=1)
                time.sleep(random.uniform(lo_h, hi_h))     # 按键持续时间也有人类差异
                self.tab.send("Input.dispatchMouseEvent", type="mouseReleased",
                              x=round(self.x), y=round(self.y), button="left", clickCount=1, buttons=0)
                if self.verbose:
                    _log(f"已点击 {label or ('(%d,%d)' % (x, y))}")
                return True
            _log(f"第 {attempt} 次复核未通过（指针下不是目标），重新定位")
            if locator_js:
                box = self.locate(locator_js)
                if box:
                    x, y = box["x"], box["y"]
                else:
                    _log("重新定位失败，放弃")
                    return False
            else:
                time.sleep(random.uniform(0.15, 0.4))
        return False

    def locate(self, locator_js):
        try:
            return self._js(locator_js)
        except Exception as e:
            _log(f"定位失败: {e}")
            return None

    def click_js(self, locator_js, verify_js=None, label="", **kw):
        box = self.locate(locator_js)
        if not box:
            _log(f"找不到目标：{label}")
            return False
        return self.click(box["x"], box["y"], verify_js=verify_js, locator_js=locator_js,
                          label=label or box.get("label", ""), **kw)

    # ── 输入 ────────────────────────────────────────────────
    def type_text(self, text, selector=None, click_target=None, min_ms=55, max_ms=170):
        """输入文本。默认 **整段插入**（老板明确不要逐字）；`method="perchar"` 才逐字。

        无论哪种方式，输入前后都遵守"两次操作之间 2~10 秒"的间隔规矩。
        """
        if not click_target:
            _log("❗拒绝输入：没给 click_target（规矩：只能先真点击输入框，禁止 JS 聚焦）")
            return False
        cx, cy, cw, ch, cchk = click_target
        if not self.click_point(cx, cy, cw, ch, check_js=cchk, label="输入框（点击聚焦）"):
            _log("❗点击输入框失败，放弃输入")
            return False
        if not self.assert_empty(selector):
            _log("❗输入框里有残留文字 → 放弃（不敢直接发，请人工清空后重试）")
            return False
        self.pause(why="准备输入（与上一个动作隔 2~10 秒）")
        t0 = time.time()
        self.tab.send("Input.insertText", text=text)
        time.sleep(random.uniform(0.25, 0.9))   # 落字本身也有个小停顿
        if self.verbose:
            _log(f"已输入 {len(text)} 字（{method}），耗时 {time.time() - t0:.1f}s")
        self.pause(why="输完停一下（下次操作前会再等 2~10 秒）")
        return True

    def assert_empty(self, selector="#prompt-textarea"):
        """规矩：不许用按键清空。这里只**检查**是否为空；有残留就让调用方停手。"""
        try:
            v = self._js(f"""(() => {{ const el = document.querySelector({json.dumps(selector)});
                return el ? (el.innerText || el.value || '').trim() : ''; }})()""")
            return not v
        except Exception:
            return True

    def scroll(self, dy=None, why=""):
        dy = dy if dy is not None else random.choice([-1, 1]) * random.randint(120, 480)
        self.tab.send("Input.dispatchMouseEvent", type="mouseWheel", x=round(self.x), y=round(self.y),
                      deltaX=0, deltaY=dy)
        if self.verbose and why:
            _log(f"滚动 {dy:+d} {why}")
        time.sleep(random.uniform(0.2, 0.7))


# ── 常用片段 ────────────────────────────────────────────────
LOCATOR_BY_TEXT = """(() => {
  const want = %s;
  const els = Array.from(document.querySelectorAll('button, a, [role=button], div[role=button]'));
  const el = els.find(e => ((e.innerText || '').trim() === want) && e.offsetParent);
  if (!el) return null;
  el.scrollIntoView({block: 'center'});
  const r = el.getBoundingClientRect();
  return {x: Math.round(r.left + r.width * (0.35 + Math.random() * 0.3)),
          y: Math.round(r.top + r.height * (0.4 + Math.random() * 0.25)), label: want};
})()"""

VERIFY_BY_TEXT = """return !!(el && ((el.innerText || '').trim() === %s
  || (el.closest && el.closest('button, [role=button], a') && (el.closest('button, [role=button], a').innerText || '').trim() === %s)));"""
