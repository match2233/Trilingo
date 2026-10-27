"""力量训练页：哑铃重量 + 动作卡片（点一次 = 一组）+ 历史明细.

卡片只显示**中文名和示意图**；点卡片任意位置记一组，右上角小圆角显示今天做了几组。
每行三张，图放大到看得清。
"""
from __future__ import annotations

import datetime as dt
import pathlib
import tkinter as tk

from .. import fit
from . import theme
from .fit_dialogs import StrengthHistory
from .widgets import Card, FlatButton, ScrollFrame

ASSETS = pathlib.Path(__file__).resolve().parent.parent.parent / "assets" / "fitness"
IMG_W, IMG_H = 300, 176

# 练的部位 -> 边框颜色
PART_COLOR = {1: theme.ERROR, 2: theme.BLUE, 3: theme.SUCCESS}
PART_SOFT = {1: theme.ERROR_SOFT, 2: theme.BLUE_SOFT, 3: theme.SUCCESS_SOFT}


class FitStrengthFrame(tk.Frame):
    def __init__(self, master, app):
        super().__init__(master, bg=theme.BG)
        self.grid(row=0, column=0, sticky="nsew")
        self.app = app
        self._imgs: dict[str, object] = {}
        self._build()

    def _build(self) -> None:
        head = tk.Frame(self, bg=theme.BG)
        head.pack(fill="x", padx=30, pady=(22, 6))
        FlatButton(head, "← 返回", lambda: self.app.show("fitness"), bg=theme.BG,
                   hover=theme.CARD, font=theme.f(11), padx=12, pady=7
                   ).pack(side="left")
        tk.Label(head, text="力量训练", bg=theme.BG, fg=theme.TEXT,
                 font=theme.f(16, "bold")).pack(side="left", padx=14)
        self.today = tk.Label(head, text="", bg=theme.BG, fg=theme.MUTED,
                              font=theme.f(10))
        self.today.pack(side="left", padx=8)

        FlatButton(head, "历史明细", self._history, bg=theme.CARD,
                   font=theme.f(11), padx=16, pady=7).pack(side="right")

        bar = Card(self)
        bar.pack(fill="x", padx=30, pady=(6, 10))
        row = tk.Frame(bar, bg=theme.CARD)
        row.pack(fill="x", padx=20, pady=12)
        tk.Label(row, text="哑铃重量", bg=theme.CARD, fg=theme.TEXT,
                 font=theme.f(13, "bold")).pack(side="left")
        self.db_var = tk.StringVar(value=self.app.db.fit_setting("dumbbell", "12.5"))
        ent = tk.Entry(row, textvariable=self.db_var, width=6, justify="right",
                       font=theme.f(12), bd=0, bg=theme.SUNK, fg=theme.TEXT,
                       relief="flat", highlightthickness=1,
                       highlightbackground=theme.BORDER)
        ent.pack(side="left", padx=(12, 4), ipady=3)
        ent.bind("<FocusOut>", lambda e: self._save_dumbbell())
        ent.bind("<Return>", lambda e: self._save_dumbbell())
        tk.Label(row, text="kg（单手，改一次长期有效）", bg=theme.CARD,
                 fg=theme.MUTED, font=theme.f(10)).pack(side="left", padx=(4, 0))

        self.scroll = ScrollFrame(self)
        self.scroll.pack(fill="both", expand=True, padx=30, pady=(0, 18))
        self.grid_box = tk.Frame(self.scroll.body, bg=theme.BG)
        self.grid_box.pack(fill="both", expand=True)

    # ------------------------------------------------------------ 动作卡
    def _save_dumbbell(self) -> None:
        v = self.db_var.get().strip()
        try:
            float(v)
        except ValueError:
            return
        self.app.db.fit_set_setting("dumbbell", v)

    def _image(self, slug: str):
        if slug in self._imgs:
            return self._imgs[slug]
        path = ASSETS / f"{slug}.png"
        if not path.exists():
            return None
        try:
            from PIL import Image, ImageTk
            im = Image.open(path).convert("RGB")
            # 统一贴到 IMG_W x IMG_H 的白底画布上, 卡片高度才会一致
            im.thumbnail((IMG_W - 8, IMG_H - 8), Image.LANCZOS)
            canvas = Image.new("RGB", (IMG_W, IMG_H), "#FFFFFF")
            canvas.paste(im, ((IMG_W - im.width) // 2, (IMG_H - im.height) // 2))
            img = ImageTk.PhotoImage(canvas)
            self._imgs[slug] = img
            return img
        except Exception:      # noqa: BLE001
            return None

    def _render(self) -> None:
        for w in self.grid_box.winfo_children():
            w.destroy()
        today = dt.date.today().isoformat()
        done = self.app.db.fit_sets_day(today)
        since = (dt.date.today() - dt.timedelta(days=30)).isoformat()
        usage = self.app.db.fit_sets_since(since)

        total = 0
        for day_no, day_name, parts, slugs in fit.DAY_PLAN:
            color = PART_COLOR.get(day_no, theme.BORDER)
            head = tk.Frame(self.grid_box, bg=theme.BG)
            head.pack(fill="x", pady=(12 if total else 0, 4))
            tk.Frame(head, bg=color, width=4, height=20).pack(side="left")
            tk.Label(head, text=f"DAY {day_no}  {day_name}", bg=theme.BG,
                     fg=color, font=theme.f(13, "bold")).pack(side="left", padx=8)
            tk.Label(head, text=parts, bg=theme.BG, fg=theme.MUTED,
                     font=theme.f(10)).pack(side="left")
            day_sets = sum(done.get(sg, 0) for sg in slugs)
            tk.Label(head, text=f"今日 {day_sets} 组" if day_sets else "",
                     bg=theme.BG, fg=color, font=theme.f(10, "bold")
                     ).pack(side="right")

            grid = tk.Frame(self.grid_box, bg=theme.BG)
            grid.pack(fill="x")
            for c in range(3):
                grid.grid_columnconfigure(c, weight=1, uniform="mv")

            ordered = sorted(slugs, key=lambda sg: -usage.get(sg, 0))
            for i, slug in enumerate(ordered):
                self._card(grid, fit.MOVE_BY_SLUG[slug], i, 3,
                           done.get(slug, 0))
                total += 1

        self.today.configure(
            text=f"今日 {sum(done.values())} 组 · {len(done)} 个动作"
            if done else "今日还没开始")

    def _card(self, parent, mv: dict, idx: int, per_row: int, done: int) -> None:
        color = PART_COLOR.get(mv["day"], theme.BORDER)
        cell = Card(parent)
        cell.configure(highlightbackground=color, highlightthickness=2)
        cell.grid(row=idx // per_row, column=idx % per_row,
                  padx=6, pady=6, sticky="nsew")

        soft = PART_SOFT.get(mv["day"], theme.SUNK)
        box = tk.Frame(cell, bg=soft)
        box.pack(fill="both", expand=True, padx=8, pady=8)

        img = self._image(mv["slug"])
        pic = tk.Label(box, bg=soft, bd=0,
                       image=img) if img else tk.Label(box, bg=soft,
                                                       text="（无图）", height=8)
        if img:
            pic.image = img
        pic.pack(fill="x")

        name = tk.Label(box, text=mv["cn"], bg=soft, fg=theme.TEXT,
                        font=theme.f(12, "bold"))
        name.pack(pady=(8, 2))

        tail = tk.Frame(box, bg=soft)
        tail.pack(fill="x", pady=(0, 2))
        tk.Label(tail, text="每组", bg=soft, fg=theme.MUTED,
                 font=theme.f(9)).pack(side="left")
        var = tk.StringVar(value=self.app.db.fit_setting(f"reps:{mv['slug']}",
                                                        str(mv["reps"])))
        ent = tk.Entry(tail, textvariable=var, width=3, justify="right",
                       font=theme.f(10), bd=0, bg=theme.SUNK, fg=theme.TEXT,
                       relief="flat", highlightthickness=1,
                       highlightbackground=theme.BORDER)
        ent.pack(side="left", padx=3, ipady=1)
        ent.bind("<FocusOut>", lambda e, s=mv["slug"], v=var:
                 self.app.db.fit_set_setting(f"reps:{s}", v.get().strip()))
        tk.Label(tail, text="次", bg=soft, fg=theme.MUTED,
                 font=theme.f(9)).pack(side="left")
        counter = tk.Label(tail, text=f"今天 {done} 组" if done else "",
                           bg=soft, fg=color, font=theme.f(10, "bold"))
        counter.pack(side="right")

        # 整张卡片可点: 点一下 = 一组
        def _hit(_e=None, slug=mv["slug"], lab=counter, reps_var=var):
            # 打卡时把**当时的**哑铃重量和每组次数一起存下来
            n = self.app.db.fit_log_add(
                slug, dumbbell=self.db_var.get().strip(),
                reps=reps_var.get().strip())
            lab.configure(text=f"今天 {n} 组")
            self._flash(cell, color)
            self._refresh_today()

        for w in (cell, box, pic, name, tail):
            w.configure(cursor="hand2")
            w.bind("<Button-1>", _hit)

    def _flash(self, card, color) -> None:
        """点完闪一下：先变实色，再恢复成部位色。"""
        try:
            card.configure(highlightbackground=color, highlightthickness=4)
            card.after(200, lambda: card.configure(
                highlightbackground=color, highlightthickness=2))
        except tk.TclError:
            pass

    def _refresh_today(self) -> None:
        today = dt.date.today().isoformat()
        done = self.app.db.fit_sets_day(today)
        self.today.configure(
            text=f"今日 {sum(done.values())} 组 · {len(done)} 个动作"
            if done else "今日还没开始")

    def _history(self) -> None:
        self._hist = StrengthHistory(self, self.app)

    def on_show(self, **_):
        self._render()
