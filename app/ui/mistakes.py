"""错题本页 (英语 / 日语共用).

复习规则: 某个词在 day0 出错, 则在 day+1 / +3 / +7 / +15 / +30 必然出现;
30 天内没有再错则移出错题本; 期间再次出错则重置回 day0.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from .. import config as C
from ..db import add_days, today
from . import theme
from .widgets import FlatButton, style_treeview

OFFSETS = "、".join(f"+{d}" for d in C.REVIEW_OFFSETS)


class MistakeFrame(tk.Frame):
    def __init__(self, master, app, lang: str):
        super().__init__(master, bg=theme.BG)
        self.grid(row=0, column=0, sticky="nsew")
        self.app = app
        self.lang = lang
        style_treeview(self)
        self._build()

    # ------------------------------------------------------------ 构建
    def _build(self) -> None:
        head = tk.Frame(self, bg=theme.BG)
        head.pack(fill="x", padx=30, pady=(22, 6))
        FlatButton(head, "← 返回", lambda: self.app.show("menu"), bg=theme.BG,
                   hover=theme.CARD, font=theme.f(11), padx=12, pady=7).pack(side="left")
        tk.Label(head, text=f"错题本（{'英' if self.lang == 'en' else '日'}）",
                 bg=theme.BG, fg=theme.TEXT, font=theme.f(16, "bold")).pack(side="left", padx=14)
        self.summary = tk.Label(head, text="", bg=theme.BG, fg=theme.MUTED, font=theme.f(10))
        self.summary.pack(side="right")

        tk.Label(
            self, text=f"规则：出错当天记为 day0，此后 day{OFFSETS} 必然重现；"
                       "连续 30 天不再出错即移出错题本，中途再错则重置 day0。",
            bg=theme.BG, fg=theme.MUTED, font=theme.f(9),
        ).pack(anchor="w", padx=32, pady=(0, 8))

        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=30, pady=(0, 8))
        self.nb = nb

        self.open_tab, self.open_tree = self._make_tab(nb, "错题本中")
        self.done_tab, self.done_tree = self._make_tab(nb, "已移出")

        bar = tk.Frame(self, bg=theme.BG)
        bar.pack(fill="x", padx=30, pady=(0, 18))
        FlatButton(bar, "立即复习（并入今日）", self._review_now, bg=theme.CARD,
                   font=theme.f(11), pady=9).pack(side="left")
        FlatButton(bar, "移出错题本", self._remove, bg=theme.CARD,
                   font=theme.f(11), pady=9).pack(side="left", padx=10)
        FlatButton(bar, "刷新", lambda: self.on_show(), bg=theme.CARD,
                   font=theme.f(11), pady=9).pack(side="right")

    def _make_tab(self, nb, title):
        tab = tk.Frame(nb, bg=theme.CARD)
        nb.add(tab, text=title)
        cols = ("word", "meaning", "detail", "errors", "anchor", "due", "stage")
        heads = ("单词", "中文意思", "音标 / 声调", "出错次数", "day0", "下次复习", "复习进度")
        widths = (150, 300, 210, 80, 100, 100, 90)
        tree = ttk.Treeview(tab, columns=cols, show="headings", selectmode="browse")
        for c, h, w in zip(cols, heads, widths):
            tree.heading(c, text=h)
            tree.column(c, width=w, minwidth=60,
                        anchor="w" if c in ("word", "meaning", "detail") else "center")
        vs = ttk.Scrollbar(tab, orient="vertical", command=tree.yview)
        hs = ttk.Scrollbar(tab, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=vs.set, xscrollcommand=hs.set)
        hs.pack(side="bottom", fill="x", padx=6, pady=(0, 6))
        vs.pack(side="right", fill="y", pady=6, padx=(0, 6))
        tree.pack(side="left", fill="both", expand=True, padx=(6, 0), pady=6)
        tree.tag_configure("due", foreground=theme.ERROR)
        tree.tag_configure("ok", foreground=theme.MUTED)
        return tab, tree

    # ------------------------------------------------------------ 数据
    def on_show(self, **_):
        lang = self.lang
        db = self.app.db
        t = today()

        self.open_tree.delete(*self.open_tree.get_children())
        rows = db.open_mistakes(lang)
        due_n = 0
        for r in rows:
            w = db.get_word(lang, r["word_id"])
            if w is None:
                continue
            is_due = r["next_due"] <= t
            due_n += 1 if is_due else 0
            detail = (w["ipa"] if lang == "en" else w["accent"]) or "—"
            if lang == "jp" and w["reading"]:
                detail = f"{detail}　{w['reading']}"
            self.open_tree.insert(
                "", "end",
                values=(
                    w["word"], w["meaning"], detail, r["error_count"],
                    r["anchor_date"], r["next_due"],
                    f"{r['stage']}/{len(C.REVIEW_OFFSETS)}",
                ),
                tags=("due",) if is_due else ("ok",),
            )

        self.done_tree.delete(*self.done_tree.get_children())
        for r in db.graduated_mistakes(lang):
            w = db.get_word(lang, r["word_id"])
            if w is None:
                continue
            self.done_tree.insert(
                "", "end",
                values=(w["word"], w["meaning"],
                        (w["ipa"] if lang == "en" else w["accent"]) or "—",
                        r["error_count"], r["anchor_date"], "—", "已毕业"),
            )

        self.summary.configure(
            text=f"在册 {len(rows)} 个　今日待复习 {due_n} 个　已移出 {len(self.done_tree.get_children())} 个"
        )

    # ------------------------------------------------------------ 操作
    def _selected(self, tree):
        sel = tree.selection()
        if not sel:
            messagebox.showinfo("提示", "请先在列表中选择一个单词。", parent=self)
            return None
        word = tree.item(sel[0], "values")[0]
        row = self.app.db.conn.execute(
            f"SELECT id FROM {'en_words' if self.lang=='en' else 'jp_words'} WHERE word=?",
            (word,),
        ).fetchone()
        return row["id"] if row else None

    def _review_now(self) -> None:
        wid = self._selected(self.open_tree)
        if wid is None:
            return
        # 把该词的复习日提前到今天, 并重新生成今日计划
        self.app.db.conn.execute(
            "UPDATE mistakes SET next_due=? WHERE lang=? AND word_id=?",
            (today(), self.lang, wid),
        )
        self.app.db.conn.commit()
        # 只把这一个词补进今日计划; 不能重建计划, 否则当天已答的记录会被清空
        self.app.db.add_to_today(self.lang, wid)
        self.on_show()
        messagebox.showinfo("已加入", "该词已并入今日复习，进入词汇页即可看到。", parent=self)

    def _remove(self) -> None:
        wid = self._selected(self.open_tree)
        if wid is None:
            return
        if not messagebox.askyesno("确认", "确定要把该单词移出错题本吗？", parent=self):
            return
        self.app.db.remove_mistake(self.lang, wid)
        self.app.db.remove_from_today(self.lang, wid)
        self.on_show()
