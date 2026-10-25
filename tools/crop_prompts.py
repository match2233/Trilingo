"""把每道题的**题干**从 PDF 页面裁成图片, 保留原卷的下划线/加粗/红色.

为什么: 这些试卷是扫描件, 富文本信息只存在于图像里 —— OCR 出来的是纯文字,
下划线、加粗、标红的被考词全丢了。裁题干当图片显示就原样还原了。

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

SCALE = 2.2          # 与 ocr_paper.py 默认一致, OCR 坐标即渲染图坐标
PAD_Y = 6


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

    # 把 OCR 行按"规范化文字"建索引, 同时记住它属于哪一页、y、高度
    index: list[tuple[str, int, float, float]] = []
    for page in ocr["items"]:
        for ln in page["lines"]:
            index.append((norm(ln["text"]), page["page"], float(ln["y"]), 30.0))

    doc = pdfium.PdfDocument(str(a.pdf))
    rendered: dict[int, object] = {}
    made = 0
    for q in qdata.get("questions") or []:
        target = norm(q["prompt"])[:12]
        if not target:
            continue
        best = None
        for text, page, y, h in index:
            if not text:
                continue
            if target in text or text.startswith(target) or \
                    (len(text) > 6 and text[:8] == target[:8]):
                best = (page, y, h)
                break
        if best is None:
            continue
        page_no, y, _ = best
        img = rendered.get(page_no)
        if img is None:
            img = doc[page_no - 1].render(scale=SCALE).to_pil()
            rendered[page_no] = img
        W, H = img.size
        y0 = int(max(0, y - PAD_Y))
        y1 = int(min(H, y + 30))   # 只到这一行文字底边, 别把下面选项行带进来
        name = f"p{a.paper:02d}-q{q['no']:03d}.png"
        img.crop((int(W * 0.03), y0, int(W * 0.97), y1)).save(out_dir / name)
        q["prompt_image"] = f"exams/{a.collection}/prompts/{name}"
        made += 1

    pathlib.Path(a.questions).write_text(
        json.dumps(qdata, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"裁出 {made} 张题干图 -> {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
