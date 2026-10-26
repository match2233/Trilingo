"""从原卷图像里识别"下划线"和"标红", 写成题干里的富文本标记.

为什么不用截图: 截图能保真, 但长题干截出来字很小、也不能复制/搜索。
用户要的是"识别到下划线的文本就在题干里加下划线" —— 所以这里做像素分析:

  1. 用 OCR 行坐标定位这道题的题干行;
  2. 在高倍渲染图上检测:
     * 标红: 像素满足 R 明显大于 G/B 的区域;
     * 下划线: 文字基线下方一条"细而长"的深色横线;
  3. 把像素 x 区间按比例映射回 OCR 文本的字符区间;
  4. 写成 `__下划线__` / `~标红~` 两种标记, 存进题目的 prompt_rich。

用法:
    python tools/rich_markup.py --paper 1 --title 2016年 --ocr data/ocr/lay_2016_.json \
        --pdf "<真题.pdf>"
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


def norm(s: str) -> str:
    return re.sub(r"[\s　]+", "", s or "")


def find_line(ocr: dict, text: str) -> tuple[int, dict] | None:
    """在 OCR 里找与这段题干最匹配的一行.

    题干是模型从 OCR 还原的, 和原始行不会逐字相同 (可能改了假名/去了标点),
    所以从长到短试前缀, 最后退化成"共享 6 字以上的子串"。
    """
    whole = norm(text)
    if not whole:
        return None
    lines = [(p["page"], ln) for p in ocr["items"] for ln in p["lines"] if norm(ln["text"])]
    for n in (14, 12, 10, 8, 6):
        target = whole[:n]
        if len(target) < n:
            continue
        for page_no, ln in lines:
            if target in norm(ln["text"]):
                return page_no, ln
    # 退一步: 找共同前缀最长的那一行
    best, best_len = None, 0
    for page_no, ln in lines:
        t = norm(ln["text"])
        k = 0
        while k < min(len(t), len(whole)) and t[k] == whole[k]:
            k += 1
        if k > best_len:
            best, best_len = (page_no, ln), k
    return best if best_len >= 6 else None


def analyze(img, line: dict, n_chars: int, scale: float) -> tuple[list, list]:
    """返回 (下划线区间, 标红区间), 都是字符下标区间 [(起, 止)]."""
    import numpy as np

    k = scale / OCR_SCALE
    x0 = max(0, int((line["x"] - 4) * k))
    x1 = int((line["x2"] + 4) * k)
    y0 = max(0, int((line["y"] - 6) * k))
    y1 = int((line["y"] + 30) * k)
    crop = img.crop((x0, y0, min(img.width, x1), min(img.height, y1)))
    g = np.asarray(crop.convert("RGB")).astype(int)
    R, G, B = g[:, :, 0], g[:, :, 1], g[:, :, 2]
    dark = (R + G + B) < 380

    H, W = dark.shape
    if H < 8 or W < 8 or n_chars <= 0:
        return [], []

    cw = W / max(1, n_chars)

    def to_chars(a: int, b: int) -> tuple[int, int] | None:
        """像素区间 -> 字符区间: 起点四舍五入, 长度按"宽度/字宽"算.

        两端各自四舍五入会时多时少 (先 / 先週 / 先週デ 都出现过),
        用"起点 + 长度"更稳。
        """
        ca = int(round(a / cw))
        n = max(1, int(round((b - a) / cw)))
        ca = max(0, min(n_chars - 1, ca))
        return ca, min(n_chars, ca + n)

    # 标红: R 高、G/B 低
    red = (R > 130) & (G < 110) & (B < 110) & (R - G > 50)
    red_cols = red.sum(axis=0) > 0
    red_ranges = []
    run = None
    for x in range(W):
        if red_cols[x]:
            if run is None:
                run = x
        elif run is not None:
            if x - run >= 4:
                r = to_chars(run, x)
                if r:
                    red_ranges.append(r)
            run = None
    if run is not None and W - run >= 4:
        r = to_chars(run, W)
        if r:
            red_ranges.append(r)

    underline = []
    # 下划线: 文字下方一条"细而长"的横线。
    # 不能要求整行都黑 (下划线只覆盖被考的那几个字), 所以按"横向连续段"找:
    for y in range(int(H * 0.55), H):
        row = dark[y]
        if row.sum() < 18:
            continue
        frac = row.sum() / W
        if frac > 0.75:        # 几乎整行都黑 -> 这是文字行, 不是下划线
            continue
        x = 0
        while x < W:
            if not row[x]:
                x += 1
                continue
            start = x
            while x < W and row[x]:
                x += 1
            seg = x - start
            # 至少两个字符宽, 且上下两行没有同样宽的线 (排除文字笔画)
            if seg >= max(16, W // max(1, n_chars) * 2):
                above = dark[max(0, y - 2):y, start:x]
                if above.size and above.mean() > 0.6:
                    continue
                r = to_chars(start, x)
                if r:
                    underline.append(r)
    return underline, red_ranges


def apply_marks(text: str, under: list, red: list) -> str:
    """把区间套成标记. 文本长度和字符下标一一对应."""
    chars = list(text)
    marks = ["" for _ in chars]
    for a, b in red:
        for i in range(a, min(b, len(chars))):
            marks[i] = "red"
    for a, b in under:
        for i in range(a, min(b, len(chars))):
            if marks[i] != "red":
                marks[i] = "under"
    out, cur = [], None
    for ch, m in zip(chars, marks):
        if m != cur:
            if cur == "under":
                out.append("__")
            elif cur == "red":
                out.append("~")
            if m == "under":
                out.append("__")
            elif m == "red":
                out.append("~")
            cur = m
        out.append(ch)
    if cur == "under":
        out.append("__")
    elif cur == "red":
        out.append("~")
    return "".join(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--paper", type=int, required=True)
    ap.add_argument("--title", required=True)
    ap.add_argument("--ocr", required=True)
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--collection", default="jlpt-n5")
    a = ap.parse_args()

    import pypdfium2 as pdfium

    from app import exams

    ocr = json.loads(pathlib.Path(a.ocr).read_text(encoding="utf-8"))
    doc = pdfium.PdfDocument(a.pdf)
    cache: dict[int, object] = {}

    path = exams.save_path(a.collection)
    bank = json.loads(path.read_text(encoding="utf-8"))
    lesson = next((l for l in bank["lessons"] if l["lesson"] == a.paper), None)
    if lesson is None:
        raise SystemExit("题库里没有这一套")

    done = under_n = red_n = 0
    for sec in lesson["sections"]:
        if sec.get("group") == "聴解":
            continue
        for it in sec["items"]:
            hit = find_line(ocr, it["prompt"])
            if hit is None:
                continue
            page_no, ln = hit
            img = cache.get(page_no)
            if img is None:
                img = doc[page_no - 1].render(scale=RENDER).to_pil()
                cache[page_no] = img
            plain = norm(ln["text"])
            under, red = analyze(img, ln, len(plain), RENDER)
            if not under and not red:
                continue
            # OCR 行前面常带题号 ("1、"/"ö、"), 而题干里没有 —— 要把偏移减掉,
            # 否则下划线会往前串两个字 ("1__、先__週" 这种)
            mine = norm(it["prompt"])
            off = 0
            for n in (8, 6, 4):
                seg = mine[:n]
                if seg and seg in plain:
                    off = plain.index(seg)
                    break
            def _shift(rngs, extra=1):
                out = []
                for a, b in rngs:
                    a2, b2 = a - off, b - off + extra
                    if a2 < 0:
                        a2 = 0
                    out.append((a2, max(a2 + 1, b2)))
                return out
            shifted_u = _shift(under, 0)
            shifted_r = _shift(red, 0)
            rich = apply_marks(mine, shifted_u, shifted_r)
            it["prompt_rich"] = rich
            done += 1
            under_n += len(under)
            red_n += len(red)

    path.write_text(json.dumps(bank, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"第 {a.paper} 套: {done} 题写入 rich, 下划线 {under_n} 处, 标红 {red_n} 处")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
