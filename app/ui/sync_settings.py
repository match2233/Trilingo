"""跨设备同步设置与手动同步."""
from __future__ import annotations

import threading
import tkinter as tk
from tkinter import messagebox

from .. import ghsync
from . import theme
from .widgets import FlatButton


class SyncDialog(tk.Toplevel):
    def __init__(self, master, app):
        super().__init__(master)
        self.app = app
        self.title("跨设备同步")
        self.configure(bg=theme.BG)
        self.resizable(False, False)
        self.transient(master)
        self.grab_set()
        self.saved = False

        cfg = ghsync.load_config()
        wrap = tk.Frame(self, bg=theme.BG)
        wrap.pack(padx=24, pady=20)

        tk.Label(wrap, text="电脑 ⇄ 手机", bg=theme.BG, fg=theme.TEXT,
                 font=theme.f(13, "bold")).grid(row=0, column=0, columnspan=3, sticky="w")
        tk.Label(wrap, text="学习数据存放在一个 GitHub 私有仓库里，两台设备各拉取、合并、回传。\n"
                            "合并按事件流求并集，不会因为一端先操作而丢掉另一端的记录。",
                 bg=theme.BG, fg=theme.MUTED, font=theme.f(9), justify="left").grid(
            row=1, column=0, columnspan=3, sticky="w", pady=(2, 12))

        self.var_token = tk.StringVar(value=cfg["token"])
        self.var_owner = tk.StringVar(value=cfg["owner"])
        self.var_repo = tk.StringVar(value=cfg["repo"])

        rows = (
            ("访问令牌", self.var_token, True, "github_pat_ 开头的细粒度令牌"),
            ("用户名", self.var_owner, False, "你的 GitHub 用户名"),
            ("数据仓库", self.var_repo, False, "建议用私有仓库"),
        )
        for i, (label, var, secret, hint) in enumerate(rows, start=2):
            tk.Label(wrap, text=label, bg=theme.BG, fg=theme.MUTED,
                     font=theme.f(10)).grid(row=i, column=0, sticky="w", pady=4)
            ent = tk.Entry(wrap, textvariable=var, width=40, font=theme.f(10),
                           relief="flat", highlightthickness=1,
                           highlightbackground=theme.BORDER, highlightcolor=theme.PRIMARY,
                           show="•" if secret else "")
            ent.grid(row=i, column=1, sticky="we", padx=(10, 8), ipady=4, pady=4)
            tk.Label(wrap, text=hint, bg=theme.BG, fg=theme.MUTED,
                     font=theme.f(8)).grid(row=i, column=2, sticky="w")

        self.status = tk.Label(wrap, text="", bg=theme.BG, fg=theme.MUTED,
                               font=theme.f(9), wraplength=470, justify="left")
        self.status.grid(row=6, column=0, columnspan=3, sticky="w", pady=(10, 0))

        bar = tk.Frame(wrap, bg=theme.BG)
        bar.grid(row=7, column=0, columnspan=3, sticky="e", pady=(14, 0))
        self.btn_test = FlatButton(bar, "测试连接", self._test, bg=theme.CARD,
                                   font=theme.f(10), padx=14, pady=7)
        self.btn_test.pack(side="left", padx=(0, 8))
        self.btn_sync = FlatButton(bar, "立即同步", self._sync, bg=theme.PRIMARY, fg="#FFFFFF",
                                   hover=theme.PRIMARY_DARK, active_bg=theme.PRIMARY_DARK,
                                   font=theme.f(10, "bold"), padx=18, pady=7)
        self.btn_sync.pack(side="left", padx=(0, 8))
        FlatButton(bar, "关闭", self.destroy, bg=theme.CARD,
                   font=theme.f(10), padx=14, pady=7).pack(side="left")

        tk.Label(wrap, text="令牌只保存在本机 data/sync.json（已 gitignore），不会上传。\n"
                            "建议用「细粒度令牌」，权限只勾该仓库的 Contents: Read and write。",
                 bg=theme.BG, fg=theme.MUTED, font=theme.f(8), justify="left").grid(
            row=8, column=0, columnspan=3, sticky="w", pady=(10, 0))

        self._center(master)
        self.bind("<Escape>", lambda e: self.destroy())

    def _center(self, master) -> None:
        self.update_idletasks()
        x = master.winfo_rootx() + (master.winfo_width() - self.winfo_width()) // 2
        y = master.winfo_rooty() + 90
        self.geometry(f"+{max(0, x)}+{max(0, y)}")

    def _apply(self) -> None:
        ghsync.save_config(
            token=self.var_token.get().strip(),
            owner=self.var_owner.get().strip(),
            repo=self.var_repo.get().strip(),
        )
        self.saved = True

    def _busy(self, on: bool) -> None:
        self.btn_test.set_enabled(not on)
        self.btn_sync.set_enabled(not on)

    def _test(self) -> None:
        self._apply()
        self.status.configure(text="正在测试…", fg=theme.MUTED)
        self._busy(True)

        def worker():
            ok, msg = ghsync.test_connection()
            def done():
                self.status.configure(text=msg, fg=theme.SUCCESS if ok else theme.ERROR)
                self._busy(False)
            try:
                self.after(0, done)
            except Exception:
                pass

        threading.Thread(target=worker, daemon=True).start()

    def _sync(self) -> None:
        self._apply()
        if not ghsync.is_configured():
            self.status.configure(text="请先填写令牌、用户名和仓库名。", fg=theme.ERROR)
            return
        self.status.configure(text="正在同步…", fg=theme.MUTED)
        self._busy(True)

        def worker():
            try:
                # 走独立连接: 同步重建错题本表期间, 界面读到的会是提交前或
                # 提交后的完整状态, 不会撞见"删除后还没插回"的空档
                r = self.app.sync_worker(lambda sdb: ghsync.sync(sdb, device="pc"))
                ok, msg = True, "同步完成" + ("" if r["changed"] else "（无变化）")
            except Exception as exc:  # noqa: BLE001
                ok, msg = False, str(exc)

            def done():
                self.status.configure(text=msg, fg=theme.SUCCESS if ok else theme.ERROR)
                self._busy(False)
                self.app.refresh_menu()
            try:
                self.after(0, done)
            except Exception:
                pass

        threading.Thread(target=worker, daemon=True).start()
