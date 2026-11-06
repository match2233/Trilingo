"""肌薄首页：上半页体重图，下半页三个入口.

体重图：
  * 灰色**包络带** —— 上沿 = 每天最高点的平滑曲线、下沿 = 最低点，
    并且**向外扩到真正包住当天所有点**；多边形裁进绘图区，不压坐标轴
  * 灰线 —— 每日均值
  * 绿线 —— 时段校正后的 7 日滚动中位数（口径见 app/fit_trend.py）
  * 散点 —— 每条记录，横轴按真实时间

悬停与记账图表一致：蓝色虚线框（内部透明）+ 顶部白色浮窗。
"""
from __future__ import annotations

import datetime as dt
import statistics
import tkinter as tk

from .. import fit, fit_trend
from . import theme
from .fit_dialogs import WeightHistory
from .widgets import Card, FlatButton

PERIODS = (("month", "月", 30), ("half", "半年", 182), ("all", "全部", 0))


def _median3(values: list[float]) -> list[float]:
    """3 点中位平滑：削掉单点尖刺，不改变整体形状."""
    out = []
    for i, _v in enumerate(values):
        chunk = values[max(0, i - 1):i + 2]
        out.append(statistics.median(chunk))
    return out


def _catmull(points: list[tuple[float, float]], samples: int = 8):
    """Catmull-Rom 平滑，插值点限制在相邻两点之间（防过冲）."""
    if len(points) < 3:
        return points
    out: list[tuple[float, float]] = []
    pts = [points[0]] + list(points) + [points[-1]]
    for i in range(1, len(pts) - 2):
        p0, p1, p2, p3 = pts[i - 1], pts[i], pts[i + 1], pts[i + 2]
        for s in range(samples):
            t = s / samples
            t2, t3 = t * t, t * t * t
            x = 0.5 * ((2 * p1[0]) + (-p0[0] + p2[0]) * t
                       + (2 * p0[0] - 5 * p1[0] + 4 * p2[0] - p3[0]) * t2
                       + (-p0[0] + 3 * p1[0] - 3 * p2[0] + p3[0]) * t3)
            y = 0.5 * ((2 * p1[1]) + (-p0[1] + p2[1]) * t
                       + (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * t2
                       + (-p0[1] + 3 * p1[1] - 3 * p2[1] + p3[1]) * t3)
            lo_y, hi_y = sorted((p1[1], p2[1]))
            out.append((x, min(max(y, lo_y), hi_y)))
    out.append(points[-1])
    return out


class WeightChart(tk.Canvas):
    PAD_L, PAD_R, PAD_T, PAD_B = 52, 18, 14, 30

    def __init__(self, master, app, **kw):
        super().__init__(master, bg=theme.CARD, highlightthickness=0, **kw)
        self.app = app
        self.period = "month"
        self._days: list[dict] = []
        self._hover = -1
        self.bind("<Configure>", lambda e: self.redraw())
        self.bind("<Motion>", self._on_motion)
        self.bind("<Leave>", self._on_leave)

    # ------------------------------------------------------------ 数据
    def _window(self) -> list[tuple[str, float]]:
        records = self.app.db.fit_weight_all()
        span = {k: v for k, _l, v in PERIODS}[self.period]
        if not span or not records:
            return records
        cut = dt.date.today() - dt.timedelta(days=span)
        window = [(at, kg) for at, kg in records
                  if dt.datetime.fromisoformat(at).date() >= cut]
        return window if len(window) >= 2 else records

    # ------------------------------------------------------------ 交互
    def _on_motion(self, event) -> None:
        if not self._days:
            return
        best, idx = 26.0, -1
        for i, d in enumerate(self._days):
            gap = 0.0 if d["x0"] <= event.x <= d["x1"] else min(
                abs(event.x - d["x0"]), abs(event.x - d["x1"]))
            if gap < best:
                best, idx = gap, i
        if idx != self._hover:
            self._hover = idx
            self.redraw()

    def _on_leave(self, _e=None) -> None:
        if self._hover != -1:
            self._hover = -1
            self.redraw()

    # ------------------------------------------------------------ 绘制
    def redraw(self) -> None:
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if w < 140 or h < 90:
            return

        window = self._window()
        if not window:
            self.create_text(w // 2, h // 2, text="还没有体重记录",
                             fill=theme.MUTED, font=theme.f(11))
            self._days = []
            return

        offsets = fit_trend.hour_offsets(self.app.db.fit_weight_all())
        items = fit_trend.corrected(window, offsets)
        by_day: dict[dt.date, list[tuple[dt.datetime, float]]] = {}
        for ts, kg, _adj in items:
            by_day.setdefault(ts.date(), []).append((ts, kg))
        if len(by_day) < 2:
            self.create_text(w // 2, h // 2, text="记录还太少，画不出趋势",
                             fill=theme.MUTED, font=theme.f(11))
            self._days = []
            return

        daily_raw = dict(fit_trend.daily_points(items, use_corrected=False))
        daily_adj = fit_trend.daily_points(items, use_corrected=True)
        trend = fit_trend.rolling_median(daily_adj, 7)
        spans = {d: (min(k for _t, k in pts), max(k for _t, k in pts))
                 for d, pts in by_day.items()}
        days = sorted(by_day)

        ts_all = [ts for ts, _k, _a in items]
        t0, t1 = min(ts_all), max(ts_all)
        if (t1 - t0).total_seconds() < 3600:
            t0 -= dt.timedelta(minutes=30)
            t1 += dt.timedelta(minutes=30)
        # 两端各留半天，否则第一天的点和日期会被纵轴压住
        span = t1 - t0
        edge = max(dt.timedelta(hours=8), span * 0.04)
        t0 -= edge
        t1 += edge

        lo = min(min(v[0] for v in spans.values()), min(v for _d, v in trend))
        hi = max(max(v[1] for v in spans.values()), max(v for _d, v in trend))
        pad = max(0.12, (hi - lo) * 0.06)
        lo, hi = lo - pad, hi + pad

        def x_of(d: dt.date) -> float:
            return dt.datetime.combine(d, dt.time(12, 0)).timestamp()

        def px(t: float) -> float:
            return self.PAD_L + (w - self.PAD_L - self.PAD_R) * (
                (t - t0.timestamp()) / (t1.timestamp() - t0.timestamp()))

        def py(v: float) -> float:
            return self.PAD_T + (h - self.PAD_T - self.PAD_B) * (
                1 - (v - lo) / (hi - lo))

        top, bot = self.PAD_T, h - self.PAD_B
        left, right = self.PAD_L, w - self.PAD_R
        # 供自检使用：投影参数 + 包络曲线
        self._proj = {"t0": t0.timestamp(), "t1": t1.timestamp(),
                      "lo": lo, "hi": hi, "left": left, "right": right,
                      "top": top, "bot": bot}
        self._band = None
        self._items = items

        # ---- ① 灰色包络带（先画，坐标轴随后压在上面）
        if len(days) > 1:
            raw_max = [spans[d][1] for d in days]
            raw_min = [spans[d][0] for d in days]
            up_vals = [max(a, b) for a, b in zip(_median3(raw_max), raw_max)]
            low_vals = [min(a, b) for a, b in zip(_median3(raw_min), raw_min)]
            xs = [min(max(px(x_of(d)), left), right) for d in days]
            up = _catmull(list(zip(xs, [py(v) for v in up_vals])))
            low = _catmull(list(zip(xs, [py(v) for v in low_vals])))

            # 每个真实数据点都必须在带子里：找到最近的采样点，把上下沿各撑开，
            # 并按距离做三角形衰减，避免出现单点尖刺。再额外留 0.1kg 余量。
            margin = 0.1 / max(1e-6, (hi - lo)) * (bot - top)
            for ts, kg, _adj in items:
                xp, yp = px(ts.timestamp()), py(kg)
                i = min(range(len(up)), key=lambda k: abs(up[k][0] - xp))
                for off in range(-4, 5):
                    j = i + off
                    if not (0 <= j < len(up)):
                        continue
                    fall = max(0.0, 1 - abs(off) / 5.0)
                    need_top = yp - margin * fall
                    need_bot = yp + margin * fall
                    if up[j][1] > need_top:
                        up[j] = (up[j][0], need_top)
                    if low[j][1] < need_bot:
                        low[j] = (low[j][0], need_bot)

            up = [(min(max(x, left), right), min(max(y, top), bot)) for x, y in up]
            low = [(min(max(x, left), right), min(max(y, top), bot)) for x, y in low]
            poly = [c for q in up for c in q] + [c for q in reversed(low) for c in q]
            self._band = (up, low)
            self.create_polygon(*poly, fill="#E9ECF4", outline="")
            self.create_line(*[c for q in up for c in q], fill="#D6DAE4", width=1.4)
            self.create_line(*[c for q in low for c in q], fill="#D6DAE4", width=1.4)

        # ---- ② 网格 + 纵轴（压在阴影带上方）
        for i in range(5):
            val = lo + (hi - lo) * i / 4
            y = py(val)
            self.create_line(left, y, right, y, fill="#E9EBF2")
            self.create_text(left - 9, y, text=f"{val:.1f}", anchor="e",
                             fill="#8E94A4", font=theme.f(9))

        # ---- ③ 横轴：能放下就每天都标
        n = len(days)
        plot_w = right - left
        per_day = plot_w / max(1, n)
        # 每天都标；太密就只写日，月初/首日写成月/日，避免互相压字
        if per_day >= 46:
            ticks = list(range(n))
            labels = [d.strftime("%m-%d") for d in days]
        else:
            ticks = list(range(n))
            labels = [(f"{d.month}/{d.day}" if (d.day == 1 or i == 0)
                       else str(d.day)) for i, d in enumerate(days)]
        fsize = 9 if per_day >= 46 else 8
        step_px = max(10, int(per_day))
        for i in ticks:
            d = days[i]
            cx = px(x_of(d))
            self.create_line(cx, bot, cx, bot + 4, fill="#D8DCE6")
            self.create_text(cx, bot + 14, text=labels[i], fill="#8E94A4",
                             font=theme.f(fsize))
            if step_px < 16 and i % 2:
                continue

        # ---- ④ 日均灰线
        pts = [(px(x_of(d)), py(daily_raw[d])) for d in days if d in daily_raw]
        if len(pts) > 1:
            self.create_line(*[c for p in _catmull(pts) for c in p],
                             fill="#B9C0CE", width=2)

        # ---- ⑤ 散点
        for ts, kg, _adj in items:
            x = px(ts.timestamp())
            self.create_oval(x - 2.6, py(kg) - 2.6, x + 2.6, py(kg) + 2.6,
                             fill="#AEB6C7", outline="")

        # ---- ⑥ 趋势线
        tpts = [(px(x_of(d)), py(v)) for d, v in trend]
        if len(tpts) > 1:
            flat = [c for p in _catmull(tpts) for c in p]
            self.create_line(*flat, fill="#D9F2E4", width=9, smooth=True)
            self.create_line(*flat, fill=theme.SUCCESS, width=3.5, smooth=True)

        # ---- ⑦ 悬停区间
        step = plot_w / max(1, n)
        self._days = []
        prev = None
        for d, v in daily_adj:
            if d not in by_day:
                continue
            cx = px(x_of(d))
            self._days.append({
                "date": d, "value": v,
                "delta": None if prev is None else v - prev,
                "x0": cx - step / 2, "x1": cx + step / 2,
            })
            prev = v

        if 0 <= self._hover < len(self._days):
            self._draw_tip(h, self._days[self._hover], w)

    def _draw_tip(self, h: int, day: dict, w: int) -> None:
        x0 = max(self.PAD_L, day["x0"])
        x1 = min(w - self.PAD_R, day["x1"])
        self.create_rectangle(x0, self.PAD_T, x1, h - self.PAD_B,
                              fill="", outline=theme.BLUE, dash=(3, 2))

        delta = day["delta"]
        lines = [(day["date"].strftime("%m-%d"), theme.TEXT, True),
                 (f"校正  {day['value']:.1f} kg", theme.SUCCESS, False),
                 (("较前日  —" if delta is None else f"较前日  {delta:+.1f} kg"),
                  theme.MUTED, False)]
        pad, row_h = 8, 15
        tw = max(len(t) for t, _c, _b in lines) * 7.8 + pad * 2
        th = len(lines) * row_h + pad
        bx = min(max((x0 + x1) / 2 - tw / 2, self.PAD_L), w - self.PAD_R - tw)
        by = 20.0
        self.create_rectangle(bx, by, bx + tw, by + th,
                              fill="#FFFFFF", outline=theme.BORDER)
        for k, (text, color, bold) in enumerate(lines):
            self.create_text(bx + pad, by + pad / 2 + k * row_h, text=text,
                             anchor="w", fill=color,
                             font=theme.f(9, "bold" if bold else "normal"))


class FitnessFrame(tk.Frame):
    def __init__(self, master, app):
        super().__init__(master, bg=theme.BG)
        self.grid(row=0, column=0, sticky="nsew")
        self.app = app
        self._build()

    def _build(self) -> None:
        head = tk.Frame(self, bg=theme.BG)
        head.pack(fill="x", padx=30, pady=(14, 2))
        FlatButton(head, "← 返回", lambda: self.app.show("life"), bg=theme.BG,
                   hover=theme.CARD, font=theme.f(11), padx=12, pady=7
                   ).pack(side="left")
        tk.Label(head, text="肌薄", bg=theme.BG, fg=theme.TEXT,
                 font=theme.f(16, "bold")).pack(side="left", padx=14)
        self.summary = tk.Label(head, text="", bg=theme.BG, fg=theme.MUTED,
                                font=theme.f(10))
        self.summary.pack(side="right")

        body = tk.Frame(self, bg=theme.BG)
        body.pack(fill="both", expand=True, padx=24, pady=(4, 14))
        body.grid_rowconfigure(0, weight=1, uniform="half")
        body.grid_rowconfigure(1, weight=1, uniform="half")
        body.grid_columnconfigure(0, weight=1)

        weight = Card(body)
        weight.grid(row=0, column=0, sticky="nsew", pady=(0, 8))
        inner = tk.Frame(weight, bg=theme.CARD)
        inner.pack(fill="both", expand=True, padx=18, pady=(10, 8))

        top = tk.Frame(inner, bg=theme.CARD)
        top.pack(fill="x")
        tk.Label(top, text="体重", bg=theme.CARD, fg=theme.TEXT,
                 font=theme.f(15, "bold")).pack(side="left")
        self.weight_var = tk.StringVar()
        ent = tk.Entry(top, textvariable=self.weight_var, width=7,
                       font=theme.f(12), justify="right", bd=0, bg=theme.SUNK,
                       fg=theme.TEXT, relief="flat", highlightthickness=1,
                       highlightbackground=theme.BORDER)
        ent.pack(side="left", padx=(16, 4), ipady=3)
        ent.bind("<Return>", lambda e: self._add_weight())
        tk.Label(top, text="kg", bg=theme.CARD, fg=theme.MUTED,
                 font=theme.f(11)).pack(side="left")
        FlatButton(top, "记录", self._add_weight, bg=theme.PRIMARY, fg="#FFFFFF",
                   hover=theme.PRIMARY_DARK, active_bg=theme.PRIMARY_DARK,
                   font=theme.f(11, "bold"), padx=18, pady=7
                   ).pack(side="left", padx=12)
        FlatButton(top, "详细数据", self._open_detail, bg=theme.CARD,
                   font=theme.f(11), padx=14, pady=7).pack(side="left")

        seg = tk.Frame(top, bg=theme.CARD)
        seg.pack(side="left", padx=(16, 0))
        self.period_btns: dict[str, FlatButton] = {}
        for key, label, _span in PERIODS:
            b = FlatButton(seg, label, lambda k=key: self._set_period(k),
                           bg=theme.SUNK, fg=theme.MUTED, font=theme.f(10),
                           padx=12, pady=5, border=theme.BORDER)
            b.pack(side="left", padx=(0, 4))
            self.period_btns[key] = b

        self.hint = tk.Label(top, text="", bg=theme.CARD, fg=theme.MUTED,
                             font=theme.f(10))
        self.hint.pack(side="left", padx=10)

        self.trend_label = tk.Label(top, text="", bg=theme.CARD,
                                    fg=theme.SUCCESS, font=theme.f(11, "bold"))
        self.trend_label.pack(side="right")

        self.chart = WeightChart(inner, self.app)
        self.chart.pack(fill="both", expand=True, pady=(6, 0))

        tiles = tk.Frame(body, bg=theme.BG)
        tiles.grid(row=1, column=0, sticky="nsew")
        for c in range(3):
            tiles.grid_columnconfigure(c, weight=1, uniform="tile")
        tiles.grid_rowconfigure(0, weight=1)

        self._tile(tiles, 0, "fit_strength", "力量训练", "哑铃动作打卡 · 历史明细",
                   "🏋", theme.BLUE, theme.BLUE_SOFT)
        self._tile(tiles, 1, "fit_cardio", "有氧运动", "跑步 · 骑行 · 配速",
                   "🏃", theme.SUCCESS, theme.SUCCESS_SOFT)
        self._tile(tiles, 2, "fit_ai", "AI建议", "周报 · 月报 · 半年报",
                   "🤖", theme.PRIMARY, theme.PRIMARY_SOFT)

    # ------------------------------------------------------------ 入口卡
    def _tile(self, parent, col, key, title, sub, glyph, color, soft) -> None:
        card = Card(parent)
        card.grid(row=0, column=col, sticky="nsew",
                  padx=(0, 8) if col == 0 else (8, 0))

        # 图标 + 标题 + 副标题放进同一个 group，让整组在卡片里居中，
        # 这样上下留白才相等（分别 pack 会把文字压到底）。
        group = tk.Frame(card, bg=theme.CARD)
        group.pack(expand=True)

        mark = tk.Label(group, text=glyph, bg=theme.CARD, fg=color,
                        font=theme.f(52))
        mark.pack()

        btn = FlatButton(group, title, lambda k=key: self.app.show(k),
                         bg=theme.CARD, hover=soft, active_bg=soft,
                         font=theme.f(22, "bold"), fg=color, pady=2,
                         border=theme.CARD, anchor="center")
        btn.pack(fill="x", pady=(8, 0))
        btn.set_subtitle(sub)
        btn.configure(highlightbackground=theme.CARD)

        btn.bind_hover_group(card, group, mark)
        for w_ in (card, group, mark):
            w_.bind("<Button-1>", lambda e, k=key: self.app.show(k))

    # ------------------------------------------------------------ 数据
    def _set_period(self, key: str) -> None:
        self.chart.period = key
        for k, b in self.period_btns.items():
            on = k == key
            b.set_palette(theme.PRIMARY_SOFT if on else theme.SUNK,
                          fg=theme.PRIMARY if on else theme.MUTED)
        self.chart.redraw()
        self._update_trend_label()

    def _update_trend_label(self) -> None:
        window = self.chart._window()
        if len(window) < 2:
            self.trend_label.configure(text="")
            return
        offsets = fit_trend.hour_offsets(self.app.db.fit_weight_all())
        items = fit_trend.corrected(window, offsets)
        daily = fit_trend.daily_points(items, use_corrected=True)
        trend = fit_trend.rolling_median(daily, 7)
        slope = fit_trend.theil_sen(daily)
        last = trend[-1][1] if trend else daily[-1][1]
        label = {"month": "近 30 天", "half": "近半年", "all": "全部"}[self.chart.period]
        self.trend_label.configure(
            text=f"{label}趋势 {last:.1f}kg · {slope:+.2f} kg/周")

    def _add_weight(self) -> None:
        try:
            kg = float(self.weight_var.get().strip())
        except ValueError:
            self.hint.configure(text="请输入数字，例如 65.4", fg=theme.ERROR)
            return
        if not 25 <= kg <= 200:
            self.hint.configure(text="数值看着不像体重", fg=theme.ERROR)
            return
        self.app.db.fit_weight_add(kg)
        self.weight_var.set("")
        self.hint.configure(
            text=f"已记录 {kg}kg（{dt.datetime.now():%H:%M}）", fg=theme.SUCCESS)
        self._refresh()

    def _open_detail(self) -> None:
        self._hist = WeightHistory(self, self.app, on_change=self._refresh)

    def _refresh(self) -> None:
        self.chart.redraw()
        self._update_trend_label()
        s = self.app.db.fit_summary()
        parts = []
        if s["weight"]:
            b = fit.bmi(s["weight"])
            parts.append(f"{s['weight']:.1f}kg" + (f" · BMI {b}" if b else ""))
        if s["sets"]:
            parts.append(f"今日 {s['sets']} 组")
        self.summary.configure(text="　·　".join(parts) if parts else "还没有数据")

    def on_show(self, **_):
        self._set_period(self.chart.period)
        self._refresh()
