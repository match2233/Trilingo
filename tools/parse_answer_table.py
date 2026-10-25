"""解析试卷最后一页的「参考答案」表格.

很多 N5 真题 PDF 的最后一页是完整的答案表:

    N5.言語知識(文字.語彙)   問題1 1番..10番 / 答案 2 4 1 2 2 3 4 2 2 3
    N5.言語知識(文法.読解)   問題1..問題6
    N5.聴解                  聴解1..聴解4

整页 OCR 会把相邻的格子粘在一起、还会把 3 认成 る, 所以这里**先找表格线**切成
格子, 再**逐格**识别 —— 一格只有一个「N番」或一个数字, 准确率高得多。

用法:
    python tools/parse_answer_table.py "<试卷.pdf>" --page 12 --out answers.json
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

RENDER = 4.0
LINE_RATIO = 0.45      # 一行里暗像素超过这个比例 → 认为是表格横线
INK = 190
KANA = re.compile(r"[\u3040-\u30ff]")


def _lines(profile, min_run=1):
    """把"是线"的连续行合并, 返回中心坐标列表."""
    idx = [i for i, v in enumerate(profile) if v]
    if not idx:
        return []
    out, start, prev = [], idx[0], idx[0]
    for i in idx[1:]:
        if i - prev <= 2:
            prev = i
        else:
            out.append((start + prev) // 2)
            start = prev = i
    out.append((start + prev) // 2)
    return out


def grid_cells(img):
    """返回 (行线, [(行带起点, 行带终点, 该带内的列线)]).

    每个行带的列数不一样 (10 列 / 8 列 / 5 列…), 所以**逐行带**找竖线,
    不能整页统一找 —— 竖线只跨自己那一行带, 整页统计会把它们全漏掉。
    """
    import numpy as np

    g = np.asarray(img.convert("L"))
    H, W = g.shape
    dark = g < INK
    rows = _lines([dark[y].sum() > W * LINE_RATIO for y in range(H)])

    bands = []
    for i in range(len(rows) - 1):
        y0, y1 = rows[i], rows[i + 1]
        band = dark[y0 + 1:y1]
        if band.size == 0:
            continue
        h = band.shape[0]
        cols = _lines([band[:, x].sum() > h * 0.6 for x in range(W)])
        if len(cols) >= 2:
            bands.append((y0, y1, cols))
    return rows, bands


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("--page", type=int, default=0, help="答案在第几页 (1 起); 0=最后一页")
    ap.add_argument("--out", default="")
    ap.add_argument("--debug", action="store_true")
    a = ap.parse_args()

    import pypdfium2 as pdfium
    from tools.ocr_paper import build_engine

    doc = pdfium.PdfDocument(str(a.pdf))
    page_no = a.page or len(doc)
    img = doc[page_no - 1].render(scale=RENDER).to_pil()
    rows, bands = grid_cells(img)
    print(f"第 {page_no} 页表格: {len(rows)} 条横线, {len(bands)} 个行带, "
          f"列数 {[len(b[2]) for b in bands]}")

    eng = build_engine()
    tmp = ROOT / "data" / "ocr" / "_cell.png"
    tmp.parent.mkdir(parents=True, exist_ok=True)

    cells = []
    for ri, (ry0, ry1, cols) in enumerate(bands):
        for ci in range(len(cols) - 1):
            x0, x1 = cols[ci] + 2, cols[ci + 1] - 2
            y0, y1 = ry0 + 2, ry1 - 2
            if x1 - x0 < 8 or y1 - y0 < 8:
                continue
            crop = img.crop((x0, y0, x1, y1))
            crop = crop.resize((crop.width * 2, crop.height * 2))
            crop.save(tmp)
            res, _ = eng(str(tmp))
            text = "".join(t for _, t, _ in (res or [])).strip()
            cells.append({"r": ri, "c": ci, "text": text})
            if a.debug and text:
                print(f"  [{ri},{ci}] {text}")

    tmp.unlink(missing_ok=True)
    out = parse_cells(cells)
    print(f"解析出 {sum(len(v) for v in out.values())} 个答案")
    for sec, mapping in out.items():
        print(f"  {sec}: {len(mapping)} 题 {sorted(mapping.items())[:6]}…")
    if a.out:
        pathlib.Path(a.out).write_text(
            json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
        print("已写入", a.out)
    return 0 if out else 1


def parse_cells(cells: list[dict]) -> dict[str, dict[int, int]]:
    """把格子还原成 {分区: {题号: 答案}}.

    表格结构 (逐行):
      行A: [问题N] 1番 2番 3番 …
      行B: [空]    1   4   2   …
    """
    by_row: dict[int, list[dict]] = {}
    for c in cells:
        by_row.setdefault(c["r"], []).append(c)
    for r in by_row:
        by_row[r].sort(key=lambda c: c["c"])

    result: dict[str, dict[int, int]] = {}
    section = "?"
    pending: list[int] = []
    for r in sorted(by_row):
        texts = [c["text"] for c in by_row[r]]
        joined = "".join(texts)
        # 分区标题 (言語知識(文字.語彙) / 文法.読解 / 聴解)
        if "文字" in joined:
            section = "文字・語彙"
            result.setdefault(section, {})
            pending = []
            continue
        if "文法" in joined:
            section = "文法・読解"
            result.setdefault(section, {})
            pending = []
            continue
        if "聴解" in joined and "聴解" in KANA.sub("", joined):
            section = "聴解"
            result.setdefault(section, {})
            pending = []
            continue
        nums = [int(m) for t in texts for m in re.findall(r"(\d{1,2})\s*番", t)]
        if nums:
            pending = nums
            continue
        # 答案行: 只取单字符 1-4
        ans = []
        for c in by_row[r]:
            t = KANA.sub("", c["text"]).strip()
            t = t.replace("．", "").replace(".", "").strip()
            if re.fullmatch(r"[1-4１-４]", t):
                ans.append(int(t.translate(
                    str.maketrans("１２３４", "1234"))))
        if pending and ans:
            for q, v in zip(pending, ans):
                result.setdefault(section, {})[q] = v
            pending = []
    return {k: v for k, v in result.items() if v}


if __name__ == "__main__":
    raise SystemExit(main())
