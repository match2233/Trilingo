"""肌薄（身体素质）模块的常量与纯函数.

统计口径决定（README 里也会写一遍）：
  * **短期**（默认 14 天）：每一条体重记录都画出来 —— 一天之内饭前饭后、
    早晚、衣服厚薄都会让体重跳 0.5~1.5kg，短期图就是给你看这个波动的，
    所以纵轴范围按实际数据自适应，不做平滑。
  * **长期**（默认 180 天）：先把同一天的多条记录取平均，再用 **7 日移动平均**
    画趋势线；原始日均点用浅色小点垫底。增肌增重看的是这条趋势线，
    单日波动没有意义。
"""
from __future__ import annotations

import datetime as dt

# 动作清单：slug, 中文名, 英文名, 默认次数/组, 属于哪一天, 是否核心动作
MOVES: list[dict] = [
    {"slug": "incline-press", "cn": "哑铃上斜卧推", "en": "Incline Press",
     "reps": 12, "day": 1, "core": True},
    {"slug": "bench-press", "cn": "哑铃卧推", "en": "Bench Press",
     "reps": 12, "day": 1, "core": True},
    {"slug": "shoulder-press", "cn": "哑铃肩推", "en": "Shoulder Press",
     "reps": 12, "day": 1, "core": True},
    {"slug": "lateral-raise", "cn": "哑铃侧平举", "en": "Lateral Raise",
     "reps": 12, "day": 1, "core": False},
    {"slug": "triceps-ext", "cn": "哑铃颈后臂屈伸", "en": "Triceps Extension",
     "reps": 12, "day": 1, "core": False},
    {"slug": "rdl", "cn": "哑铃罗马尼亚硬拉", "en": "Romanian Deadlift",
     "reps": 12, "day": 2, "core": True},
    {"slug": "bent-row", "cn": "哑铃俯身划船", "en": "Bent-Over Row",
     "reps": 12, "day": 2, "core": True},
    {"slug": "single-row", "cn": "单臂哑铃划船", "en": "Single-Arm Row",
     "reps": 12, "day": 2, "core": False},
    {"slug": "reverse-fly", "cn": "哑铃反向飞鸟", "en": "Reverse Fly",
     "reps": 12, "day": 2, "core": False},
    {"slug": "face-pull", "cn": "哑铃面拉", "en": "Face Pull",
     "reps": 12, "day": 2, "core": False},
    {"slug": "bicep-curl", "cn": "哑铃二头弯举", "en": "Bicep Curl",
     "reps": 12, "day": 2, "core": False},
    {"slug": "goblet-squat", "cn": "哑铃高脚杯深蹲", "en": "Goblet Squat",
     "reps": 12, "day": 3, "core": True},
    {"slug": "crunch", "cn": "哑铃卷腹", "en": "Crunch",
     "reps": 12, "day": 3, "core": False},
    {"slug": "hip-thrust", "cn": "哑铃臀桥", "en": "Hip Thrust",
     "reps": 12, "day": 3, "core": False},
]

MOVE_BY_SLUG = {m["slug"]: m for m in MOVES}

# 训练计划的编排：三天、共 17 个动作条目。
# 肩推 / 面拉 / 侧平举在「推日/拉日」和「腿日」都会出现，按原计划重复列，
# 但共用同一个 slug —— 计数和历史上仍然算同一个动作。
DAY_PLAN: list[tuple[int, str, str, list[str]]] = [
    (1, "推日", "胸 / 肩 / 三头",
     ["incline-press", "bench-press", "shoulder-press",
      "lateral-raise", "triceps-ext"]),
    (2, "拉日", "背 / 二头",
     ["rdl", "bent-row", "single-row",
      "reverse-fly", "face-pull", "bicep-curl"]),
    (3, "腿日", "腿 / 臀 / 腹",
     ["goblet-squat", "shoulder-press", "face-pull",
      "lateral-raise", "crunch", "hip-thrust"]),
]

# 用户基本情况（用于 AI 建议与 BMI）
PROFILE = {"sex": "male", "height_cm": 0, "birth": ""}


def age_on(day: dt.date | None = None) -> int:
    day = day or dt.date.today()
    b = dt.date.fromisoformat(PROFILE["birth"])
    return day.year - b.year - ((day.month, day.day) < (b.month, b.day))


def bmi(kg: float) -> float:
    h = PROFILE["height_cm"] / 100
    return round(kg / (h * h), 1)


def pace_text(km: float, minutes: float) -> str:
    """配速：每公里几分几秒。"""
    if km <= 0 or minutes <= 0:
        return "—"
    sec = minutes * 60 / km
    return f"{int(sec // 60)}'{int(sec % 60):02d}\"/km"


def daily_mean(records: list[tuple[str, float]]) -> list[tuple[dt.date, float]]:
    """同一天多条记录取平均, 按日期升序."""
    by_day: dict[dt.date, list[float]] = {}
    for at, kg in records:
        day = dt.datetime.fromisoformat(at).date()
        by_day.setdefault(day, []).append(kg)
    return [(d, round(sum(v) / len(v), 2)) for d, v in sorted(by_day.items())]


def moving_average(points: list[tuple[dt.date, float]], window: int = 7):
    """滑动平均（按"条数"滑，不按天补齐，缺勤的日子不参与）。"""
    out = []
    for i in range(len(points)):
        lo = max(0, i - window + 1)
        chunk = [v for _d, v in points[lo:i + 1]]
        out.append((points[i][0], round(sum(chunk) / len(chunk), 2)))
    return out


def trend_slope(points: list[tuple[dt.date, float]]) -> float:
    """最小二乘斜率，单位 kg/周。"""
    if len(points) < 2:
        return 0.0
    xs = [(d - points[0][0]).days for d, _v in points]
    ys = [v for _d, v in points]
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    den = sum((x - mx) ** 2 for x in xs)
    if not den:
        return 0.0
    k = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / den
    return round(k * 7, 2)
