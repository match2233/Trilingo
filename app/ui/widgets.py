"""通用控件: 圆角卡片式按钮等 (tkinter 原生, 无第三方依赖)."""
from __future__ import annotations

import tkinter as tk

from . import theme


class FlatButton(tk.Frame):
    """带悬停/按下反馈的扁平按钮 (用 Frame 模拟, 便于统一配色)."""

    def __init__(
        self,
        master,
        text: str,
        command=None,
        *,
        bg=theme.CARD,
        fg=theme.TEXT,
        hover=theme.CARD_HOVER,
        active_bg=None,
        font=None,
        padx=18,
        pady=10,
        anchor="center",
        width=None,
        subtitle=None,
        **kw,
    ):
        super().__init__(master, bg=bg, highlightthickness=1, highlightbackground=theme.BORDER, **kw)
        self._bg = bg
        self._hover = hover
        self._active = active_bg or hover
        self._command = command
        self._enabled = True

        self._subtitle_font = theme.f(9)
        self._subtitle_pad = (padx, pady, anchor)
        self._label = tk.Label(
            self,
            text=text,
            bg=bg,
            fg=fg,
            font=font or theme.f(13),
            padx=padx,
            pady=pady,
            anchor=anchor,
            justify="center",
        )
        self._label.pack(fill="both", expand=True)
        self._subtitle = None
        if subtitle:
            self.set_subtitle(subtitle)
        if width:
            self.configure(width=width)

        for w in (self, self._label) + ((self._subtitle,) if self._subtitle else ()):
            w.bind("<Enter>", self._on_enter)
            w.bind("<Leave>", self._on_leave)
            w.bind("<Button-1>", self._on_press)
            w.bind("<ButtonRelease-1>", self._on_release)
            try:
                w.configure(cursor="hand2")
            except tk.TclError:
                pass

    # ---------------------------------------------------------------- 状态
    def _paint(self, bg):
        self.configure(bg=bg)
        self._label.configure(bg=bg)
        if self._subtitle:
            self._subtitle.configure(bg=bg)

    def _on_enter(self, _=None):
        if self._enabled:
            self._paint(self._hover)

    def _on_leave(self, _=None):
        if self._enabled:
            self._paint(self._bg)

    def _on_press(self, _=None):
        if self._enabled:
            self._paint(self._active)

    def _on_release(self, event=None):
        if not self._enabled:
            return
        self._paint(self._hover)
        if self._command and self._inside(event):
            self._command()

    def _inside(self, event) -> bool:
        if event is None:
            return True
        try:
            x, y = self.winfo_pointerxy()
            rx, ry = self.winfo_rootx(), self.winfo_rooty()
            return rx <= x <= rx + self.winfo_width() and ry <= y <= ry + self.winfo_height()
        except Exception:
            return True

    # ---------------------------------------------------------------- API
    def set_text(self, text: str) -> None:
        self._label.configure(text=text)

    def set_subtitle(self, text: str) -> None:
        if not text:
            if self._subtitle:
                self._subtitle.pack_forget()
            return
        padx, pady, anchor = self._subtitle_pad
        if self._subtitle is None:
            self._subtitle = tk.Label(
                self, text=text, bg=self._bg, fg=theme.MUTED,
                font=self._subtitle_font, anchor=anchor,
            )
            self._subtitle.pack(fill="x", padx=padx, pady=(0, pady))
            self._subtitle.bind("<Enter>", self._on_enter)
            self._subtitle.bind("<Leave>", self._on_leave)
            self._subtitle.bind("<Button-1>", self._on_press)
            self._subtitle.bind("<ButtonRelease-1>", self._on_release)
            try:
                self._subtitle.configure(cursor="hand2")
            except tk.TclError:
                pass
        else:
            self._subtitle.configure(text=text)

    def set_enabled(self, on: bool) -> None:
        self._enabled = on
        self._label.configure(fg=theme.TEXT if on else theme.MUTED)
        self._paint(self._bg if on else theme.BG)
        try:
            self.configure(cursor="hand2" if on else "arrow")
        except tk.TclError:
            pass


class Card(tk.Frame):
    """白底卡片容器."""

    def __init__(self, master, **kw):
        kw.setdefault("bg", theme.CARD)
        kw.setdefault("highlightthickness", 1)
        kw.setdefault("highlightbackground", theme.BORDER)
        super().__init__(master, **kw)


class Stat(tk.Frame):
    """小统计块: 上方数值, 下方说明."""

    def __init__(self, master, value="0", label="", *, value_font=None, color=theme.TEXT):
        super().__init__(master, bg=theme.CARD)
        self._v = tk.Label(
            self, text=value, bg=theme.CARD, fg=color, font=value_font or theme.f(18, "bold")
        )
        self._v.pack()
        self._l = tk.Label(self, text=label, bg=theme.CARD, fg=theme.MUTED, font=theme.f(9))
        self._l.pack()

    def set(self, value: str, label: str | None = None, color: str | None = None):
        self._v.configure(text=value)
        if label is not None:
            self._l.configure(text=label)
        if color:
            self._v.configure(fg=color)


def style_treeview(widget: tk.Misc) -> None:
    """统一 ttk.Treeview 外观."""
    from tkinter import ttk

    st = ttk.Style(widget)
    try:
        st.theme_use("clam")
    except tk.TclError:
        pass
    st.configure(
        "Treeview",
        background=theme.CARD,
        fieldbackground=theme.CARD,
        foreground=theme.TEXT,
        rowheight=28,
        borderwidth=0,
        font=theme.f(10),
    )
    st.configure(
        "Treeview.Heading",
        background=theme.BG,
        foreground=theme.MUTED,
        font=theme.f(10, "bold"),
        relief="flat",
        padding=(6, 6),
    )
    st.map("Treeview.Heading", background=[("active", theme.BORDER)])
    st.map("Treeview", background=[("selected", theme.BLUE_SOFT)],
           foreground=[("selected", theme.TEXT)])
    st.configure("TNotebook", background=theme.BG, borderwidth=0)
    st.configure("TNotebook.Tab", background=theme.BG, foreground=theme.MUTED,
                 padding=(16, 8), font=theme.f(10))
    st.map("TNotebook.Tab", background=[("selected", theme.CARD)],
           foreground=[("selected", theme.PRIMARY)])


def center_window(win: tk.Misc, width: int, height: int) -> None:
    win.update_idletasks()
    sw = win.winfo_screenwidth()
    sh = win.winfo_screenheight()
    x = max(0, (sw - width) // 2)
    y = max(0, (sh - height) // 3)
    win.geometry(f"{width}x{height}+{x}+{y}")
