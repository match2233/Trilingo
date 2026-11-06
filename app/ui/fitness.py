"""肌薄首页：体重 + 三个入口.

体重图的三层：
  * **散点** —— 每一条记录（含时刻），看得见一天之内的起伏；
  * **灰线** —— 每日均值，保留了原有口径；
  * **绿线** —— 时段校正后的 7 日滚动中位数（见 app/fit_trend.py），
    单看趋势用这条：它把"早上量 / 晚上量"的固定偏差和冬衣这种缓慢偏移压掉。

鼠标悬停显示最近一个点的时刻、原始体重和校正后体重。
"""
from __future__ import annotations

import datetime as dt
import tkinter as tk

from .. import config as C
from .. import fit, fit_trend
from . import theme
from .fit_dialogs import WeightHistory
from .widgets import Card, FlatButton

# 30 天窗口
WINDOW_DAYS = 30


class WeightChart(tk.Canvas):
    """体重散点 + 日均线 + 稳健趋势线，带悬停提示。"""

    PAD_L, PAD_R, PAD_T, PAD_B = 56, 22, 30, 30

    def __init__(self, master, app, on_detail=None, **kw):
        super().__init__(master, bg=theme.CARD, highlightthickness=0, **kw)
        self.app = app
        self._pts: list[tuple[float, float, str, float, float]] = []  # x,y,ts,kg,adj
        self._hover = -1
        self.bind("<Configure>", lambda e: self.redraw())
        self.bind("<Motion>", self._on_motion)
        self.bind("<Leave>", self._on_leave)

    # ------------------------------------------------------------ 交互
    def _on_motion(self, event) -> None:
        if not self._pts:
            return
        idx, best = -1, 14.0
        for i, (x, _y, *_rest) in enumerate(self._pts):
            d = abs(x - event.x)
            if d < best:
                idx, best = i, d
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
        if w < 120 or h < 100:
            return

        records = self.app.db.fit_weight_all()
        if not records:
            self.create_text(w // 2, h // 2, text="还没有体重记录",
                             fill=theme.MUTED, font=theme.f(11))
            self._pts = []
            return

        cut = dt.date.today() - dt.timedelta(days=WINDOW_DAYS)
        raw = [(at, kg) for at, kg in records
               if dt.datetime.fromisoformat(at).date() >= cut]
        if len(raw) < 2:
            raw = records[-40:]
        self._raw = raw

        offsets = fit_trend.hour_offsets(raw)
        items = fit_trend.corrected(raw, offsets)
        daily_raw = fit_trend.daily_points(items, use_corrected=False)   # 日均（灰）
        daily_adj = fit_trend.daily_points(items, use_corrected=True)    # 校正后
        trend = fit_trend.rolling_median(daily_adj, 7)                    # 绿线

        xs = [ts.timestamp() for ts, _kg, _adj in items]
        ys_all = [kg for _ts, kg, _adj in items] + [v for _d, v in trend]
        if len(ys_all) < 2:
            self.create_text(w // 2, h // 2, text="记录还太少，画不出趋势",
                             fill=theme.MUTED, font=theme.f(11))
            self._pts = []
            return

        x0, x1 = min(xs), max(xs)
        if x1 - x0 < 3600:
            x0, x1 = x0 - 1800, x1 + 1800
        lo, hi = min(ys_all), max(ys_all)
        pad = max(0.35, (hi - lo) * 0.22)
        lo, hi = lo - pad, hi + pad

        def px(t: float) -> float:
            return self.PAD_L + (w - self.PAD_L - self.PAD_R) * ((t - x0) / (x1 - x0))

        def py(v: float) -> float:
            return self.PAD_T + (h - self.PAD_T - self.PAD_B) * (1 - (v - lo) / (hi - lo))

        # 网格 + 纵轴
        for i in range(5):
            val = lo + (hi - lo) * i / 4
            y = py(val)
            self.create_line(self.PAD_L, y, w - self.PAD_R, y,
                             fill=theme.BORDER, dash=(2, 4))
            self.create_text(self.PAD_L - 9, y, text=f"{val:.1f}", anchor="e",
                             fill=theme.MUTED, font=theme.f(9))

        # 横轴日期（每天一个刻度，最多 8 个）
        days = sorted({ts.date() for ts, _k, _a in items})
        step = max(1, len(days) // 8)
        for d in days[::step]:
            t = dt.datetime.combine(d, dt.time(12, 0)).timestamp()
            if x0 <= t <= x1:
                self.create_text(px(t), h - self.PAD_B + 15, text=d.strftime("%m-%d"),
                                 fill=theme.MUTED, font=theme.f(9))

        # 日均灰线
        mean_by_day = {d: v for d, v in daily_raw}
        line = [(px(dt.datetime.combine(d, dt.time(12, 0)).timestamp()), py(v))
                for d, v in daily_raw]
        if len(line) > 1:
            self.create_line(*[c for p in line for c in p],
                             fill="#C9CDD8", width=1)

        # 散点（每条记录）
        for ts, kg, adj in items:
            self.create_oval(px(ts.timestamp()) - 2.4, py(kg) - 2.4,
                             px(ts.timestamp()) + 2.4, py(kg) + 2.4,
                             fill="#AAB2C4", outline="")

        # 趋势绿线
        tcoords = []
        for d, v in trend:
            tcoords += [px(dt.datetime.combine(d, dt.time(12, 0)).timestamp()), py(v)]
        if len(tcoords) > 3:
            self.create_line(*tcoords, fill=theme.SUCCESS, width=3, smooth=True)

        # 图例
        self.create_text(self.PAD_L + 2, 12, anchor="w",
                         text="● 每次记录    ─ 每日均值    ━ 校正后趋势",
                         fill=theme.MUTED, font=theme.f(9))

        # 右上角：最新趋势值 + 斜率
        if trend:
            last = trend[-1][1]
            slope = fit_trend.theil_sen(daily_adj)
            self.create_text(w - self.PAD_R - 4, 16, anchor="e",
                             text=f"{last:.1f}kg", fill=theme.SUCCESS,
                             font=theme.f(13, "bold"))
            self.create_text(w - self.PAD_R - 4, 34, anchor="e",
                             text=f"{slope:+.2f} kg/周", fill=theme.MUTED,
                             font=theme.f(9))

        self._pts = [(px(ts.timestamp()), py(kg), ts.strftime("%m-%d %H:%M"),
                      kg, adj) for ts, kg, adj in items]

        if 0 <= self._hover < len(self._pts):
            self._draw_tip(w, h)

    def _draw_tip(self, w: int, h: int) -> None:
        x, y, stamp, kg, adj = self._pts[self._hover]
        delta = adj - kg
        lines = [(stamp, theme.TEXT, True),
                 (f"体重 {kg:.1f} kg", theme.TEXT, False)]
        if abs(delta) >= 0.05:
            lines.append((f"校正 {adj:.1f} kg（{delta:+.1f}）", theme.MUTED, False))
        pad, row = 9, 16
        tw = max(len(t) for t, _c, _b in lines) * 8.2 + pad * 2
        th = len(lines) * row + pad
        bx = min(max(x - tw / 2, self.PAD_L), w - self.PAD_R - tw)
        by = y - th - 14
        if by < self.PAD_T:
            by = y + 14

        self.create_line(x, self.PAD_T, x, h - self.PAD_B,
                         fill=theme.PRIMARY, dash=(3, 3))
        self.create_oval(x - 4, y - 4, x + 4, y + 4,
                         fill=theme.PRIMARY, outline="")
        self.create_rectangle(bx, by, bx + tw, by + th, fill="#FFFFFF",
                              outline=theme.BORDER)
        for i, (text, color, bold) in enumerate(lines):
            self.create_text(bx + pad, by + pad / 2 + i * row + 6, anchor="w",
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
                   font=theme.f(11, "bold"), padx=20, pady=7
                   ).pack(side="left", padx=14)
        FlatButton(top, "详细数据", self._open_detail, bg=theme.CARD,
                   font=theme.f(11), padx=16, pady=7).pack(side="left")
        self.hint = tk.Label(top, text="", bg=theme.CARD, fg=theme.MUTED,
                             font=theme.f(10))
        self.hint.pack(side="left", padx=10)
        self.recent = tk.Label(top, text="", bg=theme.CARD, fg=theme.MUTED,
                               font=theme.f(9))
        self.recent.pack(side="right")

        # 高度是原来（215）的两倍
        self.chart = WeightChart(inner, self.app, height=430)
        self.chart.pack(fill="x", pady=(8, 0))

        grid = tk.Frame(body, bg=theme.BG)
        grid.pack(fill="both", expand=True, pady=(4, 0))
        for c in range(3):
            grid.grid_columnconfigure(c, weight=1, uniform="fit")
        grid.grid_rowconfigure(0, weight=1)

        self._tile(grid, 0, "fit_strength", "力量训练", "哑铃动作打卡 · 历史明细",
                   "dumbbell", theme.BLUE, theme.BLUE_SOFT)
        self._tile(grid, 1, "fit_cardio", "有氧运动", "跑步 · 骑行 · 配速",
                   "run", theme.SUCCESS, theme.SUCCESS_SOFT)
        self._tile(grid, 2, "fit_ai", "AI建议", "周报 · 月报 · 半年报",
                   "ai", theme.PRIMARY, theme.PRIMARY_SOFT)

    # ------------------------------------------------------------ 入口卡
    def _tile(self, parent, col, key, title, sub, icon_kind, color, soft) -> None:
        card = Card(parent)
        card.grid(row=0, column=col, sticky="nsew",
                  padx=(0, 8) if col == 0 else (8, 0))
        box = tk.Frame(card, bg=theme.CARD)
        box.pack(fill="both", expand=True)

        cv = tk.Canvas(box, width=76, height=76, bg=theme.CARD,
                       highlightthickness=0)
        cv.pack(pady=(10, 2))
        _draw_icon(cv, icon_kind, color, soft)

        btn = FlatButton(box, title, lambda k=key: self.app.show(k),
                         bg=theme.CARD, hover=soft, active_bg=soft,
                         font=theme.f(19, "bold"), fg=color, pady=4,
                         border=theme.CARD)
        btn.pack(fill="x", padx=2)
        btn.set_subtitle(sub)
        btn.configure(highlightbackground=theme.CARD)

        btn.bind_hover_group(card, box, cv)
        for w_ in (card, box, cv):
            w_.bind("<Button-1>", lambda e, k=key: self.app.show(k))

    # ------------------------------------------------------------ 数据
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
        rows = self.app.db.fit_weight_all()[-3:][::-1]
        self.recent.configure(
            text="　".join(f"{at[5:16].replace('T', ' ')} {kg:.1f}"
                           for at, kg in rows) if rows else "")
        s = self.app.db.fit_summary()
        parts = []
        if s["weight"]:
            b = fit.bmi(s["weight"])
            parts.append(f"{s['weight']:.1f}kg" + (f" · BMI {b}" if b else ""))
        if s["sets"]:
            parts.append(f"今日 {s['sets']} 组")
        self.summary.configure(text="　·　".join(parts) if parts else "还没有数据")

    def on_show(self, **_):
        self._refresh()


# ---------------------------------------------------------------- 图标
def _draw_icon(cv: tk.Canvas, kind: str, color: str, soft: str) -> None:
    """在 76x76 的画布上手绘一个简洁图标（比自己拼 emoji 好看且一致）。"""
    cv.create_oval(4, 4, 72, 72, fill=soft, outline="")
    cx, cy = 38, 38
    if kind == "dumbbell":
        cv.create_rectangle(cx - 22, cy - 4, cx + 22, cy + 4, fill=color, outline="")
        for dx in (-22, 16):
            cv.create_rectangle(cx + dx, cy - 13, cx + dx + 6, cy + 13,
                                fill=color, outline="")
        for dx in (-28, 22):
            cv.create_rectangle(cx + dx, cy - 8, cx + dx + 6, cy + 8,
                                fill=color, outline="")
    elif kind == "run":
        cv.create_oval(cx - 4, cy - 22, cx + 4, cy - 14, fill=color, outline="")
        cv.create_line(cx + 1, cy - 12, cx - 3, cy + 3, width=5,
                       fill=color, capstyle="round")
        cv.create_line(cx - 3, cy + 3, cx - 14, cy + 20, width=5,
                       fill=color, capstyle="round")
        cv.create_line(cx - 3, cy + 3, cx + 12, cy + 18, width=5,
                       fill=color, capstyle="round")
        cv.create_line(cx + 1, cy - 10, cx + 15, cy - 2, width=4,
                       fill=color, capstyle="round")
        cv.create_line(cx + 1, cy - 9, cx - 12, cy - 2, width=4,
                       fill=color, capstyle="round")
    elif kind == "ai":
        cv.create_rectangle(cx - 17, cy - 12, cx + 17, cy + 16, fill="",
                            outline=color, width=3)
        cv.create_line(cx, cy - 20, cx, cy - 12, width=3, fill=color)
        cv.create_oval(cx - 3, cy - 24, cx + 3, cy - 18, fill=color, outline="")
        for dx in (-7, 7):
            cv.create_oval(cx + dx - 2, cy - 3, cx + dx + 2, cy + 1,
                           fill=color, outline="")
        cv.create_line(cx - 6, cy + 8, cx + 6, cy + 8, width=3, fill=color)
