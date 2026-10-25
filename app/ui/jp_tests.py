"""日语测试: 试卷集入口页.

一行一个试卷集 (新标日初级上单元测试 / JLPT-N5 …), 右上角【导入试卷】
选择文件夹后, 把该文件夹里的试卷批量导入成一个新的试卷集。

导入逻辑在 tools/import_papers.py 里, 这里只负责选目录、跑子进程、报结果。
"""
from __future__ import annotations

import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox

from .. import minna
from . import theme
from .widgets import Card, FlatButton, ScrollFrame


class JpTestsFrame(tk.Frame):
    def __init__(self, master, app):
        super().__init__(master, bg=theme.BG)
        self.grid(row=0, column=0, sticky="nsew")
        self.app = app
        self._rows: list[dict] = []
        self._build()

    def _build(self) -> None:
        head = tk.Frame(self, bg=theme.BG)
        head.pack(fill="x", padx=22, pady=(14, 4))
        FlatButton(head, "← 返回", lambda: self.app.show("menu"), bg=theme.CARD,
                   font=theme.f(11), padx=12, pady=6).pack(side="left")
        tk.Label(head, text="日语测试", bg=theme.BG, fg=theme.TEXT,
                 font=theme.f(19, "bold")).pack(side="left", padx=14)

        self.import_btn = FlatButton(head, "导入试卷", self._pick_folder,
                                     bg=theme.BLUE, fg="#FFFFFF",
                                     hover=theme.BLUE_DARK, active_bg=theme.BLUE_DARK,
                                     border=theme.BLUE, font=theme.f(11, "bold"),
                                     padx=16, pady=6)
        self.import_btn.pack(side="right")

        self.hint = tk.Label(self, text="选一个试卷集开始做题", bg=theme.BG,
                             fg=theme.MUTED, font=theme.f(11), anchor="w")
        self.hint.pack(fill="x", padx=24, pady=(0, 8))

        self.scroll = ScrollFrame(self)
        self.scroll.pack(fill="both", expand=True, padx=22, pady=(0, 14))

    # ------------------------------------------------------------ 列表
    def on_show(self, **_):
        minna.refresh()
        for w in self.scroll.body.winfo_children():
            w.destroy()
        self._rows.clear()
        cols = minna.collections()
        for col in cols:
            self._make_row(col)
        self.hint.configure(text="选一个试卷集开始做题")

    def _make_row(self, col: dict) -> None:
        papers = minna.lessons(col["id"])
        prog = self.app.db.minna_all_progress()
        done = 0
        for p in papers:
            row = prog.get(p["lesson"])
            if row is not None and row["status"] == "done":
                done += 1
        total_q = sum(minna.total_items(p) for p in papers)

        card = Card(self.scroll.body)
        card.pack(fill="x", pady=4)
        btn = FlatButton(card, "", lambda c=col["id"]: self._open(c),
                         bg=theme.CARD, hover=theme.PRIMARY_SOFT,
                         active_bg=theme.PRIMARY_SOFT, font=theme.f(11),
                         padx=0, pady=0, border=theme.CARD)
        btn.pack(fill="x")
        btn.configure(highlightbackground=theme.CARD)
        btn._label.pack_forget()

        row = tk.Frame(btn, bg=theme.CARD)
        row.pack(fill="x", padx=16, pady=12)

        left = tk.Frame(row, bg=theme.CARD)
        left.pack(side="left", fill="x", expand=True)
        name = tk.Label(left, text=col.get("name", ""), bg=theme.CARD,
                        fg=theme.TEXT, font=theme.f(16, "bold"), anchor="w")
        name.pack(anchor="w")
        sub = tk.Label(left, text=col.get("desc", ""), bg=theme.CARD,
                       fg=theme.MUTED, font=theme.f(10), anchor="w")
        sub.pack(anchor="w", pady=(2, 0))

        stat = tk.Label(row, text=f"{len(papers)} 套 · {total_q} 题",
                        bg=theme.CARD, fg=theme.MUTED, font=theme.f(11))
        stat.pack(side="right", padx=(12, 0))
        if papers:
            tag = tk.Label(row, text=f"已完成 {done}/{len(papers)}", bg=theme.SUCCESS_SOFT,
                           fg=theme.SUCCESS, font=theme.f(10, "bold"), padx=8, pady=3)
        else:
            tag = tk.Label(row, text="还没有试卷", bg=theme.BG, fg=theme.MUTED,
                           font=theme.f(10, "bold"), padx=8, pady=3)
        tag.pack(side="right")

        btn.bind_hover_group(row, name, sub, stat, tag)
        self._rows.append({"col": col, "btn": btn})

    def _open(self, cid: str) -> None:
        self.app.show("minna", coll=cid)

    # ------------------------------------------------------------ 导入
    def _pick_folder(self) -> None:
        folder = filedialog.askdirectory(title="选择包含试卷 PDF 的文件夹")
        if not folder:
            return
        from tkinter import simpledialog

        title = simpledialog.askstring(
            "试卷集名称", "给这个文件夹起个名字（会显示在列表里）：",
            initialvalue=folder.replace("\\", "/").rstrip("/").split("/")[-1],
            parent=self)
        if not title:
            return
        self._start_import(folder, title.strip())

    def _start_import(self, folder: str, title: str) -> None:
        self.import_btn.set_text("导入中…")
        self.import_btn.set_enabled(False)
        self.hint.configure(text=f"正在分析 {folder} …（扫描件需要 OCR，可能要几分钟）")

        root = __import__("pathlib").Path(__file__).resolve().parent.parent.parent
        cmd = [sys.executable, str(root / "tools" / "import_papers.py"),
               "--folder", folder, "--name", title]
        box: dict = {}

        def work():
            try:
                p = subprocess.run(cmd, capture_output=True, text=True,
                                   encoding="utf-8", errors="replace",
                                   timeout=3600)
                box["out"] = (p.stdout or "") + (p.stderr or "")
                box["code"] = p.returncode
            except Exception as exc:      # noqa: BLE001
                box["out"] = f"导入失败：{exc}"
                box["code"] = 1

        threading.Thread(target=work, daemon=True).start()
        self._poll(box, 0)

    def _poll(self, box: dict, waited: int) -> None:
        if not self.winfo_exists():
            return
        if "out" in box:
            self.import_btn.set_text("导入试卷")
            self.import_btn.set_enabled(True)
            out = box["out"].strip()
            tail = "\n".join(out.splitlines()[-14:])
            ok = box.get("code") == 0
            self.hint.configure(
                text="导入完成，已刷新列表" if ok else "导入未完成，详见提示",
                fg=theme.SUCCESS if ok else theme.ERROR)
            messagebox.showinfo("导入试卷" if ok else "导入失败", tail or "（无输出）",
                                parent=self)
            self.on_show()
            return
        if waited > 3600_000:
            return
        self.after(400, lambda: self._poll(box, waited + 400))
