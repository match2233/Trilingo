"""把带插图的题目, 从 PDF 页面里裁出对应区域的图片.

这些试卷里的插图多是矢量绘制的 (不是位图), 所以不能"抽取图片对象",
只能按版面裁: 以题干的 y 为起点, 到下一题的 y 为止, 横向取页面宽度的一半
或整幅 —— 具体看题目里出现的词 (絵/図/写真 提示有图)。

用法:
    python tools/crop_figures.py <pdf> --questions q.json --ocr ocr.json \
        --collection jlpt-n5 --paper 3 --out-dir data/exams/jlpt-n5/figures
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

FIG_HINT = re.compile(r"(絵|え|写真|しゃしん|図|ず)(を|の|が|は|に)")
PAD_TOP = 30
MAX_H = 420          # 裁切高度上限 (像素, 渲染后)
SCALE = 2.2          # 与 ocr_paper.py 的默认渲染倍率一致


def question_rows(ocr: dict) -> list[tuple[int, float]]:
    """OCR 行里"像题号"的行: 返回 [(题号, y)]."""
    out = []
    for page in ocr["items"]:
        for ln in page["lines"]:
            m = re.match(r"^\s*[^0-9]{0,3}(\d{1,3})\s*$", ln["text"])
            if m:
                out.append((int(m.group(1)), float(ln["y"])))
    return out


def wants_figure(q: dict) -> bool:
    """只认 AI 组装时打的 figure 标记。

    早先用关键词猜 (絵/図/写真), 实测误判严重: 「えき」「きょうなら」都会命中,
    而且 N5 的"文字・語彙"整段根本没有插图, 裁出来全是纯文本 —— 宁可不裁。
    """
    return bool(q.get("figure"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("--questions", required=True)
    ap.add_argument("--ocr", required=True)
    ap.add_argument("--collection", default="jlpt-n5")
    ap.add_argument("--paper", type=int, default=1)
    ap.add_argument("--out-dir", default="")
    ap.add_argument("--limit", type=int, default=40)
    args = ap.parse_args()

    import pypdfium2 as pdfium

    qdata = json.loads(pathlib.Path(args.questions).read_text(encoding="utf-8"))
    ocr = json.loads(pathlib.Path(args.ocr).read_text(encoding="utf-8"))
    out_dir = pathlib.Path(args.out_dir) if args.out_dir else (
        ROOT / "data" / "exams" / args.collection / "figures")
    out_dir.mkdir(parents=True, exist_ok=True)

    doc = pdfium.PdfDocument(str(args.pdf))
    # 每页的题号行 y 坐标, 用来划定"这一题到下一题"的范围
    per_page: dict[int, list[tuple[int, float]]] = {}
    for page in ocr["items"]:
        rows = []
        for ln in page["lines"]:
            m = re.match(r"^\s*[^0-9]{0,3}(\d{1,3})\s*$", ln["text"])
            if m:
                rows.append((int(m.group(1)), float(ln["y"])))
        per_page[page["page"]] = sorted(rows, key=lambda r: r[1])
    # 题干文字 -> (页码, y)
    prompt_pos: dict[str, tuple[int, float]] = {}
    for page in ocr["items"]:
        for ln in page["lines"]:
            prompt_pos.setdefault(ln["text"].strip(), (page["page"], float(ln["y"])))

    made = 0
    for q in qdata.get("questions") or []:
        if made >= args.limit:
            break
        if not wants_figure(q):
            continue
        key = q["prompt"].strip()[:24]
        page_no, y = None, None
        for text, pos in prompt_pos.items():
            if key and (key in text or text in key):
                page_no, y = pos
                break
        if page_no is None:
            continue
        page = doc[page_no - 1]
        # 下一题的 y (同一页), 没有就用 +MAX_H
        nxt = None
        for no, ry in per_page.get(page_no, []):
            if ry > y + 10:
                nxt = ry
                break
        top = max(0, y - PAD_TOP)
        h = (nxt - top) if nxt else MAX_H
        h = min(max(h, 120), MAX_H)
        # OCR 坐标就是渲染图的像素坐标, 必须用同一个 scale, 否则框会反过来
        img = page.render(scale=SCALE).to_pil()
        W, H = img.size
        y0 = int(max(0, top))
        y1 = int(min(H, top + h))
        if y1 - y0 < 40:
            y1 = min(H, y0 + 160)
        box = (int(W * 0.04), y0, int(W * 0.96), y1)
        crop = img.crop(box)
        name = f"p{args.paper:02d}-q{q['no']:03d}.png"
        crop.save(out_dir / name)
        q["image"] = f"exams/{args.collection}/figures/{name}"
        made += 1

    pathlib.Path(args.questions).write_text(
        json.dumps(qdata, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"裁出 {made} 张图 -> {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
