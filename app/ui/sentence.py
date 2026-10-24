"""句子练习 (占位页).

功能尚未开发, 先给出入口与说明, 免得主界面上少一个按钮。
"""
from __future__ import annotations

import tkinter as tk

from . import theme
from .widgets import Card, FlatButton


class SentenceFrame(tk.Frame):
    def __init__(self, master, app):
        super().__init__(master, bg=theme.BG)
        self.grid(row=0, column=0, sticky="nsew")
        self.app = app
        self._build()

    def _build(self) -> None:
        head = tk.Frame(self, bg=theme.BG)
        head.pack(fill="x", padx=30, pady=(22, 6))
        FlatButton(head, "← 返回", lambda: self.app.show("menu"), bg=theme.BG,
                   hover=theme.CARD, font=theme.f(11), padx=12, pady=7).pack(side="left")
        tk.Label(head, text="句子练习", bg=theme.BG, fg=theme.TEXT,
                 font=theme.f(16, "bold")).pack(side="left", padx=14)

        card = Card(self)
        card.pack(fill="both", expand=True, padx=30, pady=(10, 26))
        box = tk.Frame(card, bg=theme.CARD)
        box.place(relx=0.5, rely=0.45, anchor="center")
        tk.Label(box, text="🚧", bg=theme.CARD, fg=theme.MUTED,
                 font=theme.f(52)).pack()
        tk.Label(box, text="句子练习还在开发中", bg=theme.CARD, fg=theme.TEXT,
                 font=theme.f(18, "bold")).pack(pady=(10, 4))
        tk.Label(box, text="这部分先留个入口，后续版本再加。", bg=theme.CARD,
                 fg=theme.MUTED, font=theme.f(11)).pack()
