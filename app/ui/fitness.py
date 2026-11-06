"""肌薄首页：体重 + 三个入口.

体重图三层（口径见 app/fit_trend.py）：
  * 散点 —— 每一条记录
  * 灰线 —— 每日均值
  * 绿线 —— 时段校正后的 7 日滚动中位数

顶部可切「月 / 半年 / 全部」。鼠标悬停以**天**为单位吸附，
浮出「本日校正值」和「较前日增减」。
"""
from __future__ import annotations

import datetime as dt
import tkinter as tk

from .. import fit, fit_trend
from . import theme
from .fit_dialogs import WeightHistory
from .widgets import Card, FlatButton

PERIODS = (("month", "月", 30), ("half", "半年", 182), ("all", "全部", 0))


class WeightChart(tk.Canvas):
    """体重散点 + 日均线 + 稳健趋势线，带按天吸附的悬停提示。"""

    PAD_L, PAD_R, PAD_T, PAD_B = 58, 24, 26, 30

    def __init__(self, master, app, **kw):
        super().__init__(master, bg=theme.CARD, highlightthickness=0, **kw)
        self.app = app
        self.period = "month"
        self._days: list[dict] = []      # 每天一条：date, x, corrected, delta
        self._hover = -1
        self.bind("<Configure>", lambda e: self.redraw())
        self.bind("<Motion>", self._on_motion)
        self.bind("<Leave>", self._on_leave)

    # ------------------------------------------------------------ 交互
    def _on_motion(self, event) -> None:
        if not self._days:
            return
        best, idx = 16.0, -1
        for i, d in enumerate(self._days):
            gap = abs(d["x"] - event.x)
            if gap < best:
                best, idx = gap, i
        if idx != self._hover:
            self._hover = idx
            self.redraw()

    def _on_leave(self, _e=None) -> None:
        if self._hover != -1:
            self._hover = -1
            self.redraw()

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

    # ------------------------------------------------------------ 绘制
    def redraw(self) -> None:
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if w < 120 or h < 100:
            return

        window = self._window()
        if not window:
            self.create_text(w // 2, h // 2, text="还没有体重记录",
                             fill=theme.MUTED, font=theme.f(11))
            self._days = []
            return

        # 时段校正在**全部历史**上估计，窗口只影响画什么
        offsets = fit_trend.hour_offsets(self.app.db.fit_weight_all())
        items = [it for it in fit_trend.corrected(window, offsets)]
        daily_raw = dict(fit_trend.daily_points(items, use_corrected=False))
        daily_adj = fit_trend.daily_points(items, use_corrected=True)
        trend = fit_trend.rolling_median(daily_adj, 7)

        if len(items) < 2:
            self.create_text(w // 2, h // 2, text="记录还太少，画不出趋势",
                             fill=theme.MUTED, font=theme.f(11))
            self._days = []
            return

        dates = sorted({ts.date() for ts, _k, _a in items})
        d0, d1 = dates[0], dates[-1]
        span_days = max(1, (d1 - d0).days)
        vals = [a for _t, _k, a in items] + [k for _t, k, _a in items] \
            + [v for _d, v in trend]
        lo, hi = min(vals), max(vals)
        pad = max(0.35, (hi - lo) * 0.18)
        lo, hi = lo - pad, hi + pad

        def px(t: float) -> float:
            return self.PAD_L + (w - self.PAD_L - self.PAD_R) * ((t - d0.toordinal())
                                                                / span_days)

        def px_day(d: dt.date) -> float:
            return px(d.toordinal())

        def py(v: float) -> float:
            return self.PAD_T + (h - self.PAD_T - self.PAD_B) * (1 - (v - lo) / (hi - lo))

        # ---- 背景：细网格 + 纵轴
        for i in range(5):
            val = lo + (hi - lo) * i / 4
            y = py(val)
            self.create_line(self.PAD_L, y, w - self.PAD_R, y,
                             fill="#EEF0F6")
            self.create_text(self.PAD_L - 10, y, text=f"{val:.1f}", anchor="e",
                             fill="#9AA0AE", font=theme.f(9))

        # ---- 横轴：等距取刻度，**首尾都包含**，这样不会出现两个标签挤在一起
        n = len(dates)
        k = 6 if span_days <= 45 else (8 if span_days <= 200 else 9)
        k = min(k, n)
        if k <= 1:
            ticks = [0]
        else:
            ticks = sorted({round(i * (n - 1) / (k - 1)) for i in range(k)})
        for i in ticks:
            d = dates[i]
            self.create_line(px_day(d), h - self.PAD_B,
                             px_day(d), h - self.PAD_B + 4, fill="#D8DCE6")
            self.create_text(px_day(d), h - self.PAD_B + 15,
                             text=d.strftime("%m-%d"), fill="#9AA0AE",
                             font=theme.f(9))

        # ---- 日均灰线
        if len(daily_raw) > 1:
            pts = []
            for d in dates:
                if d in daily_raw:
                    pts += [px_day(d), py(daily_raw[d])]
            if len(pts) > 3:
                self.create_line(*pts, fill="#D5D9E3", width=1.1)

        # ---- 散点（按天轻微左右抖动，避免同一时刻叠成一坨）
        by_day: dict[dt.date, list[tuple[dt.datetime, float, float]]] = {}
        for ts, kg, adj in items:
            by_day.setdefault(ts.date(), []).append((ts, kg, adj))
        for d, points in by_day.items():
            for ts, kg, _adj in points:
                x = px_day(d) + (ts.hour - 12) * 0.55
                self.create_oval(x - 1.9, py(kg) - 1.9, x + 1.9, py(kg) + 1.9,
                                 fill="#C2C8D6", outline="")

        # ---- 趋势线：先画一条浅色粗线打底，再叠主线，看起来更柔和
        tcoords = []
        for d, v in trend:
            tcoords += [px_day(d), py(v)]
        if len(tcoords) > 3:
            self.create_line(*tcoords, fill="#CFEFDC", width=6, smooth=True)
            self.create_line(*tcoords, fill=theme.SUCCESS, width=2.4, smooth=True)

        # ---- 悬停用的每日数据
        deltas: dict[dt.date, float | None] = {}
        prev = None
        for d, v in daily_adj:
            deltas[d] = None if prev is None else v - prev
            prev = v
        self._days = [{"date": d, "x": px_day(d), "value": v,
                       "delta": deltas.get(d)} for d, v in daily_adj]

        if 0 <= self._hover < len(self._days):
            self._draw_tip(w, h, self._days[self._hover], lo, hi, py)

    def _draw_tip(self, w: int, h: int, day: dict, lo: float, hi: float, py) -> None:
        x = day["x"]
        y = py(day["value"])
        self.create_line(x, self.PAD_T, x, h - self.PAD_B,
                         fill="#E8622C", dash=(3, 4))
        self.create_oval(x - 5, y - 5, x + 5, y + 5, fill="#FFFFFF",
                         outline=theme.PRIMARY, width=2)

        delta = day["delta"]
        lines = [(day["date"].strftime("%m-%d"), theme.TEXT, True),
                 (f"校正 {day['value']:.1f} kg", theme.SUCCESS, False),
                 (("较前日 —" if delta is None else
                   f"较前日 {delta:+.1f} kg"), theme.MUTED, False)]
        pad, row = 10, 17
        tw = max(len(t) for t, _c, _b in lines) * 8.4 + pad * 2
        th = len(lines) * row + pad
        bx = min(max(x - tw / 2, self.PAD_L), w - self.PAD_R - tw)
        by = y - th - 16
        if by < self.PAD_T:
            by = y + 16
        self.create_rectangle(bx, by, bx + tw, by + th, fill="#FFFFFF",
                              outline="#D8DCE6")
        for i, (text, color, bold) in enumerate(lines):
            self.create_text(bx + pad, by + pad / 2 + 8 + i * row, anchor="w",
                             text=text, fill=color,
                             font=theme.f(9, "bold" if bold else "normal"))


