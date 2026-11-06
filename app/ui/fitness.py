"""肌薄首页：体重 + 三个入口.

体重图：
  * 灰色**范围带** —— 每天记录的最低~最高，一眼看出当天波动幅度
  * 灰线 —— 每日均值
  * 绿线 —— 时段校正后的 7 日滚动中位数（口径见 app/fit_trend.py）
  * 散点 —— 每条记录，横轴按**真实时间**排布（不是按天等距）

悬停和记账一致：把当天那一列框起来，浮出「本日校正值 + 较前日增减」。
"""
from __future__ import annotations

import datetime as dt
import tkinter as tk

from .. import fit, fit_trend
from . import theme
from .fit_dialogs import WeightHistory
from .widgets import Card, FlatButton

PERIODS = (("month", "月", 30), ("half", "半年", 182), ("all", "全部", 0))
CHART_H = 280


class WeightChart(tk.Canvas):
    PAD_L, PAD_R, PAD_T, PAD_B = 52, 18, 16, 26

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
        best, idx = 20.0, -1
        for i, d in enumerate(self._days):
            if d["x0"] <= event.x <= d["x1"]:
                idx = i
                break
            gap = min(abs(event.x - d["x0"]), abs(event.x - d["x1"]))
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

        ts_all = [ts for ts, _k, _a in items]
        t0, t1 = min(ts_all), max(ts_all)
        if (t1 - t0).total_seconds() < 3600:
            t0 -= dt.timedelta(minutes=30)
            t1 += dt.timedelta(minutes=30)

        lo = min(v[0] for v in spans.values())
        hi = max(v[1] for v in spans.values())
        if trend:
            lo = min(lo, min(v for _d, v in trend))
            hi = max(hi, max(v for _d, v in trend))
        pad = max(0.2, (hi - lo) * 0.1)
        lo, hi = lo - pad, hi + pad

        def px(t: float) -> float:
            return self.PAD_L + (w - self.PAD_L - self.PAD_R) * (
                (t - t0.timestamp()) / (t1.timestamp() - t0.timestamp()))

        def py(v: float) -> float:
            return self.PAD_T + (h - self.PAD_T - self.PAD_B) * (1 - (v - lo) / (hi - lo))

        # 网格
        for i in range(5):
            val = lo + (hi - lo) * i / 4
            y = py(val)
            self.create_line(self.PAD_L, y, w - self.PAD_R, y, fill="#E9EBF2")
            self.create_text(self.PAD_L - 9, y, text=f"{val:.1f}", anchor="e",
                             fill="#8E94A4", font=theme.f(9))

        days = sorted(by_day)
        # 灰色范围带
        if len(days) > 1:
            up, down = [], []
            for d in days:
                cx = px(dt.datetime.combine(d, dt.time(12, 0)).timestamp())
                up += [cx, py(spans[d][1])]
                down = [cx, py(spans[d][0])] + down
            self.create_polygon(*up, *down, fill="#F1F2F7", outline="")

        # 横轴刻度（等距、含首尾）
        n = len(days)
        k = min(6 if (t1 - t0).days <= 45 else 8, n)
        ticks = (sorted({round(i * (n - 1) / (k - 1)) for i in range(k)})
                 if k > 1 else [0])
        for i in ticks:
            d = days[i]
            cx = px(dt.datetime.combine(d, dt.time(12, 0)).timestamp())
            self.create_line(cx, h - self.PAD_B, cx, h - self.PAD_B + 5,
                             fill="#D8DCE6")
            self.create_text(cx, h - self.PAD_B + 15, text=d.strftime("%m-%d"),
                             fill="#8E94A4", font=theme.f(9))

        # 日均灰线
        pts = []
        for d in days:
            if d in daily_raw:
                pts += [px(dt.datetime.combine(d, dt.time(12, 0)).timestamp()),
                        py(daily_raw[d])]
        if len(pts) > 3:
            self.create_line(*pts, fill="#B9C0CE", width=2)

        # 散点（真实时间、点更大）
        for ts, kg, _adj in items:
            x = px(ts.timestamp())
            self.create_oval(x - 3.0, py(kg) - 3.0, x + 3.0, py(kg) + 3.0,
                             fill="#AEB6C7", outline="")

        # 趋势线（粗 + 浅色描边）
        tcoords = []
        for d, v in trend:
            tcoords += [px(dt.datetime.combine(d, dt.time(12, 0)).timestamp()), py(v)]
        if len(tcoords) > 3:
            self.create_line(*tcoords, fill="#D9F2E4", width=9, smooth=True)
            self.create_line(*tcoords, fill=theme.SUCCESS, width=4, smooth=True)

        # 悬停区间
        step = (w - self.PAD_L - self.PAD_R) / max(1, n)
        self._days = []
        prev = None
        for d, v in daily_adj:
            if d not in by_day:
                continue
            cx = px(dt.datetime.combine(d, dt.time(12, 0)).timestamp())
            self._days.append({
                "date": d, "value": v,
                "delta": None if prev is None else v - prev,
                "x0": cx - step / 2, "x1": cx + step / 2,
            })
            prev = v

        if 0 <= self._hover < len(self._days):
            self._draw_hover(h, self._days[self._hover], py)

    def _draw_hover(self, h: int, day: dict, py) -> None:
        x0 = max(self.PAD_L, day["x0"])
        x1 = min(self.winfo_width() - self.PAD_R, day["x1"])
        self.create_rectangle(x0, self.PAD_T, x1, h - self.PAD_B,
                              fill="#F5F7FC", outline="#DCE0EA")
        y = py(day["value"])
        cx = (x0 + x1) / 2
        self.create_line(x0, y, x1, y, fill=theme.PRIMARY, width=1, dash=(3, 3))
        self.create_oval(cx - 5, y - 5, cx + 5, y + 5, fill="#FFFFFF",
                         outline=theme.PRIMARY, width=2)

        delta = day["delta"]
        lines = [(day["date"].strftime("%m-%d"), theme.TEXT, True),
                 (f"校正 {day['value']:.1f} kg", theme.SUCCESS, False),
                 (("较前日 —" if delta is None else f"较前日 {delta:+.1f} kg"),
                  theme.MUTED, False)]
        pad, row = 10, 17
        tw = max(len(t) for t, _c, _b in lines) * 8.4 + pad * 2
        th = len(lines) * row + pad
        bx = min(max(cx - tw / 2, self.PAD_L),
                 self.winfo_width() - self.PAD_R - tw)
        by = self.PAD_T + 6
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
        self._cards: list[Card] = []
        self._tile_side = 0
        self._build()

    def _build(self) -> None:
        head = tk.Frame(self, bg=theme.BG)
        head.pack(fill="x", padx=30, pady=(16, 2))
        FlatButton(head, "← 返回", lambda: self.app.show("life"), bg=theme.BG,
                   hover=theme.CARD, font=theme.f(11), padx=12, pady=7
                   ).pack(side="left")
        tk.Label(head, text="肌薄", bg=theme.BG, fg=theme.TEXT,
                 font=theme.f(16, "bold")).pack(side="left", padx=14)
        self.summary = tk.Label(head, text="", bg=theme.BG, fg=theme.MUTED,
                                font=theme.f(10))
        self.summary.pack(side="right")

        body = tk.Frame(self, bg=theme.BG)
        body.pack(fill="both", expand=True, padx=30, pady=(6, 16))
        self.body = body

        weight = Card(body)
        weight.pack(fill="x", pady=(0, 8))
        inner = tk.Frame(weight, bg=theme.CARD)
        inner.pack(fill="x", padx=20, pady=(12, 10))

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

        self.trend_label = tk.Label(inner, text="", bg=theme.CARD,
                                    fg=theme.SUCCESS, font=theme.f(11, "bold"))
        self.trend_label.pack(anchor="e", pady=(4, 0))

        self.chart = WeightChart(inner, self.app, height=CHART_H)
        self.chart.pack(fill="x")

        grid = tk.Frame(body, bg=theme.BG)
        grid.pack(fill="x", pady=(6, 0))
        self.grid_box = grid
        for c in range(3):
            grid.grid_columnconfigure(c, weight=1, uniform="fit")
        grid.grid_rowconfigure(0, weight=0)

        self._tile(grid, 0, "fit_strength", "力量训练", "哑铃动作打卡 · 历史明细",
                   "🏋", theme.BLUE, theme.BLUE_SOFT)
        self._tile(grid, 1, "fit_cardio", "有氧运动", "跑步 · 骑行 · 配速",
                   "🏃", theme.SUCCESS, theme.SUCCESS_SOFT)
        self._tile(grid, 2, "fit_ai", "AI建议", "周报 · 月报 · 半年报",
                   "🤖", theme.PRIMARY, theme.PRIMARY_SOFT)

        body.bind("<Configure>", lambda e: self._square_tiles())
        for delay in (60, 200, 400):
            self.after(delay, self._square_tiles)

    # ------------------------------------------------------------ 入口卡
    def _tile(self, parent, col, key, title, sub, glyph, color, soft) -> None:
        card = Card(parent)
        card.grid(row=0, column=col, sticky="",
                  padx=(0, 8) if col == 0 else (8, 0))
        self._cards.append(card)

        box = tk.Frame(card, bg=theme.CARD)
        box.pack(fill="both", expand=True, padx=10, pady=(14, 14))

        mark = tk.Label(box, text=glyph, bg=theme.CARD, fg=color,
                        font=theme.f(46))
        mark.pack(expand=True)

        btn = FlatButton(box, title, lambda k=key: self.app.show(k),
                         bg=theme.CARD, hover=soft, active_bg=soft,
                         font=theme.f(20, "bold"), fg=color, pady=2,
                         border=theme.CARD)
        btn.pack(fill="x", padx=2)
        btn.set_subtitle(sub)
        btn.configure(highlightbackground=theme.CARD)

        btn.bind_hover_group(card, box, mark)
        for w_ in (card, box, mark):
            w_.bind("<Button-1>", lambda e, k=key: self.app.show(k))

    def _square_tiles(self) -> None:
        """三张入口卡做成正方形：宽高都等于列宽（受可用高度限制）."""
        gw = self.grid_box.winfo_width()
        if gw < 90:
            return
        avail = self.body.winfo_height() - self.chart.winfo_height() - 210
        side = max(150, min((gw - 16) // 3, max(avail, 260)))
        if side == self._tile_side:
            return
        self._tile_side = side
        for card in self._cards:
            card.pack_propagate(False)      # 内容用 pack，关的是这个
            card.grid_propagate(False)
            card.configure(width=side, height=side)

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
