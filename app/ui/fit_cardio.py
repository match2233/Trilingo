"""有氧运动页：跑步（配速自动）/ 骑行 + 历史明细."""
from __future__ import annotations

import datetime as dt
import tkinter as tk

from .. import fit
from . import theme
from .fit_dialogs import CardioHistory
from .widgets import Card, FlatButton

ENTRY_W = 7


def _entry(parent, var: tk.StringVar, width: int = ENTRY_W,
           justify: str = "right") -> tk.Entry:
    ent = tk.Entry(parent, textvariable=var, width=width, justify=justify,
                   font=theme.f(12), bd=0, bg=theme.SUNK, fg=theme.TEXT,
                   relief="flat", highlightthickness=1,
                   highlightbackground=theme.BORDER)
    ent.pack(side="left", ipady=3)
    return ent


class FitCardioFrame(tk.Frame):
    def __init__(self, master, app):
        super().__init__(master, bg=theme.BG)
        self.grid(row=0, column=0, sticky="nsew")
        self.app = app
        self._build()

    def _build(self) -> None:
        head = tk.Frame(self, bg=theme.BG)
        head.pack(fill="x", padx=30, pady=(22, 6))
        FlatButton(head, "← 返回", lambda: self.app.show("fitness"), bg=theme.BG,
                   hover=theme.CARD, font=theme.f(11), padx=12, pady=7
                   ).pack(side="left")
        tk.Label(head, text="有氧运动", bg=theme.BG, fg=theme.TEXT,
                 font=theme.f(16, "bold")).pack(side="left", padx=14)
        self.week = tk.Label(head, text="", bg=theme.BG, fg=theme.MUTED,
                             font=theme.f(10))
        self.week.pack(side="left", padx=8)
        FlatButton(head, "历史明细", self._history, bg=theme.CARD,
                   font=theme.f(11), padx=16, pady=7).pack(side="right")

        body = tk.Frame(self, bg=theme.BG)
        body.pack(fill="both", expand=True, padx=30, pady=(10, 20))

        # ------------------------------------------------ 跑步
        run_card = Card(body)
        run_card.pack(fill="x", pady=(0, 12))
        inner = tk.Frame(run_card, bg=theme.CARD)
        inner.pack(fill="x", padx=22, pady=16)
        title = tk.Frame(inner, bg=theme.CARD)
        title.pack(fill="x")
        tk.Label(title, text="户外长跑", bg=theme.CARD, fg=theme.TEXT,
                 font=theme.f(14, "bold")).pack(side="left")
        self.pace = tk.Label(title, text="配速 —", bg=theme.CARD,
                             fg=theme.SUCCESS, font=theme.f(12, "bold"))
        self.pace.pack(side="right")

        row = tk.Frame(inner, bg=theme.CARD)
        row.pack(fill="x", pady=(12, 0))
        self.run_km = tk.StringVar()
        self.run_min = tk.StringVar()
        self.run_hr = tk.StringVar()
        for label, unit, var in (("距离", "km", self.run_km),
                                 ("时间", "分:秒", self.run_min),
                                 ("平均心率", "bpm", self.run_hr)):
            tk.Label(row, text=label, bg=theme.CARD, fg=theme.MUTED,
                     font=theme.f(10)).pack(side="left", padx=(0, 4) if label == "距离" else (18, 4))
            _entry(row, var, width=8 if label == "时间" else ENTRY_W,
                   justify="left" if label == "时间" else "right")
            tk.Label(row, text=unit, bg=theme.CARD, fg=theme.MUTED,
                     font=theme.f(9)).pack(side="left", padx=(3, 0))
            if label == "时间":
                tk.Label(row, text="如 32:15", bg=theme.CARD, fg=theme.MUTED,
                         font=theme.f(8)).pack(side="left", padx=(4, 0))
        for var in (self.run_km, self.run_min):
            var.trace_add("write", lambda *_: self._update_pace())
        FlatButton(row, "保存", lambda: self._save("run"), bg=theme.SUCCESS,
                   fg="#FFFFFF", hover="#1B8A4B", active_bg="#1B8A4B",
                   font=theme.f(11, "bold"), padx=20, pady=7
                   ).pack(side="right")

        # ------------------------------------------------ 骑行
        bike_card = Card(body)
        bike_card.pack(fill="x", pady=(0, 12))
        binner = tk.Frame(bike_card, bg=theme.CARD)
        binner.pack(fill="x", padx=22, pady=16)
        btitle = tk.Frame(binner, bg=theme.CARD)
        btitle.pack(fill="x")
        tk.Label(btitle, text="户外骑行", bg=theme.CARD, fg=theme.TEXT,
                 font=theme.f(14, "bold")).pack(side="left")
        self.bike_speed = tk.Label(btitle, text="均速 —", bg=theme.CARD,
                                   fg=theme.BLUE, font=theme.f(12, "bold"))
        self.bike_speed.pack(side="right")

        brow = tk.Frame(binner, bg=theme.CARD)
        brow.pack(fill="x", pady=(12, 0))
        self.bike_km = tk.StringVar()
        self.bike_min = tk.StringVar()
        for label, unit, var in (("距离", "km", self.bike_km),
                                 ("时间", "分:秒", self.bike_min)):
            tk.Label(brow, text=label, bg=theme.CARD, fg=theme.MUTED,
                     font=theme.f(10)).pack(side="left", padx=(0, 4) if label == "距离" else (18, 4))
            _entry(brow, var, width=8 if label == "时间" else ENTRY_W,
                   justify="left" if label == "时间" else "right")
            tk.Label(brow, text=unit, bg=theme.CARD, fg=theme.MUTED,
                     font=theme.f(9)).pack(side="left", padx=(3, 0))
            if label == "时间":
                tk.Label(brow, text="如 45:00", bg=theme.CARD, fg=theme.MUTED,
                         font=theme.f(8)).pack(side="left", padx=(4, 0))
        for var in (self.bike_km, self.bike_min):
            var.trace_add("write", lambda *_: self._update_bike())
        FlatButton(brow, "保存", lambda: self._save("bike"), bg=theme.BLUE,
                   fg="#FFFFFF", hover=theme.BLUE_DARK, active_bg=theme.BLUE_DARK,
                   font=theme.f(11, "bold"), padx=20, pady=7).pack(side="right")

        self.hint = tk.Label(body, text="", bg=theme.BG, fg=theme.MUTED,
                             font=theme.f(10))
        self.hint.pack(anchor="w", pady=(2, 8))

        # ------------------------------------------------ 最近记录
        recent = Card(body)
        recent.pack(fill="both", expand=True)
        self.recent_box = tk.Frame(recent, bg=theme.CARD)
        self.recent_box.pack(fill="both", expand=True, padx=22, pady=14)
        tk.Label(self.recent_box, text="最近记录", bg=theme.CARD, fg=theme.TEXT,
                 font=theme.f(13, "bold")).pack(anchor="w")
        self.recent_rows = tk.Frame(self.recent_box, bg=theme.CARD)
        self.recent_rows.pack(fill="x", pady=(8, 0))

    # ------------------------------------------------------------ 行为
    def _update_pace(self) -> None:
        try:
            km = float(self.run_km.get() or 0)
        except ValueError:
            km = 0
        sec = fit.parse_duration(self.run_min.get()) or 0
        self.pace.configure(
            text="配速 " + fit.pace_text(km, sec / 60 if sec else 0))

    def _update_bike(self) -> None:
        try:
            km = float(self.bike_km.get() or 0)
        except ValueError:
            km = 0
        sec = fit.parse_duration(self.bike_min.get()) or 0
        if km > 0 and sec > 0:
            self.bike_speed.configure(text=f"均速 {km / (sec / 3600):.1f} km/h")
        else:
            self.bike_speed.configure(text="均速 —")

    def _save(self, kind: str) -> None:
        if kind == "run":
            vars_ = (self.run_km, self.run_min)
            hr_var = self.run_hr
        else:
            vars_ = (self.bike_km, self.bike_min)
            hr_var = None
        try:
            km = float(vars_[0].get().strip() or 0)
        except ValueError:
            km = 0
        sec = fit.parse_duration(vars_[1].get())
        if km <= 0 or not sec:
            self.hint.configure(text="距离要填数字，时间按 分:秒 填（如 32:15）",
                                fg=theme.ERROR)
            return
        minutes = sec / 60
        hr = 0
        if hr_var is not None:
            try:
                hr = int(float(hr_var.get().strip() or 0))
            except ValueError:
                hr = 0
        self.app.db.fit_cardio_add(kind, km, minutes, hr)
        for v in vars_:
            v.set("")
        if hr_var is not None:
            hr_var.set("")
        label = "跑步" if kind == "run" else "骑行"
        self.hint.configure(
            text=f"已记录 {label} {km}km / {fit.fmt_duration(sec)}"
                 + (f" · 配速 {fit.pace_text(km, minutes)}" if kind == "run" else ""),
            fg=theme.SUCCESS)
        self._refresh()

    def _history(self) -> None:
        self._hist = CardioHistory(self, self.app)

    def _refresh_recent(self) -> None:
        for w in self.recent_rows.winfo_children():
            w.destroy()
        rows = self.app.db.fit_cardio_all()[:8]
        if not rows:
            tk.Label(self.recent_rows, text="还没有记录", bg=theme.CARD,
                     fg=theme.MUTED, font=theme.f(10)).pack(anchor="w")
            return
        for r in rows:
            row = tk.Frame(self.recent_rows, bg=theme.CARD)
            row.pack(fill="x", pady=2)
            kind = "跑步" if r["kind"] == "run" else "骑行"
            color = theme.SUCCESS if r["kind"] == "run" else theme.BLUE
            tk.Label(row, text=r["at"][:16].replace("T", " "), bg=theme.CARD,
                     fg=theme.MUTED, font=theme.f(10), width=17,
                     anchor="w").pack(side="left")
            tk.Label(row, text=kind, bg=theme.CARD, fg=color,
                     font=theme.f(10, "bold"), width=5, anchor="w").pack(side="left")
            tk.Label(row, text=f'{r["km"]:.2f} km', bg=theme.CARD,
                     fg=theme.TEXT, font=theme.f(10), width=10,
                     anchor="e").pack(side="left")
            tk.Label(row, text=fit.fmt_duration(r["minutes"] * 60),
                     bg=theme.CARD, fg=theme.TEXT, font=theme.f(10), width=9,
                     anchor="e").pack(side="left")
            if r["kind"] == "run":
                tk.Label(row, text=fit.pace_text(r["km"], r["minutes"]),
                         bg=theme.CARD, fg=theme.MUTED, font=theme.f(10),
                         width=12, anchor="e").pack(side="left")
                if r["hr"]:
                    tk.Label(row, text=f'{r["hr"]} bpm', bg=theme.CARD,
                             fg=theme.MUTED, font=theme.f(10), width=9,
                             anchor="e").pack(side="left")

    def _refresh(self) -> None:
        self._refresh_recent()
        since = (dt.date.today() - dt.timedelta(days=7)).isoformat()
        rows = self.app.db.fit_cardio_since(since)
        rk = sum(r["km"] for r in rows if r["kind"] == "run")
        bk = sum(r["km"] for r in rows if r["kind"] == "bike")
        self.week.configure(text=f"近 7 天　跑步 {rk:.1f}km · 骑行 {bk:.1f}km")

    def on_show(self, **_):
        self._refresh()
