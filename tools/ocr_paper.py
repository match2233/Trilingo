"""用日语 OCR 把扫描版试卷读成行文本, 存成 <paper>.ocr.json 供解析.

为什么需要: N5 的真题 PDF 多数是扫描件, 没有文字层; 少数有文字层的是
"逐字替换乱码" (伈京寸 = います)。OCR 渲染页是唯一能拿到真实文字的路径。

用法:
    python tools/ocr_paper.py <pdf 路径> [--out 输出.json] [--pages 1-20]
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

JP_MODEL = ROOT / "data" / "ocr" / "japan_rec.onnx"
JP_DICT = ROOT / "data" / "ocr" / "japan_dict.txt"
JP_CFG = ROOT / "data" / "ocr" / "rapidocr_japan.yaml"


def build_engine():
    """构造一个用日语识别模型的 RapidOCR (检测/方向分类沿用中文模型)."""
    import rapidocr_onnxruntime as R

    if JP_CFG.exists():
        return R.RapidOCR(config_path=str(JP_CFG))
    raise SystemExit("缺少 data/ocr/rapidocr_japan.yaml, 先跑 tools/fetch_ocr_models.py")


def ocr_pdf(pdf: pathlib.Path, pages: str = "", scale: float = 2.2,
            progress=None) -> dict:
    import pypdfium2 as pdfium

    engine = build_engine()
    doc = pdfium.PdfDocument(str(pdf))
    total = len(doc)
    if pages:
        a, _, b = pages.partition("-")
        lo = max(1, int(a))
        hi = min(total, int(b or a))
    else:
        lo, hi = 1, total

    out = {"pdf": str(pdf), "pages": total, "scale": scale, "items": []}
    for i in range(lo, hi + 1):
        page = doc[i - 1]
        img = page.render(scale=scale).to_pil()
        tmp = ROOT / "data" / "ocr" / f"_p{i}.png"
        img.save(tmp)
        t0 = time.time()
        res, _ = engine(str(tmp))
        lines = []
        for box, text, score in (res or []):
            ys = [pt[1] for pt in box]
            xs = [pt[0] for pt in box]
            lines.append({"text": text, "score": round(float(score), 3),
                          "y": round(min(ys)), "x": round(min(xs)),
                          "x2": round(max(xs))})
        lines.sort(key=lambda r: (r["y"], r["x"]))
        out["items"].append({"page": i, "lines": lines,
                             "seconds": round(time.time() - t0, 1)})
        if progress:
            progress(i, hi, len(lines))
        tmp.unlink(missing_ok=True)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("--out", default="")
    ap.add_argument("--pages", default="")
    ap.add_argument("--scale", type=float, default=2.2)
    args = ap.parse_args()

    pdf = pathlib.Path(args.pdf)
    out = pathlib.Path(args.out) if args.out else pdf.with_suffix(".ocr.json")

    def progress(i, hi, n):
        print(f"  第 {i}/{hi} 页, {n} 行", flush=True)

    data = ocr_pdf(pdf, args.pages, args.scale, progress)
    out.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"已写入 {out} ({len(data['items'])} 页)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
