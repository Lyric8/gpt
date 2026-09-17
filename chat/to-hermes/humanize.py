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


# ── 四条运动链参数（所有区间都集中在这里，方便后续实机调参）──────────────
# 权重先按距离档位独立随机抽样，再归一化到总和为 1。
MOTION_WEIGHT_RANGES = {
    "short": {
        "finger": (0.44, 0.62),
        "wrist": (0.28, 0.46),
        "elbow": (0.05, 0.14),
        "shoulder": (0.01, 0.07),
    },
    "medium": {
        "finger": (0.10, 0.22),
        "wrist": (0.44, 0.62),
        "elbow": (0.22, 0.38),
        "shoulder": (0.06, 0.16),
    },
    "long": {
        "finger": (0.12, 0.24),
        "wrist": (0.30, 0.48),
        "elbow": (0.24, 0.40),
        "shoulder": (0.18, 0.34),
    },
}

# 每次移动内的归一化周期数。典型 skilled 手势约 0.15~0.35s，finger 区间
# 对应约 8~15Hz 量级；其余三条运动链逐级降低。
MOTION_FREQUENCY_CYCLES = {
    "finger": (2.4, 4.2),
    "wrist": (0.85, 1.55),
    "elbow": (0.35, 0.80),
    "shoulder": (0.10, 0.32),
}

# 未加权分量的幅度区间。finger 用绝对像素；其余用移动距离比例。
FINGER_AMPLITUDE_PX = (0.5, 2.5)
WRIST_AMPLITUDE_RATIO = {
    "short": (0.05, 0.10), "medium": (0.12, 0.24), "long": (0.14, 0.26),
}
ELBOW_AMPLITUDE_RATIO = {
    "short": (0.015, 0.05), "medium": (0.08, 0.16), "long": (0.10, 0.20),
}
SHOULDER_AMPLITUDE_RATIO = {
    "short": (0.005, 0.025), "medium": (0.03, 0.08), "long": (0.08, 0.16),
}

