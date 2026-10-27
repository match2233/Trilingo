"""批量导入 N5 文件夹下的所有卷子 (逐套调用 import_paper 的流程)."""
from __future__ import annotations

import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import exams  # noqa: E402

PY = sys.executable
N5 = pathlib.Path(__file__).resolve().parent.parent / "data" / "import" / "N5"

# 已经导过的标题关键字 (跳过)
SKIP = ("2016年", "2012年12月")


def next_paper_no(cid: str) -> int:
    bank = exams.load(cid) or {}
    used = {int(l.get("lesson", 0)) for l in bank.get("lessons") or []}
    n = 1
    while n in used:
        n += 1
    return n


def main() -> int:
    folders = [d for d in sorted(N5.iterdir()) if d.is_dir()]
    for d in folders:
        name = d.name
        key = name.split("(")[0]
        if any(s in name for s in SKIP):
            print(f"跳过 {name} (已导入)")
            continue
        paper_no = next_paper_no("jlpt-n5")
        print(f"\n=== {name} -> 第 {paper_no} 套 ===", flush=True)
        rc = subprocess.call(
            [PY, str(ROOT / "tools" / "import_paper.py"), str(d),
             "--title", key, "--minutes", "105", "--paper", str(paper_no)],
            cwd=ROOT)
        print(f"  -> {'成功' if rc == 0 else '失败 rc=' + str(rc)}", flush=True)
    bank = exams.load("jlpt-n5") or {}
    for les in bank.get("lessons") or []:
        n = sum(len(s["items"]) for s in les["sections"])
        print(f"  第{les['lesson']}套 {les['title'][:26]:28s} {n:3d} 题")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
