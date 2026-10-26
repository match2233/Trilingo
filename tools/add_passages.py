"""给「七、阅读」的题补上文章 —— 题面变成 「【文章】… 【問】…」.

为什么: 题库里只存了问题和选项, 用户答题时看不到文章, 根本没法做。
上册的読解就是这么做的 (prompt 里带【文章】), 这里沿用同一套约定,
界面遇到长题干会自动放进可滚动区域。
"""
from __future__ import annotations

import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools.build_chujixia_ai import split_lessons, TXT  # noqa: E402

BANK = ROOT / "data" / "exams" / "shinbunpo-2.json"


def passage_of(body: str) -> str:
    """取这一课「七、」里文章部分 (第一个小题之前的所有内容)."""
    i = body.find("七、")
    if i < 0:
        return ""
    rest = body[i:]
    # 截到答案段
    for marker in ("\n一、", "\n第", "\n一、 "):
        p = rest.find(marker, 3)
        if p > 0:
            rest = rest[:p]
    # 去掉大题说明
    rest = re.sub(r"^七、[^)]*\)\s*", "", rest, count=1)
    rest = re.sub(r"^七、[^\n]*?\s{2,}", "", rest, count=1)
    # 文章 = 第一个「1.」之前
    m = re.search(r"(?<![0-9])1\s*[.．]", rest)
    passage = rest[:m.start()] if m else rest
    passage = re.sub(r"\s+", " ", passage).strip()
    return passage


def main() -> int:
    lessons_text = dict(split_lessons(TXT.read_text(encoding="utf-8")))
    bank = json.loads(BANK.read_text(encoding="utf-8"))

    filled = 0
    for les in bank["lessons"]:
        no = les["lesson"]
        passage = passage_of(lessons_text.get(no, ""))
        if not passage:
            continue
        for sec in les["sections"]:
            if not sec["title"].startswith("七"):
                continue
            for it in sec["items"]:
                if it["prompt"].startswith("【文章】"):
                    continue
                it["prompt"] = f"【文章】{passage}\n【問】{it['prompt']}"
                filled += 1
            sec["passage"] = passage

    BANK.write_text(json.dumps(bank, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"给 {filled} 道阅读题补上了文章")
    sample = next((it["prompt"] for les in bank["lessons"] for sec in les["sections"]
                   if sec["title"].startswith("七") for it in sec["items"]), "")
    print("样例:", sample[:160].replace("\n", " ⏎ "))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
