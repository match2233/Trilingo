"""把每道题的**题干**从 PDF 页面裁成图片, 保留原卷的下划线/加粗/红色.

为什么: 这些试卷是扫描件, 富文本信息只存在于图像里 —— OCR 出来的是纯文字,
下划线、加粗、标红的被考词全丢了。裁题干当图片显示就原样还原了。

关键: **只裁这一行文字自己的横向范围**, 不要整页宽。
整页宽裁下来 (约 1200px) 压到 900px 显示, 字只剩 30px 高, 看着很小;
按文字实际宽度裁, 同样的显示宽度下字就大得多, 和选项字号相当。

用法:
    python tools/crop_prompts.py <pdf> --ocr x.ocr.json --questions q.json \
        --collection jlpt-n5 --paper 3
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

RENDER = 4.5        # 重新渲染的倍率 (清晰度)
OCR_SCALE = 2.2     # ocr_paper.py 用的倍率, OCR 坐标基于它
PAD_X = 6
PAD_Y = 8
LINE_H = 34         # 一行文字高度 (OCR 坐标)


def norm(s: str) -> str:
    return re.sub(r"[\s　]+", "", s or "")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("--ocr", required=True)
    ap.add_argument("--questions", required=True)
    ap.add_argument("--collection", default="jlpt-n5")
    ap.add_argument("--paper", type=int, default=1)
    ap.add_argument("--out-dir", default="")
    a = ap.parse_args()

    import pypdfium2 as pdfium

    ocr = json.loads(pathlib.Path(a.ocr).read_text(encoding="utf-8"))
    qdata = json.loads(pathlib.Path(a.questions).read_text(encoding="utf-8"))
    out_dir = pathlib.Path(a.out_dir) if a.out_dir else (
        ROOT / "data" / "exams" / a.collection / "prompts")
    out_dir.mkdir(parents=True, exist_ok=True)

    index = []
    for page in ocr["items"]:
        for ln in page["lines"]:
            index.append((norm(ln["text"]), page["page"], float(ln["y"]),
                          float(ln["x"]), float(ln["x2"])))

    doc = pdfium.PdfDocument(str(a.pdf))
    cache: dict[int, object] = {}
    made = 0
    for q in qdata.get("questions") or []:
        target = norm(q["prompt"])[:12]
        if not target:
            continue
        hit = None
        for text, page, y, x, x2 in index:
            if text and (target in text or text.startswith(target)
                         or (len(text) > 6 and text[:8] == target[:8])):
                hit = (page, y, x, x2)
                break
        if hit is None:
            continue
        page_no, y, x, x2 = hit
        img = cache.get(page_no)
        if img is None:
            img = doc[page_no - 1].render(scale=RENDER).to_pil()
            cache[page_no] = img
        k = RENDER / OCR_SCALE
        W, H = img.size
        x0 = int(max(0, (x - PAD_X) * k))
        x1 = int(min(W, (x2 + PAD_X) * k))
        y0 = int(max(0, (y - PAD_Y) * k))
        y1 = int(min(H, (y - PAD_Y + LINE_H) * k))
        if x1 - x0 < 120:
            x1 = min(W, x0 + 480)
        name = f"p{a.paper:02d}-q{q['no']:03d}.png"
        img.crop((x0, y0, x1, y1)).save(out_dir / name)
        q["prompt_image"] = f"exams/{a.collection}/prompts/{name}"
        made += 1

    pathlib.Path(a.questions).write_text(
        json.dumps(qdata, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"裁出 {made} 张题干图 -> {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
