"""错题本页 (英语 / 日语合并在同一页, 用分页切换).

复习规则: 某个词在 day0 出错, 则在 day+1 / +3 / +7 / +15 / +30 必然出现;
30 天内没有再错则移出错题本; 期间再次出错则重置回 day0。
"""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from .. import config as C
from ..db import today
from . import theme
from .widgets import FlatButton, style_treeview

OFFSETS = "、".join(f"+{d}" for d in C.REVIEW_OFFSETS)
LANGS = (("en", "英语"), ("jp", "日语"))


class MistakeFrame(tk.Frame):
    """英语 / 日语两个错题本, 分页展示, 操作按钮对当前分页生效."""

    def __init__(self, master, app):
        super().__init__(master, bg=theme.BG)
        self.grid(row=0, column=0, sticky="nsew")
        self.app = app
        self.trees: dict[str, ttk.Treeview] = {}
        style_treeview(self)
        self._build()

    # ------------------------------------------------------------ 构建
    def _build(self) -> None:
        head = tk.Frame(self, bg=theme.BG)
        head.pack(fill="x", padx=30, pady=(22, 6))
        FlatButton(head, "← 返回", lambda: self.app.show("menu"), bg=theme.BG,
                   hover=theme.CARD, font=theme.f(11), padx=12, pady=7).pack(side="left")
        tk.Label(head, text="错题本", bg=theme.BG, fg=theme.TEXT,
                 font=theme.f(16, "bold")).pack(side="left", padx=14)
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
        self.tabs: dict[str, tk.Frame] = {}
        self.done_trees: dict[str, ttk.Treeview] = {}
        for lang, name in LANGS:
            tab = self._make_lang_tab(nb, lang, name)
            self.tabs[lang] = tab
        # 切换分页要重新载入, 否则另一页一直是空的
        nb.bind("<<NotebookTabChanged>>", lambda e: self.on_show())

        bar = tk.Frame(self, bg=theme.BG)
        bar.pack(fill="x", padx=30, pady=(0, 18))
        FlatButton(bar, "立即复习（并入今日）", self._review_now, bg=theme.CARD,
                   font=theme.f(11), pady=9).pack(side="left")
        FlatButton(bar, "移出错题本", self._remove, bg=theme.CARD,
                   font=theme.f(11), pady=9).pack(side="left", padx=10)
        FlatButton(bar, "刷新", lambda: self.on_show(), bg=theme.CARD,
                   font=theme.f(11), pady=9).pack(side="right")

    def _make_lang_tab(self, nb, lang: str, title: str) -> tk.Frame:
        outer = tk.Frame(nb, bg=theme.BG)
        nb.add(outer, text=title)

        inner = ttk.Notebook(outer)
        inner.pack(fill="both", expand=True, pady=(6, 0))
        cols = ("word", "meaning", "detail", "errors", "anchor", "due", "stage")
        heads = ("单词", "中文意思", "音标 / 声调", "出错次数", "day0", "下次复习", "复习进度")
        widths = (150, 300, 210, 80, 100, 100, 90)

        trees = []
        for key, tab_title in (("open", "错题本中"), ("done", "已移出")):
            tab = tk.Frame(inner, bg=theme.CARD)
            inner.add(tab, text=tab_title)
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
            trees.append(tree)

        self.trees[lang], self.done_trees[lang] = trees
        outer._nb = inner        # type: ignore[attr-defined]
        outer._lang = lang       # type: ignore[attr-defined]
        return outer

    # ------------------------------------------------------------ 数据
    def _current_lang(self) -> str:
        """当前显示的是英语页还是日语页."""
        idx = self.nb.index(self.nb.select()) if self.nb.tabs() else 0
        return LANGS[idx][0]

    def _open_tree(self, lang: str) -> ttk.Treeview:
        return self.trees[lang]

    def on_show(self, **_):
        db = self.app.db
        t = today()
        due_total = 0
        total = 0

        for lang, _name in LANGS:
            tree = self.trees[lang]
            tree.delete(*tree.get_children())
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
                tree.insert(
                    "", "end",
                    values=(
                        w["word"], w["meaning"], detail, r["error_count"],
                        r["anchor_date"], r["next_due"],
                        f"{r['stage']}/{len(C.REVIEW_OFFSETS)}",
                    ),
                    tags=("due",) if is_due else ("ok",),
                )

            done_tree = self.done_trees[lang]
            done_tree.delete(*done_tree.get_children())
            for r in db.graduated_mistakes(lang):
                w = db.get_word(lang, r["word_id"])
                if w is None:
                    continue
                done_tree.insert(
                    "", "end",
                    values=(w["word"], w["meaning"],
                            (w["ipa"] if lang == "en" else w["accent"]) or "—",
                            r["error_count"], r["anchor_date"], "—", "已毕业"),
                )
            total += len(rows)
            due_total += due_n

            # 分页标题上带数量, 不切页也能看到另一门语言的情况
            idx = [l for l, _ in LANGS].index(lang)
            self.nb.tab(idx, text=f"{LANGS[idx][1]}（{len(rows)}）")

        self.summary.configure(
            text=f"在册 {total} 个　今日待复习 {due_total} 个")

    # ------------------------------------------------------------ 操作
    def _selected(self, tree: ttk.Treeview, lang: str):
        sel = tree.selection()
        if not sel:
            messagebox.showinfo("提示", "请先在列表中选择一个单词。", parent=self)
            return None
        word = tree.item(sel[0], "values")[0]
        row = self.app.db.conn.execute(
            f"SELECT id FROM {'en_words' if lang == 'en' else 'jp_words'} WHERE word=?",
            (word,),
        ).fetchone()
        return row["id"] if row else None

    def _review_now(self) -> None:
        lang = self._current_lang()
        wid = self._selected(self._open_tree(lang), lang)
        if wid is None:
            return
        # 把该词的复习日提前到今天, 并只把这一个词补进今日计划
        self.app.db.conn.execute(
            "UPDATE mistakes SET next_due=? WHERE lang=? AND word_id=?",
            (today(), lang, wid),
        )
        self.app.db.conn.commit()
        # 不能重建计划, 否则当天已答的记录会被清空
        self.app.db.add_to_today(lang, wid)
        self.on_show()
        messagebox.showinfo("已加入", "该词已并入今日复习，进入词汇页即可看到。", parent=self)

    def _remove(self) -> None:
        lang = self._current_lang()
        wid = self._selected(self._open_tree(lang), lang)
        if wid is None:
            return
        if not messagebox.askyesno("确认", "确定要把该单词移出错题本吗？", parent=self):
            return
        self.app.db.remove_mistake(lang, wid)
        self.app.db.remove_from_today(lang, wid)
        self.on_show()
