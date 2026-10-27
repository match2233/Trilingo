"""肌薄的历史明细弹窗：力量训练 / 有氧 / AI 报告.

风格跟记账的「账单明细」一致：Toplevel + Treeview + 顶部汇总。
"""
from __future__ import annotations

import datetime as dt
import tkinter as tk

from .. import fit
from . import theme
from tkinter import messagebox

from .widgets import FlatButton, center_window, style_treeview

KIND_LABEL = {"week": "周报", "month": "月报", "half": "半年报"}


def _dialog(master, title: str, w: int = 940, h: int = 700) -> tk.Toplevel:
    win = tk.Toplevel(master, bg=theme.BG)
    win.title(title)
    win.transient(master.winfo_toplevel())
    center_window(win, w, h)
    win.minsize(760, 520)
    style_treeview(win)
    return win


class StrengthHistory:
    """力量训练历史：日期 / 动作 / 组数."""

    def __init__(self, master, app):
        win = _dialog(master, "力量训练历史")
        self.win = win
        self.app = app
        head = tk.Frame(win, bg=theme.BG)
        head.pack(fill="x", padx=20, pady=(16, 6))
        tk.Label(head, text="力量训练历史", bg=theme.BG, fg=theme.TEXT,
                 font=theme.f(15, "bold")).pack(side="left")
        self.summary = tk.Label(head, text="", bg=theme.BG, fg=theme.MUTED,
                                font=theme.f(10))
        self.summary.pack(side="right")
        FlatButton(head, "关闭", win.destroy, bg=theme.CARD, font=theme.f(10),
                   padx=14, pady=5).pack(side="right", padx=(0, 10))

        cols = ("at", "move", "sets", "dumbbell", "reps")
        self.tree = self._tree(win, cols,
                               ("时间", "动作", "组数", "哑铃", "每组次数"),
                               (150, 220, 60, 90, 90))
        self._reload(win)

    def _tree(self, parent, cols, heads, widths) -> "ttk.Treeview":
        from tkinter import ttk
        wrap = tk.Frame(parent, bg=theme.BG)
        wrap.pack(fill="both", expand=True, padx=20, pady=(6, 16))
        tree = ttk.Treeview(wrap, columns=cols, show="headings", height=18)
        for c, h, w in zip(cols, heads, widths):
            tree.heading(c, text=h)
            tree.column(c, width=w, anchor="center" if w < 120 else "w")
        vs = ttk.Scrollbar(wrap, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=vs.set)
        vs.pack(side="right", fill="y")
        tree.pack(side="left", fill="both", expand=True)
        return tree

    def _reload(self, win) -> None:
        rows = self.app.db.fit_log_history(400)
        days = self.app.db.fit_log_day_totals(400)
        total_sets = sum(d["sets"] for d in days)
        title = {}
        for r in rows:
            mv = fit.MOVE_BY_SLUG.get(r["move"], {})
            title[r["move"]] = mv.get("cn", r["move"])
        for r in rows:
            dumbbell = f'{r["dumbbell"]} kg' if r.get("dumbbell") else "—"
            reps = f'{r["reps"]} 次' if r.get("reps") else "—"
            self.tree.insert("", "end", values=(
                r["last_at"][:16].replace("T", " "),
                title.get(r["move"], r["move"]), r["n"], dumbbell, reps))
        self.summary.configure(
            text=f"{len(days)} 天 · {total_sets} 组")


class CardioHistory:
    """有氧历史：日期 / 项目 / 距离 / 时间 / 配速 / 心率."""

    def __init__(self, master, app):
        win = _dialog(master, "有氧运动历史")
        self.win = win
        self.app = app
        head = tk.Frame(win, bg=theme.BG)
        head.pack(fill="x", padx=20, pady=(16, 6))
        tk.Label(head, text="有氧运动历史", bg=theme.BG, fg=theme.TEXT,
                 font=theme.f(15, "bold")).pack(side="left")
        self.summary = tk.Label(head, text="", bg=theme.BG, fg=theme.MUTED,
                                font=theme.f(10))
        self.summary.pack(side="right")
        FlatButton(head, "关闭", win.destroy, bg=theme.CARD, font=theme.f(10),
                   padx=14, pady=5).pack(side="right", padx=(0, 10))

        from tkinter import ttk
        wrap = tk.Frame(win, bg=theme.BG)
        wrap.pack(fill="both", expand=True, padx=20, pady=(6, 16))
        cols = ("at", "kind", "km", "min", "pace", "hr")
        self.tree = ttk.Treeview(wrap, columns=cols, show="headings", height=18)
        for c, h, w in zip(cols, ("时间", "项目", "距离", "时长", "配速", "心率"),
                           (130, 90, 90, 90, 110, 80)):
            self.tree.heading(c, text=h)
            self.tree.column(c, width=w, anchor="center")
        vs = ttk.Scrollbar(wrap, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vs.set)
        vs.pack(side="right", fill="y")
        self.tree.pack(side="left", fill="both", expand=True)

        rows = app.db.fit_cardio_all()
        rk = sum(r["km"] for r in rows if r["kind"] == "run")
        bk = sum(r["km"] for r in rows if r["kind"] == "bike")
        for r in rows:
            self.tree.insert("", "end", values=(
                r["at"][:16].replace("T", " "),
                "跑步" if r["kind"] == "run" else "骑行",
                f'{r["km"]:.2f} km', f'{r["minutes"]:.0f} min',
                fit.pace_text(r["km"], r["minutes"]) if r["kind"] == "run" else "—",
                r["hr"] or "—"))
        self.summary.configure(text=f"跑步 {rk:.1f}km · 骑行 {bk:.1f}km")


