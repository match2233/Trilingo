"""记鹿页: 0/1/2/3 四个按钮 + 月历/年历.

规则:
  * **记的是「昨天」按了几次** —— 今天填的是前一天的数据, 所以日历上高亮的
    永远是昨天, 提交也落在昨天。
  * 每天只能选一个按一次。再按同一天就是**覆盖**当天已记的值 (以 day 为主键),
    所以不存在一天两条记录。
  * 记录**不可清除**, 日历**只作展示**, 日期不可选择。
  * 日历颜色直接取自按钮颜色; 当月"鹿次数"= 当月每天按下的数字之和。
"""
from __future__ import annotations

import datetime as dt
import tkinter as tk

from .. import config as C
from . import theme
from .widgets import Card, FlatButton


class DeerFrame(tk.Frame):
    def __init__(self, master, app):
        super().__init__(master, bg=theme.BG)
        self.grid(row=0, column=0, sticky="nsew")
        self.app = app
        self.view = "month"             # month | year
        self._build()

    # ------------------------------------------------------------ 构建
    def _build(self) -> None:
        head = tk.Frame(self, bg=theme.BG)
        head.pack(fill="x", padx=30, pady=(22, 6))
        FlatButton(head, "← 返回", lambda: self.app.show("life"), bg=theme.BG,
                   hover=theme.CARD, font=theme.f(11), padx=12, pady=7).pack(side="left")
        tk.Label(head, text="记鹿", bg=theme.BG, fg=theme.TEXT,
                 font=theme.f(16, "bold")).pack(side="left", padx=14)
        self.day_label = tk.Label(head, text="", bg=theme.BG, fg=theme.MUTED, font=theme.f(10))
        self.day_label.pack(side="left")
        self.total_label = tk.Label(head, text="", bg=theme.BG, fg=theme.SUCCESS,
                                    font=theme.f(12, "bold"))
        self.total_label.pack(side="right")

        body = tk.Frame(self, bg=theme.BG)
        body.pack(fill="both", expand=True, padx=30, pady=(10, 22))
        body.grid_columnconfigure(0, weight=3)
        body.grid_columnconfigure(1, weight=4)
        body.grid_rowconfigure(0, weight=1)

        self._build_picker(body)
        self._build_calendar(body)

    # ---------------------------------------------------------- 左侧: 四个按钮
    def _build_picker(self, parent) -> None:
        card = Card(parent)
        card.grid(row=0, column=0, sticky="nsew", padx=(0, 12))

        wrap = tk.Frame(card, bg=theme.CARD)
        wrap.pack(fill="both", expand=True, padx=22, pady=22)

        self.pick_title = tk.Label(wrap, text="昨天按了几次？", bg=theme.CARD,
                                   fg=theme.TEXT, font=theme.f(13, "bold"))
        self.pick_title.pack(anchor="w")
        self.pick_sub = tk.Label(wrap, text="", bg=theme.CARD, fg=theme.MUTED,
                                 font=theme.f(9))
        self.pick_sub.pack(anchor="w", pady=(2, 14))

        row = tk.Frame(wrap, bg=theme.CARD)
        row.pack(fill="x")
        for i in range(4):
            row.grid_columnconfigure(i, weight=1, uniform="deer")
        self.btns: dict[int, FlatButton] = {}
        for i, lv in enumerate(C.DEER_LEVELS):
            b = FlatButton(
                row, str(lv), lambda v=lv: self._pick(v),
                bg=C.DEER_COLOR[lv], fg=C.DEER_TEXT_COLOR[lv],
                hover=C.DEER_COLOR[lv], active_bg=C.DEER_COLOR[lv],
                font=theme.f(30, "bold"), pady=22,
            )
            b.grid(row=0, column=i, sticky="nsew", padx=4)
            self.btns[lv] = b

        # 图例
        legend = tk.Frame(wrap, bg=theme.CARD)
        legend.pack(anchor="w", pady=(16, 0))
        for lv in C.DEER_LEVELS:
            chip = tk.Frame(legend, bg=C.DEER_COLOR[lv], highlightthickness=1,
                            highlightbackground=theme.BORDER)
            chip.pack(side="left", padx=(0, 4))
            tk.Label(chip, text="  ", bg=C.DEER_COLOR[lv], font=theme.f(8)).pack()
            tk.Label(legend, text=f"{lv} {C.DEER_LABEL[lv]}", bg=theme.CARD,
                     fg=theme.MUTED, font=theme.f(9)).pack(side="left", padx=(0, 12))

        self.status = tk.Label(wrap, text="", bg=theme.CARD, fg=theme.MUTED,
                               font=theme.f(10), wraplength=260, justify="left")
        self.status.pack(anchor="w", pady=(18, 0))

    # ---------------------------------------------------------- 右侧: 日历
    def _build_calendar(self, parent) -> None:
        from .calendarview import MonthCalendar, YearSummary

        card = Card(parent)
        card.grid(row=0, column=1, sticky="nsew")
        inner = tk.Frame(card, bg=theme.BG)
        inner.pack(fill="both", expand=True, padx=14, pady=14)

        self.month_page = tk.Frame(inner, bg=theme.BG)
        self.year_page = tk.Frame(inner, bg=theme.BG)
        # 不传 on_pick: 日历只作展示, 日期不能选
        self.cal = MonthCalendar(self.month_page, cell_fn=self._cal_cell,
                                 on_change=self._cal_summary,
                                 on_year=self._show_year)
        self.cal.pack(fill="both", expand=True)
        self.year = YearSummary(self.year_page, value_fn=self._year_value,
                                title_of=lambda m: f"{m} 月 鹿次数",
                                on_back=self._back_to_month,
                                on_pick_month=self._pick_month,
                                note=self._year_note)
        self.year.pack(fill="both", expand=True)

    def _show_year(self, year: int) -> None:
        self.month_page.pack_forget()
        self.year_page.pack(fill="both", expand=True)
        self.year.set_year(year)
        self.view = "year"

    def _back_to_month(self) -> None:
        self.year_page.pack_forget()
        self.month_page.pack(fill="both", expand=True)
        self.view = "month"
        self.cal.refresh()

    def _pick_month(self, month: int) -> None:
        self._back_to_month()
        self.cal.set_month(self.year.year, month)

    def _cal_cell(self, date: dt.date):
        lv = self.app.db.deer_get(date.isoformat())
        if lv is None:
            return "", theme.CARD, theme.TEXT, ""
        return C.DEER_LABEL[lv], C.DEER_COLOR[lv], C.DEER_TEXT_COLOR[lv], str(lv)

    def _year_value(self, month: int):
        """年视图: 每个月一个数值 = 当月鹿次数之和, 底色取当月最重的一天."""
        levels = self.app.db.deer_month(self.year.year, month)
        total = sum(levels.values())
        if not total:
            return "—", theme.CARD, theme.MUTED
        lv = max(levels.values())
        return str(total), C.DEER_COLOR[lv], C.DEER_TEXT_COLOR[lv]

    def _year_note(self, year: int) -> str:
        total = sum(
            sum(self.app.db.deer_month(year, m).values()) for m in range(1, 13))
        return f"合计 {total} 次"

    def _cal_summary(self) -> None:
        month = self.app.db.deer_month(self.cal.year, self.cal.month)
        self.cal.summary.configure(
            text=f"{self.cal.year}年{self.cal.month}月　鹿次数 {sum(month.values())}　"
                 f"记录 {len(month)} 天")

    # ------------------------------------------------------------ 生命周期
    def on_show(self, **_):
        self._back_to_month()
        target = self.target_day()
        self.cal.set_month(target.year, target.month)
        self._refresh()

    @staticmethod
    def target_day() -> dt.date:
        """记的是昨天 —— 今天填前一天的数据."""
        return dt.date.today() - dt.timedelta(days=1)

    def _refresh(self) -> None:
        target = self.target_day()
        cur = self.app.db.deer_get(target.isoformat())
        self.day_label.configure(
            text=f"填写 {target.strftime('%Y-%m-%d')}（昨天）的数据")

        for lv, b in self.btns.items():
            on = lv == cur
            # 选中档位加粗描边, 一眼看出昨天记的是哪个
            b.configure(highlightthickness=3 if on else 1,
                        highlightbackground=theme.TEXT if on else theme.BORDER)

        month = self.app.db.deer_month(self.cal.year, self.cal.month)
        total = sum(month.values())
        self.total_label.configure(text=f"{self.cal.year}年{self.cal.month}月 鹿次数 {total}")

        if cur is None:
            self.pick_sub.configure(text=f"{target.strftime('%m-%d')} 还没有记录")
            self.status.configure(text="昨天还没有记录，按一下就是填写。", fg=theme.MUTED)
        else:
            self.pick_sub.configure(text=f"{target.strftime('%m-%d')} 已记为 {cur}"
                                         f"（{C.DEER_LABEL[cur]}）")
            self.status.configure(
                text=f"昨天记为 {cur}（{C.DEER_LABEL[cur]}）。\n"
                     f"{self.cal.year} 年 {self.cal.month} 月累计鹿次数：{total}",
                fg=theme.TEXT)
        if self.view == "month":
            self.cal.refresh()
        else:
            self.year.refresh()

    # ------------------------------------------------------------ 操作
    def _pick(self, level: int) -> None:
        # 记录**不可清除**: 这里只写入, 没有任何删除入口
        self.app.db.deer_set(self.target_day().isoformat(), level)
        self._refresh()
