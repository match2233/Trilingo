"""体重趋势的统计工具：时段校正 + 稳健趋势.

为什么不能直接对原始体重拟合：
  * **一天内波动大**：晨起空腹与晚间饭后能差 1~2kg，直接平均会被"记录时间"
    带偏（某段时间只在晚上记，趋势就会假性上翘）。
  * **冬衣**：整体水位随季节抬高，属于系统偏差，不是肌肉/脂肪的变化。

做法：
  1. **时段校正**：先用历史数据估计每个整点相对"当天中位数"的偏移，
     再把每条记录减掉对应偏移 —— 相当于统一折算到"同一生理状态"。
  2. 每天取校正后的**中位数**（比均值抗离群点）。
  3. **7 日滚动中位数** 作为绿线（比均值更抗单个异常日）。
  4. **Theil–Sen 斜率**（所有点两两斜率的中位数）估计 kg/周，对离群点免疫。
"""
from __future__ import annotations

import datetime as dt
import statistics

# ---------------- 时段偏移 ----------------

def hour_offsets(records: list[tuple[str, float]]) -> dict[int, float]:
    """估计每个整点相对当天中位数的平均偏移（kg）。

    数据不够时返回空字典，调用方要能接受"没有校正"。
    """
    by_day: dict[dt.date, list[tuple[int, float]]] = {}
    for at, kg in records:
        ts = dt.datetime.fromisoformat(at)
        by_day.setdefault(ts.date(), []).append((ts.hour, kg))

    diffs: dict[int, list[float]] = {}
    for items in by_day.values():
        if len(items) < 2:          # 当天只有一条记录，没法比较
            continue
        med = statistics.median(kg for _h, kg in items)
        for hour, kg in items:
            diffs.setdefault(hour, []).append(kg - med)

    # 至少要有两个不同时段、且样本不太少才值得校正
    usable = {h: v for h, v in diffs.items() if len(v) >= 2}
    if len(usable) < 2:
        return {}
    return {h: statistics.median(v) for h, v in usable.items()}


def corrected(records: list[tuple[str, float]],
              offsets: dict[int, float] | None = None
              ) -> list[tuple[dt.datetime, float, float]]:
    """返回 [(时间, 原始体重, 校正后体重)]."""
    offsets = offsets if offsets is not None else hour_offsets(records)
    out = []
    for at, kg in records:
        ts = dt.datetime.fromisoformat(at)
        adj = offsets.get(ts.hour, 0.0) if offsets else 0.0
        out.append((ts, kg, round(kg - adj, 3)))
    return out


def daily_points(items: list[tuple[dt.datetime, float, float]],
                 use_corrected: bool = True) -> list[tuple[dt.date, float]]:
    """每天取中位数（校正后或原始）。"""
    by_day: dict[dt.date, list[float]] = {}
    for ts, kg, adj in items:
        by_day.setdefault(ts.date(), []).append(adj if use_corrected else kg)
    return [(d, round(statistics.median(v), 2)) for d, v in sorted(by_day.items())]


def rolling_median(points: list[tuple[dt.date, float]],
                   window: int = 7) -> list[tuple[dt.date, float]]:
    """滚动中位数：比滚动均值更抗单日异常（比如某天喝了很多水）。"""
    out = []
    for i in range(len(points)):
        lo = max(0, i - window + 1)
        chunk = [v for _d, v in points[lo:i + 1]]
        out.append((points[i][0], round(statistics.median(chunk), 2)))
    return out


def theil_sen(points: list[tuple[dt.date, float]]) -> float:
    """Theil–Sen 斜率，单位 kg/周；对离群点免疫。"""
    if len(points) < 2:
        return 0.0
    xs = [(d - points[0][0]).days for d, _v in points]
    ys = [v for _d, v in points]
    slopes = []
    for i in range(len(points)):
        for j in range(i + 1, len(points)):
            dx = xs[j] - xs[i]
            if dx:
                slopes.append((ys[j] - ys[i]) / dx)
    if not slopes:
        return 0.0
    return round(statistics.median(slopes) * 7, 2)
