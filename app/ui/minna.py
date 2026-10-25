"""试卷列表页 (某个试卷集下的一套套试卷).

每套一整行按钮, 从左到右: 名称 / 进度条 / 完成时间 / 成绩。
点进去开始答题; 已经做完的直接显示整张试卷。
右上角是本试卷集专属的收藏夹。
"""
from __future__ import annotations

import tkinter as tk

from .. import minna
from . import theme
from .widgets import Card, FlatButton, ProgressBar, ScrollFrame


class MinnaListFrame(tk.Frame):
    def __init__(self, master, app):
        super().__init__(master, bg=theme.BG)
        self.grid(row=0, column=0, sticky="nsew")
        self.app = app
        self.coll_id: str | None = None
        self._rows: dict[int, dict] = {}
        self._build()

    # ------------------------------------------------------------ 构建
    def _build(self) -> None:
        head = tk.Frame(self, bg=theme.BG)
        head.pack(fill="x", padx=22, pady=(14, 2))
        FlatButton(head, "← 返回", lambda: self.app.show("jp_tests"), bg=theme.CARD,
                   font=theme.f(11), padx=12, pady=6).pack(side="left")
        self.title = tk.Label(head, text="", bg=theme.BG, fg=theme.TEXT,
                              font=theme.f(19, "bold"))
        self.title.pack(side="left", padx=14)
        self.summary = tk.Label(head, text="", bg=theme.BG, fg=theme.MUTED,
                                font=theme.f(11))
        self.summary.pack(side="right")
        self.fav_btn = FlatButton(head, "收藏夹", self._open_fav, bg=theme.CARD,
                                  font=theme.f(11), padx=14, pady=6)
        self.fav_btn.pack(side="right", padx=(0, 12))

        cols = tk.Frame(self, bg=theme.BG)
        cols.pack(fill="x", padx=36, pady=(6, 2))
        tk.Label(cols, text="试卷", bg=theme.BG, fg=theme.MUTED,
                 font=theme.f(10, "bold"), width=16, anchor="w").pack(side="left")
        tk.Label(cols, text="完成进度", bg=theme.BG, fg=theme.MUTED,
                 font=theme.f(10, "bold")).pack(side="left", padx=(6, 40))
        tk.Label(cols, text="成绩", bg=theme.BG, fg=theme.MUTED,
                 font=theme.f(10, "bold"), width=11).pack(side="right")
        tk.Label(cols, text="用时/限时", bg=theme.BG, fg=theme.MUTED,
                 font=theme.f(10, "bold"), width=12).pack(side="right")

        self.scroll = ScrollFrame(self)
        self.scroll.pack(fill="both", expand=True, padx=22, pady=(2, 12))

        self.note = tk.Label(self, justify="left", anchor="w", bg=theme.BG,
                             fg=theme.MUTED, font=theme.f(9), text="",
                             wraplength=900)
        self.note.pack(fill="x", padx=24, pady=(0, 10))

    # ------------------------------------------------------------ 行
    def _make_row(self, parent, les: dict) -> None:
        num = les["lesson"]
        card = Card(parent)
        card.pack(fill="x", pady=2)

        btn = FlatButton(card, "", lambda n=num: self._enter(n),
                         bg=theme.CARD, hover=theme.PRIMARY_SOFT,
                         active_bg=theme.PRIMARY_SOFT, font=theme.f(11),
                         padx=0, pady=0, border=theme.CARD)
        btn.pack(fill="x")
        btn.configure(highlightbackground=theme.CARD)
        btn._label.pack_forget()

        row = tk.Frame(btn, bg=theme.CARD)
        row.pack(fill="x", padx=12, pady=7)

        name = tk.Label(row, text=les.get("title") or f"第 {num} 课",
                        bg=theme.CARD, fg=theme.TEXT, font=theme.f(13, "bold"),
                        width=16, anchor="w")
        name.pack(side="left")

        bar = ProgressBar(row, width=170, height=9)
        bar.pack(side="left", padx=(6, 10))
        pct = tk.Label(row, text="未开始", bg=theme.CARD, fg=theme.MUTED,
                       font=theme.f(10), width=9, anchor="w")
        pct.pack(side="left")

        score = tk.Label(row, text="—", bg=theme.CARD, fg=theme.MUTED,
                         font=theme.f(13, "bold"), width=11)
        score.pack(side="right")
        spent = tk.Label(row, text="—", bg=theme.CARD, fg=theme.MUTED,
                         font=theme.f(11), width=12)
        spent.pack(side="right")

        btn.bind_hover_group(row, name, pct, score, spent, bar)
        self._rows[num] = {"bar": bar, "pct": pct, "score": score,
                           "spent": spent, "label": name, "btn": btn}

    # ------------------------------------------------------------ 生命周期
    def on_show(self, coll: str | None = None, **_):
        col = minna.collection(coll) or minna.collection(self.coll_id) \
            or (minna.collections() or [None])[0]
        if not col:
            return
        self.coll_id = col["id"]
        minna.set_current(col["id"])
        self.title.configure(text=col.get("name", "试卷"))
        self.fav_btn.set_text("收藏夹")

        # 重建行 (换试卷集时列表长度会变)
        for w in self.scroll.body.winfo_children():
            w.destroy()
        self._rows.clear()
        all_les = minna.lessons(col["id"])
        for les in all_les:
            self._make_row(self.scroll.body, les)

        prog = self.app.db.minna_all_progress()
        done = 0
        for les in all_les:
            num = les["lesson"]
            row = self._rows.get(num)
            if row is None:
                continue
            p = prog.get(num)
            total = minna.total_items(les) or 1
            limit = int(les.get("minutes") or 0)
            limit_txt = minna.fmt_clock(limit * 60) if limit else "不限时"
            if p is None or p["status"] == "idle":
                row["bar"].set(0.0, theme.BORDER)
                row["pct"].configure(text="未开始", fg=theme.MUTED)
                row["score"].configure(text="—", fg=theme.MUTED)
                row["spent"].configure(text=limit_txt)
                continue
            got = len(self.app.db.minna_results(num))
            ratio = got / total
            if p["status"] == "doing":
                row["bar"].set(ratio, theme.BLUE)
                row["pct"].configure(text=f"{got}/{total}", fg=theme.BLUE)
                row["score"].configure(text="进行中", fg=theme.BLUE)
                row["spent"].configure(text=minna.fmt_seconds(p["seconds"]))
                continue
            done += 1
            row["bar"].set(ratio, theme.SUCCESS)
            row["pct"].configure(text=f"{got}/{total}", fg=theme.SUCCESS)
            sc, tt = p["score"], p["total"] or total
            row["score"].configure(
                text=f"{sc}/{tt}",
                fg=theme.SUCCESS if sc * 2 >= tt else theme.ERROR)
            row["spent"].configure(text=minna.fmt_seconds(p["seconds"]))

        self.summary.configure(
            text=f"共 {len(all_les)} 套　已完成 {done} 套")
        self.note.configure(text=col.get("note") or "")

    def _open_fav(self) -> None:
        self.app.show("minna_fav", coll=self.coll_id)

    def _enter(self, num: int) -> None:
        p = self.app.db.minna_progress(num)
        self.app.show("minna_test", lesson=num,
                      resume=bool(p and p["status"] == "doing"),
                      review=bool(p and p["status"] == "done"))
