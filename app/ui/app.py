"""Trilingo 主窗口与主界面."""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox

from .. import config as C
from ..db import Database
from . import theme
from .widgets import Card, FlatButton, center_window


class TrilingoApp(tk.Tk):
    def __init__(self, db: Database):
        super().__init__()
        self.db = db
        self.title(f"{C.APP_NAME} — 背单词")
        center_window(self, 1000, 700)
        self.minsize(880, 620)
        self.configure(bg=theme.BG)
        self._set_icon()

        self._frames: dict[str, tk.Frame] = {}
        self.container = tk.Frame(self, bg=theme.BG)
        self.container.pack(fill="both", expand=True)
        self.container.grid_rowconfigure(0, weight=1)
        self.container.grid_columnconfigure(0, weight=1)

        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self._enrich_notice: str = ""

        self.show("menu")

    # ------------------------------------------------------------ 基础设施
    def _set_icon(self) -> None:
        try:
            if C.ICON_PATH.is_file():
                self.iconbitmap(default=str(C.ICON_PATH))
        except Exception:
            pass

    def show(self, name: str, **kw) -> tk.Frame:
        """切换页面. 复用已存在的页面实例, 每次进入时调用其 on_show()."""
        if name not in self._frames:
            self._frames[name] = self._build(name)
        frame = self._frames[name]
        if hasattr(frame, "on_show"):
            frame.on_show(**kw)
        frame.tkraise()
        return frame

    def _build(self, name: str) -> tk.Frame:
        if name == "menu":
            return MenuFrame(self.container, self)
        if name == "quiz_en":
            from .quiz import QuizFrame

            return QuizFrame(self.container, self, "en")
        if name == "quiz_jp":
            from .quiz import QuizFrame

            return QuizFrame(self.container, self, "jp")
        if name == "mistakes_en":
            from .mistakes import MistakeFrame

            return MistakeFrame(self.container, self, "en")
        if name == "mistakes_jp":
            from .mistakes import MistakeFrame

            return MistakeFrame(self.container, self, "jp")
        if name == "database":
            from .database import DatabaseFrame

            return DatabaseFrame(self.container, self)
        raise KeyError(name)

    def refresh_menu(self) -> None:
        f = self._frames.get("menu")
        if isinstance(f, MenuFrame):
            f.on_show()

    def set_enrich_notice(self, text: str) -> None:
        self._enrich_notice = text
        f = self._frames.get("menu")
        if isinstance(f, MenuFrame):
            f.on_show()

    # ------------------------------------------------------------ 退出
    def on_close(self) -> None:
        """关闭窗口: 结束后台任务, 落盘并释放缓存, 退出进程."""
        try:
            self._cancel_all_timers()
        except Exception:
            pass
        try:
            self.db.close()          # 含 WAL checkpoint, 释放 SQLite 缓存
        except Exception:
            pass
        try:
            self.quit()
            self.destroy()
        except Exception:
            pass

    def _cancel_all_timers(self) -> None:
        for f in list(self._frames.values()):
            cancel = getattr(f, "cancel_timers", None)
            if callable(cancel):
                cancel()


