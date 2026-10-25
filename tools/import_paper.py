"""一条命令导入一份扫描版卷子: OCR → AI 组装 → AI 生成答案 → 写入试卷集.

用法:
    python tools/import_paper.py "<文件夹>" --collection jlpt-n5 --title 2012年12月 \
        --paper 2 --minutes 105 [--pages 1-8]

文件夹里只要有真题 PDF 就行; 答案/音频不影响 (没答案时用 AI 生成)。
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import exam_import as EI  # noqa: E402
from app import exams  # noqa: E402

PY = sys.executable
TMP = ROOT / "data" / "ocr"


def run(*args: str) -> int:
    print("$", " ".join(str(a) for a in args))
    return subprocess.call([PY, *args], cwd=ROOT)


def next_paper_no(cid: str) -> int:
    bank = exams.load(cid) or {}
    used = {int(l.get("lesson", 0)) for l in bank.get("lessons") or []}
    n = 1
    while n in used:
        n += 1
    return n


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("folder")
    ap.add_argument("--collection", default="jlpt-n5")
    ap.add_argument("--title", default="")
    ap.add_argument("--paper", type=int, default=0)
    ap.add_argument("--minutes", type=int, default=105)
    ap.add_argument("--pages", default="1-8")
    a = ap.parse_args()

    folder = pathlib.Path(a.folder)
    papers = [p for p in EI.scan_folder(folder)]
    usable = [p for p in papers if p.pdfs]
    if not usable:
        print("没找到题目 PDF")
        return 1
    # 取页数最多的那份当正卷
    main_pdf = max(usable[0].pdfs, key=lambda p: p.stat().st_size)
    print("正卷:", main_pdf.name)

    TMP.mkdir(parents=True, exist_ok=True)
    stem = re.sub(r"[^0-9A-Za-z]+", "_", main_pdf.stem)[:40]
    ocr_json = TMP / f"{stem}.ocr.json"
    q_json = TMP / f"{stem}.questions.json"
    ans_json = TMP / f"{stem}.answers.json"

    if run("tools/ocr_paper.py", str(main_pdf), "--out", str(ocr_json),
           "--pages", a.pages) != 0:
        return 1
    if run("tools/assemble_questions.py", str(ocr_json), "--out", str(q_json)) != 0:
        return 1

    n_q = len(json.loads(q_json.read_text(encoding="utf-8")).get("questions") or [])
    if n_q == 0:
        print("没组装出题目, 放弃")
        return 1
    if run("tools/generate_answers.py", str(q_json), "--out", str(ans_json)) != 0:
        return 1

    paper_no = a.paper or next_paper_no(a.collection)
    title = a.title or main_pdf.stem
    if run("tools/build_exam_bank.py", "--questions", str(q_json),
           "--title", f"{title}（文字・語彙）", "--collection", a.collection,
           "--paper", str(paper_no), "--minutes", str(a.minutes),
           "--answers", str(ans_json)) != 0:
        return 1
    print(f"\n完成: 第 {paper_no} 套「{title}」{n_q} 题")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
