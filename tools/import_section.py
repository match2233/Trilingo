"""按「問題」分块导入一个分区 (文字・語彙 / 文法・読解), 答案精确对齐.

为什么按問題而不是按页: 答案表就是 `問題N + 顺序` 的组织方式
(問題1 十个答案、問題2 八个答案…)。只要在同一个問題内按顺序编号,
答案顺序就是准的; 按页组装会多解/漏解一两题, 后面的答案就整体错位。

用法:
    python tools/import_section.py <ocr.json> --pages 3-4 \
        --answers data/ocr/answers_2010.json --section 文字・語彙 \
        --paper 3 --out data/ocr/sec_2010_text.json
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

MONDAI = re.compile(r"^\s*問題\s*([0-9０-９]+)")
TR = str.maketrans("０１２３４５６７８９", "0123456789")


def split_blocks(items: list[dict]) -> list[dict]:
    """把指定页的行按「問題N」切块."""
    out: list[dict] = []
    cur = None
    for page in items:
        for ln in page["lines"]:
            m = MONDAI.match(ln["text"])
            if m and len(ln["text"]) <= 50:
                num = int(str(m.group(1)).translate(TR))
                cur = {"no": num, "lines": [], "pages": [page["page"]]}
                out.append(cur)
                continue
            if cur is not None:
                cur["lines"].append(ln)
                if page["page"] not in cur["pages"]:
                    cur["pages"].append(page["page"])
    return [b for b in out if len(b["lines"]) >= 3]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("ocr")
    ap.add_argument("--pages", required=True)
    ap.add_argument("--answers", required=True)
    ap.add_argument("--section", required=True)
    ap.add_argument("--paper", type=int, required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    from tools.assemble_questions import ask, valid

    data = json.loads(pathlib.Path(a.ocr).read_text(encoding="utf-8-sig"))
    lo, _, hi = a.pages.partition("-")
    lo_i, hi_i = int(lo), int(hi or lo)
    items = [p for p in data["items"] if lo_i <= p["page"] <= hi_i]

    ans = json.loads(pathlib.Path(a.answers).read_text(encoding="utf-8-sig"))
    table = ans.get(a.section) or {}

    blks = split_blocks(items)
    print(f"第 {a.pages} 页 → {len(blks)} 个問題块, "
          f"答案表有 {sorted(table)}")

    out_items, problems = [], []
    for b in blks:
        key = f"問題{b['no']}"
        answers = table.get(key) or []
        if not answers:
            print(f"  ! {key} 没有答案, 跳过")
            continue
        page = {"page": b["pages"][0], "lines": b["lines"]}
        try:
            qs = [q for q in ask(page, "reading") if valid(q)[0]]
        except Exception as exc:      # noqa: BLE001
            print(f"  ! {key} 组装失败: {exc}")
            continue
        if len(qs) != len(answers):
            problems.append(f"{key}: 组装 {len(qs)} / 答案 {len(answers)}")
        for i, q in enumerate(qs[:len(answers)]):
            prompt = q["prompt"]
            if q.get("passage"):
                prompt = f'【文章】{q["passage"]}\n【問】{prompt}'
            out_items.append({"mondai": b["no"], "idx": i + 1,
                              "prompt": prompt, "options": q["options"],
                              "answer": answers[i]})
        print(f"  {key}: {min(len(qs), len(answers))}/{len(answers)} 题")

    pathlib.Path(a.out).write_text(
        json.dumps({"section": a.section, "paper": a.paper,
                    "items": out_items, "problems": problems},
                   ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"共 {len(out_items)} 题 -> {a.out}")
    for p in problems:
        print("  !", p)
    return 0 if out_items else 1


if __name__ == "__main__":
    raise SystemExit(main())
