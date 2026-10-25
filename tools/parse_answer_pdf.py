"""从「答案」PDF 的文字层解析正答表.

这些答案 PDF 有文字层, 但每个汉字后面跟着振假名, 直接读是乱的:
    正 せい 答 とう 表 ひょう ●言 げん 語 ご ...
去掉假名之后结构很干净:
    ●言語知識（文字語彙）●言語知識（文法）読解
    問題１  1 2 3 4 5 6 7 8 9 10   2 4 1 2 2 3 4 2 2 3
    問題２  11 12 ... 18            1 2 3 4 4 1 3 1
即: 「問題N」→ 题号列表 → 同长度的答案列表 (每个 1-4)。

用法:
    python tools/parse_answer_pdf.py "<答案.pdf>" --out answers.json
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

KANA = re.compile(r"[\u3040-\u30ff]")
SEP = re.compile(r"[●・\s\u3000:：()（）]")


def clean(text: str) -> str:
    """去掉振假名、标点和空白, 只留汉字/数字/大写标记."""
    text = KANA.sub("", text)
    return text


def runs_of(nums: list[int]) -> list[tuple[int, int]]:
    """找"连续递增 1"的片段, 返回 [(起点下标, 长度)]."""
    out = []
    i = 0
    n = len(nums)
    while i < n:
        j = i
        while j + 1 < n and nums[j + 1] == nums[j] + 1:
            j += 1
        if j > i:
            out.append((i, j - i + 1))
        i = j + 1 if j > i else i + 1
    return out


def parse(text: str) -> dict[int, int]:
    """返回 {题号: 答案1-4}."""
    raw = clean(text)
    marks = list(re.finditer(r"問題\s*([0-9０-９]+)", raw))
    out: dict[int, int] = {}
    warnings: list[str] = []
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(raw)
        block = raw[m.end():end]
        nums = [int(n) for n in re.findall(r"\d{1,2}", block)]
        if len(nums) < 6:
            continue
        candidates = [c for c in runs_of(nums) if c[0] <= 2]
        if not candidates:
            continue
        # 题号列表紧跟在「問題N」后面 (block 开头), 用第一个够长的连续片段:
        # 不能只看"最长", 因为答案本身 1-4 连起来也像一串递增数字。
        candidates.sort(key=lambda t: t[0])
        start, length = candidates[0]
        qnos = nums[start:start + length]
        rest = nums[start + length:]
        answers = rest[:length]
        # 聴解每个大题前面有个「例」(例题), 会多一个答案, 要去掉第一个
        if "例" in block and len(rest) > length and all(1 <= v <= 4 for v in rest[:length + 1]):
            answers = rest[1:length + 1]
        if len(answers) != length or not all(1 <= v <= 4 for v in answers):
            warnings.append(f"問題{m.group(1)}: 题号 {qnos[:3]}… 答案对不上 "
                            f"({len(answers)}/{length})")
            continue
        for q, a in zip(qnos, answers):
            out[q] = a
    if warnings:
        for w in warnings[:4]:
            print("  !", w)
    return out


def extract_text(pdf: pathlib.Path) -> str:
    import pypdfium2 as pdfium

    doc = pdfium.PdfDocument(str(pdf))
    return "\n".join(doc[i].get_textpage().get_text_range() for i in range(len(doc)))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("--out", default="")
    a = ap.parse_args()

    pdf = pathlib.Path(a.pdf)
    text = extract_text(pdf)
    if len(text.strip()) < 50:
        print(f"这个 PDF 没有文字层 ({len(text)} 字), 需要 OCR 才能解析")
        return 1
    answers = parse(text)
    print(f"解析出 {len(answers)} 个答案: "
          f"{sorted(answers.items())[:8]} …")
    if a.out:
        pathlib.Path(a.out).write_text(
            json.dumps({str(k): v for k, v in sorted(answers.items())},
                       ensure_ascii=False, indent=1), encoding="utf-8")
        print("已写入", a.out)
    return 0 if answers else 1


if __name__ == "__main__":
    raise SystemExit(main())
