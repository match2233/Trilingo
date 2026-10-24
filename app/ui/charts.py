"""图表控件: 每日收入/支出柱状图 + 净值折线 (纯 Canvas 手绘).

* **柱子** —— 横轴就是 0 线: 向上是当日**收入**(绿色), 向下是当日**支出**(红色)
* **折线** —— 当日净值 (收入 − 支出)

柱子、折线**共用同一根纵轴**: 三者本来就是同一个量纲 (元), 净值又必然落在
[−最大支出, +最大收入] 之间, 分两根轴只会让人对不上数。
柱子的高度直接就是金额, 不做任何压缩或放大, 所以"哪天花得多"一眼能比出来。
"""
from __future__ import annotations

import tkinter as tk

from . import theme

PAD_L = 62          # 左侧留白: 金额刻度
PAD_R = 20          # 右侧留白
PAD_T = 26          # 顶部留白: 图例
PAD_B = 28          # 底部留白: 日期刻度
GRID = "#EEF0F6"

COLOR_LINE = "#4A6CF7"      # 净值折线
BAR_W_RATIO = 0.52          # 柱子宽度占格子宽的比例
HOVER = "hover"             # 悬停覆盖层的标签 (高亮框 + 数值提示)


def _floor_log10(x: float) -> int:
    n = 0
    while x >= 10:
        x /= 10
        n += 1
    while x < 1:
        x *= 10
        n -= 1
    return n


def _nice_step(span: float, want: int = 4) -> float:
    """把刻度间隔取成 1/2/5×10^n 这类好读的数."""
    if span <= 0:
        return 1.0
    raw = span / max(1, want)
    mag = 10 ** _floor_log10(raw)
    for m in (1, 2, 2.5, 5, 10):
        if raw <= m * mag:
            return m * mag
    return 10 * mag


def _ticks(lo: float, hi: float, want: int = 4) -> list[float]:
    if hi <= lo:
        hi = lo + 1
    step = _nice_step(hi - lo, want)
    start = int(lo / step) * step
    out, v = [], start
    while v <= hi + step * 0.001:
        if v >= lo - step * 0.001:
            out.append(round(v, 6))
        v += step
    return out or [lo, hi]


