"""试卷集 (collection): 一套题库 = 一个 JSON 文件.

目录约定:
    data/minna_tests.json      —— 历史遗留, 视作「新标日初级上单元测试」
    data/exams/*.json          —— 其余试卷集, 每个文件自带 meta

每个 JSON 的结构:
    {
      "version": 2,
      "meta": {"id": "...", "name": "...", "kind": "unit|jlpt",
               "desc": "...", "duration_min": 105, "order": 20},
      "lessons": [ {"lesson": 1, "title": "2010年07月",
                    "duration_min": 105, "sections": [...] } ]
    }

新标日那份没有 meta, 这里给它补一份默认值, 保证两套数据用同一套代码。
"""
from __future__ import annotations

import json
from pathlib import Path

from .config import APP_DIR

DATA_DIR = APP_DIR / "data"
EXAM_DIR = DATA_DIR / "exams"

# 历史题库的默认 meta (它没有 meta 字段)
DEFAULT_META = {
    "id": "shinbunpo-1",
    "name": "新标日初级上单元测试",
    "kind": "unit",
    "desc": "24 课同步测试卷",
    "duration_min": 0,          # 0 = 不计时 (练习模式)
    "order": 10,
}


def _bank_paths() -> list[Path]:
    out: list[Path] = []
    legacy = DATA_DIR / "minna_tests.json"
    if legacy.is_file():
        out.append(legacy)
    if EXAM_DIR.is_dir():
        out.extend(sorted(EXAM_DIR.glob("*.json")))
    return out


def _load(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:       # noqa: BLE001
        return None
    if not isinstance(data, dict):
        return None
    meta = dict(DEFAULT_META) if path.name == "minna_tests.json" else {}
    if not meta and not isinstance(data.get("meta"), dict):
        return None
    # 允许"占位"试卷集 (meta 有、卷子还没导入), 方便先列出来再导入
    if "lessons" not in data:
        data["lessons"] = []
    if not isinstance(data["lessons"], list):
        return None
    meta.update(data.get("meta") or {})
    if "id" not in meta or not meta["id"]:
        meta["id"] = path.stem
    meta.setdefault("name", path.stem)
    meta.setdefault("kind", "unit")
    meta.setdefault("desc", "")
    meta.setdefault("duration_min", 0)
    meta.setdefault("order", 50)
    for les in data["lessons"]:
        les.setdefault("duration_min", meta["duration_min"])
    data["meta"] = meta
    data["_path"] = str(path)
    return data


def all_collections() -> list[dict]:
    """按 order 排序的所有试卷集 (含 meta 与统计数据)."""
    out = []
    seen = set()
    for path in _bank_paths():
        data = _load(path)
        if not data:
            continue
        meta = data["meta"]
        if meta["id"] in seen:
            continue
        seen.add(meta["id"])
        items = sum(len(s.get("items") or [])
                    for les in data["lessons"] for s in les.get("sections") or [])
        out.append({
            **meta,
            "path": data["_path"],
            "papers": len(data["lessons"]),
            "items": items,
        })
    out.sort(key=lambda m: (m.get("order", 50), m.get("name", "")))
    return out


def collection(cid: str) -> dict | None:
    for meta in all_collections():
        if meta["id"] == cid:
            return meta
    return None


def load(cid: str) -> dict | None:
    """读某个试卷集的完整题库 (带 meta)."""
    for path in _bank_paths():
        data = _load(path)
        if data and data["meta"]["id"] == cid:
            return data
    return None


def default_id() -> str:
    cols = all_collections()
    return cols[0]["id"] if cols else DEFAULT_META["id"]


def save_path(cid: str) -> Path:
    """导入新试卷集时建议写入的文件名."""
    EXAM_DIR.mkdir(parents=True, exist_ok=True)
    return EXAM_DIR / f"{cid}.json"
