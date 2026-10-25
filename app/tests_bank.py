"""日语试卷集: 一套一套的试卷, 按"试卷集"分组管理.

目录结构 (data/tests/):
    index.json          试卷集清单
    minna_l1.json       新标日初级上 24 课单元测试
    jlpt_n5.json        JLPT N5 历年真题

每个试卷集文件: {"id","name","kind","papers":[{"lesson":1,"title":"...","minutes":105,...}]}
* `lesson` 是该试卷在**全库唯一**的编号 —— 各集分配不重叠的号段
  (单元测试 1..999, N5 从 1001 起, 以后的 N4 从 2001 起…), 这样收藏夹、
  进度、成绩都不必改表结构, 天然按集独立。

对外的 `lesson(n)` / `lessons()` 仍以全局编号工作, 老代码不用改。
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from .config import APP_DIR

DATA_DIR = APP_DIR / "data"
TESTS_DIR = DATA_DIR / "tests"
INDEX_FILE = TESTS_DIR / "index.json"

KIND_NAME = {"fill": "填空", "choice": "选择", "translate": "翻译"}
TYPE_NAME = {"unit": "单元测试", "jlpt": "能力考试"}


# ------------------------------------------------------------------ 清单
@lru_cache(maxsize=1)
def collections() -> list[dict]:
    """试卷集清单. 文件不存在时退回到内置的单集结构."""
    try:
        raw = json.loads(INDEX_FILE.read_text(encoding="utf-8"))
        cols = raw.get("collections") or []
        if cols:
            return cols
    except Exception:      # noqa: BLE001
        pass
    return [{"id": "minna_l1", "name": "新标日初级上单元测试", "kind": "unit",
             "base": 1, "file": "minna_l1.json", "desc": "24 课同步测试卷"}]


def collection(cid: str | None = None) -> dict | None:
    cols = collections()
    if cid is None:
        return cols[0] if cols else None
    for c in cols:
        if c["id"] == cid:
            return c
    return None


@lru_cache(maxsize=16)
def bank(cid: str | None = None) -> dict:
    col = collection(cid)
    if col is None:
        return {"lessons": []}
    path = TESTS_DIR / col["file"]
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:      # noqa: BLE001
        return {"lessons": []}


def refresh() -> None:
    """导入试卷后调用, 清掉缓存."""
    collections.cache_clear()
    bank.cache_clear()


# ------------------------------------------------------------------ 查询
def lessons(cid: str | None = None) -> list[dict]:
    return bank(cid).get("lessons") or []


def lesson(num: int, cid: str | None = None) -> dict | None:
    """按全局编号取试卷; 不指定 cid 时在所有试卷集里找."""
    if cid is None:
        for col in collections():
            for les in lessons(col["id"]):
                if les.get("lesson") == num:
                    return les
        return None
    for les in lessons(cid):
        if les.get("lesson") == num:
            return les
    return None


def collection_of(num: int) -> dict | None:
    """这道试卷属于哪个集."""
    for col in collections():
        for les in lessons(col["id"]):
            if les.get("lesson") == num:
                return col
    return None


def total_items(les: dict) -> int:
    return sum(len(s.get("items") or []) for s in les.get("sections") or [])


def all_items(les: dict) -> list[dict]:
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
    return isinstance(a, str) and bool(a.strip())


def lesson_ready(les: dict) -> bool:
    return any(has_answer(it) for s in les.get("sections") or []
               for it in s.get("items") or [])


def fmt_seconds(sec: int) -> str:
    if not sec:
        return "—"
    return fmt_clock(sec)


def fmt_clock(sec: int) -> str:
    sec = max(0, int(sec or 0))
    m, s = divmod(sec, 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def paper_meta(les: dict) -> dict:
    """交卷/倒计时用的元信息."""
    total = total_items(les)
    return {
        "minutes": int(les.get("minutes") or 0),      # 0 = 不限时(计时用)
        "total": total,
        "score_max": int(les.get("score_max") or 0),  # 0 = 按题数计分
    }
