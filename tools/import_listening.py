"""导入聴解: 把每一番的版面区域整块裁成题目图片 (按图像空白带切块).

JLPT 聴解每一番是「番号 + 插图/选项」, 一页上可能并排两番, 也可能一行五番。
靠 OCR 的「N番」行坐标切块不稳 (会把两番裁进一张, 或者只裁到 129px),
所以直接看图的空白带: 整页找横向全白的行 → 行带; 行带内再找纵向全白的列
→ 格子; 每个格子就是一番, 阅读顺序即番号顺序。

聴解没有文字题干, 模型无法代答, 所以答案默认留空 (answer=None),
答题界面按"自评"处理 —— 听完自己判对错。

用法:
    python tools/import_listening.py <pdf> --pages 9-12 --collection jlpt-n5 --paper 3
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

RENDER = 2.6
INK = 200
ROW_GAP = 14
COL_GAP = 14
MIN_W, MIN_H = 90, 90


def bands(flags, gap):
    """把 False 的连续段当分隔, 返回有内容的区段 [(起, 止)]."""
    out, start, blank = [], None, 0
    for i, has in enumerate(flags):
        if has:
            if start is None:
                start = i
            blank = 0
        elif start is not None:
            blank += 1
            if blank >= gap:
                out.append((start, i - blank + 1))
                start, blank = None, 0
    if start is not None:
        out.append((start, len(flags)))
    return [(a, b) for a, b in out if b - a > 8]


def segment(img):
    import numpy as np

    g = np.asarray(img.convert("L"))
    ink = g < INK
    W, H = img.size
    x_lo, y_lo = int(W * 0.02), int(H * 0.02)
    sub = ink[y_lo:int(H * 0.98), x_lo:int(W * 0.98)]
    cells = []
    for r0, r1 in bands(list(sub.any(axis=1)), ROW_GAP):
        strip = sub[r0:r1, :]
        for c0, c1 in bands(list(strip.any(axis=0)), COL_GAP):
            x0, x1 = x_lo + c0, x_lo + c1
            y0, y1 = y_lo + r0, y_lo + r1
            if x1 - x0 >= MIN_W and y1 - y0 >= MIN_H:
                cells.append((x0, y0, x1, y1))
    return cells


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("--pages", default="")
    ap.add_argument("--collection", default="jlpt-n5")
    ap.add_argument("--paper", type=int, default=1)
    ap.add_argument("--out", default="")
    ap.add_argument("--start-no", type=int, default=1)
    a = ap.parse_args()

    import pypdfium2 as pdfium

    doc = pdfium.PdfDocument(str(a.pdf))
    total = len(doc)
    if a.pages:
        lo, _, hi = a.pages.partition("-")
        lo_i, hi_i = max(1, int(lo)), min(total, int(hi or lo))
    else:
        lo_i, hi_i = 1, total

    out_dir = ROOT / "data" / "exams" / a.collection / "listening"
    out_dir.mkdir(parents=True, exist_ok=True)

    questions, ban = [], a.start_no
    for page_no in range(lo_i, hi_i + 1):
        img = doc[page_no - 1].render(scale=RENDER).to_pil()
        for (x0, y0, x1, y1) in segment(img):
            name = f"p{a.paper:02d}-{ban:02d}.png"
            img.crop((x0, y0, x1, y1)).save(out_dir / name)
            questions.append({
                "no": ban, "group": "聴解",
                "prompt": f"聴解　第 {ban} 番",
                "options": ["①", "②", "③", "④"],
                "answer": None,
                "image": f"exams/{a.collection}/listening/{name}",
                "page": page_no,
            })
            ban += 1

    print(f"聴解: 第 {lo_i}-{hi_i} 页 → {len(questions)} 块 (题号 "
          f"{[q['no'] for q in questions][:10]}…)")
    if a.out:
        pathlib.Path(a.out).write_text(
            json.dumps({"questions": questions}, ensure_ascii=False, indent=1),
            encoding="utf-8")
        print("已写入", a.out)
    return 0 if questions else 1


if __name__ == "__main__":
    raise SystemExit(main())
