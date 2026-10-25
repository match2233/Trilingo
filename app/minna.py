"""新标日 / JLPT 试卷的读取入口.

实际数据在 data/tests/ 下按"试卷集"分文件存放, 具体见 app/tests_bank.py。
这里保留原来的函数名, 让界面与老代码不必改动 —— 只是多了一个可选的
`cid` 参数: 不传就用当前试卷集。
"""
from __future__ import annotations

from . import tests_bank as tb
from .tests_bank import (KIND_NAME, TYPE_NAME, all_items, collection,  # noqa: F401
                         collection_of, collections, fmt_clock, fmt_seconds,
                         has_answer, lesson_ready, paper_meta, refresh,
                         total_items)

__all__ = [
    "KIND_NAME", "TYPE_NAME", "all_items", "collections", "collection",
    "collection_of", "lessons", "lesson", "total_items", "has_answer",
    "lesson_ready", "fmt_seconds", "fmt_clock", "paper_meta", "refresh",
    "current", "set_current",
]

# 当前正在看的试卷集 id (界面切换时设置); 只影响 lessons() 的默认值
_current: str | None = None


def set_current(cid: str | None) -> None:
    global _current
    _current = cid


def current() -> dict | None:
    return tb.collection(_current)


def lessons(cid: str | None = None) -> list[dict]:
    return tb.lessons(cid if cid is not None else _current)


def lesson(num: int, cid: str | None = None) -> dict | None:
    return tb.lesson(num, cid)
