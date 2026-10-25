"""扫描每套 N5 试卷的页面结构, 判断三块的页范围.

自动判断不可靠的地方: 封面页也会写「聴解」「読解」, 而聴解首页往往没有
「聴解」两个字 (只有「まず質問を聞いてください」)。所以这里用更具体的锚点:

  文字・語彙  ← 「言語知識(文字・語彙)」或最早出现的「問題１」
  文法・読解  ← 「文法・読解」
  聴解        ← 「まず質問を聞いて」/「まずしつもんを聞いて」/「聴解」
  答案表      ← 最后一页或含「参考答案」「正答表」

输出 data/exams/n5_layout.json:
    {"2010年07月": {"pdf": "...", "text": [3,4], "reading": [5,6,7,8],
                    "listening": [9,10,11], "answers": 12, "pages": 12}}
"""
from __future__ import annotations

import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

N5 = pathlib.Path(r"C:/Users/<user>\Desktop\N5")
OUT = ROOT / "data" / "exams" / "n5_layout.json"
CACHE = ROOT / "data" / "ocr"

TEXT_HINT = re.compile(r"言語知識.*(文字|語彙)|文字・語彙|文字\.語彙")
READ_HINT = re.compile(r"文法.*読解|文法\.読解")
LIS_HINT = re.compile(r"まず(質問|しつもん)を聞|聴解")
ANS_HINT = re.compile(r"参考答案|正答表")


def pick_pdf(folder: pathlib.Path) -> pathlib.Path | None:
    best = None
    for p in folder.rglob("*.pdf"):
        name = p.name
        if re.search(r"答案|解析|听力原文|答题卡|听力$", name):
            continue
        if best is None or p.stat().st_size > best.stat().st_size:
            best = p
    return best


def ocr(pdf: pathlib.Path, tag: str) -> dict:
    cache = CACHE / f"lay_{tag}.json"
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))
    from tools.ocr_paper import ocr_pdf

    data = ocr_pdf(pdf, "", 2.2, lambda i, hi, n: print(f"    {tag} 第 {i}/{hi} 页", flush=True))
    cache.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return data


def detect(data: dict) -> dict:
    pages = data["items"]
    ans = None
    for p in pages:
        j = "".join(l["text"] for l in p["lines"])
        if ANS_HINT.search(j):
            ans = p["page"]
    if ans is None:
        ans = len(pages)

    text_pages, read_pages, lis_pages = [], [], []
    for p in pages:
        if p["page"] == ans:
            continue
        j = "".join(l["text"] for l in p["lines"])
        if LIS_HINT.search(j):
            lis_pages.append(p["page"])
        elif READ_HINT.search(j):
            read_pages.append(p["page"])
    return {"pages": len(pages), "answers": ans,
            "reading_start": read_pages[0] if read_pages else None,
            "listening_start": lis_pages[0] if lis_pages else None}


def main() -> int:
    folders = sorted(d for d in N5.iterdir() if d.is_dir())
    layout = {}
    for d in folders:
        pdf = pick_pdf(d)
        if pdf is None:
            continue
        tag = re.sub(r"[^0-9A-Za-z]+", "_", d.name)[:24]
        print(f"== {d.name} -> {pdf.name}", flush=True)
        data = ocr(pdf, tag)
        info = detect(data)
        info["pdf"] = str(pdf)
        info["title"] = d.name.split("(")[0]
        # 用锚点切三段: 文字 = 首页之后到阅读开始; 阅读 = 阅读开始到听力开始;
        # 听力 = 听力开始到答案表之前
        last = info["answers"] - 1
        rs = info["reading_start"] or last + 1
        ls = info["listening_start"] or last + 1
        info["text"] = list(range(1, rs))
        info["reading"] = list(range(rs, ls))
        info["listening"] = list(range(ls, last + 1))
        layout[info["title"]] = info
        print(f"   文字{info['text']} 阅读{info['reading']} 听力{info['listening']} 答案页{info['answers']}",
              flush=True)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(layout, ensure_ascii=False, indent=1), encoding="utf-8")
    print("已写入", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