class IncomeExpenseChart(tk.Canvas):
    """每日收支柱状图 + 净值折线."""

    def __init__(self, master, **kw):
        kw.setdefault("height", 300)
        super().__init__(master, bg=theme.CARD, highlightthickness=1,
                         highlightbackground=theme.BORDER, **kw)
        # [(标签, 收入, 支出)]
        self._data: list[tuple[str, float, float]] = []
        self._fmt = lambda v: f"{v:,.0f}"      # 刻度用: 整数够读
        self._tip_fmt = lambda v: f"{v:,.2f}"  # 悬停提示用: 精确到分
        self._cur = -1          # 鼠标当前停在哪个格子 (-1 = 没停)
        self._unit = ""         # 提示里的货币符号
        self.bind("<Configure>", lambda e: self.redraw())
        self.bind("<Motion>", self._on_motion)
        self.bind("<Leave>", self._on_leave)

    def set_data(self, rows: list[tuple[str, float, float]], fmt=None,
                 unit: str = "") -> None:
        self._data = list(rows)
        if fmt:
            self._fmt = fmt
        self._unit = unit
        self._cur = -1
        self.redraw()

    # ------------------------------------------------------------ 悬停
    def _on_motion(self, event) -> None:
        """鼠标移到某一天的区域, 就把那天的三个数标出来."""
        if not self._data:
            return
        n = len(self._data)
        left = PAD_L
        right = max(self.winfo_width(), 160) - PAD_R
        step = (right - left) / n
        idx = int((event.x - left) // step) if event.x >= left else -1
        if idx < 0 or idx >= n:
            idx = -1
        if idx != self._cur:
            self._cur = idx
            self.redraw()

    def _on_leave(self, _event=None) -> None:
        if self._cur != -1:
            self._cur = -1
            self.redraw()

    def _draw_tip(self, w) -> None:
        """在光标所在的那一天上标出 收入 / 支出 / 净值 三个数.

        全部打上 HOVER 标签, 只要"当天的三行数字"就能被单独取出来。
        """
        i = self._cur
        label, inc, exp = self._data[i]
        net = inc - exp
        lines = [
            (label, theme.TEXT, True),
            (f"收入  {self._unit}{self._tip_fmt(inc)}", theme.SUCCESS, False),
            (f"支出  {self._unit}{self._tip_fmt(exp)}", theme.ERROR, False),
            (f"净值  {self._unit}{self._tip_fmt(net)}",
             theme.SUCCESS if net >= 0 else theme.ERROR, False),
        ]
        pad, row_h = 8, 15
        tw = max(len(t) for t, _c, _b in lines) * 7.8 + pad * 2
        th = len(lines) * row_h + pad
        # 贴着上沿放, 免得盖住柱子
        bx = PAD_L + (w - PAD_L - PAD_R) * (i + 0.5) - tw / 2
        bx = min(max(bx, PAD_L), w - PAD_R - tw)
        by = 20.0
        self.create_rectangle(bx, by, bx + tw, by + th,
                              fill="#FFFFFF", outline=theme.BORDER, tags=HOVER)
        for k, (text, color, bold) in enumerate(lines):
            self.create_text(bx + pad, by + pad / 2 + k * row_h, text=text,
                             anchor="w", fill=color, tags=HOVER,
                             font=theme.f(9, "bold" if bold else "normal"))

    # ------------------------------------------------------------ 绘制
    def redraw(self) -> None:
        self.delete("all")
        w = max(self.winfo_width(), 160)
        h = max(self.winfo_height(), 100)
        if not self._data:
            self.create_text(w / 2, h / 2, text="本月还没有记录",
                             fill=theme.MUTED, font=theme.f(10))
            return

        n = len(self._data)
        left, right = PAD_L, w - PAD_R
        top, bot = PAD_T, h - PAD_B
        step = (right - left) / n

        # ---- 纵轴: 金额. 柱子与净值共用这一根, 必须含 0。
        #
        # 先算出 0 线上方/下方**各需要多少量程**, 再据此定 0 线的位置, 最后由
        # 几何反推出 ± 两端的实际刻度值。这样保证:
        #   * 任何数据都完整落在画布内 (不会像固定量程那样把柱子裁掉)
        #   * 上下两侧刚好填满, 不会因为"多留一截"而浪费高度
        data = self._data
        up_need = max([i for _, i, _e in data] + [0.0])          # 收入最高
        down_need = max([e for _, _i, e in data] + [0.0])        # 支出最高
        nets = [i - e for _, i, e in data]
        # 净值可能比"最大单日收入/支出"更极端 (同一天又收又支时不会, 但保险起见)
        up_need = max(up_need, max(nets + [0.0]))
        down_need = max(down_need, max([-x for x in nets] + [0.0]))
        up_need = max(up_need, 1e-9)
        down_need = max(down_need, 1e-9)

        # 先按数据比例分, 再夹到 25%~75%, 免得金额太小被放大得顶天立地
        zero_ratio = up_need / (up_need + down_need)
        zero_ratio = min(max(zero_ratio, 0.25), 0.75)

        # 由 0 线位置反推两端刻度: 各自多留 8% 余量, 且不低于一点最小量程
        a_hi = max(up_need * 1.08, (bot - top) * zero_ratio * 0.02)
        a_lo = -max(down_need * 1.08, (bot - top) * (1 - zero_ratio) * 0.02)

        def y_of(v):
            """金额 -> 像素. 0 线按 zero_ratio 定位, 正数向上、负数向下."""
            y0_ = top + (bot - top) * zero_ratio
            if v >= 0:
                return y0_ - (v / a_hi) * (y0_ - top)
            return y0_ + (-v / -a_lo) * (bot - y0_)

        # ---- 网格 + 左侧金额刻度 (唯一一根纵轴)
        for v in _ticks(a_lo, a_hi):
            y = y_of(v)
            if not (top - 1 <= y <= bot + 1):
                continue
            self.create_line(left, y, right, y, fill=GRID)
            self.create_text(left - 8, y, text=self._fmt(v), anchor="e",
                             fill=theme.MUTED, font=theme.f(8))

        # ---- 横轴 (零线): 收入的柱子从它往上, 支出的从它往下
        y0 = y_of(0)
        self.create_line(left, y0, right, y0, fill=theme.BORDER, width=1)

        # ---- 柱子
        bw = max(4.0, min(26.0, step * BAR_W_RATIO))
        for i, (_label, inc, exp) in enumerate(self._data):
            cx = left + step * (i + 0.5)
            if inc <= 0 and exp <= 0:
                continue
            if inc > 0:      # 收入: 向上, 绿色
                self.create_rectangle(cx - bw / 2, y_of(inc), cx + bw / 2, y0,
                                      fill=theme.SUCCESS, outline=theme.SUCCESS)
            if exp > 0:      # 支出: 向下, 红色
                self.create_rectangle(cx - bw / 2, y0, cx + bw / 2, y_of(-exp),
                                      fill=theme.ERROR, outline=theme.ERROR)

        # ---- 净值折线 + 节点 (同一根轴)
        pts: list[float] = []
        for i, net in enumerate(nets):
            pts += [left + step * (i + 0.5), y_of(net)]
        if len(pts) >= 4:
            self.create_line(*pts, fill=COLOR_LINE, width=2, joinstyle="round")
        for i in range(0, len(pts), 2):
            x, y = pts[i], pts[i + 1]
            self.create_oval(x - 3, y - 3, x + 3, y + 3,
                             fill=theme.CARD, outline=COLOR_LINE, width=2)

        # ---- 底部日期刻度: 每格至少 34px 才不挤
        every = max(1, int(34 / max(step, 1)) + 1)
        for i, (label, _i, _e) in enumerate(self._data):
            if i % every and i != n - 1:
                continue
            self.create_text(left + step * (i + 0.5), bot + 14, text=label,
                             fill=theme.MUTED, font=theme.f(8))

        # ---- 图例
        self.create_rectangle(left, 7, left + 12, 19,
                              fill=theme.SUCCESS, outline=theme.SUCCESS)
        self.create_text(left + 18, 13, text="收入（向上）", anchor="w",
                         fill=theme.SUCCESS, font=theme.f(8))
        self.create_rectangle(left + 104, 7, left + 116, 19,
                              fill=theme.ERROR, outline=theme.ERROR)
        self.create_text(left + 122, 13, text="支出（向下）", anchor="w",
                         fill=theme.ERROR, font=theme.f(8))
        self.create_line(left + 208, 13, left + 232, 13, fill=COLOR_LINE, width=2)
        self.create_text(left + 238, 13, text="净值", anchor="w",
                         fill=COLOR_LINE, font=theme.f(8))

        # ---- 悬停: 高亮所在那一天 + 标出三个数
        if 0 <= self._cur < n:
            hl = left + step * self._cur
            self.create_rectangle(hl, top, hl + step, bot,
                                  fill="", outline=theme.BLUE, dash=(3, 2),
                                  tags=HOVER)
            self._draw_tip(w)
