"""记账页: 三行表单 + 币种切换 + 账单明细入口 + 日历入口.

表单三行:
    第一行  收入 | 收入来源 | 金额 | 提交
    第二行  支出 | 支出方向 | 金额 | 提交
    第三行  总余额 | 总收入 | 账单明细

人民币 / 日元 / 美元分开记账, 互不换算; 右上角切换当前显示的币种。
同一天可以提交任意多笔, 明细里显示到秒。
"""
from __future__ import annotations

import datetime as dt
import tkinter as tk
from tkinter import messagebox, ttk

from .. import config as C
from ..db import today
from . import theme
from .widgets import Card, FlatButton, center_window, style_treeview

ENTRY_W = 22
AMOUNT_W = 14
CHART_DAYS = 16        # 图表横坐标: 最近 16 天 (day-15 … day0)


# ------------------------------------------------------------------ 占位符
def _placeholder(entry: tk.Entry, text: str) -> None:
    """给输入框加占位提示 (tk 原生 Entry 没有 placeholder)."""
    entry._ph = text                      # type: ignore[attr-defined]
    entry._has_ph = True                  # type: ignore[attr-defined]
    entry.insert(0, text)
    entry.configure(fg=theme.MUTED)

    def on_focus_in(_=None):
        if entry._has_ph:                 # type: ignore[attr-defined]
            entry.delete(0, "end")
            entry.configure(fg=theme.TEXT)
            entry._has_ph = False         # type: ignore[attr-defined]

    def on_focus_out(_=None):
        if not entry.get().strip():
            entry._has_ph = True          # type: ignore[attr-defined]
            entry.insert(0, text)
            entry.configure(fg=theme.MUTED)

    entry.bind("<FocusIn>", on_focus_in)
    entry.bind("<FocusOut>", on_focus_out)


def _real_text(entry: tk.Entry) -> str:
    """取用户真正输入的内容 —— 占位提示不算输入."""
    if getattr(entry, "_has_ph", False):
        return ""
    return entry.get().strip()


def _reset_entry(entry: tk.Entry) -> None:
    """清空输入框并恢复占位提示."""
    entry.delete(0, "end")
    entry._has_ph = True                  # type: ignore[attr-defined]
    entry.insert(0, getattr(entry, "_ph", ""))
    entry.configure(fg=theme.MUTED)


