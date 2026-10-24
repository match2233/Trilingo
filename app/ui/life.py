"""生活记录入口页: 【记账】与【记鹿】.

说明: 这两部分数据只存本机 SQLite (ledger / deer 两张表), 不写进 events/base,
因此不会随 GitHub 同步到手机 —— 这是刻意的, 生活记录属于私人数据。
"""
from __future__ import annotations

import datetime as dt
import tkinter as tk

from . import theme
from .widgets import Card, FlatButton


class LifeFrame(tk.Frame):
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
        tk.Label(head, text="生活记录", bg=theme.BG, fg=theme.TEXT,
                 font=theme.f(16, "bold")).pack(side="left", padx=14)
        self.summary = tk.Label(head, text="", bg=theme.BG, fg=theme.MUTED, font=theme.f(10))
        self.summary.pack(side="right")

        tk.Label(self, text="仅保存在本机，不参与跨设备同步",
                 bg=theme.BG, fg=theme.MUTED, font=theme.f(9)).pack(anchor="w", padx=32)

        grid = tk.Frame(self, bg=theme.BG)
        grid.pack(fill="both", expand=True, padx=30, pady=(14, 26))
        grid.grid_rowconfigure(0, weight=1)
        for c in (0, 1):
            grid.grid_columnconfigure(c, weight=1, uniform="life")

        self.tiles: dict[str, tuple[Card, FlatButton]] = {}
        self._tile(grid, 0, "ledger", "记账", "收入 · 支出 · 账单明细", "¥",
                   theme.PRIMARY, theme.PRIMARY_SOFT)
        self._tile(grid, 1, "deer", "记鹿", "每天记一次 · 月历/年历统计", "🦌",
                   theme.SUCCESS, theme.SUCCESS_SOFT)

    def _tile(self, parent, col, key, title, sub, glyph, color, soft) -> None:
        """整张卡片都是点击热区, 且悬停时整块方框一起染色.

        原来 FlatButton 只覆盖"标题+副标题"那一条, 鼠标移到图标或留白上
        既没有高亮也不能点 —— 看起来像只有文字能点进去。
        """
        card = Card(parent)
        card.grid(row=0, column=col, sticky="nsew",
                  padx=(0, 10) if col == 0 else (10, 0))
        box = tk.Frame(card, bg=theme.CARD)
        box.pack(fill="both", expand=True)

        mark = tk.Label(box, text=glyph, bg=theme.CARD, fg=color,
                        font=theme.f(46, "bold"))
        mark.pack(expand=True)
        btn = FlatButton(box, title, lambda k=key: self.app.show(k),
                         bg=theme.CARD, hover=soft, active_bg=soft,
                         font=theme.f(23, "bold"), fg=color, pady=8)
        btn.pack(fill="x", padx=2)
        btn.set_subtitle(sub)
        btn.configure(highlightbackground=theme.CARD)
        spacer = tk.Frame(box, bg=theme.CARD)
        spacer.pack(expand=True, fill="both")

        # 卡片、图标、留白全部纳入同一组高亮 + 同一个动作
        btn.bind_hover_group(card, box, mark, spacer)
        for w in (card, box, mark, spacer):
            w.bind("<Button-1>", lambda e, k=key: self.app.show(k))
        self.tiles[key] = (card, btn)

    # ------------------------------------------------------------ 刷新
    def on_show(self, **_):
        from .. import config as C

        db = self.app.db
        parts = []
        for cur in C.CURRENCIES:
            t = db.ledger_totals(cur)
            if t["income"] or t["expense"]:
                parts.append(f"{C.CURRENCY_SIGN[cur]}{C.fmt_money(t['balance'], cur)}")
        y, m = _ym_today()
        month = db.deer_month(y, m)
        if month:
            parts.append(f"本月 {sum(month.values())} 次")
        self.summary.configure(text="　·　".join(parts) if parts else "还没有记录")


def _ym_today() -> tuple[int, int]:
    t = dt.date.today()
    return t.year, t.month