# 各链允许少量沿运动方向的分量，避免轨迹只是“直线 + 纵向波纹”。
MOTION_TANGENT_MIX = {
    "finger": (-0.35, 0.35),
    "wrist": (-0.10, 0.10),
    "elbow": (-0.20, 0.20),
    "shoulder": (-0.28, 0.28),
}
MOTION_SHAPE_NORMALIZE_SAMPLES = 64


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

    @staticmethod
    def _motion_band(dist):
        if dist < 60.0:
            return "short"
        if dist < 400.0:
            return "medium"
        return "long"

    @staticmethod
    def _bridge_wave(t, cycles, phase):
        """任意相位正弦的端点桥接版本：t=0/1 都严格回到 0。"""
        a = math.sin(phase)
        b = math.sin(2.0 * math.pi * cycles + phase)
        raw = math.sin(2.0 * math.pi * cycles * t + phase)
        return raw - ((1.0 - t) * a + t * b)

    @staticmethod
    def _endpoint_window(t):
        """端点位移和一阶速度都归零；中点为 1。"""
        u = t * (1.0 - t)
        return 16.0 * u * u

    @staticmethod
    def _shape_peak(fn):
        peak = 0.0
        for i in range(MOTION_SHAPE_NORMALIZE_SAMPLES + 1):
            peak = max(peak, abs(fn(i / MOTION_SHAPE_NORMALIZE_SAMPLES)))
        return max(peak, 1e-9)

    def _sample_motion_model(self, dist):
        """为单次移动抽样四条运动链的权重、频率、幅度与相位。"""
        band = self._motion_band(dist)
        ranges = MOTION_WEIGHT_RANGES[band]
        raw_weights = {name: random.uniform(*ranges[name]) for name in ranges}
        total = sum(raw_weights.values())
        weights = {name: value / total for name, value in raw_weights.items()}

        model = {
            "band": band,
            "distance": dist,
            "weights": weights,
            "finger": {
                "cycles": random.uniform(*MOTION_FREQUENCY_CYCLES["finger"]),
                "phase": random.uniform(0.0, 2.0 * math.pi),
                "amplitude": random.uniform(*FINGER_AMPLITUDE_PX),
                "tangent_mix": random.uniform(*MOTION_TANGENT_MIX["finger"]),
            },
            "wrist": {
                "cycles": random.uniform(*MOTION_FREQUENCY_CYCLES["wrist"]),
                "phase": random.uniform(0.0, 2.0 * math.pi),
                "amplitude": dist * random.uniform(*WRIST_AMPLITUDE_RATIO[band]),
                "sign": random.choice((-1.0, 1.0)),
                "tangent_mix": random.uniform(*MOTION_TANGENT_MIX["wrist"]),
            },
            "elbow": {
                "cycles": random.uniform(*MOTION_FREQUENCY_CYCLES["elbow"]),
                "phase": random.uniform(0.0, 2.0 * math.pi),
                "amplitude": dist * random.uniform(*ELBOW_AMPLITUDE_RATIO[band]),
                "sign": random.choice((-1.0, 1.0)),
                "tangent_mix": random.uniform(*MOTION_TANGENT_MIX["elbow"]),
            },
            "shoulder": {
                "cycles": random.uniform(*MOTION_FREQUENCY_CYCLES["shoulder"]),
                "phase": random.uniform(0.0, 2.0 * math.pi),
                "amplitude": dist * random.uniform(*SHOULDER_AMPLITUDE_RATIO[band]),
                "sign": random.choice((-1.0, 1.0)),
                "tangent_mix": random.uniform(*MOTION_TANGENT_MIX["shoulder"]),
            },
        }

        f = model["finger"]
        f["normal_peak"] = self._shape_peak(
            lambda t: self._bridge_wave(t, f["cycles"], f["phase"]) *
                      self._endpoint_window(t) * (1.0 - 0.55 * self._ease(t))
        )
        f["tangent_peak"] = self._shape_peak(
            lambda t: self._bridge_wave(t, f["cycles"], f["phase"] + math.pi / 2.0) *
                      self._endpoint_window(t) * (1.0 - 0.55 * self._ease(t))
        )

        w = model["wrist"]
        w["peak"] = self._shape_peak(
            lambda t: w["sign"] * (
                0.82 * math.sin(math.pi * t) +
                0.18 * self._bridge_wave(t, w["cycles"], w["phase"])
            ) * self._endpoint_window(t)
        )

        e = model["elbow"]
        e["peak"] = self._shape_peak(
            lambda t: e["sign"] * self._bridge_wave(t, e["cycles"], e["phase"]) *
                      self._endpoint_window(t)
        )

        sh = model["shoulder"]
        sh["peak"] = self._shape_peak(
            lambda t: sh["sign"] * (4.0 * t * (1.0 - t)) *
                      (0.74 + 0.26 * math.cos(2.0 * math.pi * sh["cycles"] * t + sh["phase"])) *
                      self._endpoint_window(t)
        )
        return model

    def _motion_offsets(self, t, tx, ty, nx, ny, model):
        """返回四条运动链在进度 t 上的独立二维贡献，便于测试/频谱分析。"""
        weights = model["weights"]
        result = {}

        f = model["finger"]
        fade = 1.0 - 0.55 * self._ease(t)
        window = self._endpoint_window(t)
        fn = self._bridge_wave(t, f["cycles"], f["phase"]) * window * fade / f["normal_peak"]
        ft = self._bridge_wave(t, f["cycles"], f["phase"] + math.pi / 2.0) * window * fade / f["tangent_peak"]
        amp = weights["finger"] * f["amplitude"]
        result["finger"] = (
            nx * amp * fn + tx * amp * f["tangent_mix"] * ft,
            ny * amp * fn + ty * amp * f["tangent_mix"] * ft,
        )

        w = model["wrist"]
        ws = w["sign"] * (
            0.82 * math.sin(math.pi * t) +
            0.18 * self._bridge_wave(t, w["cycles"], w["phase"])
        ) * window / w["peak"]
        amp = weights["wrist"] * w["amplitude"]
        result["wrist"] = (
            nx * amp * ws + tx * amp * w["tangent_mix"] * ws,
            ny * amp * ws + ty * amp * w["tangent_mix"] * ws,
        )

        e = model["elbow"]
        es = (
            e["sign"] * self._bridge_wave(t, e["cycles"], e["phase"]) *
            window / e["peak"]
        )
        amp = weights["elbow"] * e["amplitude"]
        result["elbow"] = (
            nx * amp * es + tx * amp * e["tangent_mix"] * es,
            ny * amp * es + ty * amp * e["tangent_mix"] * es,
        )

        sh = model["shoulder"]
        ss = (
            sh["sign"] * (4.0 * t * (1.0 - t)) *
            (0.74 + 0.26 * math.cos(2.0 * math.pi * sh["cycles"] * t + sh["phase"])) *
            window / sh["peak"]
        )
        amp = weights["shoulder"] * sh["amplitude"]
        result["shoulder"] = (
            nx * amp * ss + tx * amp * sh["tangent_mix"] * ss,
            ny * amp * ss + ty * amp * sh["tangent_mix"] * ss,
        )
        return result

    def _arc_base(self, x0, y0, x1, y1, n):
        """四运动链复合轨迹：finger / wrist / elbow / shoulder 加权叠加。

        沿弦方向的主进度始终使用 smootherstep；所有横向/纵向附加分量都构造成
        端点为 0 的函数，所以复合后不会积累端点偏移。
        """
        dx, dy = x1 - x0, y1 - y0
        dist = math.hypot(dx, dy)
        if dist < 1e-9:
            self._last_motion = self._sample_motion_model(0.0)
            return [(x1, y1) for _ in range(n)]

        tx, ty = dx / dist, dy / dist
        nx, ny = -ty, tx
        model = self._sample_motion_model(dist)
        self._last_motion = model

        pts = []
        for i in range(1, n + 1):
            if i == n:
                pts.append((x1, y1))
                continue
            t = i / n
            e = self._ease(t)
            bx = x0 + dx * e
            by = y0 + dy * e
            offsets = self._motion_offsets(t, tx, ty, nx, ny, model)
            ox = sum(v[0] for v in offsets.values())
            oy = sum(v[1] for v in offsets.values())
            pts.append((bx + ox, by + oy))
        return pts

    def _segment(self, x0, y0, x1, y1, profile_only=False):
        """走一段：四运动链复合轨迹 + smootherstep 基础速度 + 偶发启停/微回撤。"""
        dx, dy = x1 - x0, y1 - y0
        dist = max(math.hypot(dx, dy), 1.0)
        lo_s, hi_s = self.profile["steps"]
        lo_m, hi_m = self.profile["step_ms"]
        n = max(lo_s, min(hi_s, int(dist / random.uniform(24, 46))))
        base = self._arc_base(x0, y0, x1, y1, n)
        prev = (x0, y0)
        for i, (bx, by) in enumerate(base, start=1):
            e = self._ease(i / n)
            jx, jy = bx, by
            r = random.random()
            if i < n and r < 0.035:                # 启停：原地顿一下（速度突然为 0）
                time.sleep(random.uniform(0.02, 0.07))
                jx, jy = prev
            elif i < n and r < 0.055:              # 微回撤：像手抖过头再拉回来
                jx = bx - (bx - prev[0]) * random.uniform(0.15, 0.5)
                jy = by - (by - prev[1]) * random.uniform(0.15, 0.5)
            self.tab.send("Input.dispatchMouseEvent", wait=False, type="mouseMoved",
                          x=round(jx, 1), y=round(jy, 1), buttons=0)
            time.sleep(random.uniform(lo_m, hi_m) * (1.0 + 1.4 * (1.0 - e)))
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
    def type_text(self, text, selector=None, focus_js=None, method="insert", min_ms=55, max_ms=170, clear_first=True):
        """输入文本。默认 **整段插入**（老板明确不要逐字）；`method="perchar"` 才逐字。

        无论哪种方式，输入前后都遵守"两次操作之间 2~10 秒"的间隔规矩。
        """
        if selector or focus_js:
            fj = focus_js or f"""(() => {{ const el = document.querySelector({json.dumps(selector)});
                if (!el) return false; el.focus(); el.click && el.click(); return true; }})()"""
            if not self._js(fj):
                _log(f"聚焦失败：{selector}")
                return False
        if clear_first:
            self.clear_field(pause_first=False)      # 清空是"输入"这个动作的一部分，不另算一次间隔
        self.pause(why="准备输入（与上一个动作隔 2~10 秒）")
        t0 = time.time()
        if method == "insert":
            self.tab.send("Input.insertText", text=text)
            time.sleep(random.uniform(0.25, 0.9))    # 落字本身也有个小停顿
        else:
            for ch in text:
                self.tab.send("Input.dispatchKeyEvent", wait=False, type="keyDown", text=ch, unmodifiedText=ch)
                time.sleep(random.uniform(0.012, 0.045))
                self.tab.send("Input.dispatchKeyEvent", wait=False, type="keyUp")
                time.sleep(random.uniform(min_ms, max_ms) / 1000.0)
                if random.random() < 0.06:
                    time.sleep(random.uniform(0.35, 1.30))
        if self.verbose:
            _log(f"已输入 {len(text)} 字（{method}），耗时 {time.time() - t0:.1f}s")
        self.pause(why="输完停一下（下次操作前会再等 2~10 秒）")
        return True

    def clear_field(self, pause_first=True):
        """人类式清空：全选 + 删除（不误发）。"""
        if pause_first:
            self.pause(why="清空前的停顿（2~10 秒）")
        self.tab.send("Input.dispatchKeyEvent", type="keyDown", modifiers=2, key="a", code="KeyA",
                      windowsVirtualKeyCode=65, nativeVirtualKeyCode=65)
        self.tab.send("Input.dispatchKeyEvent", type="keyUp", modifiers=2, key="a", code="KeyA",
                      windowsVirtualKeyCode=65, nativeVirtualKeyCode=65)
        time.sleep(random.uniform(0.08, 0.25))
        for k, code, vk in (("Backspace", "Backspace", 8),):
            self.tab.send("Input.dispatchKeyEvent", type="keyDown", key=k, code=code,
                          windowsVirtualKeyCode=vk, nativeVirtualKeyCode=vk)
            self.tab.send("Input.dispatchKeyEvent", type="keyUp", key=k, code=code,
                          windowsVirtualKeyCode=vk, nativeVirtualKeyCode=vk)
        time.sleep(random.uniform(0.15, 0.4))

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
