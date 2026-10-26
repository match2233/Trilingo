"""新标日测试: 24 课的列表页.

每课一整行按钮, 从左到右: 第几课 / 完成进度(进度条) / 完成时间 / 成绩。
点进去开始答题; 已经做完的课直接显示整张试卷。
"""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox

from .. import minna
from . import theme
from .widgets import Card, FlatButton, ProgressBar, ScrollFrame


class MinnaListFrame(tk.Frame):
    def __init__(self, master, app):
        super().__init__(master, bg=theme.BG)
        self.grid(row=0, column=0, sticky="nsew")
        self.app = app
        self.collection = "shinbunpo-1"
        self._rows: dict[int, dict] = {}
        self._build()

    # ------------------------------------------------------------ 构建
    def _build(self) -> None:
        head = tk.Frame(self, bg=theme.BG)
        head.pack(fill="x", padx=22, pady=(14, 2))
        FlatButton(head, "← 返回", lambda: self.app.show("exams"), bg=theme.CARD,
                   font=theme.f(11), padx=12, pady=6).pack(side="left")
        self.title = tk.Label(head, text="日语测试", bg=theme.BG, fg=theme.TEXT,
                              font=theme.f(19, "bold"))
        self.title.pack(side="left", padx=14)
        self.summary = tk.Label(head, text="", bg=theme.BG, fg=theme.MUTED,
                                font=theme.f(11))
        self.summary.pack(side="right")
        self.fav_btn = FlatButton(head, "收藏夹", lambda: self.app.show("minna_fav"),
                                  bg=theme.CARD, font=theme.f(11), padx=14, pady=6)
        self.fav_btn.pack(side="right", padx=(0, 10))

        # 列标题: 与下面的行对齐
        cols = tk.Frame(self, bg=theme.BG)
        cols.pack(fill="x", padx=36, pady=(6, 2))
        tk.Label(cols, text="试卷", bg=theme.BG, fg=theme.MUTED,
                 font=theme.f(10, "bold"), width=7, anchor="w").pack(side="left")
        tk.Label(cols, text="完成进度", bg=theme.BG, fg=theme.MUTED,
                 font=theme.f(10, "bold")).pack(side="left", padx=(6, 40))
        tk.Label(cols, text="成绩", bg=theme.BG, fg=theme.MUTED,
                 font=theme.f(10, "bold"), width=11).pack(side="right")
        tk.Label(cols, text="完成时间", bg=theme.BG, fg=theme.MUTED,
                 font=theme.f(10, "bold"), width=10).pack(side="right")

        sc = ScrollFrame(self)
        sc.pack(fill="both", expand=True, padx=22, pady=(2, 12))
        self.scroll = sc
        self._list_parent = sc.body

        # 版权标注: 题库是从出版教辅转录的, 注明来源
        tk.Label(self, justify="left", anchor="w", bg=theme.BG, fg=theme.MUTED,
                 font=theme.f(9),
                 text="题库来源：《新版中日交流标准日本语（初级上）同步测试卷》"
                      "（版权归原出版方所有，仅供个人学习使用）",
                 ).pack(fill="x", padx=24, pady=(0, 10))

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
        btn._label.pack_forget()          # 用自绘的一行替掉默认文字

        row = tk.Frame(btn, bg=theme.CARD)
        row.pack(fill="x", padx=12, pady=7)

        # 标题: 单元卷用"第 N 课", 真题卷用"2016年 / 2012年12月"这种
        label = les.get("title") or f"第 {num} 课"
        name = tk.Label(row, text=label, bg=theme.CARD, fg=theme.TEXT,
                        font=theme.f(13, "bold"), width=12, anchor="w")
        name.pack(side="left")

        bar = ProgressBar(row, width=190, height=9)
        bar.pack(side="left", padx=(6, 10))
        pct = tk.Label(row, text="未开始", bg=theme.CARD, fg=theme.MUTED,
                       font=theme.f(10), width=9, anchor="w")
        pct.pack(side="left")

        score = tk.Label(row, text="—", bg=theme.CARD, fg=theme.MUTED,
                         font=theme.f(13, "bold"), width=11)
        score.pack(side="right")
        spent = tk.Label(row, text="—", bg=theme.CARD, fg=theme.MUTED,
                         font=theme.f(11), width=10)
        spent.pack(side="right")
        # 重置这一套的进度 (先问一句, 免得误点)
        reset = tk.Label(row, text="重置", bg=theme.SUNK, fg=theme.MUTED,
                         font=theme.f(10), cursor="hand2", padx=8, pady=2,
                         highlightthickness=1,
                         highlightbackground=theme.BORDER)
        reset.pack(side="right", padx=(0, 10))
        reset.bind("<Button-1>", lambda e, n=num, t=label: self._reset(n, t))
        reset.bind("<Enter>", lambda e: reset.configure(bg=theme.PRIMARY_SOFT,
                                                        fg=theme.PRIMARY))
        reset.bind("<Leave>", lambda e: reset.configure(bg=theme.SUNK,
                                                        fg=theme.MUTED))

        # 整行(含进度条与所有文字)一起高亮 + 一起可点
        # 注意: 不要把 reset 放进 hover 组, 否则它的点击会被覆盖成"进入这一课"
        btn.bind_hover_group(row, name, pct, score, spent, bar)
        self._rows[num] = {"bar": bar, "pct": pct, "score": score,
                           "spent": spent, "label": name, "btn": btn}

    # ------------------------------------------------------------ 生命周期
    def _reset(self, num: int, label: str) -> None:
        if not messagebox.askyesno("重置", f"清空「{label}」的作答记录？",
                                   parent=self):
            return
        self.app.db.minna_reset(num)
        self.on_show(collection=self.collection)

    def _switch(self, cid: str) -> None:
        """切到某个试卷集: 读题库、告诉 db 当前在哪套卷子、重建列表行."""
        from .. import exams

        self.collection = cid
        bank = exams.load(cid)
        minna.use(bank)
        self.app.db.set_collection(cid)
        meta = (bank or {}).get("meta") or exams.DEFAULT_META
        self.title.configure(text=meta.get("name") or "日语测试")
        self.fav_btn_meta = meta
        for w in getattr(self, "_list_parent", self).winfo_children():
            w.destroy()
        self._rows.clear()
        for les in minna.lessons():
            self._make_row(self._list_parent, les)
        if not minna.lessons():
            tk.Label(self._list_parent, bg=theme.BG, fg=theme.MUTED,
                     font=theme.f(12), justify="left", anchor="w",
                     text="这套试卷还没有卷子。",
                     ).pack(fill="x", padx=14, pady=30)

    def on_show(self, collection: str | None = None, **_):
        self._switch(collection or self.collection)
        prog = self.app.db.minna_all_progress()
        all_les = minna.lessons()
        done = 0
        for les in all_les:
            num = les["lesson"]
            row = self._rows.get(num)
            if row is None:
                continue
            p = prog.get(num)
            total = minna.total_items(les) or 1
            if p is None or p["status"] == "idle":
                row["bar"].set(0.0, theme.BORDER)
                row["pct"].configure(text="未开始", fg=theme.MUTED)
                row["score"].configure(text="—", fg=theme.MUTED)
                row["spent"].configure(text="—")
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
            text=f"共 {len(all_les)} 课　已完成 {done} 课"
                 + ("　·　第 24 课原卷未附答案，按自评计"
                    if any(l.get("no_answer") for l in all_les) else ""))

    def _enter(self, num: int) -> None:
        p = self.app.db.minna_progress(num)
        self.app.show("minna_test", lesson=num,
                      resume=bool(p and p["status"] == "doing"),
                      review=bool(p and p["status"] == "done"))