class FitnessFrame(tk.Frame):
    def __init__(self, master, app):
        super().__init__(master, bg=theme.BG)
        self.grid(row=0, column=0, sticky="nsew")
        self.app = app
        self._build()

    def _build(self) -> None:
        head = tk.Frame(self, bg=theme.BG)
        head.pack(fill="x", padx=30, pady=(18, 4))
        FlatButton(head, "← 返回", lambda: self.app.show("life"), bg=theme.BG,
                   hover=theme.CARD, font=theme.f(11), padx=12, pady=7
                   ).pack(side="left")
        tk.Label(head, text="肌薄", bg=theme.BG, fg=theme.TEXT,
                 font=theme.f(16, "bold")).pack(side="left", padx=14)
        self.summary = tk.Label(head, text="", bg=theme.BG, fg=theme.MUTED,
                                font=theme.f(10))
        self.summary.pack(side="right")

        body = tk.Frame(self, bg=theme.BG)
        body.pack(fill="both", expand=True, padx=30, pady=(8, 18))

        weight = Card(body)
        weight.pack(fill="x", pady=(0, 10))
        inner = tk.Frame(weight, bg=theme.CARD)
        inner.pack(fill="x", padx=22, pady=(14, 12))

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

        # 周期切换：月 / 半年 / 全部
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

        # 趋势摘要放在图表上方，不画在画布里，避免和曲线文字重叠
        self.trend_label = tk.Label(inner, text="", bg=theme.CARD,
                                    fg=theme.SUCCESS, font=theme.f(11, "bold"))
        self.trend_label.pack(anchor="e", pady=(6, 0))

        self.chart = WeightChart(inner, self.app, height=430)
        self.chart.pack(fill="x", pady=(2, 0))
        self._set_period("month")

        grid = tk.Frame(body, bg=theme.BG)
        grid.pack(fill="both", expand=True, pady=(6, 0))
        for c in range(3):
            grid.grid_columnconfigure(c, weight=1, uniform="fit")
        grid.grid_rowconfigure(0, weight=1)

        self._tile(grid, 0, "fit_strength", "力量训练", "哑铃动作打卡 · 历史明细",
                   "🏋", theme.BLUE, theme.BLUE_SOFT)
        self._tile(grid, 1, "fit_cardio", "有氧运动", "跑步 · 骑行 · 配速",
                   "🏃", theme.SUCCESS, theme.SUCCESS_SOFT)
        self._tile(grid, 2, "fit_ai", "AI建议", "周报 · 月报 · 半年报",
                   "🤖", theme.PRIMARY, theme.PRIMARY_SOFT)

    # ------------------------------------------------------------ 入口卡
    def _tile(self, parent, col, key, title, sub, glyph, color, soft) -> None:
        card = Card(parent)
        card.grid(row=0, column=col, sticky="nsew",
                  padx=(0, 8) if col == 0 else (8, 0))
        box = tk.Frame(card, bg=theme.CARD)
        box.pack(fill="both", expand=True, padx=6, pady=6)

        # 图标水平垂直都居中
        mark = tk.Label(box, text=glyph, bg=theme.CARD, fg=color,
                        font=theme.f(40))
        mark.pack(expand=True)

        btn = FlatButton(box, title, lambda k=key: self.app.show(k),
                         bg=theme.CARD, hover=soft, active_bg=soft,
                         font=theme.f(19, "bold"), fg=color, pady=2,
                         border=theme.CARD)
        btn.pack(fill="x", padx=2)
        btn.set_subtitle(sub)
        btn.configure(highlightbackground=theme.CARD)

        btn.bind_hover_group(card, box, mark)
        for w_ in (card, box, mark):
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
        records = self.app.db.fit_weight_all()
        offsets = fit_trend.hour_offsets(records)
        items = fit_trend.corrected(window, offsets)
        daily = fit_trend.daily_points(items, use_corrected=True)
        trend = fit_trend.rolling_median(daily, 7)
        slope = fit_trend.theil_sen(daily)
        last = trend[-1][1] if trend else daily[-1][1]
        label = {"month": "近 30 天", "half": "近半年", "all": "全部"}[self.chart.period]
        self.trend_label.configure(
            text=f"{label}趋势 {last:.1f} kg　·　{slope:+.2f} kg/周")

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
