"""肌薄入口页：体重 + 三个入口（力量训练 / 有氧运动 / AI 建议）.

布局参照「生活记录」: 上面是体重卡片（输入 + 30 天趋势图），下面是三张同样式的大卡片。
按钮点了**进入新页面**，不再就地展开。
"""
from __future__ import annotations

import datetime as dt
import tkinter as tk

from .. import fit
from . import theme
from .widgets import Card, FlatButton

LONG_DAYS = 30


class WeightChart(tk.Canvas):
    """30 天体重趋势：日均点 + 7 日移动平均。"""

    PAD_L, PAD_R, PAD_T, PAD_B = 54, 20, 18, 28

    def __init__(self, master, app, **kw):
        super().__init__(master, bg=theme.CARD, highlightthickness=0, **kw)
        self.app = app
        self.bind("<Configure>", lambda e: self.redraw())

    def redraw(self) -> None:
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if w < 80 or h < 60:
            return
        records = self.app.db.fit_weight_all()
        if not records:
            self.create_text(w // 2, h // 2, text="还没有体重记录",
                             fill=theme.MUTED, font=theme.f(11))
            return

        cut = dt.date.today() - dt.timedelta(days=LONG_DAYS)
        raw = [(at, kg) for at, kg in records
               if dt.datetime.fromisoformat(at).date() >= cut]
        if len(raw) < 2:
            raw = records[-30:]
        daily = fit.daily_mean(raw)
        if len(daily) < 2:
            self.create_text(w // 2, h // 2, text="记录还太少，画不出趋势",
                             fill=theme.MUTED, font=theme.f(11))
            return

        xs = [(d - daily[0][0]).days for d, _v in daily]
        ys = [v for _d, v in daily]
        trend = fit.moving_average(daily, 7)

        lo = min(min(ys), min(v for _d, v in trend))
        hi = max(max(ys), max(v for _d, v in trend))
        pad = max(0.4, (hi - lo) * 0.3)
        lo, hi = lo - pad, hi + pad
        x_max = max(xs) or 1

        def px(x):
            return self.PAD_L + (w - self.PAD_L - self.PAD_R) * (x / x_max)

        def py(y):
            return self.PAD_T + (h - self.PAD_T - self.PAD_B) * (1 - (y - lo) / (hi - lo))

        for i in range(5):
            yv = lo + (hi - lo) * i / 4
            yy = py(yv)
            self.create_line(self.PAD_L, yy, w - self.PAD_R, yy, fill=theme.BORDER)
            self.create_text(self.PAD_L - 8, yy, text=f"{yv:.1f}", anchor="e",
                             fill=theme.MUTED, font=theme.f(9))

        step = max(1, len(daily) // 6)
        for i in range(0, len(daily), step):
            d, _v = daily[i]
            self.create_text(px((d - daily[0][0]).days), h - self.PAD_B + 14,
                             text=d.strftime("%m-%d"), fill=theme.MUTED,
                             font=theme.f(9))

        coords = []
        for x, y in zip(xs, ys):
            coords += [px(x), py(y)]
            self.create_oval(px(x) - 2, py(y) - 2, px(x) + 2, py(y) + 2,
                             fill=theme.BORDER_STRONG, outline="")
        self.create_line(*coords, fill=theme.BORDER_STRONG, width=1)

        tcoords = []
        for d, v in trend:
            tcoords += [px((d - daily[0][0]).days), py(v)]
        if len(tcoords) > 3:
            self.create_line(*tcoords, fill=theme.SUCCESS, width=3, smooth=True)

        self.create_text(self.PAD_L + 4, 10, anchor="w",
                         text="最近 30 天 · 7 日移动平均",
                         fill=theme.MUTED, font=theme.f(9))
        last = ys[-1]
        self.create_text(w - self.PAD_R - 4, py(last) - 13,
                         text=f"{last:.1f}kg", anchor="e", fill=theme.SUCCESS,
                         font=theme.f(11, "bold"))
        slope = fit.trend_slope(daily)
        self.create_text(w - self.PAD_R - 4, py(last) + 3,
                         text=f"{slope:+.2f} kg/周", anchor="e", fill=theme.MUTED,
                         font=theme.f(9))


class FitnessFrame(tk.Frame):
    def __init__(self, master, app):
        super().__init__(master, bg=theme.BG)
        self.grid(row=0, column=0, sticky="nsew")
        self.app = app
        self._build()

    def _build(self) -> None:
        head = tk.Frame(self, bg=theme.BG)
        head.pack(fill="x", padx=30, pady=(22, 6))
        FlatButton(head, "← 返回", lambda: self.app.show("life"), bg=theme.BG,
                   hover=theme.CARD, font=theme.f(11), padx=12, pady=7
                   ).pack(side="left")
        tk.Label(head, text="肌薄", bg=theme.BG, fg=theme.TEXT,
                 font=theme.f(16, "bold")).pack(side="left", padx=14)
        self.summary = tk.Label(head, text="", bg=theme.BG, fg=theme.MUTED,
                                font=theme.f(10))
        self.summary.pack(side="right")

        body = tk.Frame(self, bg=theme.BG)
        body.pack(fill="both", expand=True, padx=30, pady=(12, 22))

        weight = Card(body)
        weight.pack(fill="x", pady=(0, 12))
        inner = tk.Frame(weight, bg=theme.CARD)
        inner.pack(fill="x", padx=22, pady=(16, 12))

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
        self.hint = tk.Label(top, text="", bg=theme.CARD, fg=theme.MUTED,
                             font=theme.f(10))
        self.hint.pack(side="left")
        self.recent = tk.Label(top, text="", bg=theme.CARD, fg=theme.MUTED,
                               font=theme.f(9))
        self.recent.pack(side="right")

        self.chart = WeightChart(inner, self.app, height=215)
        self.chart.pack(fill="x", pady=(10, 0))

        grid = tk.Frame(body, bg=theme.BG)
        grid.pack(fill="both", expand=True)
        for c in range(3):
            grid.grid_columnconfigure(c, weight=1, uniform="fit")
        grid.grid_rowconfigure(0, weight=1)

        self._tile(grid, 0, "fit_strength", "力量训练", "哑铃动作打卡 · 历史明细", "🏋",
                   theme.BLUE, theme.BLUE_SOFT)
        self._tile(grid, 1, "fit_cardio", "有氧运动", "跑步 · 骑行 · 配速", "🏃",
                   theme.SUCCESS, theme.SUCCESS_SOFT)
        self._tile(grid, 2, "fit_ai", "AI建议", "周报 · 月报 · 半年报", "🤖",
                   theme.PRIMARY, theme.PRIMARY_SOFT)

    def _tile(self, parent, col, key, title, sub, glyph, color, soft) -> None:
        card = Card(parent)
        card.grid(row=0, column=col, sticky="nsew",
                  padx=(0, 8) if col == 0 else (8, 0))
        box = tk.Frame(card, bg=theme.CARD)
        box.pack(fill="both", expand=True)
        mark = tk.Label(box, text=glyph, bg=theme.CARD, fg=color,
                        font=theme.f(42, "bold"))
        mark.pack(expand=True)
        btn = FlatButton(box, title, lambda k=key: self.app.show(k),
                         bg=theme.CARD, hover=soft, active_bg=soft,
                         font=theme.f(21, "bold"), fg=color, pady=6,
                         border=theme.CARD)
        btn.pack(fill="x", padx=2)
        btn.set_subtitle(sub)
        btn.configure(highlightbackground=theme.CARD)
        spacer = tk.Frame(box, bg=theme.CARD)
        spacer.pack(expand=True, fill="both")
        btn.bind_hover_group(card, box, mark, spacer)
        for w in (card, box, mark, spacer):
            w.bind("<Button-1>", lambda e, k=key: self.app.show(k))

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

    def _refresh(self) -> None:
        self.chart.redraw()
        rows = self.app.db.fit_weight_all()[-4:][::-1]
        if rows:
            self.recent.configure(
                text="　".join(
                    f"{at[5:16].replace('T', ' ')} {kg:.1f}" for at, kg in rows))
        s = self.app.db.fit_summary()
        parts = []
        if s["weight"]:
            parts.append(f"{s['weight']:.1f}kg · BMI {fit.bmi(s['weight'])}")
        if s["sets"]:
            parts.append(f"今日 {s['sets']} 组")
        self.summary.configure(text="　·　".join(parts) if parts else "还没有数据")

    def on_show(self, **_):
        self._refresh()
