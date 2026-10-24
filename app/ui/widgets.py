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
        border=theme.BORDER_STRONG,
        **kw,
    ):
        super().__init__(master, bg=bg, highlightthickness=1,
                         highlightbackground=border, **kw)
        self._bg = bg
        self._hover = hover
        self._active = active_bg or hover
        self._command = command
        self._enabled = True
        self._border = border

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
    def bind_hover_group(self, *widgets) -> None:
        """把悬停/按下反馈扩展到同一张卡片里的其它控件.

        FlatButton 本身只覆盖"标题+副标题"那一条, 外面若还包着卡片和图标,
        鼠标移到那些地方就没有任何反馈 —— 看起来像只有文字能点。
        调用它把这些控件也纳入同一次高亮, 整块方框一起变色。
        """
        targets = [w for w in widgets if w is not None]
        self._hover_group = list(targets)
        # 卡片本身也留着 1px 描边, 一起染色才不会露出一圈浅色细线
        for w in targets:
            if isinstance(w, Card):
                self._hover_group.append(w)
                break
        for w in targets:
            w.bind("<Enter>", self._on_enter)
            w.bind("<Leave>", self._on_leave)
            w.bind("<Button-1>", self._on_press)
            w.bind("<ButtonRelease-1>", self._on_release)
            try:
                w.configure(cursor="hand2")
            except tk.TclError:
                pass

    def _paint(self, bg):
        self.configure(bg=bg)
        self._label.configure(bg=bg)
        if self._subtitle:
            self._subtitle.configure(bg=bg)
        self._paint_border()
        for w in getattr(self, "_hover_group", ()):
            try:
                w.configure(bg=bg)
            except tk.TclError:
                continue
            # Card 是外圈容器, 它的描边要一直留着, 否则卡片就没有轮廓了;
            # 其余子控件(都是纯装饰的 Label/Frame)描边跟随底色
            if not isinstance(w, Card):
                self._paint_border(w)

    def _paint_border(self, widget=None) -> None:
        """描边跟随底色.

        卡片式按钮(底色=白)用自己的边框色, 这样按钮有清晰的轮廓;
        其它底色(悬停态/实心按钮)直接用底色, 免得出现一圈套色。
        """
        w = widget if widget is not None else self
        try:
            bg = w.cget("bg")
            if bg == theme.CARD:
                w.configure(highlightbackground=getattr(self, "_border", theme.BORDER_STRONG))
            else:
                w.configure(highlightbackground=bg)
        except tk.TclError:
            pass

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

    def set_palette(self, bg: str, *, fg: str | None = None) -> None:
        """同时换底色与文字色 (用于"选中态"这类需要整体换色的按钮)."""
        self._bg = bg
        self._hover = bg
        self._active = bg
        if fg is not None:
            self._label.configure(fg=fg)
        self._paint(bg)


class Card(tk.Frame):
    """白底卡片容器."""

    def __init__(self, master, **kw):
        kw.setdefault("bg", theme.CARD)
        kw.setdefault("highlightthickness", 1)
        kw.setdefault("highlightbackground", theme.BORDER_STRONG)
        super().__init__(master, **kw)


class ScrollFrame(tk.Frame):
    """带竖向滚动条的容器, 内容放进 self.body.

    窗口变小时靠它兜住长内容 (24 课列表、整张试卷), 不会把布局撑破。
    """

    def __init__(self, master, bg=theme.BG, **kw):
        super().__init__(master, bg=bg, **kw)
        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0)
        self.vs = tk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.vs.set)
        self.vs.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.body = tk.Frame(self.canvas, bg=bg)
        self._win = self.canvas.create_window((0, 0), window=self.body, anchor="nw")
        self.body.bind("<Configure>", self._on_inner)
        self.canvas.bind("<Configure>", self._on_canvas)
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.canvas.bind_all(seq, self._on_wheel, add="+")

    def _on_inner(self, _=None) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas(self, event) -> None:
        self.canvas.itemconfigure(self._win, width=event.width)

    def _on_wheel(self, event) -> None:
        """滚轮只在指针位于本控件上时生效, 免得抢别的页面的滚动."""
        if not self.winfo_ismapped():
            return
        try:
            w = self.winfo_containing(event.x_root, event.y_root)
        except Exception:          # noqa: BLE001
            return
        inside = False
        while w is not None:
            if w is self:
                inside = True
                break
            w = getattr(w, "master", None)
        if not inside:
            return
        if getattr(event, "num", None) == 4:
            delta = -1
        elif getattr(event, "num", None) == 5:
            delta = 1
        else:
            delta = -1 if getattr(event, "delta", 0) > 0 else 1
        self.canvas.yview_scroll(delta * 3, "units")

    def scroll_to_top(self) -> None:
        self.canvas.yview_moveto(0)


class ProgressBar(tk.Canvas):
    """细长进度条 (纯展示, 不接收事件)."""

    def __init__(self, master, *, width=150, height=8, color=theme.PRIMARY,
                 bg=theme.CARD):
        super().__init__(master, width=width, height=height, bg=bg,
                         highlightthickness=0)
        # 注意: 不能叫 self._w —— 那是 tkinter 内部的控件路径名
        self._bw, self._bh, self._color, self._bg = width, height, color, bg
        self._ratio = 0.0
        self._paint()

    def set(self, ratio: float, color: str | None = None) -> None:
        self._ratio = max(0.0, min(1.0, ratio))
        if color:
            self._color = color
        self._paint()

    def set_bg(self, bg: str) -> None:
        self._bg = bg
        self.configure(bg=bg)
        self._paint()

    def _paint(self) -> None:
        self.delete("all")
        self.create_rectangle(0, 0, self._bw, self._bh,
                              fill=theme.BORDER, outline=theme.BORDER)
        done = self._bw * self._ratio
        if done > 0:
            self.create_rectangle(0, 0, max(done, self._bh), self._bh,
                                  fill=self._color, outline=self._color)


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
