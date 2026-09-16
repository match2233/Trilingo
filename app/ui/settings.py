"""AI 补全设置对话框 (DeepSeek / OpenAI 兼容接口)."""
from __future__ import annotations

import threading
import tkinter as tk
from tkinter import messagebox

from .. import llm
from . import theme
from .widgets import FlatButton


class LLMSettingsDialog(tk.Toplevel):
    def __init__(self, master):
        super().__init__(master)
        self.title("AI 补全设置")
        self.configure(bg=theme.BG)
        self.resizable(False, False)
        self.transient(master)
        self.grab_set()

        self.saved = False
        cfg = llm.load_config()
        wrap = tk.Frame(self, bg=theme.BG)
        wrap.pack(padx=24, pady=20)

        tk.Label(wrap, text="用 AI 为新词生成中文释义", bg=theme.BG, fg=theme.TEXT,
                 font=theme.f(13, "bold")).grid(row=0, column=0, columnspan=3, sticky="w")
        tk.Label(wrap, text="填一次即可，之后启动时自动为新词补全。留空则退回免费的翻译接口。",
                 bg=theme.BG, fg=theme.MUTED, font=theme.f(9)).grid(
            row=1, column=0, columnspan=3, sticky="w", pady=(2, 12))

        self.var_key = tk.StringVar(value=cfg["api_key"])
        self.var_url = tk.StringVar(value=cfg["base_url"])
        self.var_model = tk.StringVar(value=cfg["model"])

        rows = (
            ("API Key", self.var_key, True),
            ("Base URL", self.var_url, False),
            ("模型", self.var_model, False),
        )
        for i, (label, var, secret) in enumerate(rows, start=2):
            tk.Label(wrap, text=label, bg=theme.BG, fg=theme.MUTED,
                     font=theme.f(10)).grid(row=i, column=0, sticky="w", pady=4)
            ent = tk.Entry(wrap, textvariable=var, width=44, font=theme.f(10),
                           relief="flat", highlightthickness=1,
                           highlightbackground=theme.BORDER, highlightcolor=theme.PRIMARY,
                           show="•" if secret else "")
            ent.grid(row=i, column=1, columnspan=2, sticky="we", padx=(10, 0), ipady=4, pady=4)
            if secret:
                self._key_entry = ent

        self.status = tk.Label(wrap, text="", bg=theme.BG, fg=theme.MUTED,
                               font=theme.f(9), wraplength=420, justify="left")
        self.status.grid(row=6, column=0, columnspan=3, sticky="w", pady=(10, 0))

        bar = tk.Frame(wrap, bg=theme.BG)
        bar.grid(row=7, column=0, columnspan=3, sticky="e", pady=(14, 0))
        self.btn_test = FlatButton(bar, "测试连接", self._test, bg=theme.CARD,
                                   font=theme.f(10), padx=14, pady=7)
        self.btn_test.pack(side="left", padx=(0, 8))
        FlatButton(bar, "保存", self._save, bg=theme.PRIMARY, fg="#FFFFFF",
                   hover=theme.PRIMARY_DARK, active_bg=theme.PRIMARY_DARK,
                   font=theme.f(10, "bold"), padx=18, pady=7).pack(side="left", padx=(0, 8))
        FlatButton(bar, "取消", self.destroy, bg=theme.CARD,
                   font=theme.f(10), padx=14, pady=7).pack(side="left")

        tk.Label(wrap, text="申请地址：platform.deepseek.com　（密钥以明文保存在 data/llm.json）",
                 bg=theme.BG, fg=theme.MUTED, font=theme.f(8)).grid(
            row=8, column=0, columnspan=3, sticky="w", pady=(10, 0))

        self._center(master)
        self.bind("<Escape>", lambda e: self.destroy())
        self._key_entry.focus_set()

    def _center(self, master) -> None:
        self.update_idletasks()
        x = master.winfo_rootx() + (master.winfo_width() - self.winfo_width()) // 2
        y = master.winfo_rooty() + 120
        self.geometry(f"+{max(0, x)}+{max(0, y)}")

    def _apply_fields(self) -> None:
        llm.save_config(self.var_key.get(), self.var_url.get(), self.var_model.get())

    def _test(self) -> None:
        self._apply_fields()
        self.status.configure(text="正在测试…", fg=theme.MUTED)
        self.btn_test.set_enabled(False)

        def worker():
            ok, msg = llm.test_connection()
            def done():
                self.status.configure(text=msg, fg=theme.SUCCESS if ok else theme.ERROR)
                self.btn_test.set_enabled(True)
            try:
                self.after(0, done)
            except Exception:
                pass

        threading.Thread(target=worker, daemon=True).start()

    def _save(self) -> None:
        self._apply_fields()
        self.saved = True
        if not self.var_key.get().strip():
            self.status.configure(text="已清空 API key：将退回免费翻译接口。", fg=theme.MUTED)
            self.destroy()
            return
        self.destroy()
