"""肌薄：每日身体训练记录.

页面结构（从上到下）：
  1. 体重 —— 记录（带精确时刻）、最近记录、短期/长期折线图
  2. 【力量训练】—— 哑铃重量（长期保存）+ 14 个动作按钮（点一次 = 一组）
  3. 【有氧运动】—— 跑步（距离/时间/配速自动/心率）、骑行（距离/时间）
  4. 【AI建议】—— 周报 / 月报 / 半年报，点了才调 AI

统计口径见 app/fit.py 顶部注释。
"""
from __future__ import annotations

import datetime as dt
import pathlib
import threading
import tkinter as tk
from tkinter import messagebox

from .. import fit, llm
from .. import config as C
from . import theme
from .widgets import Card, FlatButton, ScrollFrame

ASSETS = pathlib.Path(__file__).resolve().parent.parent.parent / "assets" / "fitness"

PERIODS = {"week": ("周报", 7), "month": ("月报", 30), "half": ("半年报", 182)}


class WeightChart(tk.Canvas):
    """体重折线图。

    短期：把每条记录都画出来（横轴是"第几天+一天中的时刻"），看的是波动；
    长期：同一天取平均后用 7 日移动平均画趋势，原始日均点用淡点垫底。
    """

    PAD_L, PAD_R, PAD_T, PAD_B = 52, 18, 16, 26

    def __init__(self, master, app, **kw):
        super().__init__(master, bg=theme.CARD, highlightthickness=0, **kw)
        self.app = app
        self.mode = "short"
        self.bind("<Configure>", lambda e: self.redraw())

    # ------------------------------------------------------------------
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

        today = dt.date.today()
        if self.mode == "short":
            cut = today - dt.timedelta(days=14)
            pts = [(dt.datetime.fromisoformat(at), kg) for at, kg in records
                   if dt.datetime.fromisoformat(at).date() >= cut]
            if len(pts) < 2:
                cut = today - dt.timedelta(days=60)
                pts = [(dt.datetime.fromisoformat(at), kg) for at, kg in records
                       if dt.datetime.fromisoformat(at).date() >= cut]
            xs = [(p[0] - pts[0][0]).total_seconds() / 86400 for p in pts]
            ys = [p[1] for p in pts]
            labels = [(x, p[0].strftime("%m-%d")) for x, p in zip(xs, pts)]
            trend = None
            title = "最近体重（每条记录都画出来）"
        else:
            cut = today - dt.timedelta(days=182)
            raw = [(at, kg) for at, kg in records
                   if dt.datetime.fromisoformat(at).date() >= cut]
            daily = fit.daily_mean(raw)
            if len(daily) < 2:
                daily = fit.daily_mean(records)
            xs = [(d - daily[0][0]).days for d, _v in daily]
            ys = [v for _d, v in daily]
            labels = [(x, d.strftime("%m-%d")) for x, (d, _v) in zip(xs, daily)]
            trend = fit.moving_average(daily)
            title = "长期趋势（日均 + 7 日移动平均）"

        if not xs:
            self.create_text(w // 2, h // 2, text="记录太少，画不出图",
                             fill=theme.MUTED, font=theme.f(11))
            return

        lo, hi = min(ys), max(ys)
        if trend:
            lo = min(lo, min(v for _d, v in trend))
            hi = max(hi, max(v for _d, v in trend))
        pad = max(0.4, (hi - lo) * 0.25)
        lo, hi = lo - pad, hi + pad
        x_max = max(xs) or 1

        def px(x: float) -> float:
            return self.PAD_L + (w - self.PAD_L - self.PAD_R) * (x / x_max)

        def py(y: float) -> float:
            return self.PAD_T + (h - self.PAD_T - self.PAD_B) * (1 - (y - lo) / (hi - lo))

        # 网格 + 纵轴刻度
        for i in range(5):
            yv = lo + (hi - lo) * i / 4
            yy = py(yv)
            self.create_line(self.PAD_L, yy, w - self.PAD_R, yy,
                             fill=theme.BORDER)
            self.create_text(self.PAD_L - 8, yy, text=f"{yv:.1f}",
                             anchor="e", fill=theme.MUTED, font=theme.f(9))

        # 横轴日期（最多 6 个刻度）
        step = max(1, len(labels) // 6)
        for x, lb in labels[::step]:
            self.create_text(px(x), h - self.PAD_B + 14, text=lb,
                             fill=theme.MUTED, font=theme.f(9))

        self.create_text(self.PAD_L, 8, text=title, anchor="w",
                         fill=theme.MUTED, font=theme.f(9))

        # 原始点 + 折线
        for x, y in zip(xs, ys):
            r = 2 if trend else 3
            self.create_oval(px(x) - r, py(y) - r, px(x) + r, py(y) + r,
                             fill=theme.PRIMARY if not trend else theme.BORDER_STRONG,
                             outline="")
        if len(xs) > 1:
            coords = []
            for x, y in zip(xs, ys):
                coords += [px(x), py(y)]
            self.create_line(*coords, fill=theme.PRIMARY if not trend else theme.BORDER_STRONG,
                             width=2 if not trend else 1, smooth=False)

        # 趋势线
        if trend:
            tcoords = []
            for (d, v) in trend:
                x = (d - daily[0][0]).days
                tcoords += [px(x), py(v)]
            if len(tcoords) > 3:
                self.create_line(*tcoords, fill=theme.SUCCESS, width=3,
                                 smooth=True)
            last = trend[-1][1]
            self.create_text(w - self.PAD_R - 4, py(last) - 10,
                             text=f"{last:.1f}kg", anchor="e",
                             fill=theme.SUCCESS, font=theme.f(10, "bold"))

        # 最近一次数值
        last_kg = ys[-1]
        self.create_text(w - self.PAD_R - 4, py(last_kg) + 12,
                         text=f"最近 {last_kg:.1f}kg", anchor="e",
                         fill=theme.PRIMARY, font=theme.f(10, "bold"))


class FitnessFrame(tk.Frame):
    def __init__(self, master, app):
        super().__init__(master, bg=theme.BG)
        self.grid(row=0, column=0, sticky="nsew")
        self.app = app
        self._imgs: dict[str, object] = {}
        self._strength_open = False
        self._cardio_open = False
        self._ai_open = False
        self._build()

    # ------------------------------------------------------------ 构建
    def _build(self) -> None:
        head = tk.Frame(self, bg=theme.BG)
        head.pack(fill="x", padx=26, pady=(16, 6))
        FlatButton(head, "← 返回", lambda: self.app.show("life"), bg=theme.BG,
                   hover=theme.CARD, font=theme.f(11), padx=12, pady=7
                   ).pack(side="left")
        tk.Label(head, text="肌薄", bg=theme.BG, fg=theme.TEXT,
                 font=theme.f(18, "bold")).pack(side="left", padx=14)
        self.summary = tk.Label(head, text="", bg=theme.BG, fg=theme.MUTED,
                                font=theme.f(10))
        self.summary.pack(side="right")

        self.scroll = ScrollFrame(self)
        self.scroll.pack(fill="both", expand=True, padx=22, pady=(4, 14))
        body = self.scroll.body

        self._build_weight(body)
        self._build_strength(body)
        self._build_cardio(body)
        self._build_ai(body)

    # ------------------------------------------------------------ 体重
    def _build_weight(self, parent) -> None:
        card = Card(parent)
        card.pack(fill="x", pady=(0, 10))
        inner = tk.Frame(card, bg=theme.CARD)
        inner.pack(fill="x", padx=16, pady=12)

        top = tk.Frame(inner, bg=theme.CARD)
        top.pack(fill="x")
        tk.Label(top, text="体重", bg=theme.CARD, fg=theme.TEXT,
                 font=theme.f(15, "bold")).pack(side="left")
        self.weight_var = tk.StringVar()
        ent = tk.Entry(top, textvariable=self.weight_var, width=7,
                       font=theme.f(12), justify="right", bd=0,
                       bg=theme.SUNK, fg=theme.TEXT, relief="flat",
                       highlightthickness=1, highlightbackground=theme.BORDER)
        ent.pack(side="left", padx=(14, 4), ipady=3, pady=1)
        ent.bind("<Return>", lambda e: self._add_weight())
        tk.Label(top, text="kg", bg=theme.CARD, fg=theme.MUTED,
                 font=theme.f(11)).pack(side="left")
        FlatButton(top, "记录", self._add_weight, bg=theme.PRIMARY, fg="#FFFFFF",
                   hover=theme.PRIMARY_DARK, active_bg=theme.PRIMARY_DARK,
                   font=theme.f(11, "bold"), padx=18, pady=6).pack(side="left", padx=12)
        self.weight_hint = tk.Label(top, text="", bg=theme.CARD, fg=theme.MUTED,
                                    font=theme.f(10))
        self.weight_hint.pack(side="left")

        # 短期 / 长期
        seg = tk.Frame(inner, bg=theme.CARD)
        seg.pack(fill="x", pady=(10, 4))
        tk.Label(seg, text="曲线", bg=theme.CARD, fg=theme.MUTED,
                 font=theme.f(10)).pack(side="left")
        self.mode_btns: dict[str, FlatButton] = {}
        for key, label in (("short", "短期（波动）"), ("long", "长期（趋势）")):
            b = FlatButton(seg, label, lambda k=key: self._set_mode(k),
                           bg=theme.SUNK, fg=theme.MUTED, font=theme.f(10),
                           padx=12, pady=4, border=theme.BORDER)
            b.pack(side="left", padx=(8, 4))
            self.mode_btns[key] = b

        self.chart = WeightChart(inner, self.app, height=190)
        self.chart.pack(fill="x", pady=(6, 4))

        self.weight_list = tk.Label(inner, text="", bg=theme.CARD,
                                    fg=theme.MUTED, font=theme.f(9),
                                    justify="left", anchor="w")
        self.weight_list.pack(fill="x")

    def _set_mode(self, mode: str) -> None:
        self.chart.mode = mode
        for k, b in self.mode_btns.items():
            on = k == mode
            b.set_palette(theme.PRIMARY_SOFT if on else theme.SUNK,
                          fg=theme.PRIMARY if on else theme.MUTED)
        self.chart.redraw()

    def _add_weight(self) -> None:
        raw = self.weight_var.get().strip()
        try:
            kg = float(raw)
        except ValueError:
            self.weight_hint.configure(text="请输入数字，例如 65.4", fg=theme.ERROR)
            return
        if not 25 <= kg <= 200:
            self.weight_hint.configure(text="数值看着不像体重", fg=theme.ERROR)
            return
        self.app.db.fit_weight_add(kg)
        self.weight_var.set("")
        now = dt.datetime.now().strftime("%H:%M")
        self.weight_hint.configure(text=f"已记录 {kg}kg（{now}）", fg=theme.SUCCESS)
        self.chart.redraw()
        self._refresh_weight_list()
        self._refresh_summary()

    def _refresh_weight_list(self) -> None:
        rows = self.app.db.fit_weight_all()[-5:][::-1]
        if not rows:
            self.weight_list.configure(text="")
            return
        parts = [f"{at[5:16].replace('T', ' ')}  {kg:.1f}kg" for at, kg in rows]
        self.weight_list.configure(text="最近：" + "　|　".join(parts))

    # ------------------------------------------------------------ 力量训练
    def _build_strength(self, parent) -> None:
        self.strength_btn = FlatButton(
            parent, "力量训练  ▾", self._toggle_strength, bg=theme.BLUE,
            fg="#FFFFFF", hover=theme.BLUE_DARK, active_bg=theme.BLUE_DARK,
            font=theme.f(14, "bold"), padx=20, pady=12, anchor="w")
        self.strength_btn.pack(fill="x", pady=(4, 8))

        self.strength_panel = tk.Frame(parent, bg=theme.BG)
        card = Card(self.strength_panel)
        card.pack(fill="x")
        inner = tk.Frame(card, bg=theme.CARD)
        inner.pack(fill="x", padx=14, pady=12)

        row = tk.Frame(inner, bg=theme.CARD)
        row.pack(fill="x", pady=(0, 8))
        tk.Label(row, text="当前哑铃重量", bg=theme.CARD, fg=theme.TEXT,
                 font=theme.f(12, "bold")).pack(side="left")
        self.dumbbell_var = tk.StringVar(value=self.app.db.fit_setting("dumbbell", "10"))
        ent = tk.Entry(row, textvariable=self.dumbbell_var, width=6,
                       font=theme.f(12), justify="right", bg=theme.SUNK,
                       fg=theme.TEXT, relief="flat", highlightthickness=1,
                       highlightbackground=theme.BORDER)
        ent.pack(side="left", padx=(10, 4), ipady=3)
        ent.bind("<FocusOut>", lambda e: self._save_dumbbell())
        ent.bind("<Return>", lambda e: self._save_dumbbell())
        tk.Label(row, text="kg（单手，改一次长期有效）", bg=theme.CARD,
                 fg=theme.MUTED, font=theme.f(10)).pack(side="left")
        self.today_total = tk.Label(row, text="", bg=theme.CARD, fg=theme.MUTED,
                                    font=theme.f(10))
        self.today_total.pack(side="right")

        self.moves_box = tk.Frame(inner, bg=theme.CARD)
        self.moves_box.pack(fill="x")

    def _save_dumbbell(self) -> None:
        v = self.dumbbell_var.get().strip()
        try:
            float(v)
        except ValueError:
            return
        self.app.db.fit_set_setting("dumbbell", v)

    def _toggle_strength(self) -> None:
        self._strength_open = not self._strength_open
        if self._strength_open:
            self.strength_btn.set_text("力量训练  ▴")
            self.strength_panel.pack(fill="x", pady=(0, 10),
                                     after=self.strength_btn)
            self._render_moves()
        else:
            self.strength_btn.set_text("力量训练  ▾")
            self.strength_panel.pack_forget()

    def _render_moves(self) -> None:
        for w in self.moves_box.winfo_children():
            w.destroy()
        today = dt.date.today().isoformat()
        done = self.app.db.fit_sets_day(today)
        # 常用的排前面：先按近 30 天使用次数，再按预设顺序
        since = (dt.date.today() - dt.timedelta(days=30)).isoformat()
        usage = self.app.db.fit_sets_since(since)
        moves = sorted(fit.MOVES,
                       key=lambda m: (-usage.get(m["slug"], 0), fit.MOVES.index(m)))

        grid = tk.Frame(self.moves_box, bg=theme.CARD)
        grid.pack(fill="x")
        per_row = 4
        for i, mv in enumerate(moves):
            self._move_card(grid, mv, i, per_row, done.get(mv["slug"], 0))
        self.today_total.configure(
            text=f"今日 {sum(done.values())} 组 / {len(done)} 个动作")

    def _move_card(self, parent, mv: dict, idx: int, per_row: int, done: int) -> None:
        cell = tk.Frame(parent, bg=theme.SUNK, highlightthickness=1,
                        highlightbackground=theme.BORDER)
        cell.grid(row=idx // per_row, column=idx % per_row,
                  padx=5, pady=5, sticky="nsew")
        parent.grid_columnconfigure(idx % per_row, weight=1, uniform="mv")

        img = self._load_image(mv["slug"], 150, 92)
        if img is not None:
            lab = tk.Label(cell, image=img, bg=theme.SUNK, bd=0)
            lab.image = img
            lab.pack(fill="x", pady=(6, 2))
        name = tk.Label(cell, text=mv["cn"], bg=theme.SUNK, fg=theme.TEXT,
                        font=theme.f(11, "bold"))
        name.pack()
        tk.Label(cell, text=mv["en"], bg=theme.SUNK, fg=theme.MUTED,
                 font=theme.f(8)).pack()

        reps_row = tk.Frame(cell, bg=theme.SUNK)
        reps_row.pack(pady=(4, 0))
        tk.Label(reps_row, text="每组", bg=theme.SUNK, fg=theme.MUTED,
                 font=theme.f(9)).pack(side="left")
        var = tk.StringVar(value=self.app.db.fit_setting(f"reps:{mv['slug']}",
                                                        str(mv["reps"])))
        ent = tk.Entry(reps_row, textvariable=var, width=3, justify="right",
                       font=theme.f(10), bg=theme.CARD, fg=theme.TEXT,
                       relief="flat", highlightthickness=1,
                       highlightbackground=theme.BORDER)
        ent.pack(side="left", padx=3, ipady=1)
        ent.bind("<FocusOut>", lambda e, s=mv["slug"], v=var:
                 self.app.db.fit_set_setting(f"reps:{s}", v.get().strip()))
        tk.Label(reps_row, text="次", bg=theme.SUNK, fg=theme.MUTED,
                 font=theme.f(9)).pack(side="left")

        cnt = tk.Label(cell, text=f"今天 {done} 组" if done else "今天还没做",
                       bg=theme.SUNK, fg=theme.SUCCESS if done else theme.MUTED,
                       font=theme.f(10, "bold"))
        cnt.pack(pady=(2, 0))

        # 点按钮 = 加一组
        btn = FlatButton(cell, "+1 组", lambda m=mv["slug"]: self._add_set(m, cnt),
                         bg=theme.BLUE_SOFT, fg=theme.BLUE, font=theme.f(11, "bold"),
                         padx=10, pady=5, border=theme.BLUE_SOFT)
        btn.pack(fill="x", padx=8, pady=(4, 8))

    def _load_image(self, slug: str, max_w: int, max_h: int):
        if slug in self._imgs:
            return self._imgs[slug]
        path = ASSETS / f"{slug}.png"
        if not path.exists():
            return None
        try:
            from PIL import Image, ImageTk
            im = Image.open(path)
            im.thumbnail((max_w, max_h), Image.LANCZOS)
            img = ImageTk.PhotoImage(im)
            self._imgs[slug] = img
            return img
        except Exception:      # noqa: BLE001
            return None

    def _add_set(self, slug: str, label: tk.Label) -> None:
        n = self.app.db.fit_log_add(slug)
        label.configure(text=f"今天 {n} 组", fg=theme.SUCCESS)
        self.moves_box.after(1, self._refresh_today)

    def _refresh_today(self) -> None:
        today = dt.date.today().isoformat()
        done = self.app.db.fit_sets_day(today)
        self.today_total.configure(
            text=f"今日 {sum(done.values())} 组 / {len(done)} 个动作")
        self._refresh_summary()

    # ------------------------------------------------------------ 有氧
    def _build_cardio(self, parent) -> None:
        self.cardio_btn = FlatButton(
            parent, "有氧运动  ▾", self._toggle_cardio, bg=theme.SUCCESS,
            fg="#FFFFFF", hover="#1B8A4B", active_bg="#1B8A4B",
            font=theme.f(14, "bold"), padx=20, pady=12, anchor="w")
        self.cardio_btn.pack(fill="x", pady=(4, 8))

        self.cardio_panel = tk.Frame(parent, bg=theme.BG)
        card = Card(self.cardio_panel)
        card.pack(fill="x")
        inner = tk.Frame(card, bg=theme.CARD)
        inner.pack(fill="x", padx=14, pady=12)

        self.run_vars = self._cardio_row(
            inner, "户外长跑", [("距离", "km"), ("时间", "min"), ("心率", "bpm")],
            extra="配速")
        self.bike_vars = self._cardio_row(
            inner, "户外骑行", [("距离", "km"), ("时间", "min")])

        foot = tk.Frame(inner, bg=theme.CARD)
        foot.pack(fill="x", pady=(10, 0))
        FlatButton(foot, "保存今天的有氧", self._save_cardio,
                   bg=theme.SUCCESS, fg="#FFFFFF", hover="#1B8A4B",
                   active_bg="#1B8A4B", font=theme.f(11, "bold"),
                   padx=18, pady=7).pack(side="left")
        self.cardio_hint = tk.Label(foot, text="", bg=theme.CARD, fg=theme.MUTED,
                                    font=theme.f(10))
        self.cardio_hint.pack(side="left", padx=12)

    def _cardio_row(self, parent, title: str, fields: list[tuple[str, str]],
                    extra: str = "") -> dict:
        row = tk.Frame(parent, bg=theme.CARD)
        row.pack(fill="x", pady=(6, 2))
        tk.Label(row, text=title, bg=theme.CARD, fg=theme.TEXT,
                 font=theme.f(12, "bold"), width=9, anchor="w").pack(side="left")
        vars_ = {}
        for label, unit in fields:
            tk.Label(row, text=label, bg=theme.CARD, fg=theme.MUTED,
                     font=theme.f(10)).pack(side="left", padx=(8, 2))
            var = tk.StringVar()
            ent = tk.Entry(row, textvariable=var, width=6, justify="right",
                           font=theme.f(11), bg=theme.SUNK, fg=theme.TEXT,
                           relief="flat", highlightthickness=1,
                           highlightbackground=theme.BORDER)
            ent.pack(side="left", ipady=2)
            tk.Label(row, text=unit, bg=theme.CARD, fg=theme.MUTED,
                     font=theme.f(9)).pack(side="left", padx=(2, 0))
            vars_[label] = var
        if extra:
            lab = tk.Label(row, text=f"{extra} —", bg=theme.CARD, fg=theme.MUTED,
                           font=theme.f(10))
            lab.pack(side="left", padx=12)
            vars_["_pace"] = lab
            for label in ("距离", "时间"):
                vars_[label].trace_add("write", lambda *_: self._update_pace(vars_))
        return vars_

    def _update_pace(self, vars_: dict) -> None:
        try:
            km = float(vars_["距离"].get() or 0)
            minutes = float(vars_["时间"].get() or 0)
        except ValueError:
            km = minutes = 0
        vars_["_pace"].configure(text=f"配速 {fit.pace_text(km, minutes)}")

    def _toggle_cardio(self) -> None:
        self._cardio_open = not self._cardio_open
        if self._cardio_open:
            self.cardio_btn.set_text("有氧运动  ▴")
            self.cardio_panel.pack(fill="x", pady=(0, 10),
                                   after=self.cardio_btn)
        else:
            self.cardio_btn.set_text("有氧运动  ▾")
            self.cardio_panel.pack_forget()

    def _save_cardio(self) -> None:
        def num(var, cast=float):
            try:
                return cast(var.get().strip() or 0)
            except ValueError:
                return 0
        saved = []
        km = num(self.run_vars["距离"]); mi = num(self.run_vars["时间"])
        hr = num(self.run_vars["心率"], int)
        if km > 0 and mi > 0:
            self.app.db.fit_cardio_add("run", km, mi, hr)
            saved.append(f"跑步 {km}km / {mi}min")
        bkm = num(self.bike_vars["距离"]); bmi = num(self.bike_vars["时间"])
        if bkm > 0 and bmi > 0:
            self.app.db.fit_cardio_add("bike", bkm, bmi, 0)
            saved.append(f"骑行 {bkm}km / {bmi}min")
        if not saved:
            self.cardio_hint.configure(text="距离和时间都填一下", fg=theme.ERROR)
            return
        self.cardio_hint.configure(text="已保存：" + "、".join(saved), fg=theme.SUCCESS)
        for v in list(self.run_vars.values()) + list(self.bike_vars.values()):
            if isinstance(v, tk.StringVar):
                v.set("")
        self._refresh_summary()

    # ------------------------------------------------------------ AI
    def _build_ai(self, parent) -> None:
        self.ai_btn = FlatButton(
            parent, "AI建议  ▾", self._toggle_ai, bg=theme.PRIMARY,
            fg="#FFFFFF", hover=theme.PRIMARY_DARK, active_bg=theme.PRIMARY_DARK,
            font=theme.f(14, "bold"), padx=20, pady=12, anchor="w")
        self.ai_btn.pack(fill="x", pady=(4, 8))

        self.ai_panel = tk.Frame(parent, bg=theme.BG)
        card = Card(self.ai_panel)
        card.pack(fill="x")
        inner = tk.Frame(card, bg=theme.CARD)
        inner.pack(fill="x", padx=14, pady=12)

        row = tk.Frame(inner, bg=theme.CARD)
        row.pack(fill="x")
        for key, (label, _days) in PERIODS.items():
            FlatButton(row, label, lambda k=key: self._run_ai(k),
                       bg=theme.PRIMARY_SOFT, fg=theme.PRIMARY,
                       font=theme.f(11, "bold"), padx=16, pady=6,
                       border=theme.PRIMARY_SOFT).pack(side="left", padx=(0, 8))
        self.ai_hint = tk.Label(row, text="点按钮才会调用 AI", bg=theme.CARD,
                                fg=theme.MUTED, font=theme.f(10))
        self.ai_hint.pack(side="left", padx=10)

        self.ai_text = tk.Text(inner, height=12, wrap="word", bg=theme.SUNK,
                               fg=theme.TEXT, font=theme.f(11), bd=0,
                               padx=12, pady=10, relief="flat",
                               highlightthickness=1,
                               highlightbackground=theme.BORDER)
        self.ai_text.pack(fill="both", expand=True, pady=(10, 0))
        self.ai_text.configure(state="disabled")

    def _toggle_ai(self) -> None:
        self._ai_open = not self._ai_open
        if self._ai_open:
            self.ai_btn.set_text("AI建议  ▴")
            self.ai_panel.pack(fill="x", pady=(0, 10), after=self.ai_btn)
        else:
            self.ai_btn.set_text("AI建议  ▾")
            self.ai_panel.pack_forget()

    def _digest(self, days: int) -> str:
        """把这段时间的数据整理成一段给模型的文字。"""
        db = self.app.db
        since = (dt.date.today() - dt.timedelta(days=days)).isoformat()
        lines = [f"统计区间：最近 {days} 天（{since} 起）",
                 f"用户：男，{fit.PROFILE['height_cm']}cm，"
                 f"{fit.age_on()} 岁，目标增重增肌、每天至少不比前一天轻松"]

        ws = [(at, kg) for at, kg in db.fit_weight_all() if at[:10] >= since]
        if ws:
            daily = fit.daily_mean(ws)
            first, last = daily[0][1], daily[-1][1]
            lines.append(
                f"体重：{len(ws)} 次记录 / {len(daily)} 天；"
                f"期初 {first}kg，期末 {last}kg，变化 {last - first:+.1f}kg；"
                f"趋势斜率 {fit.trend_slope(daily):+.2f} kg/周；"
                f"BMI {fit.bmi(last)}")
        else:
            lines.append("体重：这段时间没有记录")

        sets = db.fit_sets_since(since)
        days_done = db.fit_days_since(since)
        top = sorted(sets.items(), key=lambda kv: -kv[1])[:6]
        lines.append(f"力量训练：{len(days_done)} 天有打卡，共 {sum(sets.values())} 组；"
                     f"主要动作 " + "、".join(
                         f"{fit.MOVE_BY_SLUG.get(k, {}).get('cn', k)}{v}组"
                         for k, v in top))
        cardio = db.fit_cardio_since(since)
        runs = [c for c in cardio if c["kind"] == "run"]
        bikes = [c for c in cardio if c["kind"] == "bike"]
        if runs or bikes:
            lines.append(
                f"有氧：跑步 {len(runs)} 次 {sum(c['km'] for c in runs):.1f}km，"
                f"骑行 {len(bikes)} 次 {sum(c['km'] for c in bikes):.1f}km")
        else:
            lines.append("有氧：这段时间没有记录")
        return "\n".join(lines)

    def _run_ai(self, key: str) -> None:
        label, days = PERIODS[key]
        if not llm.is_configured():
            self.ai_hint.configure(text="还没配置 AI，去「同步 → AI」里填 key",
                                   fg=theme.ERROR)
            return
        digest = self._digest(days)
        self._set_ai_text(f"正在生成{label}……\n\n{digest}")
        self.ai_hint.configure(text=f"正在生成{label}…", fg=theme.MUTED)

        def work():
            try:
                cfg = llm.load_config()
                url = cfg["base_url"].rstrip("/") + "/chat/completions"
                payload = {
                    "model": cfg["model"],
                    "messages": [
                        {"role": "system", "content":
                         "你是健身教练。根据用户的训练与体重数据写一份"
                         f"{label}。要点：1) 用数据说话（体重趋势、训练量、"
                         "有氧）；2) 给出下一步的具体建议（组数/次数/频率/饮食）；"
                         "3) 有风险就明确预警（掉体重过快、训练量骤降、连续缺练等）；"
                         "4) 语气直接、不客套，控制在 400 字以内。"},
                        {"role": "user", "content": digest},
                    ],
                    "temperature": 0.4,
                    "stream": False,
                }
                data = llm._post(url, payload, cfg["api_key"], timeout=180)
                text = (data.get("choices") or [{}])[0].get(
                    "message", {}).get("content", "")
                self.after(0, lambda: self._set_ai_text(text or "（AI 没有返回内容）"))
                self.after(0, lambda: self.ai_hint.configure(
                    text=f"{label} 已生成", fg=theme.SUCCESS))
            except Exception as exc:      # noqa: BLE001
                msg = str(exc)[:120]
                self.after(0, lambda: self._set_ai_text(f"生成失败：{msg}"))
                self.after(0, lambda: self.ai_hint.configure(
                    text="生成失败", fg=theme.ERROR))

        threading.Thread(target=work, daemon=True).start()

    def _set_ai_text(self, text: str) -> None:
        self.ai_text.configure(state="normal")
        self.ai_text.delete("1.0", "end")
        self.ai_text.insert("1.0", text)
        self.ai_text.configure(state="disabled")

    # ------------------------------------------------------------ 刷新
    def _refresh_summary(self) -> None:
        s = self.app.db.fit_summary()
        parts = []
        if s["weight"]:
            parts.append(f"{s['weight']:.1f}kg · BMI {fit.bmi(s['weight'])}")
        if s["sets"]:
            parts.append(f"今日 {s['sets']} 组")
        self.summary.configure(text="　·　".join(parts) if parts else "还没有数据")

    def on_show(self, **_):
        self._refresh_weight_list()
        self.chart.redraw()
        self._refresh_summary()
        if self._strength_open:
            self._render_moves()
