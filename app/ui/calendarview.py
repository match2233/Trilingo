"""日历控件: 月视图 (MonthCalendar) 与年视图 (YearSummary), 记账与记鹿共用.

* **月视图** —— 一个月的日期网格。格子尺寸刻意**写死** (CELL_W × CELL_H),
  不随月份、不随数据、也不随月/年视图切换而变 —— 4 周和 6 周的月份看起来
  必须一样大, 否则一翻月整个页面都在跳。
* **年视图** —— 一屏 12 个格子, 每个月只显示**一个汇总数值**(求和), 不画每天。
* 格子内容由调用方决定: 月视图用 `cell_fn(日期) -> (文字, 底色, 字色, 提示)`,
  年视图用 `value_fn(月) -> 文字`.
"""
from __future__ import annotations

import calendar as pycal
import datetime as dt
import tkinter as tk

from . import theme
from .widgets import FlatButton

WEEK = ("一", "二", "三", "四", "五", "六", "日")

CELL = 70           # 日期格子边长: 宽高一致 = 正方形
CELL_W = CELL       # 兼容旧名
CELL_H = CELL
CELL_GAP = 3        # 格子之间的间距 (四周各留一半)
NAV = 34            # 翻月/翻年按钮边长 (正方形)


class MonthCalendar(tk.Frame):
    """一个月的日期网格, 带上/下月切换、跳年视图与底部汇总行."""

    def __init__(self, master, *, cell_fn=None, on_change=None, on_pick=None,
                 on_year=None):
        super().__init__(master, bg=theme.BG)
        self.cell_fn = cell_fn or (lambda d: ("", theme.CARD, theme.TEXT, ""))
        self.on_change = on_change
        self.on_pick = on_pick          # 不传 = 格子不可选(纯展示)
        self.on_year = on_year          # 不传 = 不显示"年视图"按钮

        # 宽度写死: 否则某个月的汇总文字更长时, 会把整个控件(以及日历格子)
        # 一起撑宽 —— 一翻月页面就在左右跳
        self.configure(width=CELL_W * 7)
        self.pack_propagate(False)

        today = dt.date.today()
        self.year, self.month = today.year, today.month
        self._cells: list[tk.Frame] = []
        self._build()

    # ------------------------------------------------------------ 构建
    def _nav(self, parent, text: str, cmd, col: int) -> FlatButton:
        """正方形翻月按钮.

        以前给的是 width=30 —— 那是**像素**不是字符, 两个按钮各要 300px,
        控件总宽才 490px, 于是右边的 › 被挤出可视区, 只剩一条缝 (像坏了)。
        """
        b = FlatButton(parent, text, cmd, bg=theme.CARD, font=theme.f(16, "bold"),
                       padx=0, pady=0)
        b.configure(width=NAV, height=NAV)
        b.pack_propagate(False)
        b.grid_propagate(False)
        b.grid(row=0, column=col)
        return b

    def _build(self) -> None:
        head = tk.Frame(self, bg=theme.BG)
        head.pack(fill="x", pady=(0, 8))
        # 固定列宽: 标题列吃掉多余空间, 按钮列各自固定 —— 换月时不会左右抖
        head.grid_columnconfigure(1, weight=1)

        self._nav(head, "‹", self.prev_month, 0)
        self.title = tk.Label(head, text="", bg=theme.BG, fg=theme.TEXT,
                              font=theme.f(14, "bold"))
        self.title.grid(row=0, column=1, padx=14, sticky="w")
        self._nav(head, "›", self.next_month, 2)

        # 汇总行单独占一行, 并限制换行宽度 —— 文字长短不能反过来把日历撑宽,
        # 否则换个月份日历整体宽度就会跟着文字跳
        self.summary = tk.Label(self, text="", bg=theme.BG, fg=theme.MUTED,
                               font=theme.f(10), anchor="w", justify="left",
                               wraplength=CELL_W * 7)
        self.summary.pack(fill="x", pady=(0, 6))
        if self.on_year:
            FlatButton(self, "年视图", lambda: self.on_year(self.year),
                       bg=theme.CARD, font=theme.f(10), padx=12, pady=4).pack(
                anchor="e", pady=(0, 6))

        wk = tk.Frame(self, bg=theme.BG)
        wk.pack(fill="x")
        for i, w in enumerate(WEEK):
            wk.grid_columnconfigure(i, weight=1, uniform="cal")
            fg = theme.ERROR if i >= 5 else theme.MUTED
            tk.Label(wk, text=w, bg=theme.BG, fg=fg, font=theme.f(9)).grid(
                row=0, column=i, sticky="ew", pady=(0, 4))

        self.grid_wrap = tk.Frame(self, bg=theme.BG, width=CELL_W * 7,
                                  height=CELL_H * 6)
        self.grid_wrap.pack(fill="x")
        self.grid_wrap.pack_propagate(False)     # 宽高都写死, 不受内容影响
        for i in range(7):
            self.grid_wrap.grid_columnconfigure(i, weight=1, uniform="cal")
        for r in range(6):
            self.grid_wrap.grid_rowconfigure(r, minsize=CELL_H)   # 不设 weight
        # 余下的竖向空间留白, 这样日历总高恒定
        self.spacer = tk.Frame(self, bg=theme.BG)
        self.spacer.pack(fill="both", expand=True)

        for r in range(6):
            for c in range(7):
                cell = tk.Frame(self.grid_wrap, bg=theme.CARD,
                                width=CELL - CELL_GAP * 2,
                                height=CELL - CELL_GAP * 2,
                                highlightthickness=1, highlightbackground=theme.BORDER)
                cell.grid(row=r, column=c, sticky="nsew",
                          padx=CELL_GAP, pady=CELL_GAP)
                cell.grid_propagate(False)
                day = tk.Label(cell, text="", bg=theme.CARD, fg=theme.TEXT,
                               font=theme.f(11, "bold"), anchor="nw")
                day.pack(anchor="nw", padx=6, pady=(5, 0))
                info = tk.Label(cell, text="", bg=theme.CARD, fg=theme.MUTED,
                                font=theme.f(9), anchor="center", justify="center")
                info.pack(expand=True, fill="both", padx=3)
                cell._day = day          # type: ignore[attr-defined]
                cell._info = info        # type: ignore[attr-defined]
                # 只有传了 on_pick 才让格子可点 —— 记鹿那种纯展示的日历不该能选日期
                if self.on_pick:
                    for w in (cell, day, info):
                        w.bind("<Button-1>", lambda e, cc=cell: self._click(cc))
                        w.bind("<Enter>", lambda e, cc=cell: self._hover(cc, True))
                        w.bind("<Leave>", lambda e, cc=cell: self._hover(cc, False))
                self._cells.append(cell)

    # ------------------------------------------------------------ 绘制
    def refresh(self) -> None:
        self.title.configure(text=f"{self.year} 年 {self.month} 月")
        weeks = pycal.monthcalendar(self.year, self.month)      # 周一起
        today = dt.date.today()
        flat: list[int] = []
        for wk in weeks:
            flat += wk
        flat += [0] * (42 - len(flat))

        for idx, cell in enumerate(self._cells):
            d = flat[idx]
            cell._date = None        # type: ignore[attr-defined]
            if d == 0:
                cell.configure(bg=theme.BG, highlightbackground=theme.BG)
                cell._day.configure(text="", bg=theme.BG)       # type: ignore[attr-defined]
                cell._info.configure(text="", bg=theme.BG)      # type: ignore[attr-defined]
                continue
            date = dt.date(self.year, self.month, d)
            cell._date = date        # type: ignore[attr-defined]
            text, bg, fg, tip = self.cell_fn(date)
            is_today = date == today
            cell.configure(bg=bg, highlightbackground=theme.PRIMARY if is_today else theme.BORDER,
                           highlightthickness=2 if is_today else 1)
            cell._day.configure(text=str(d), bg=bg,
                                fg=theme.PRIMARY if is_today else fg)   # type: ignore[attr-defined]
            cell._info.configure(text=tip, bg=bg, fg=fg)                # type: ignore[attr-defined]
        if self.on_change:
            self.on_change()

    def _hover(self, cell, on: bool) -> None:
        if getattr(cell, "_date", None) is None:
            return
        # 悬停只加一点边框提示, 不动底色 (底色是数据含义)
        cur = cell.cget("highlightbackground")
        if on:
            cell._hover_prev = cur          # type: ignore[attr-defined]
            cell.configure(highlightbackground=theme.BLUE)
        else:
            cell.configure(highlightbackground=getattr(cell, "_hover_prev", cur))

    def _click(self, cell) -> None:
        date = getattr(cell, "_date", None)
        if date is not None and self.on_pick:
            self.on_pick(date)

    # ------------------------------------------------------------ 导航
    def prev_month(self) -> None:
        self.year, self.month = (self.year - 1, 12) if self.month == 1 else \
                                (self.year, self.month - 1)
        self.refresh()

    def next_month(self) -> None:
        self.year, self.month = (self.year + 1, 1) if self.month == 12 else \
                                (self.year, self.month + 1)
        self.refresh()

    def go_today(self) -> None:
        t = dt.date.today()
        self.year, self.month = t.year, t.month
        self.refresh()

    def set_month(self, year: int, month: int) -> None:
        self.year, self.month = year, month
        self.refresh()

    def days_in_month(self) -> list[dt.date]:
        n = pycal.monthrange(self.year, self.month)[1]
        return [dt.date(self.year, self.month, d) for d in range(1, n + 1)]