class MenuFrame(tk.Frame):
    """主界面: 两行两列四个按钮 + 右上角连续打卡 + 底部数据库按钮."""

    def __init__(self, master, app: TrilingoApp):
        super().__init__(master, bg=theme.BG)
        self.app = app
        self.grid(row=0, column=0, sticky="nsew")

        # ---------------- 顶栏
        top = tk.Frame(self, bg=theme.BG)
        top.pack(fill="x", padx=34, pady=(26, 6))

        left = tk.Frame(top, bg=theme.BG)
        left.pack(side="left", anchor="w")
        tk.Label(left, text=C.APP_NAME, bg=theme.BG, fg=theme.PRIMARY,
                 font=theme.f(26, "bold")).pack(anchor="w")
        tk.Label(left, text="英语 · 日语 背单词", bg=theme.BG, fg=theme.MUTED,
                 font=theme.f(10)).pack(anchor="w", pady=(2, 0))

        # 右上角: 连续打卡天数
        self.streak_card = Card(top)
        self.streak_card.pack(side="right", anchor="ne")
        inner = tk.Frame(self.streak_card, bg=theme.CARD)
        inner.pack(padx=16, pady=10)
        tk.Label(inner, text="🔥", bg=theme.CARD,
                 font=("Segoe UI Emoji", 16)).pack(side="left", padx=(0, 8))
        col = tk.Frame(inner, bg=theme.CARD)
        col.pack(side="left")
        tk.Label(col, text="已连续打卡", bg=theme.CARD, fg=theme.MUTED,
                 font=theme.f(9)).pack(anchor="w")
        self.streak_label = tk.Label(col, text="0 天", bg=theme.CARD, fg=theme.PRIMARY,
                                     font=theme.f(17, "bold"))
        self.streak_label.pack(anchor="w")

        # ---------------- 四个主按钮
        grid = tk.Frame(self, bg=theme.BG)
        grid.pack(fill="both", expand=True, padx=34, pady=(16, 8))
        grid.grid_rowconfigure(0, weight=1)
        grid.grid_rowconfigure(1, weight=1)
        grid.grid_columnconfigure(0, weight=1)
        grid.grid_columnconfigure(1, weight=1)

        self.btn_en = self._quad(grid, 0, 0, "英语词汇", "从《词汇英.xlsx》每日抽取",
                                 theme.PRIMARY, theme.PRIMARY_SOFT,
                                 lambda: self.app.show("quiz_en"))
        self.btn_err_en = self._quad(grid, 0, 1, "错题本（英）", "英语错词与复习计划",
                                     theme.BLUE, theme.BLUE_SOFT,
                                     lambda: self.app.show("mistakes_en"))
        self.btn_jp = self._quad(grid, 1, 0, "日语词汇", "从《词汇日.xlsx》每日抽取",
                                 theme.PRIMARY, theme.PRIMARY_SOFT,
                                 lambda: self.app.show("quiz_jp"))
        self.btn_err_jp = self._quad(grid, 1, 1, "错题本（日）", "日语错词与复习计划",
                                     theme.BLUE, theme.BLUE_SOFT,
                                     lambda: self.app.show("mistakes_jp"))

        # ---------------- 底部
        bottom = tk.Frame(self, bg=theme.BG)
        bottom.pack(fill="x", padx=34, pady=(4, 22))
        self.notice = tk.Label(bottom, text="", bg=theme.BG, fg=theme.MUTED, font=theme.f(9))
        self.notice.pack(anchor="w", pady=(0, 6))
        FlatButton(bottom, "数据库", lambda: self.app.show("database"),
                   bg=theme.CARD, fg=theme.TEXT, font=theme.f(12), pady=12).pack(fill="x")

    def _quad(self, parent, r, c, title, sub, color, soft, cmd) -> FlatButton:
        card = Card(parent)
        card.grid(row=r, column=c, sticky="nsew", padx=8, pady=8)
        btn = FlatButton(
            card, title, cmd, bg=theme.CARD, hover=soft, active_bg=soft,
            font=theme.f(21, "bold"), fg=color, pady=30,
        )
        btn.pack(fill="both", expand=True, padx=2, pady=2)
        btn.set_subtitle(sub)
        btn.configure(highlightbackground=theme.BORDER)
        return btn

    # ------------------------------------------------------------ 刷新
    def on_show(self, **_):
        self.streak_label.configure(text=f"{self.app.db.streak()} 天")

        for lang, btn, label in (
            ("en", self.btn_en, "英语词汇"),
            ("jp", self.btn_jp, "日语词汇"),
        ):
            answered, total = self.app.db.today_status(lang)
            if total:
                btn.set_subtitle(f"今日进度 {answered}/{total}")
            else:
                btn.set_subtitle(f"每日 {C.EN_DAILY_NEW if lang=='en' else C.JP_DAILY_NEW} 个新词")

        for lang, btn, label in (
            ("en", self.btn_err_en, "错题本（英）"),
            ("jp", self.btn_err_jp, "错题本（日）"),
        ):
            n = len(self.app.db.open_mistakes(lang))
            due = len(self.app.db.due_mistakes(lang))
            if n == 0:
                btn.set_subtitle("暂无错题")
            elif due:
                btn.set_subtitle(f"{n} 个错词 · 今日待复习 {due}")
            else:
                btn.set_subtitle(f"{n} 个错词")

        self.notice.configure(text=self.app._enrich_notice)
