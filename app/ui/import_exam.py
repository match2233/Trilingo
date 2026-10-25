"""导入试卷: 选文件夹 → 体检评分 → 告诉你哪些能导、哪些不行.

真正的解析放在 app/exam_import.py; 这里只做交互与展示。
"""
from __future__ import annotations

import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog

from .. import exam_import as EI
from . import theme
from .widgets import FlatButton, ScrollFrame, center_window


class ImportExamDialog(tk.Toplevel):
    def __init__(self, master, app, on_done=None):
        super().__init__(master)
        self.app = app
        self.on_done = on_done
        self.title("导入试卷")
        self.configure(bg=theme.BG)
        self.transient(master.winfo_toplevel())
        center_window(self, 780, 620)

        head = tk.Frame(self, bg=theme.BG)
        head.pack(fill="x", padx=18, pady=(16, 6))
        tk.Label(head, text="导入试卷", bg=theme.BG, fg=theme.TEXT,
                 font=theme.f(17, "bold")).pack(side="left")
        FlatButton(head, "选择文件夹…", self._pick, bg=theme.PRIMARY, fg="#FFFFFF",
                   hover=theme.PRIMARY_DARK, active_bg=theme.PRIMARY_DARK,
                   border=theme.PRIMARY, font=theme.f(11, "bold"),
                   padx=16, pady=6).pack(side="right")

        self.tip = tk.Label(
            self, bg=theme.BG, fg=theme.MUTED, font=theme.f(10), justify="left",
            anchor="w", text="选一个装着试卷的文件夹。会先体检：是否重复、题目是否完整、"
                             "有没有答案、有没有听力音频、PDF 文字层能不能用，"
                             "再打分 —— 分数太低的直接放弃，不浪费 AI。")
        self.tip.pack(fill="x", padx=18, pady=(0, 8))

        self.scroll = ScrollFrame(self)
        self.scroll.pack(fill="both", expand=True, padx=18, pady=(0, 10))

        foot = tk.Frame(self, bg=theme.BG)
        foot.pack(fill="x", padx=18, pady=(0, 14))
        self.summary = tk.Label(foot, text="", bg=theme.BG, fg=theme.MUTED,
                                font=theme.f(11))
        self.summary.pack(side="left")
        FlatButton(foot, "关闭", self.destroy, bg=theme.CARD, font=theme.f(11),
                   padx=18, pady=7).pack(side="right")

    # ------------------------------------------------------------ 交互
    def _pick(self) -> None:
        folder = filedialog.askdirectory(title="选择试卷文件夹", parent=self)
        if not folder:
            return
        self.tip.configure(text=f"正在体检：{folder}")
        self.summary.configure(text="扫描中…")
        for w in self.scroll.body.winfo_children():
            w.destroy()

        box: dict = {}

        def work():
            try:
                box["r"] = EI.report(Path(folder))
            except Exception as exc:      # noqa: BLE001
                box["e"] = exc

        threading.Thread(target=work, daemon=True).start()
        self.after(120, lambda: self._poll(box))

    def _poll(self, box: dict) -> None:
        if not self.winfo_exists():
            return
        if not box:
            self.after(150, lambda: self._poll(box))
            return
        if "e" in box:
            self.tip.configure(text=f"读取失败：{box['e']}")
            self.summary.configure(text="")
            return
        self._show(box["r"])

    # ------------------------------------------------------------ 展示
    def _show(self, rep: dict) -> None:
        rows = rep["papers"]
        ok = [r for r in rows if r["ok"]]
        self.tip.configure(text=rep["folder"])
        self.summary.configure(text=f"{len(rows)} 份卷子　·　可导入 {len(ok)} 份")
        if not rows:
            tk.Label(self.scroll.body, text="这个文件夹里没找到 PDF。",
                     bg=theme.BG, fg=theme.MUTED, font=theme.f(12)).pack(pady=30)
            return
        for r in rows:
            self._row(r)
        if not ok:
            tk.Label(self.scroll.body,
                     text="这些卷子都不满足自动导入条件：PDF 是扫描件（没有文字层）"
                          "或文字层字体映射损坏。\n"
                          "要导入这种卷子需要 OCR（文字识别），当前没有接入；"
                          "可以考虑换成「高清打印版/文字版」的 PDF。",
                     bg=theme.BG, fg=theme.ERROR, font=theme.f(11),
                     justify="left", anchor="w", wraplength=700).pack(
                fill="x", pady=(10, 0))

    def _row(self, r: dict) -> None:
        card = tk.Frame(self.scroll.body, bg=theme.CARD, highlightthickness=1,
                        highlightbackground=theme.BORDER)
        card.pack(fill="x", pady=3)
        inner = tk.Frame(card, bg=theme.CARD)
        inner.pack(fill="x", padx=12, pady=8)

        if r["ok"]:
            badge, color, bg = "可导入", theme.SUCCESS, theme.SUCCESS_SOFT
        elif r["duplicate"]:
            badge, color, bg = "已导入", theme.BLUE, theme.BLUE_SOFT
        else:
            badge, color, bg = "放弃", theme.ERROR, theme.ERROR_SOFT
        tk.Label(inner, text=badge, bg=bg, fg=color, font=theme.f(9, "bold"),
                 padx=6).pack(side="left", padx=(0, 8))

        left = tk.Frame(inner, bg=theme.CARD)
        left.pack(side="left", fill="x", expand=True)
        tk.Label(left, text=r["title"], bg=theme.CARD, fg=theme.TEXT,
                 font=theme.f(13, "bold"), anchor="w").pack(fill="x")
        meta = (f'{r["pages"]} 页　·　文字 {r["text"]}　·　'
                f'答案 {"有" if r["answers"] else "无"}　·　'
                f'音频 {"有" if r["audio"] else "无"}')
        if r["problems"]:
            meta += "　·　" + "；".join(r["problems"])
        tk.Label(left, text=meta, bg=theme.CARD,
                 fg=theme.MUTED if r["ok"] else theme.ERROR,
                 font=theme.f(10), anchor="w", justify="left",
                 wraplength=560).pack(fill="x")

        tk.Label(inner, text=f'{r["score"]} 分', bg=theme.CARD, fg=color,
                 font=theme.f(14, "bold")).pack(side="right")
