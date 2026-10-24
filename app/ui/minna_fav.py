"""收藏夹: 收藏的题目 + 自己的笔记.

题库是从原卷转录的, 复习时总有些题想反复看 —— 收藏一题, 顺手写一句
"为什么错 / 记住哪个用法", 之后从这里集中看。

笔记单独存在 minna_fav 表里, 与题库文件分开 —— 重新生成题库不会冲掉。
"""
from __future__ import annotations

import tkinter as tk

from .. import minna
from . import theme
from .widgets import Card, FlatButton, ScrollFrame


def section_of(lesson_no: int, qid: str) -> dict | None:
    """从 qid (L01-S2-3) 找出所属大题."""
    les = minna.lesson(lesson_no)
    if not les:
        return None
    try:
        sec_no = int(qid.split("-")[1][1:])
    except (IndexError, ValueError):
        return None
    for sec in les.get("sections") or []:
        if int(sec.get("no", 0)) == sec_no:
            return sec
    return None


def item_of(lesson_no: int, qid: str) -> dict | None:
    sec = section_of(lesson_no, qid)
    if not sec:
        return None
    for it in sec.get("items") or []:
        if it.get("id") == qid:
            return it
    return None


def answer_text(sec: dict | None, it: dict | None) -> str:
    if not it:
        return "（题目已不在题库里）"
    ans = it.get("answer")
    if ans in (None, ""):
        return "（未提供答案）"
    if sec and sec.get("kind") == "choice" and isinstance(ans, int):
        opts = it.get("options") or []
        mark = "①②③④" [ans - 1] if 1 <= ans <= 4 else str(ans)
        text = opts[ans - 1] if 0 < ans <= len(opts) else ""
        return f"{mark} {text}".strip()
    return str(ans)


