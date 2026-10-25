"""新标日测试题库: 读取 data/minna_tests.json 并提供查询/统计.

题库是**只读**的静态数据, 由 tools/build_minna_tests.py 从 PDF 生成,
桌面与手机 PWA 共用同一份 JSON。进度与成绩存本机 SQLite (见 db.py)。
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from .config import APP_DIR

CANDIDATES = (
    APP_DIR / "data" / "minna_tests.json",
    Path(__file__).resolve().parent.parent / "data" / "minna_tests.json",
)

KIND_NAME = {"fill": "填空", "choice": "选择", "translate": "翻译"}

# 当前正在使用的题库 (由界面按试卷集切换); None = 用历史那份
_ACTIVE: dict | None = None


def use(bank: dict | None) -> None:
    """切换当前试卷集. 传 None 回到默认的历史题库."""
    global _ACTIVE
    _ACTIVE = bank
    # load_bank 是 lru_cache 的, 不清掉的话切到另一套卷子读到的还是旧题库
    load_bank.cache_clear()


def active_meta() -> dict:
    if _ACTIVE and _ACTIVE.get("meta"):
        return dict(_ACTIVE["meta"])
    return {"id": "shinbunpo-1", "name": "新标日初级上单元测试",
            "kind": "unit", "duration_min": 0}


@lru_cache(maxsize=1)
def load_bank() -> dict:
    """读取题库; 找不到时返回空壳 (界面会提示)。"""
    if _ACTIVE is not None:
        return _ACTIVE
    for p in CANDIDATES:
        try:
            if p.is_file():
                return json.loads(p.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
    return {"version": 1, "lessons": [], "source": ""}


def lessons() -> list[dict]:
    return load_bank().get("lessons") or []


def lesson(num: int) -> dict | None:
    for les in lessons():
        if les.get("lesson") == num:
            return les
    return None


def total_items(les: dict) -> int:
    return sum(len(s.get("items") or []) for s in les.get("sections") or [])


def all_items(les: dict) -> list[dict]:
    """按大题/小题顺序摊平, 附带所属大题信息."""
    out = []
    for sec in les.get("sections") or []:
        for i, it in enumerate(sec.get("items") or []):
            out.append({**it, "section": sec["no"], "kind": sec["kind"],
                        "title": sec.get("title", ""), "index": i})
    return out


def has_answer(item: dict) -> bool:
    a = item.get("answer")
    if item.get("kind") == "choice":
        return isinstance(a, int) and a >= 1
    return bool(a)


def lesson_ready(les: dict) -> bool:
    """整课是否有答案可判分 (第 24 课原卷缺答案, 全部改自评)."""
    return bool(les) and not les.get("no_answer")


def fmt_seconds(sec: int) -> str:
    """列表里的"完成时间": 没有记录时给破折号."""
    if not sec:
        return "—"
    return fmt_clock(sec)


def fmt_clock(sec: int) -> str:
    """计时器/用时: 永远给出 mm:ss (0 秒也是 00:00)."""
    sec = max(0, int(sec or 0))
    m, s = divmod(sec, 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"