class ReportHistory:
    """AI 报告历史：左边列表（日期+类型），右边正文."""

    def __init__(self, master, app):
        win = _dialog(master, "AI 报告历史", 1040, 720)
        self.win = win
        self.app = app
        head = tk.Frame(win, bg=theme.BG)
        head.pack(fill="x", padx=20, pady=(16, 6))
        tk.Label(head, text="AI 报告历史", bg=theme.BG, fg=theme.TEXT,
                 font=theme.f(15, "bold")).pack(side="left")
        self.count = tk.Label(head, text="", bg=theme.BG, fg=theme.MUTED,
                              font=theme.f(10))
        self.count.pack(side="left", padx=10)
        FlatButton(head, "关闭", win.destroy, bg=theme.CARD, font=theme.f(10),
                   padx=14, pady=5).pack(side="right")
        FlatButton(head, "删除选中", self._delete, bg=theme.ERROR_SOFT,
                   fg=theme.ERROR, hover=theme.ERROR_SOFT, font=theme.f(10),
                   padx=14, pady=5, border=theme.ERROR_SOFT
                   ).pack(side="right", padx=(0, 8))

        body = tk.Frame(win, bg=theme.BG)
        body.pack(fill="both", expand=True, padx=20, pady=(6, 16))

        left = tk.Frame(body, bg=theme.CARD, width=250)
        left.pack(side="left", fill="y")
        left.pack_propagate(False)
        self.listbox = tk.Listbox(left, bg=theme.CARD, fg=theme.TEXT, bd=0,
                                  highlightthickness=0, font=theme.f(11),
                                  activestyle="none", selectmode="browse")
        self.listbox.pack(fill="both", expand=True, padx=8, pady=8)
        self.listbox.bind("<<ListboxSelect>>", self._on_pick)

        right = tk.Frame(body, bg=theme.BG)
        right.pack(side="left", fill="both", expand=True, padx=(12, 0))
        self.text = tk.Text(right, wrap="word", bg=theme.CARD, fg=theme.TEXT,
                            font=theme.f(11), bd=0, padx=16, pady=14,
                            relief="flat", highlightthickness=1,
                            highlightbackground=theme.BORDER)
        self.text.pack(fill="both", expand=True)
        self.text.configure(state="disabled")

        self._reload()

    def _reload(self, keep: int | None = None) -> None:
        self.listbox.delete(0, "end")
        self.reports = self.app.db.fit_reports(200)
        for r in self.reports:
            label = (f'{r["at"][:16].replace("T", " ")}  '
                     f'{KIND_LABEL.get(r["kind"], r["kind"])}')
            self.listbox.insert("end", label)
        self.count.configure(text=f"共 {len(self.reports)} 份")
        if not self.reports:
            self._show("还没有报告。")
            return
        idx = 0 if keep is None else min(keep, len(self.reports) - 1)
        self.listbox.selection_set(idx)
        self.listbox.activate(idx)
        self._show(self.reports[idx]["content"])

    def _delete(self) -> None:
        sel = self.listbox.curselection()
        if not sel or not self.reports:
            return
        idx = sel[0]
        r = self.reports[idx]
        label = f'{r["at"][:16].replace("T", " ")} {KIND_LABEL.get(r["kind"], r["kind"])}'
        if not messagebox.askyesno("删除报告", f"确定删除这份报告吗？\n\n{label}",
                                   parent=self.win):
            return
        self.app.db.fit_report_delete(r["id"])
        self._reload(keep=idx)

    def _on_pick(self, _evt=None) -> None:
        sel = self.listbox.curselection()
        if not sel:
            return
        self._show(self.reports[sel[0]]["content"])

    def _show(self, content: str) -> None:
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.insert("1.0", content)
        self.text.configure(state="disabled")
