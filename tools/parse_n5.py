"""把 ocr_paper.py 产出的行数据解析成题目 (四选一).

版式规律 (JLPT 试卷):
  * 题号单独一行 (1、2、3…), 有时 OCR 会把前后杂字带上
  * 题号下面 1-2 行是题干
  * 再下面四行/四段是选项; 有的题型把四个选项排在同一行, 靠 x 间距分开

所以按"视觉行"重组, 再用 x 间距把行切成若干段:
  段数 >= 2 -> 这一行的每一段各是一个选项
  段数 == 1 -> 这一行整体是题干或一个选项
遇到下一个题号就收一题; 选项数不是 4 的题会被丢掉并计入 rejected。

用法:
    python tools/parse_n5.py <ocr.json> --title 2016年 --out data/exams/_n5_2016.json
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

NUM_RE = re.compile(r"^\s*[^0-9]{0,3}(\d{1,3})\s*$")
MONDAI_RE = re.compile(r"問題\s*([0-9一二三四五六七八九十]+)")
ROW_TOL = 14        # 同一行的 y 容差
SEG_GAP = 70        # 同一行里切成两段的 x 间距


def rows_of(lines: list[dict]) -> list[list[dict]]:
    """按 y 把行归并成"视觉行", 行内按 x 排序。"""
    out: list[list[dict]] = []
    for ln in sorted(lines, key=lambda r: (r["y"], r["x"])):
        if out and abs(ln["y"] - out[-1][0]["y"]) <= ROW_TOL:
            out[-1].append(ln)
        else:
            out.append([ln])
    for r in out:
        r.sort(key=lambda x: x["x"])
    return out


def segments(row: list[dict]) -> list[str]:
    """把一行按 x 间距切段; 段内文字用空格连接。"""
    segs: list[list[dict]] = []
    for ln in row:
        if segs and ln["x"] - segs[-1][-1]["x2"] <= SEG_GAP:
            segs[-1].append(ln)
        else:
            segs.append([ln])
    return ["".join(s["text"] for s in seg).strip() for seg in segs]


# 题号常被 OCR 粘进题干, 例如 "ê5日本（）ラーメンはおいしいです。"
NUM_INLINE = re.compile(r"^[^0-9\u3040-\u30ff\u4e00-\u9fff]{0,3}(\d{1,3})\s*(.+)$")


def question_no(seg_list: list[str]) -> tuple[int | None, str]:
    """这一行是不是题号行. 返回 (题号, 剩余文字)."""
    first = seg_list[0] if seg_list else ""
    m = NUM_RE.match(first)
    if m:
        n = int(m.group(1))
        rest = " ".join(seg_list[1:]).strip()
        return n, rest
    # 题号粘在题干前面
    m2 = NUM_INLINE.match(first)
    if m2:
        n = int(m2.group(1))
        rest = m2.group(2).strip()
        if re.search(r"[\u3040-\u30ff\u4e00-\u9fff]", rest) and len(rest) >= 4:
            return n, rest
    return None, ""


def parse_pages(items: list[dict]) -> tuple[list[dict], list[dict]]:
    """返回 (题目列表, 被丢弃的题)."""
    questions: list[dict] = []
    rejected: list[dict] = []
    cur: dict | None = None
    section = 1

    def close():
        nonlocal cur
        if not cur:
            return
        opts = [o for o in cur["options"] if o]
        prompt = "".join(cur["prompt"]).strip()
        if len(opts) == 4 and prompt:
            questions.append({"no": cur["no"], "section": section,
                              "prompt": prompt, "options": opts})
        else:
            rejected.append({"no": cur["no"], "prompt": prompt,
                             "options": opts,
                             "why": f"选项 {len(opts)} 个" if len(opts) != 4 else "题干为空"})
        cur = None

    for page in items:
        for row in rows_of(page["lines"]):
            segs = [s for s in segments(row) if s]
            if not segs:
                continue
            joined = "".join(segs)
            m = MONDAI_RE.search(joined)
            if m and len(joined) <= 12:
                close()
                section += 1
                continue
            n, rest = question_no(segs)
            if n is not None:
                close()
                cur = {"no": n, "prompt": [rest] if rest else [], "options": []}
                continue
            if cur is None:
                continue
            if len(segs) >= 2:
                # 同一行里多个选项
                cur["options"].extend(segs)
            else:
                text = segs[0]
                if not cur["prompt"]:
                    cur["prompt"].append(text)
                elif len(cur["options"]) < 4:
                    cur["options"].append(text)
                else:
                    cur["prompt"].append(text)
    close()
    return questions, rejected


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("ocr")
    ap.add_argument("--title", default="")
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    data = json.loads(pathlib.Path(args.ocr).read_text(encoding="utf-8"))
    qs, bad = parse_pages(data["items"])
    print(f"解析出 {len(qs)} 题, 丢弃 {len(bad)} 题")
    for q in qs[:5]:
        print(f"  {q['no']:>3} {q['prompt'][:34]}")
        print(f"      {q['options']}")
    for b in bad[:5]:
        print(f"  × {b['no']:>3} {b['why']}: {b['prompt'][:26]} {b['options']}")

    if not args.out:
        return 0
    out = pathlib.Path(args.out)
    out.write_text(json.dumps({"title": args.title, "questions": qs,
                               "rejected": bad}, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    print("已写入", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
