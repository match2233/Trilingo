"""下载日语 OCR 模型并生成 rapidocr 配置.

rapidocr-onnxruntime 自带的是中文模型, 认不出假名 (「話させて」只会认出「話」)。
这里取 SWHL/RapidOCR 仓库里现成的日语识别模型 (PP-OCRv1 japan_rec_crnn.onnx,
3.4MB) 和 PaddleOCR 的 japan_dict.txt, 拼一份自己的配置。

跑法:
    python tools/fetch_ocr_models.py
"""
from __future__ import annotations

import math
import pathlib
import sys
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "ocr"

MODEL_URL = ("https://huggingface.co/SWHL/RapidOCR/resolve/main/"
             "PP-OCRv1/japan_rec_crnn.onnx")
DICT_URL = ("https://raw.githubusercontent.com/PaddlePaddle/PaddleOCR/main/"
            "ppocr/utils/dict/japan_dict.txt")


def download(url: str, dest: pathlib.Path) -> None:
    if dest.exists() and dest.stat().st_size > 1024:
        print(f"  已存在 {dest.name} ({math.ceil(dest.stat().st_size / 1024)} KB)")
        return
    print(f"  下载 {url}")
    tmp = dest.with_suffix(dest.suffix + ".part")
    with urllib.request.urlopen(url, timeout=120) as r, open(tmp, "wb") as f:
        while True:
            chunk = r.read(1 << 16)
            if not chunk:
                break
            f.write(chunk)
    tmp.replace(dest)
    print(f"  -> {dest} ({math.ceil(dest.stat().st_size / 1024)} KB)")


def build_config() -> pathlib.Path:
    """照着 rapidocr 自带的 config.yaml 改一份日语版本."""
    import rapidocr_onnxruntime as R

    pkg = pathlib.Path(R.__file__).parent
    text = (pkg / "config.yaml").read_text(encoding="utf-8")
    for name in ("ch_PP-OCRv4_det_infer.onnx",
                 "ch_ppocr_mobile_v2.0_cls_infer.onnx"):
        text = text.replace(f"models/{name}",
                            str(pkg / "models" / name).replace("\\", "/"))
    text = text.replace("models/ch_PP-OCRv4_rec_infer.onnx",
                        str((OUT / "japan_rec.onnx")).replace("\\", "/"))
    text = text.replace("rec_img_shape: [3, 48, 320]", "rec_img_shape: [3, 32, 320]")
    old = f"model_path: {str((OUT / 'japan_rec.onnx')).replace(chr(92), '/')}"
    text = text.replace(old, old + f"\n    rec_keys_path: "
                        f"{str((OUT / 'japan_dict.txt')).replace(chr(92), '/')}")
    dest = OUT / "rapidocr_japan.yaml"
    dest.write_text(text, encoding="utf-8")
    print(f"  配置已写入 {dest}")
    return dest


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    download(MODEL_URL, OUT / "japan_rec.onnx")
    download(DICT_URL, OUT / "japan_dict.txt")
    build_config()
    print("完成。用 python tools/ocr_paper.py <pdf> 测试。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