class YearSummary(tk.Frame):
    """年视图: 12 个格子, 每个月只显示一个**汇总数值**(求和), 不画每天.

    `value_fn(月份) -> (主文字, 底色, 字色)` 由调用方给出 ——
    记账给当月净收支, 记鹿给当月鹿次数。
    """

    def __init__(self, master, *, value_fn=None, title_of=None, on_back=None,
                 on_pick_month=None, note=""):
        super().__init__(master, bg=theme.BG)
        self.value_fn = value_fn or (lambda m: ("", theme.CARD, theme.TEXT))
        self.title_of = title_of or (lambda m: f"{m} 月")
        self.on_back = on_back
        self.on_pick_month = on_pick_month
        self.note = note
        self.year = dt.date.today().year
        self._boxes: list[tuple[int, tk.Frame, tk.Label, tk.Label]] = []
        self._build()

    def _nav(self, parent, text: str, cmd, col: int) -> FlatButton:
        b = FlatButton(parent, text, cmd, bg=theme.CARD, font=theme.f(16, "bold"),
                       padx=0, pady=0)
        b.configure(width=NAV, height=NAV)
        b.pack_propagate(False)
        b.grid_propagate(False)
        b.grid(row=0, column=col)
        return b

    def _build(self) -> None:
        head = tk.Frame(self, bg=theme.BG)
        head.pack(fill="x", pady=(0, 8))
        head.grid_columnconfigure(1, weight=1)
        self._nav(head, "‹", self.prev_year, 0)
        # 年份与全年合计合成一行, 免得汇总单独成行后被挤成好几段
        self.title = tk.Label(head, text="", bg=theme.BG, fg=theme.TEXT,
                              font=theme.f(11), anchor="w")
        self.title.grid(row=0, column=1, padx=14, sticky="w")
        self._nav(head, "›", self.next_year, 2)

        if self.on_back:
            FlatButton(self, "月视图", self.on_back, bg=theme.CARD, font=theme.f(10),
                       padx=12, pady=4).pack(anchor="e", pady=(0, 6))

        grid = tk.Frame(self, bg=theme.BG)
        grid.pack(fill="both", expand=True)
        for c in range(3):
            grid.grid_columnconfigure(c, weight=1, uniform="ycol")
        # 月份格子只要够放"标题 + 数值"两行, 不跟着窗口一起长高
        for r in range(4):
            grid.grid_rowconfigure(r, weight=1, uniform="yrow", minsize=72)

        for month in range(1, 13):
            box = tk.Frame(grid, bg=theme.CARD, highlightthickness=1,
                           highlightbackground=theme.BORDER)
            box.grid(row=(month - 1) // 3, column=(month - 1) % 3,
                     sticky="nsew", padx=5, pady=5)
            label = tk.Label(box, text="", bg=theme.CARD, fg=theme.MUTED,
                             font=theme.f(11, "bold"), anchor="w")
            label.pack(fill="x", padx=10, pady=(8, 0))
            value = tk.Label(box, text="", bg=theme.CARD, fg=theme.TEXT,
                             font=theme.f(16, "bold"), anchor="w")
            value.pack(fill="x", padx=10, pady=(0, 8))
            if self.on_pick_month:
                for w in (box, label, value):
                    w.bind("<Button-1>", lambda e, mm=month: self.on_pick_month(mm))
                    try:
                        w.configure(cursor="hand2")
                    except tk.TclError:
                        pass
            self._boxes.append((month, box, label, value))

    def refresh(self) -> None:
        line = f"{self.year} 年"
        if self.note:
            extra = self.note(self.year)
            if extra:
                line += "　·　" + extra
        self.title.configure(text=line)
        for month, box, label, value in self._boxes:
            text, bg, fg = self.value_fn(month)
            # 底色也要跟着数据走: 只看数字看不出哪个月最厉害
            box.configure(bg=bg, highlightbackground=bg if bg != theme.CARD else theme.BORDER)
            label.configure(text=self.title_of(month), bg=bg,
                            fg=fg if bg != theme.CARD else theme.MUTED)
            value.configure(text=text, bg=bg, fg=fg)

    def prev_year(self) -> None:
        self.year -= 1
        self.refresh()

    def next_year(self) -> None:
        self.year += 1
        self.refresh()

    def set_year(self, year: int) -> None:
        self.year = year
        self.refresh()