class LedgerFrame(tk.Frame):
    def __init__(self, master, app):
        super().__init__(master, bg=theme.BG)
        self.grid(row=0, column=0, sticky="nsew")
        self.app = app
        self.currency = tk.StringVar(value=C.CURRENCIES[0])
        self.showing = "form"          # form | calendar
        self.view = "month"            # month | year
        style_treeview(self)
        self._build()

    # ------------------------------------------------------------ 构建
    def _build(self) -> None:
        head = tk.Frame(self, bg=theme.BG)
        head.pack(fill="x", padx=30, pady=(22, 6))
        FlatButton(head, "← 返回", lambda: self.app.show("life"), bg=theme.BG,
                   hover=theme.CARD, font=theme.f(11), padx=12, pady=7).pack(side="left")
        tk.Label(head, text="记账", bg=theme.BG, fg=theme.TEXT,
                 font=theme.f(16, "bold")).pack(side="left", padx=14)
        self.date_label = tk.Label(head, text="", bg=theme.BG, fg=theme.MUTED, font=theme.f(10))
        self.date_label.pack(side="left")

        # 右上角: 日历入口 + 币种切换
        FlatButton(head, "📅 日历", self._toggle_calendar, bg=theme.CARD,
                   font=theme.f(11), padx=14, pady=7).pack(side="right")
        self.cal_btn = head.winfo_children()[-1]

        seg = tk.Frame(head, bg=theme.CARD, highlightthickness=1,
                       highlightbackground=theme.BORDER)
        seg.pack(side="right", padx=(0, 10))
        self.cur_btns: dict[str, FlatButton] = {}
        for i, cur in enumerate(C.CURRENCIES):
            b = FlatButton(seg, C.CURRENCY_NAME[cur], lambda c=cur: self._set_currency(c),
                           bg=theme.CARD, hover=theme.PRIMARY_SOFT,
                           active_bg=theme.PRIMARY_SOFT, font=theme.f(10),
                           padx=14, pady=7)
            b.configure(highlightthickness=0)
            b.pack(side="left")
            self.cur_btns[cur] = b

        self.body = tk.Frame(self, bg=theme.BG)
        self.body.pack(fill="both", expand=True, padx=30, pady=(12, 22))

        self.form_page = tk.Frame(self.body, bg=theme.BG)
        self.cal_page = tk.Frame(self.body, bg=theme.BG)
        self._build_form()
        self._build_calendar()

    # ---------------------------------------------------------- 表单
    def _build_form(self) -> None:
        page = self.form_page

        # 第一行: 收入
        self.income_card = Card(page)
        self.income_card.pack(fill="x", pady=(0, 10))
        self.inc_source, self.inc_amount = self._io_row(
            self.income_card, "收入", "收入来源", "例如：工资 / 兼职",
            theme.SUCCESS, theme.SUCCESS_SOFT, lambda: self._submit("income"))

        # 第二行: 支出
        self.expense_card = Card(page)
        self.expense_card.pack(fill="x", pady=(0, 10))
        self.exp_source, self.exp_amount = self._io_row(
            self.expense_card, "支出", "支出方向", "例如：餐饮 / 交通",
            theme.ERROR, theme.ERROR_SOFT, lambda: self._submit("expense"))

        # 第三行: 总览
        self.total_card = Card(page)
        self.total_card.pack(fill="x")
        wrap = tk.Frame(self.total_card, bg=theme.CARD)
        wrap.pack(fill="x", padx=22, pady=18)

        for i in range(2):
            wrap.grid_columnconfigure(i, weight=1, uniform="tot")
        self.stat_labels: dict[str, tk.Label] = {}
        for col, (key, title, color) in enumerate((
                ("balance", "总余额", theme.PRIMARY), ("income", "总收入", theme.SUCCESS))):
            box = tk.Frame(wrap, bg=theme.CARD)
            box.grid(row=0, column=col, sticky="w")
            tk.Label(box, text=title, bg=theme.CARD, fg=theme.MUTED,
                     font=theme.f(10)).pack(anchor="w")
            lab = tk.Label(box, text="—", bg=theme.CARD, fg=color, font=theme.f(22, "bold"))
            lab.pack(anchor="w")
            self.stat_labels[key] = lab

        FlatButton(wrap, "账单明细", self._open_detail, bg=theme.BLUE, fg="#FFFFFF",
                   hover="#3A5BE0", active_bg="#3A5BE0", font=theme.f(12, "bold"),
                   padx=22, pady=11).grid(row=0, column=2, sticky="e")

        self.hint = tk.Label(page, text="", bg=theme.BG, fg=theme.MUTED, font=theme.f(9))
        self.hint.pack(anchor="w", pady=(10, 0))

    def _io_row(self, card, title, place, ph, color, soft, cmd):
        """一行 收入/支出 表单: 文字 | 来源输入框 | 金额输入框 | 提交按钮."""
        wrap = tk.Frame(card, bg=theme.CARD)
        wrap.pack(fill="x", padx=22, pady=16)

        tk.Label(wrap, text=title, bg=theme.CARD, fg=color,
                 font=theme.f(15, "bold"), width=4, anchor="w").pack(side="left")

        tk.Label(wrap, text=place, bg=theme.CARD, fg=theme.MUTED,
                 font=theme.f(9)).pack(side="left", padx=(14, 6))
        src = tk.Entry(wrap, font=theme.f(11), width=ENTRY_W, relief="flat",
                       highlightthickness=1, highlightbackground=theme.BORDER,
                       highlightcolor=color)
        src.pack(side="left", ipady=6)
        _placeholder(src, ph)

        tk.Label(wrap, text="金额", bg=theme.CARD, fg=theme.MUTED,
                 font=theme.f(9)).pack(side="left", padx=(16, 6))
        amt = tk.Entry(wrap, font=theme.f(12), width=AMOUNT_W, relief="flat",
                       justify="right", highlightthickness=1,
                       highlightbackground=theme.BORDER, highlightcolor=color)
        amt.pack(side="left", ipady=6)
        tk.Label(wrap, text="元", bg=theme.CARD, fg=theme.MUTED,
                 font=theme.f(9)).pack(side="left", padx=(4, 0))

        FlatButton(wrap, "提交", cmd, bg=color, fg="#FFFFFF", hover=color,
                   active_bg=color, font=theme.f(11, "bold"), padx=24, pady=9).pack(
            side="right")
        amt.bind("<Return>", lambda e: cmd())
        src.bind("<Return>", lambda e: amt.focus_set())
        return src, amt

    # ---------------------------------------------------------- 日历
    def _build_calendar(self) -> None:
        from .calendarview import MonthCalendar, YearSummary

        # 月视图与年视图叠在同一块区域, 用 pack/pack_forget 切换
        self.month_page = tk.Frame(self.cal_page, bg=theme.BG)
        self.year_page = tk.Frame(self.cal_page, bg=theme.BG)
        self.cal = MonthCalendar(self.month_page, cell_fn=self._cal_cell,
                                 on_change=self._cal_summary,
                                 on_year=self._show_year)
        self.cal.pack(fill="both", expand=True)
        self.year = YearSummary(self.year_page, value_fn=self._year_value,
                                title_of=lambda m: f"{m} 月 结余",
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
        """每天显示 净收支, 净收入绿色 / 支出红色."""
        cur = self.currency.get()
        per = self.app.db.ledger_daily(
            cur, date.isoformat(), date.isoformat()).get(date.isoformat())
        if not per or (not per["inc"] and not per["exp"]):
            return "", theme.CARD, theme.TEXT, ""
        net = per["inc"] - per["exp"]
        sign = C.CURRENCY_SIGN[cur]
        if net > 0:
            return theme.SUCCESS, theme.SUCCESS_SOFT, theme.SUCCESS, f"+{sign}{C.fmt_money(net, cur)}"
        if net < 0:
            return theme.ERROR, theme.ERROR_SOFT, theme.ERROR, f"-{sign}{C.fmt_money(-net, cur)}"
        return theme.MUTED, theme.CARD, theme.MUTED, f"{sign}0.00"

    def _year_value(self, month: int):
        """年视图: 每个月一个数值 = 当月结余 (收入 − 支出), 底色随正负变化."""
        cur = self.currency.get()
        m = self.app.db.ledger_month(cur, self.year.year, month)
        if not m["count"]:
            return "—", theme.CARD, theme.MUTED
        sign = C.CURRENCY_SIGN[cur]
        net = m["balance"]
        if net > 0:
            return f"+{sign}{C.fmt_money(net, cur)}", theme.SUCCESS_SOFT, theme.SUCCESS
        if net < 0:
            return f"-{sign}{C.fmt_money(-net, cur)}", theme.ERROR_SOFT, theme.ERROR
        return f"{sign}0.00", theme.CARD, theme.MUTED

    def _year_note(self, year: int) -> str:
        cur = self.currency.get()
        sign = C.CURRENCY_SIGN[cur]
        inc = exp = cnt = 0
        for m in range(1, 13):
            r = self.app.db.ledger_month(cur, year, m)
            inc += r["income"]
            exp += r["expense"]
            cnt += r["count"]
        net = inc - exp
        return (f"合计 {cnt} 笔　收入 {sign}{C.fmt_money(inc, cur)}　"
                f"支出 {sign}{C.fmt_money(exp, cur)}　"
                f"结余 {sign}{C.fmt_money(abs(net), cur)}"
                + ("（净支出）" if net < 0 else ""))

    def _cal_summary(self) -> None:
        cur = self.currency.get()
        m = self.app.db.ledger_month(cur, self.cal.year, self.cal.month)
        sign = C.CURRENCY_SIGN[cur]
        net = m["balance"]
        self.cal.summary.configure(
            text=f"{self.cal.year}年{self.cal.month}月　共 {m['count']} 笔　"
                 f"收入 {sign}{C.fmt_money(m['income'], cur)}　"
                 f"支出 {sign}{C.fmt_money(m['expense'], cur)}　"
                 f"结余 {sign}{C.fmt_money(abs(net), cur)}"
                 + ("（净支出）" if net < 0 else ""),
            fg=theme.SUCCESS if net >= 0 else theme.ERROR,
        )

    # ------------------------------------------------------------ 生命周期
    def on_show(self, **_):
        self.date_label.configure(text=dt.date.today().strftime("今天是 %Y-%m-%d"))
        self._set_currency(self.currency.get(), refresh=False)
        self._show_form()
        self._reload()

    def _show_form(self) -> None:
        self.showing = "form"
        self.cal_page.pack_forget()
        self.form_page.pack(fill="both", expand=True)
        self.cal_btn.set_text("📅 日历")

    def _show_calendar(self) -> None:
        self.showing = "calendar"
        self.form_page.pack_forget()
        self.cal_page.pack(fill="both", expand=True)
        self.cal_btn.set_text("✎ 记账")
        self._back_to_month()
        self.cal.refresh()

    def _toggle_calendar(self) -> None:
        self._show_calendar() if self.showing == "form" else self._show_form()

    def _set_currency(self, cur: str, refresh: bool = True) -> None:
        self.currency.set(cur)
        for c, b in self.cur_btns.items():
            on = c == cur
            # 选中态: 淡橙底 + 主色字
            b.set_palette(theme.PRIMARY_SOFT if on else theme.CARD,
                          fg=theme.PRIMARY if on else theme.TEXT)
        if refresh:
            self._reload()

    def _reload(self) -> None:
        cur = self.currency.get()
        sign = C.CURRENCY_SIGN[cur]
        t = self.app.db.ledger_totals(cur)
        self.stat_labels["balance"].configure(text=f"{sign}{C.fmt_money(t['balance'], cur)}")
        self.stat_labels["income"].configure(text=f"{sign}{C.fmt_money(t['income'], cur)}")
        self.stat_labels["balance"].configure(
            fg=theme.SUCCESS if t["balance"] >= 0 else theme.ERROR)
        self.income_card.configure(highlightbackground=theme.BORDER)
        self.expense_card.configure(highlightbackground=theme.BORDER)
        for ent, color in ((self.inc_amount, theme.SUCCESS), (self.exp_amount, theme.ERROR)):
            ent.configure(highlightcolor=color)
        n = len(self.app.db.ledger_all(cur))
        self.hint.configure(
            text=f"当前币种：{C.CURRENCY_NAME[cur]}　共 {n} 笔记录　"
                 f"金额最多两位小数，同一天可以多次提交")
        if self.showing == "calendar":
            self.cal.refresh()

    # ------------------------------------------------------------ 操作
    def _submit(self, kind: str) -> None:
        cur = self.currency.get()
        src_ent, amt_ent = ((self.inc_source, self.inc_amount) if kind == "income"
                            else (self.exp_source, self.exp_amount))
        cents = C.parse_money(amt_ent.get())
        if cents is None:
            messagebox.showwarning("金额不对", "请填写金额，最多两位小数，例如 22.70。", parent=self)
            amt_ent.focus_set()
            return
        if cents == 0:
            messagebox.showwarning("金额为 0", "金额需要大于 0。", parent=self)
            amt_ent.focus_set()
            return
        src = _real_text(src_ent)
        if not src:
            src = "未填写"
        self.app.db.ledger_add(kind, src, cur, cents)
        _reset_entry(amt_ent)
        _reset_entry(src_ent)
        self._reload()
        word = "收入" if kind == "income" else "支出"
        self.hint.configure(
            text=f"已记一笔{word}：{C.CURRENCY_NAME[cur]} "
                 f"{C.CURRENCY_SIGN[cur]}{C.fmt_money(cents, cur)}　·　{src}")

    def _open_detail(self) -> None:
        LedgerDetailDialog(self, self.app, self.currency.get())


# ==================================================================== 账单明细
class LedgerDetailDialog(tk.Toplevel):
    """账单明细 + 底部一张每日收支柱状图 (含净值折线, 双纵轴).

    横坐标是"天", 但一天可能提交很多笔, 全画出来会挤成一团 —— 所以
    明细表按月列出每一笔(精确到秒), 图表按天聚合。
    """

    def __init__(self, master, app, currency: str):
        super().__init__(master, bg=theme.BG)
        self.app = app
        self.title(f"账单明细 — {C.CURRENCY_NAME[currency]}")
        self.transient(master.winfo_toplevel())
        center_window(self, 1000, 780)
        self.minsize(880, 660)
        self.currency = currency
        today_d = dt.date.today()
        self.year, self.month = today_d.year, today_d.month
        style_treeview(self)
        self._build()
        self._reload()
        self.grab_set()

    def _build(self) -> None:
        head = tk.Frame(self, bg=theme.BG)
        head.pack(fill="x", padx=22, pady=(18, 6))
        tk.Label(head, text="账单明细", bg=theme.BG, fg=theme.TEXT,
                 font=theme.f(15, "bold")).pack(side="left")
        # 月份切换: 顺序必须是 ‹ 上个月 在左、› 下个月 在右
        FlatButton(head, "‹ 上个月", self._prev_month, bg=theme.CARD, font=theme.f(10),
                   padx=10, pady=5).pack(side="left", padx=(16, 0))
        self.month_label = tk.Label(head, text="", bg=theme.BG, fg=theme.TEXT,
                                    font=theme.f(12, "bold"), width=12)
        self.month_label.pack(side="left", padx=6)
        FlatButton(head, "下个月 ›", self._next_month, bg=theme.CARD, font=theme.f(10),
                   padx=10, pady=5).pack(side="left")
        FlatButton(head, "关闭", self.destroy, bg=theme.CARD, font=theme.f(10),
                   padx=14, pady=6).pack(side="right")
        FlatButton(head, "删除选中", self._delete_selected, bg=theme.CARD,
                   font=theme.f(10), padx=14, pady=6).pack(side="right", padx=(0, 8))

        self.stat = tk.Label(self, text="", bg=theme.BG, fg=theme.MUTED, font=theme.f(10))
        self.stat.pack(anchor="w", padx=24)

        # 表格与图表区用 grid 按权重分高度: 表格约 2/5, 图表约 3/5。
        # 全部用 pack 时 Treeview 会一路撑高, 把折线图挤出可视区域。
        area = tk.Frame(self, bg=theme.BG)
        area.pack(fill="both", expand=True, padx=22, pady=(8, 16))
        area.grid_rowconfigure(0, weight=2)
        area.grid_rowconfigure(1, weight=3)
        area.grid_columnconfigure(0, weight=1)

        cols = ("time", "kind", "source", "amount", "balance")
        heads = ("时间", "类型", "来源 / 方向", "金额", "累计余额")
        widths = (150, 80, 320, 130, 140)
        wrap = tk.Frame(area, bg=theme.BG)
        wrap.grid(row=0, column=0, sticky="nsew", pady=(0, 8))
        self.tree = ttk.Treeview(wrap, columns=cols, show="headings", selectmode="browse")
        for c, h, w in zip(cols, heads, widths):
            self.tree.heading(c, text=h)
            self.tree.column(c, width=w, minwidth=70,
                             anchor="center" if c in ("kind", "amount", "balance") else "w")
        vs = ttk.Scrollbar(wrap, orient="vertical", command=self.tree.yview)
        hs = ttk.Scrollbar(wrap, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vs.set, xscrollcommand=hs.set)
        hs.pack(side="bottom", fill="x")
        vs.pack(side="right", fill="y")
        self.tree.pack(fill="both", expand=True)
        self.tree.tag_configure("income", foreground=theme.SUCCESS)
        self.tree.tag_configure("expense", foreground=theme.ERROR)
        self.tree.bind("<Delete>", lambda e: self._delete_selected())

        # ---- 图表区: 每日收支柱状图 + 净值折线 (双纵轴)
        charts = tk.Frame(area, bg=theme.BG)
        charts.grid(row=1, column=0, sticky="nsew")
        tk.Label(charts, text=f"最近 {CHART_DAYS} 天　"
                              "绿柱向上 = 当日收入　红柱向下 = 当日支出　"
                              "蓝线 = 当日净值（三者共用左侧金额轴）",
                 bg=theme.BG, fg=theme.MUTED, font=theme.f(9)).pack(anchor="w")
        from .charts import IncomeExpenseChart

        self.chart = IncomeExpenseChart(charts)
        self.chart.pack(fill="both", expand=True, pady=(2, 0))

    # ------------------------------------------------------------ 数据
    def _prev_month(self) -> None:
        self.year, self.month = (self.year - 1, 12) if self.month == 1 else \
                                (self.year, self.month - 1)
        self._reload()

    def _next_month(self) -> None:
        self.year, self.month = (self.year + 1, 1) if self.month == 12 else \
                                (self.year, self.month + 1)
        self._reload()

    def _reload(self) -> None:
        import calendar as pycal

        cur = self.currency
        sign = C.CURRENCY_SIGN[cur]
        pre = f"{self.year:04d}-{self.month:02d}"
        self.month_label.configure(text=f"{self.year} 年 {self.month} 月")

        rows = [r for r in self.app.db.ledger_all(cur) if str(r["day"]).startswith(pre)]
        self.tree.delete(*self.tree.get_children())
        # 明细按时间正序显示, 便于看"累计余额"这一列
        running = 0
        for r in reversed(rows):
            amt = int(r["cents"])
            running += amt if r["kind"] == "income" else -amt
            self.tree.insert(
                "", "end", iid=str(r["id"]),
                values=(" ".join(str(r["at"]).replace("T", " ").split(" ")[:2]),
                        "收入" if r["kind"] == "income" else "支出",
                        r["source"] or "—",
                        ("+" if r["kind"] == "income" else "−") + f"{sign}{C.fmt_money(amt, cur)}",
                        f"{sign}{C.fmt_money(abs(running), cur)}"
                        + ("（负）" if running < 0 else "")),
                tags=(r["kind"],),
            )

        m = self.app.db.ledger_month(cur, self.year, self.month)
        self.stat.configure(
            text=f"本月 {m['count']} 笔　收入 {sign}{C.fmt_money(m['income'], cur)}　"
                 f"支出 {sign}{C.fmt_money(m['expense'], cur)}　"
                 f"结余 {sign}{C.fmt_money(abs(m['balance']), cur)}"
                 + ("（净支出）" if m["balance"] < 0 else ""),
            fg=theme.SUCCESS if m["balance"] >= 0 else theme.ERROR,
        )

        # 图表只看最近 CHART_DAYS 天 (day-15 … day0), 横坐标单位为天。
        # 颗粒度按天比整月更有用: 整月 31 格时每格太窄, 也看不出近期趋势。
        now = dt.date.today()
        last_of_month = dt.date(self.year, self.month,
                                pycal.monthrange(self.year, self.month)[1])
        end = min(last_of_month, now)
        start = end - dt.timedelta(days=CHART_DAYS - 1)
        daily = self.app.db.ledger_daily(cur, start.isoformat(), end.isoformat())
        data = []
        for i in range(CHART_DAYS):
            d = start + dt.timedelta(days=i)
            per = daily.get(d.isoformat()) or {"inc": 0, "exp": 0}
            data.append((f"{d.month}/{d.day}", per["inc"] / 100.0, per["exp"] / 100.0))
        # 刻度用整数够读; 悬停提示要精确到分, 所以两者分开
        self.chart.set_data(data, lambda v: f"{v:,.0f}",
                            unit=C.CURRENCY_SIGN[cur])

    def _delete_selected(self) -> None:
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("提示", "请先选中一条记录。", parent=self)
            return
        if not messagebox.askyesno("确认", f"确定删除选中的 {len(sel)} 条记录吗？", parent=self):
            return
        for iid in sel:
            self.app.db.ledger_del(int(iid))
        self._reload()
