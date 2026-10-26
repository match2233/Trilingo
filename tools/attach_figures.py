"""给非听力题也挂图: 题干下方如果有一块"不是文字"的图区, 就裁下来.

判断办法 (不需要模型):
  * OCR 已经给出每一行文字的 y 和 x 范围;
  * 题干所在行到下一行文字之间的"空白带"里, 如果有一大块深色像素,
    而这块地方**没有对应的 OCR 行**, 那它就是插图 (JLPT 的絵/図/照片);
  * 把这块区域裁出来挂到这道题上。

纯文字的题目这块区域基本是空的, 所以不会被误挂 —— 这正好满足
"読解是纯文本就用文字, 有图就截图"。

用法:
    python tools/attach_figures.py --paper 1 --title 2016年 \
        --ocr data/ocr/lay_2016_.json --pdf "<真题.pdf>"
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

RENDER = 3.0
OCR_SCALE = 2.2
MIN_AREA = 9000        # 图区最小面积 (渲染像素)
INK_RATIO = 0.008        # 深色像素占比下限


def norm(s: str) -> str:
    return re.sub(r"[\s　]+", "", s or "")


def find_line(ocr: dict, text: str):
    whole = norm(text)
    if not whole:
        return None
    lines = [(p["page"], ln) for p in ocr["items"] for ln in p["lines"]
             if norm(ln["text"])]
    for n in (14, 12, 10, 8, 6):
        seg = whole[:n]
        if len(seg) < n:
            continue
        for page_no, ln in lines:
            if seg in norm(ln["text"]):
                return page_no, ln
    return None


def page_lines(ocr: dict, page_no: int) -> list[dict]:
    for p in ocr["items"]:
        if p["page"] == page_no:
            return sorted(p["lines"], key=lambda r: (r["y"], r["x"]))
    return []


def figure_bands(img, lines: list[dict]) -> list[tuple[float, float]]:
    """返回图区的 OCR 坐标 [(y_top, y_bottom)].

    做法: 把每一行文字的 y 范围标成"文字", 其余行里只要有足够墨迹,
    而且连续成片, 就算一块插图。
    """
    import numpy as np

    k = RENDER / OCR_SCALE
    H = img.height
    g = np.asarray(img.convert("L"))
    ink = g < 200
    col = ink[:, int(g.shape[1] * 0.03):int(g.shape[1] * 0.97)]
    row_ink = col.sum(axis=1)

    covered = np.zeros(H, dtype=bool)
    for ln in lines:
        y0 = int(max(0, (ln["y"] - 10) * k))
        y1 = int(min(H, (ln["y"] + 26) * k))
        covered[y0:y1] = True

    out, start = [], None
    for y in range(H):
        has = row_ink[y] > 4 and not covered[y]
        if has and start is None:
            start = y
        elif not has and start is not None:
            if y - start > 60:
                out.append((start / k, y / k))
            start = None
    if start is not None and H - start > 60:
        out.append((start / k, H / k))
    return out


def crop_figure(img, y_top: float, y_bottom: float):
    """在 [y_top, y_bottom] 这条带里找深色像素的外接框, 返回裁好的图或 None."""
    import numpy as np

    k = RENDER / OCR_SCALE
    H, W = img.height, img.width
    y0 = int(max(0, y_top * k))
    y1 = int(min(H, y_bottom * k))
    if y1 - y0 < 40:
        return None
    band = img.crop((int(W * 0.03), y0, int(W * 0.97), y1))
    g = np.asarray(band.convert("L"))
    ink = g < 200
    if ink.sum() < MIN_AREA:
        return None
    if ink.mean() < INK_RATIO:
        return None
    ys, xs = np.where(ink)
    pad = 6
    box = (max(0, int(xs.min()) - pad), max(0, int(ys.min()) - pad),
           min(band.width, int(xs.max()) + pad),
           min(band.height, int(ys.max()) + pad))
    if (box[2] - box[0]) < 120 or (box[3] - box[1]) < 90:
        return None
    return band.crop(box)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--paper", type=int, required=True)
    ap.add_argument("--title", required=True)
    ap.add_argument("--ocr", required=True)
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--collection", default="jlpt-n5")
    ap.add_argument("--force", action="store_true", help="已有图也重新裁")
    a = ap.parse_args()

    import pypdfium2 as pdfium

    from app import exams

    ocr = json.loads(pathlib.Path(a.ocr).read_text(encoding="utf-8"))
    doc = pdfium.PdfDocument(a.pdf)
    cache: dict[int, object] = {}

    out_dir = ROOT / "data" / "exams" / a.collection / "fig"
    out_dir.mkdir(parents=True, exist_ok=True)

    path = exams.save_path(a.collection)
    bank = json.loads(path.read_text(encoding="utf-8"))
    lesson = next((l for l in bank["lessons"] if l["lesson"] == a.paper), None)
    if lesson is None:
        raise SystemExit("题库里没有这一套")

    made = 0
    fig_cache: dict[int, list] = {}
    for sec in lesson["sections"]:
        if sec.get("group") == "聴解":
            continue
        for it in sec["items"]:
            if it.get("image") and not a.force:
                continue
            hit = find_line(ocr, it["prompt"])
            if hit is None:
                continue
            page_no, ln = hit
            img = cache.get(page_no)
            if img is None:
                img = doc[page_no - 1].render(scale=RENDER).to_pil()
                cache[page_no] = img
            lines = page_lines(ocr, page_no)
            bands = fig_cache.get(page_no)
            if bands is None:
                bands = figure_bands(img, lines)
                fig_cache[page_no] = bands
            # 挑离题干最近的一块 (上方 500px 内 / 下方 500px 内)
            best, best_d = None, 1e9
            for (a0, a1) in bands:
                if a0 >= ln["y"] - 12:
                    d = abs(a0 - ln["y"])
                elif a1 <= ln["y"] - 12:
                    d = abs(ln["y"] - a1) + 60      # 上方的图稍嫌弃一点
                else:
                    continue
                if d < best_d:
                    best, best_d = (a0, a1), d
            if best is None or best_d > 150:
                continue
            fig = crop_figure(img, best[0], best[1])
            if fig is None:
                continue
            name = f"p{a.paper:02d}-f{made + 1:02d}.png"
            fig.save(out_dir / name)
            it["image"] = f"exams/{a.collection}/fig/{name}"
            made += 1

    path.write_text(json.dumps(bank, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"第 {a.paper} 套: 给 {made} 道非听力题挂上了插图")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
