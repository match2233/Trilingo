"""日语测试: 试卷集列表 (一级入口).

一行一个试卷集, 比如「新标日初级上单元测试」「JLPT-N5」。
点进去才是该试卷集的卷子列表; 收藏夹、导入试卷都挂在那一层,
不同试卷集之间互不干扰。
"""
from __future__ import annotations

import tkinter as tk

from .. import exams
from . import theme
from .widgets import Card, FlatButton, center_window


KIND_TAG = {"unit": ("单元卷", theme.PRIMARY, theme.PRIMARY_SOFT),
            "jlpt": ("能力考", theme.BLUE, theme.BLUE_SOFT)}


class ExamPickerFrame(tk.Frame):
    def __init__(self, master, app):
        super().__init__(master, bg=theme.BG)
        self.app = app
        self.grid(row=0, column=0, sticky="nsew")

        head = tk.Frame(self, bg=theme.BG)
        head.pack(fill="x", padx=24, pady=(16, 4))
        FlatButton(head, "← 返回", lambda: self.app.show("menu"), bg=theme.CARD,
                   font=theme.f(11), padx=12, pady=6).pack(side="left")
        tk.Label(head, text="日语测试", bg=theme.BG, fg=theme.TEXT,
                 font=theme.f(20, "bold")).pack(side="left", padx=14)
        self.summary = tk.Label(head, text="", bg=theme.BG, fg=theme.MUTED,
                                font=theme.f(11))
        self.summary.pack(side="right")
        FlatButton(head, "导入试卷", self._import, bg=theme.PRIMARY, fg="#FFFFFF",
                   hover=theme.PRIMARY_DARK, active_bg=theme.PRIMARY_DARK,
                   border=theme.PRIMARY, font=theme.f(11, "bold"),
                   padx=16, pady=6).pack(side="right", padx=(0, 12))

        self.list = tk.Frame(self, bg=theme.BG)
        self.list.pack(fill="both", expand=True, padx=24, pady=(8, 20))

    # ------------------------------------------------------------ 渲染
    def on_show(self, **_):
        for w in self.list.winfo_children():
            w.destroy()
        cols = exams.all_collections()
        papers = sum(c["papers"] for c in cols)
        items = sum(c["items"] for c in cols)
        self.summary.configure(text=f"{len(cols)} 套试卷集　·　{papers} 份卷子　·　{items} 题")
        if not cols:
            tk.Label(self.list, text="还没有试卷集，点右上角【导入试卷】开始。",
                     bg=theme.BG, fg=theme.MUTED, font=theme.f(12)).pack(pady=40)
            return
        for meta in cols:
            self._row(meta)

    def _row(self, meta: dict) -> None:
        card = Card(self.list)
        card.pack(fill="x", pady=5)
        inner = tk.Frame(card, bg=theme.CARD)
        inner.pack(fill="x", padx=16, pady=12)

        left = tk.Frame(inner, bg=theme.CARD)
        left.pack(side="left", fill="x", expand=True)
        title = tk.Frame(left, bg=theme.CARD)
        title.pack(anchor="w")
        tag, fg, soft = KIND_TAG.get(meta.get("kind"), ("试卷", theme.MUTED, theme.BG))
        tk.Label(title, text=tag, bg=soft, fg=fg, font=theme.f(9, "bold"),
                 padx=6).pack(side="left", padx=(0, 8))
        tk.Label(title, text=meta["name"], bg=theme.CARD, fg=theme.TEXT,
                 font=theme.f(17, "bold")).pack(side="left")

        sub = f'{meta["papers"]} 份卷子　·　{meta["items"]} 题'
        if meta.get("duration_min"):
            sub += f'　·　限时 {meta["duration_min"]} 分钟'
        if meta.get("desc"):
            sub += f'　·　{meta["desc"]}'
        tk.Label(left, text=sub, bg=theme.CARD, fg=theme.MUTED,
                 font=theme.f(11)).pack(anchor="w", pady=(4, 0))

        FlatButton(inner, "进入", lambda c=meta["id"]: self._enter(c),
                   bg=theme.CARD, hover=soft, active_bg=soft, fg=fg,
                   font=theme.f(12, "bold"), padx=20, pady=8).pack(side="right")

    # ------------------------------------------------------------ 动作
    def _enter(self, cid: str) -> None:
        self.app.show("minna", collection=cid)

    def _import(self) -> None:
        from .import_exam import ImportExamDialog

        ImportExamDialog(self, self.app, on_done=self.on_show)