class NoteDialog(tk.Toplevel):
    """编辑笔记的小窗口."""

    def __init__(self, master, title: str, note: str, on_save):
        super().__init__(master)
        self.title(title)
        self.configure(bg=theme.BG)
        self.resizable(False, False)
        self._on_save = on_save
        self.transient(master.winfo_toplevel())
        self.grab_set()

        tk.Label(self, text=title, bg=theme.BG, fg=theme.TEXT,
                 font=theme.f(15, "bold")).pack(anchor="w", padx=20, pady=(16, 8))
        self.text = tk.Text(self, width=56, height=8, wrap="word",
                            font=theme.f(13), bg=theme.CARD, fg=theme.TEXT,
                            relief="flat", padx=10, pady=8,
                            highlightthickness=1,
                            highlightbackground=theme.BORDER_STRONG,
                            highlightcolor=theme.BLUE)
        self.text.pack(padx=20, fill="both", expand=True)
        self.text.insert("1.0", note or "")
        self.text.focus_set()

        row = tk.Frame(self, bg=theme.BG)
        row.pack(fill="x", padx=20, pady=(12, 16))
        FlatButton(row, "保存", self._save, bg=theme.BLUE, fg="#FFFFFF",
                   hover=theme.BLUE_DARK, active_bg=theme.BLUE_DARK,
                   border=theme.BLUE, font=theme.f(11, "bold"),
                   padx=20, pady=7).pack(side="right")
        FlatButton(row, "取消", self.destroy, bg=theme.CARD, font=theme.f(11),
                   padx=20, pady=7).pack(side="right", padx=(0, 8))
        self.bind("<Escape>", lambda e: self.destroy())
        self.bind("<Control-Return>", lambda e: self._save())
        self.update_idletasks()
        x = master.winfo_rootx() + max(0, (master.winfo_width() - self.winfo_width()) // 2)
        y = master.winfo_rooty() + 90
        self.geometry(f"+{x}+{y}")

    def _save(self) -> None:
        self._on_save(self.text.get("1.0", "end").strip())
        self.destroy()


class MinnaFavFrame(tk.Frame):
    def __init__(self, master, app):
        super().__init__(master, bg=theme.BG)
        self.app = app
        # 必须自己放进容器: show() 只是 tkraise(), 没摆放过的控件抬起来也看不见
        self.grid(row=0, column=0, sticky="nsew")

        head = tk.Frame(self, bg=theme.BG)
        head.pack(fill="x", padx=22, pady=(14, 2))
        FlatButton(head, "← 返回", lambda: self.app.show("minna"), bg=theme.CARD,
                   font=theme.f(11), padx=12, pady=6).pack(side="left")
        tk.Label(head, text="收藏夹", bg=theme.BG, fg=theme.TEXT,
                 font=theme.f(19, "bold")).pack(side="left", padx=14)
        self.summary = tk.Label(head, text="", bg=theme.BG, fg=theme.MUTED,
                                font=theme.f(11))
        self.summary.pack(side="right")

        self.scroll = ScrollFrame(self)
        self.scroll.pack(fill="both", expand=True, padx=22, pady=(6, 12))

    # ------------------------------------------------------------ 渲染
    def on_show(self, **_):
        self.render()

    def render(self) -> None:
        for w in self.scroll.body.winfo_children():
            w.destroy()
        favs = self.app.db.minna_fav_all()
        total_note = sum(1 for f in favs if (f.get("note") or "").strip())
        self.summary.configure(
            text=f"共 {len(favs)} 题" + (f"　·　{total_note} 题有笔记" if favs else ""))
        if not favs:
            box = Card(self.scroll.body)
            box.pack(fill="x", pady=6)
            tk.Label(box, bg=theme.CARD, fg=theme.MUTED, font=theme.f(12),
                     text="还没有收藏。做题时点题目右边的 ☆ 就能收藏，"
                          "收藏后可以在这里写笔记。").pack(padx=16, pady=26)
            return
        for fav in favs:
            self._row(fav)

    def _row(self, fav: dict) -> None:
        les_no = int(fav["lesson"])
        qid = fav["qid"]
        sec = section_of(les_no, qid)
        it = item_of(les_no, qid)
        note = (fav.get("note") or "").strip()

        card = Card(self.scroll.body)
        card.pack(fill="x", pady=4)
        inner = tk.Frame(card, bg=theme.CARD)
        inner.pack(fill="x", padx=14, pady=10)

        top = tk.Frame(inner, bg=theme.CARD)
        top.pack(fill="x")
        title = f"第 {les_no} 课"
        if sec:
            title += f"　大{sec['no']}　{minna.KIND_NAME.get(sec['kind'], '')}"
        tk.Label(top, text=title, bg=theme.CARD, fg=theme.MUTED,
                 font=theme.f(10, "bold")).pack(side="left")
        FlatButton(top, "取消收藏", lambda: self._remove(les_no, qid),
                   bg=theme.CARD, hover=theme.ERROR_SOFT, active_bg=theme.ERROR_SOFT,
                   font=theme.f(10), padx=10, pady=3).pack(side="right")
        FlatButton(top, "编辑笔记", lambda: self._edit_note(les_no, qid, note),
                   bg=theme.CARD, hover=theme.BLUE_SOFT, active_bg=theme.BLUE_SOFT,
                   font=theme.f(10), padx=10, pady=3).pack(side="right", padx=(0, 6))

        prompt = (it or {}).get("prompt") or "（题目已不在题库里）"
        tk.Label(inner, text=prompt, bg=theme.CARD, fg=theme.TEXT,
                 font=theme.f(15, "bold"), wraplength=900,
                 justify="left", anchor="w").pack(fill="x", pady=(6, 2))
        tk.Label(inner, text=answer_text(sec, it), bg=theme.CARD, fg=theme.BLUE,
                 font=theme.f(13, "bold"), wraplength=900,
                 justify="left", anchor="w").pack(fill="x")
        if note:
            tk.Label(inner, text=f"笔记：{note}", bg=theme.SUNK, fg=theme.TEXT,
                     font=theme.f(12), wraplength=880, justify="left", anchor="w",
                     padx=10, pady=6).pack(fill="x", pady=(8, 0))
        else:
            tk.Label(inner, text="（还没有笔记）", bg=theme.CARD, fg=theme.MUTED,
                     font=theme.f(11)).pack(anchor="w", pady=(6, 0))

    # ------------------------------------------------------------ 动作
    def _remove(self, lesson: int, qid: str) -> None:
        self.app.db.minna_fav_remove(lesson, qid)
        self.render()

    def _edit_note(self, lesson: int, qid: str, note: str) -> None:
        it = item_of(lesson, qid)
        title = f"第 {lesson} 课 · 笔记"
        if it:
            title += f"　{(it.get('prompt') or '')[:14]}"

        def save(text: str) -> None:
            self.app.db.minna_fav_note(lesson, qid, text)
            self.render()

        NoteDialog(self, title, note, save)
