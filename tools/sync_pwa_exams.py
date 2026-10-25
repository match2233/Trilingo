"""把试卷集清单同步给手机端 (docs/exams/index.json + 题库副本).

PWA 不能扫目录, 所以由电脑端在导入后跑一次这个脚本:
    python tools/sync_pwa_exams.py
"""
from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import exams  # noqa: E402

DOCS = ROOT / "docs"
OUT = DOCS / "exams"


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    for meta in exams.all_collections():
        bank = exams.load(meta["id"]) or {}
        row = {
            "id": meta["id"], "name": meta["name"], "kind": meta["kind"],
            "desc": meta.get("desc", ""),
            "duration_min": meta.get("duration_min", 0),
            "papers": meta["papers"], "items": meta["items"],
            "empty": not bank.get("lessons"),
        }
        if bank.get("lessons"):
            if meta["id"] == "shinbunpo-1":
                row["bank"] = "minna_tests.json"
            else:
                name = f"{meta['id']}.json"
                src = pathlib.Path(bank["_path"])
                (OUT / name).write_text(src.read_text(encoding="utf-8"),
                                        encoding="utf-8")
                row["bank"] = f"exams/{name}"
        rows.append(row)
    (OUT / "index.json").write_text(
        json.dumps({"collections": rows}, ensure_ascii=False, indent=1),
        encoding="utf-8")
    print("已写 docs/exams/index.json:", [(r["id"], r["papers"]) for r in rows])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
