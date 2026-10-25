"""试卷导入: 从文件夹里找出 PDF, 做质量检查与评分, 合格的解析成题库.

用户会把一整套真题放在一个文件夹里 (可能带"资源二"之类的子目录),
里面有: 真题 PDF、答案 PDF/图片、听力 mp3/mp4、有时还有答题卡。

导入前先体检, 不合格的直接放弃 (省 token):
  1. **重复**    同一份卷子已经导入过 (按指纹: 题数 + 标题 + 原文前若干字)
  2. **完整性**  PDF 页数、题目能不能成组
  3. **答案**    有没有答案文件; 没有的话, 文字层可用时可以让 AI 生成
  4. **听力**    有没有音频 (JLPT 有聴解部分)
  5. **文字层**  PDF 有没有可用的文字层 —— 扫描件/字体映射错乱的一律不合格

评分 0-100, 低于 MIN_SCORE 不导入。
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

MIN_SCORE = 55          # 低于这个分数不导入

PDF_SUFFIX = {".pdf"}
AUDIO_SUFFIX = {".mp3", ".m4a", ".wav", ".mp4"}
IMAGE_SUFFIX = {".png", ".jpg", ".jpeg", ".webp"}


@dataclass
class Paper:
    """文件夹里的"一份卷子" (可能由多个文件组成)."""
    title: str
    root: Path
    pdfs: list[Path] = field(default_factory=list)
    answer_files: list[Path] = field(default_factory=list)
    audio: list[Path] = field(default_factory=list)
    checks: dict = field(default_factory=dict)
    score: int = 0
    problems: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.score >= MIN_SCORE and not self.checks.get("bad_text")


# ------------------------------------------------------------------ 体检
def _pdf_text(path: Path, pages: int = 3) -> tuple[int, str]:
    """返回 (总页数, 前几页文字). 读不了返回 (0, "")。"""
    try:
        import pypdfium2 as pdfium
    except Exception:      # noqa: BLE001
        return 0, ""
    try:
        doc = pdfium.PdfDocument(str(path))
        n = len(doc)
        text = []
        for i in range(min(n, pages)):
            text.append(doc[i].get_textpage().get_text_range())
        return n, "".join(text)
    except Exception:      # noqa: BLE001
        return 0, ""


def text_is_garbled(text: str) -> bool:
    """判断文字层是不是"乱码".

    正常的日语卷子, 平假名/片假名占比很高; PDF 字体映射坏掉时,
    假名会被映射成形近的汉字或怪符号, 假名占比会低得离谱。
    """
    if not text.strip():
        return True
    kana = sum(1 for c in text if 0x3040 <= ord(c) <= 0x30FF)
    cjk = sum(1 for c in text if 0x4E00 <= ord(c) <= 0x9FFF)
    letters = kana + cjk
    if letters < 20:
        return True
    # 日语里假名通常占一半以上; 低于 25% 基本可以断定映射坏了
    return kana / letters < 0.25


def _fingerprint(paper: Paper) -> str:
    h = hashlib.sha1()
    h.update(paper.title.encode("utf-8"))
    for p in paper.pdfs:
        h.update(p.name.encode("utf-8"))
        h.update(str(p.stat().st_size).encode())
    return h.hexdigest()[:16]


# ------------------------------------------------------------------ 扫描
def _group(folder: Path) -> list[Paper]:
    """把文件夹拆成"一份卷子一组".

    真题 PDF 可能直接放在文件夹里, 也可能塞在子目录 (如 `N5真题2017.7/`)。
    所以按**题目 PDF 所在的目录**分组; 答案、音频则在整个树里找, 归给每个组。
    """
    folder = Path(folder)
    papers: list[Paper] = []
    by_dir: dict[Path, list[Path]] = {}
    answers: list[Path] = []
    audios: list[Path] = []

    for p in folder.rglob("*"):
        if not p.is_file():
            continue
        suf = p.suffix.lower()
        name = p.name
        is_answer = bool(re.search(r"答案|解析|听力原文|答题卡", name))
        if suf in PDF_SUFFIX:
            if is_answer:
                answers.append(p)
            else:
                by_dir.setdefault(p.parent, []).append(p)
        elif suf in AUDIO_SUFFIX:
            audios.append(p)
        elif suf in IMAGE_SUFFIX and is_answer:
            answers.append(p)

    for d, pdfs in by_dir.items():
        title = folder.name if d == folder else d.name
        papers.append(Paper(title=title, root=d, pdfs=sorted(pdfs),
                            answer_files=sorted(answers), audio=sorted(audios)))
    if not papers:
        papers.append(Paper(title=folder.name, root=folder,
                            answer_files=sorted(answers), audio=sorted(audios)))
    return papers


def inspect(paper: Paper) -> Paper:
    """体检 + 评分."""
    checks = paper.checks
    problems = paper.problems
    score = 0

    if not paper.pdfs:
        checks["no_pdf"] = True
        problems.append("没有找到试卷 PDF")
        paper.score = 0
        return paper

    main = paper.pdfs[0]
    pages, text = _pdf_text(main, pages=4)
    checks["pages"] = pages
    checks["text_chars"] = len(text)
    checks["has_text"] = len(text.strip()) > 20
    garbled = text_is_garbled(text)
    checks["bad_text"] = garbled

    if pages:
        score += 15
    if checks["has_text"] and not garbled:
        score += 35
    elif checks["has_text"]:
        problems.append("文字层是乱码（PDF 字体映射损坏），无法自动识别")
    else:
        problems.append("扫描件，没有文字层（需要 OCR 才能导入）")

    if paper.answer_files:
        score += 25
    else:
        problems.append("没有答案文件（文字层可用时可以让 AI 生成答案）")

    if paper.audio:
        score += 15
    else:
        problems.append("没有听力音频")

    if len(paper.pdfs) >= 1:
        score += 10

    paper.score = min(100, score)
    paper.checks["fingerprint"] = _fingerprint(paper)
    return paper


def scan_folder(folder: Path) -> list[Paper]:
    """扫描一个文件夹, 返回每份卷子的体检结果 (按分数从高到低)."""
    out = []
    for paper in _group(Path(folder)):
        out.append(inspect(paper))
    out.sort(key=lambda p: -p.score)
    return out


def known_titles() -> set[str]:
    """已经导入过的卷子标题 (粗略去重用)."""
    from . import exams

    titles: set[str] = set()
    for meta in exams.all_collections():
        bank = exams.load(meta["id"]) or {}
        for les in bank.get("lessons") or []:
            if les.get("title"):
                titles.add(str(les["title"]))
    return titles


def report(folder: Path) -> dict:
    """给界面用的一次性报告."""
    papers = scan_folder(folder)
    known = known_titles()
    rows = []
    for p in papers:
        dup = p.title in known
        rows.append({
            "title": p.title,
            "score": p.score,
            "ok": p.ok and not dup,
            "duplicate": dup,
            "pages": p.checks.get("pages", 0),
            "text": "乱码" if p.checks.get("bad_text") else
                    ("可用" if p.checks.get("has_text") else "扫描件"),
            "answers": bool(p.answer_files),
            "audio": bool(p.audio),
            "problems": p.problems,
            "pdf": str(p.pdfs[0]) if p.pdfs else "",
        })
    return {"folder": str(folder), "papers": rows}
