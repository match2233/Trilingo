"""数据库页: 以表格显示全部单词, 支持排序、检索与人工修改并保存."""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from .. import config as C
from ..db import today
from . import theme
from .widgets import Card, FlatButton, style_treeview

EN_COLS = [
    ("word", "单词", 160, "w"),
    ("meaning", "中文意思", 330, "w"),
    ("ipa", "美式音标", 230, "w"),
    ("source", "数据来源", 150, "center"),
    ("times", "学习次数", 80, "center"),
    ("last", "最后学习", 100, "center"),
    ("active", "状态", 90, "center"),
]
JP_COLS = [
    ("word", "单词", 160, "w"),
    ("reading", "假名读音", 180, "w"),
    ("meaning", "中文意思", 330, "w"),
    ("accent", "声调", 90, "center"),
    ("source", "数据来源", 150, "center"),
    ("times", "学习次数", 80, "center"),
    ("last", "最后学习", 100, "center"),
    ("active", "状态", 90, "center"),
]


class DatabaseFrame(tk.Frame):
    def __init__(self, master, app):
        super().__init__(master, bg=theme.BG)
        self.grid(row=0, column=0, sticky="nsew")
        self.app = app
        style_treeview(self)
        self.sort_col: str | None = None
        self.sort_desc = False
        self.show_inactive = tk.BooleanVar(value=False)
        self._build()

    # ------------------------------------------------------------ 构建
    def _build(self) -> None:
        head = tk.Frame(self, bg=theme.BG)
        head.pack(fill="x", padx=30, pady=(22, 6))
        FlatButton(head, "← 返回", lambda: self.app.show("menu"), bg=theme.BG,
                   hover=theme.CARD, font=theme.f(11), padx=12, pady=7).pack(side="left")
        tk.Label(head, text="数据库", bg=theme.BG, fg=theme.TEXT,
                 font=theme.f(16, "bold")).pack(side="left", padx=14)
        self.count_label = tk.Label(head, text="", bg=theme.BG, fg=theme.MUTED, font=theme.f(10))
        self.count_label.pack(side="right")

        tools = tk.Frame(self, bg=theme.BG)
        tools.pack(fill="x", padx=30, pady=(0, 6))
        tk.Label(tools, text="检索", bg=theme.BG, fg=theme.MUTED, font=theme.f(10)).pack(side="left")
        self.search = tk.Entry(tools, font=theme.f(11), width=26, relief="flat",
                               highlightthickness=1, highlightbackground=theme.BORDER,
                               highlightcolor=theme.PRIMARY)
        self.search.pack(side="left", padx=8, ipady=4)
        self.search.bind("<KeyRelease>", lambda e: self._reload())
        tk.Checkbutton(tools, text="显示已从 Excel 移除的词", variable=self.show_inactive,
                       command=self._reload, bg=theme.BG, fg=theme.MUTED,
                       activebackground=theme.BG, font=theme.f(10),
                       selectcolor=theme.CARD, bd=0).pack(side="left", padx=12)
        FlatButton(tools, "重新读取 Excel", self._resync, bg=theme.CARD,
                   font=theme.f(10), padx=12, pady=5).pack(side="right", padx=(8, 0))
        FlatButton(tools, "AI 补全设置", self._ai_settings, bg=theme.CARD,
                   font=theme.f(10), padx=12, pady=5).pack(side="right")
        tk.Label(self, text="点击表头排序 · 选中一行后在下方修改并保存",
                 bg=theme.BG, fg=theme.MUTED, font=theme.f(9)).pack(anchor="w", padx=32)
        self.source_label = tk.Label(self, text="", bg=theme.BG, fg=theme.MUTED,
                                     font=theme.f(8), justify="left", anchor="w")
        self.source_label.pack(anchor="w", padx=32, pady=(1, 4))

        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=30, pady=(0, 6))
        self.trees: dict[str, ttk.Treeview] = {}
        for lang, cols, title in (("en", EN_COLS, "英语词汇"), ("jp", JP_COLS, "日语词汇")):
            tab = tk.Frame(nb, bg=theme.CARD)
            nb.add(tab, text=title)
            tree = ttk.Treeview(tab, columns=[c[0] for c in cols], show="headings",
                                selectmode="browse")
            for key, h, w, anchor in cols:
                tree.heading(key, text=h, command=lambda k=key: self._sort(k))
                tree.column(key, width=w, minwidth=55, anchor=anchor)
            vs = ttk.Scrollbar(tab, orient="vertical", command=tree.yview)
            hs = ttk.Scrollbar(tab, orient="horizontal", command=tree.xview)
            tree.configure(yscrollcommand=vs.set, xscrollcommand=hs.set)
            hs.pack(side="bottom", fill="x", padx=6, pady=(0, 6))
            vs.pack(side="right", fill="y", pady=6, padx=(0, 6))
            tree.pack(side="left", fill="both", expand=True, padx=(6, 0), pady=6)
            tree.tag_configure("inactive", foreground=theme.MUTED)
            tree.bind("<<TreeviewSelect>>", lambda e, t=tree, l=lang: self._on_select(l, t))
            tree.bind("<Double-1>", lambda e, t=tree, l=lang: self._on_select(l, t))
            self.trees[lang] = tree
        self.nb = nb
        # 切换分页要重新载入该语言的表格 (否则另一页一直是空的)
        nb.bind("<<NotebookTabChanged>>", lambda e: self._reload())

        self._build_editor()

    def _build_editor(self) -> None:
        self.editor_card = Card(self)
        self.editor_card.pack(fill="x", padx=30, pady=(0, 18))
        wrap = tk.Frame(self.editor_card, bg=theme.CARD)
        wrap.pack(fill="x", padx=16, pady=12)

        self.editor_title = tk.Label(wrap, text="未选中单词", bg=theme.CARD, fg=theme.MUTED,
                                     font=theme.f(10))
        self.editor_title.grid(row=0, column=0, columnspan=8, sticky="w", pady=(0, 4))

        self.fields: dict[str, tk.Entry] = {}
        self.labels: dict[str, tk.Label] = {}
        # 宽度按内容分配, 保证英/日两种布局都能放进窗口
        widths = {"word": 15, "reading": 13, "meaning": 30, "ipa": 20, "accent": 7}
        for key, label in (
            ("word", "单词"),
            ("reading", "假名读音"),
            ("meaning", "中文意思"),
            ("ipa", "美式音标"),
            ("accent", "声调"),
        ):
            lab = tk.Label(wrap, text=label, bg=theme.CARD, fg=theme.MUTED, font=theme.f(9))
            ent = tk.Entry(wrap, font=theme.f(11), width=widths[key], relief="flat",
                           highlightthickness=1, highlightbackground=theme.BORDER,
                           highlightcolor=theme.PRIMARY)
            self.labels[key] = lab
            self.fields[key] = ent

        self.save_btn = FlatButton(wrap, "保存修改", self._save, bg=theme.PRIMARY, fg="#FFFFFF",
                                   hover=theme.PRIMARY_DARK, active_bg=theme.PRIMARY_DARK,
                                   font=theme.f(11, "bold"), padx=20, pady=8)
        self.save_btn.grid(row=1, column=5, padx=(12, 0), sticky="e")

    # ------------------------------------------------------------ 生命周期
    def on_show(self, **_):
        self._reload()

    def _current_lang(self) -> str:
        return "en" if self.nb.index(self.nb.select()) == 0 else "jp"

    def _layout_fields(self, lang: str) -> None:
        keys = ("word", "reading", "meaning", "accent") if lang == "jp" else \
               ("word", "meaning", "ipa")
        for lab in self.labels.values():
            lab.grid_forget()
        for ent in self.fields.values():
            ent.grid_forget()
        for i, k in enumerate(keys):
            self.labels[k].grid(row=1, column=i, sticky="w", padx=(0, 10))
            self.fields[k].grid(row=2, column=i, sticky="w", padx=(0, 10), ipady=5, pady=(2, 0))
        self.save_btn.grid(row=2, column=len(keys), padx=(12, 0), sticky="e")

    def _sync_editor_tab(self) -> None:
        self._clear_editor()
        self._layout_fields(self._current_lang())

    # ------------------------------------------------------------ 载入
    def _iter_rows(self, lang: str):
        db = self.app.db
        rows = db.en_words(active_only=False) if lang == "en" else db.jp_words(active_only=False)
        if not self.show_inactive.get():
            rows = [r for r in rows if r["active"]]
        q = self.search.get().strip().lower()
        if q:
            def hit(r):
                vals = [str(r[k]) for k in r.keys() if k in
                        ("word", "meaning", "ipa", "reading", "accent")]
                return any(q in v.lower() for v in vals)
            rows = [r for r in rows if hit(r)]
        return rows

    def _sort(self, col: str) -> None:
        if self.sort_col == col:
            self.sort_desc = not self.sort_desc
        else:
            self.sort_col, self.sort_desc = col, False
        self._reload()

    def _reload(self) -> None:
        lang = self._current_lang()
        self._layout_fields(lang)
        tree = self.trees[lang]
        tree.delete(*tree.get_children())

        rows = self._iter_rows(lang)
        if self.sort_col:
            def key(r):
                if self.sort_col == "source":
                    return (r["meaning_source"] or "", r["word"])
                if self.sort_col == "active":
                    return r["active"]
                try:
                    return r[self.sort_col] or ""
                except (IndexError, KeyError):
                    return ""
            rows = sorted(rows, key=key, reverse=self.sort_desc)

        for r in rows:
            if lang == "en":
                src = "＋".join(x for x in (
                    {"xlsx": "Excel", "manual": "人工", "auto": "自动"}.get(r["meaning_source"], ""),
                    {"cmudict": "音标库", "manual": "人工", "auto": "自动"}.get(r["ipa_source"], ""),
                ) if x)
                values = (r["word"], r["meaning"], r["ipa"], src or "—",
                          r["times_studied"], r["last_studied"] or "—",
                          "在用" if r["active"] else "已移除")
            else:
                src = "＋".join(x for x in (
                    {"manual": "人工", "seed": "内置", "ai": "AI",
                     "auto": "免费接口"}.get(r["meaning_source"], ""),
                    {"manual": "人工", "kanjium": "声调库", "supplement": "补录",
                     "auto": "自动"}.get(r["accent_source"], ""),
                ) if x)
                values = (r["word"], r["reading"], r["meaning"], r["accent"], src or "—",
                          r["times_studied"], r["last_studied"] or "—",
                          "在用" if r["active"] else "已移除")
            tree.insert("", "end", iid=str(r["id"]), values=values,
                        tags=() if r["active"] else ("inactive",))

        total = len(rows)
        self.count_label.configure(text=f"{'英语' if lang=='en' else '日语'} 共 {total} 条")
        self._clear_editor()
        self._update_source_label()

    def _update_source_label(self) -> None:
        """显示当前实际读取的词表文件, 用错文件时高亮告警."""
        from .. import config as C

        parts, warn = [], False
        for label, p in (("英语", C.en_source_path()), ("日语", C.jp_source_path())):
            if p is None:
                parts.append(f"{label}: 未找到")
                warn = True
                continue
            if C.is_desktop_file(p):
                parts.append(f"{label}: {p}")
            else:
                parts.append(f"{label}: {p}  ← 仓库自带的示例表")
                warn = True

        text = "数据源　" + "　｜　".join(parts)
        if warn:
            text += "\n⚠ 当前没有使用桌面上的词表，你往桌面表格里新加的词不会生效"
        self.source_label.configure(text=text, fg=theme.ERROR if warn else theme.MUTED)

    # ------------------------------------------------------------ 编辑
    def _clear_editor(self) -> None:
        self.selected_id: int | None = None
        self.editor_title.configure(text="未选中单词（在上方表格中选择一行）", fg=theme.MUTED)
        for ent in self.fields.values():
            ent.delete(0, tk.END)

    def _on_select(self, lang: str, tree: ttk.Treeview) -> None:
        sel = tree.selection()
        if not sel:
            return
        wid = int(sel[0])
        row = self.app.db.get_word(lang, wid)
        if row is None:
            return
        self.selected_id = wid
        self._layout_fields(lang)
        self.editor_title.configure(
            text=f"正在编辑：{row['word']}　（保存后标记为人工内容，不会被自动补全覆盖）",
            fg=theme.TEXT,
        )
        for key, ent in self.fields.items():
            ent.delete(0, tk.END)
            if key in row.keys():
                ent.insert(0, row[key] or "")

    def _save(self) -> None:
        if getattr(self, "selected_id", None) is None:
            messagebox.showinfo("提示", "请先在表格中选择一行。", parent=self)
            return
        lang = self._current_lang()
        vals = {k: e.get().strip() for k, e in self.fields.items()}
        word = vals.get("word", "")
        if not word:
            messagebox.showwarning("提示", "单词不能为空。", parent=self)
            return
        if lang == "en":
            self.app.db.update_en(self.selected_id, word=word, meaning=vals.get("meaning", ""),
                                  ipa=vals.get("ipa", ""))
        else:
            self.app.db.update_jp(self.selected_id, word=word, reading=vals.get("reading", ""),
                                  meaning=vals.get("meaning", ""), accent=vals.get("accent", ""))
        self._reload()
        messagebox.showinfo("已保存", "修改已写入数据库。", parent=self)

    # ------------------------------------------------------------ 重新同步
    def _ai_settings(self) -> None:
        from .settings import LLMSettingsDialog

        dlg = LLMSettingsDialog(self)
        self.wait_window(dlg)
        if getattr(dlg, "saved", False):
            self._run_enrich()

    def _run_enrich(self) -> None:
        """立即为缺失释义的新词调用 AI 补全 (后台线程, 不卡界面)."""
        import threading

        from .. import enrich as enrich_mod

        self.count_label.configure(text="正在补全…")

        def worker():
            try:
                stats = enrich_mod.enrich_japanese(self.app.db, online=True)
            except Exception as exc:  # noqa: BLE001
                stats = {"error": str(exc)}

            def done():
                self._reload()
                if stats.get("error"):
                    messagebox.showerror("补全失败", stats["error"], parent=self)
                    return
                n = (stats.get("ai") or 0) + (stats.get("online") or 0)
                detail = f"其中 AI 补全 {stats['ai']} 条。" if stats.get("ai") else ""
                messagebox.showinfo(
                    "补全完成",
                    f"新增释义 {n} 条。{detail}\n"
                    + ("若为 0，说明没有缺释义的新词。" if n == 0 else ""),
                    parent=self,
                )

            try:
                self.after(0, done)
            except Exception:
                pass

        threading.Thread(target=worker, daemon=True).start()

    def _resync(self) -> None:
        from ..sync import sync_all

        try:
            stats = sync_all(self.app.db, enrich=False)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("同步失败", str(exc), parent=self)
            return
        self._reload()
        messagebox.showinfo(
            "同步完成",
            f"英语 新增 {stats['en']['new']} / 更新 {stats['en']['updated']} / 移除 {stats['en']['deactivated']}\n"
            f"日语 新增 {stats['jp']['new']} / 更新 {stats['jp']['updated']} / 移除 {stats['jp']['deactivated']}\n\n"
            "源文件《词汇英.xlsx》《词汇日.xlsx》始终只读，未被修改。",
            parent=self,
        )
