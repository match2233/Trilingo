"""把一套 N5 试卷建成完整形态: 文字・語彙 + 文法・読解 + 聴解.

三块的来源:
  文字・語彙 / 文法・読解  —— OCR 页面 → AI 组装成四选一题
  聴解                     —— 每题配"卷面那一页"的图 (番号在页内), 选项 ①②③④

答案策略 (重要):
  * 官方答案表是按 `問題N + 顺序` 排的。组装出来的题目数**正好等于**答案数时,
    直接按顺序套用, 这就是精确对齐;
  * 数量对不上时**不硬套**(会整体错位), 改用 AI 生成答案, 并在报告里标出来。
    宁可答案来源不同, 也不给错答案。

用法:
    python tools/build_paper_full.py --paper 3 --title 2010年07月 \
        --pdf "<pdf>" --answers data/ocr/answers_2010.json \
        --text-pages 3-4 --reading-pages 5-8 --listening-pages 9-11
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

TMP = ROOT / "data" / "ocr"


def flatten(table: dict) -> list[int]:
    """把 {問題1: [...], 問題2: [...]} 按问题顺序摊平."""
    out: list[int] = []
    for key in sorted(table, key=lambda k: int("".join(c for c in k if c.isdigit()) or 0)):
        out.extend(table[key])
    return out


def parse_range(s: str) -> list[int]:
    lo, _, hi = s.partition("-")
    return list(range(int(lo), int(hi or lo) + 1))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--paper", type=int, required=True)
    ap.add_argument("--title", required=True)
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--answers", required=True)
    ap.add_argument("--collection", default="jlpt-n5")
    ap.add_argument("--text-pages", required=True)
    ap.add_argument("--reading-pages", required=True)
    ap.add_argument("--listening-pages", required=True)
    ap.add_argument("--minutes", type=int, default=105)
    a = ap.parse_args()

    from app import exams
    from tools.assemble_questions import ask, valid
    from tools.generate_answers import ask as ask_answers

    pdf = pathlib.Path(a.pdf)
    answers = json.loads(pathlib.Path(a.answers).read_text(encoding="utf-8-sig"))
    # OCR 缓存由 scan_layout.py 生成: lay_2010_07_.json 这种
    import re as _re
    key = _re.sub(r"[^0-9A-Za-z]+", "_", a.title)[:12]
    cands = sorted(TMP.glob("lay_*.json"), key=lambda p: len(p.stem), reverse=True)
    ocr_path = next((c for c in cands if key and key[:7] in c.stem), None)
    if ocr_path is None:
        raise SystemExit(f"找不到 {a.title} 的 OCR 缓存 (key={key})")
    ocr = json.loads(ocr_path.read_text(encoding="utf-8"))
    print("OCR 缓存:", ocr_path.name)

    out_root = ROOT / "data" / "exams" / a.collection
    (out_root / "img").mkdir(parents=True, exist_ok=True)

    sections: list[dict] = []
    report: list[str] = []

    def raw_assemble(pages: list[int], mode: str = "normal") -> list[dict]:
        """只组装, 不配答案."""
        qs: list[dict] = []
        for page in ocr["items"]:
            if page["page"] not in pages:
                continue
            try:
                got = ask(page, mode)
            except Exception as exc:      # noqa: BLE001
                report.append(f"第{page['page']}页组装失败: {exc}")
                continue
            qs.extend([q for q in got if valid(q)[0]])
        return qs

    def align(qs: list[dict], section: str) -> list[dict]:
        """按**题号**套官方答案; 题号对不上时才退回 AI 答案.

        实测模型返回的 no 就是卷面题号 (2010 文字語彙: 1..33 缺 20),
        所以哪怕少解出几题, 答案依然能精确对上 —— 不用再靠"数量相等"。
        """
        key = flatten(answers.get(section) or {})
        hit = 0
        for q in qs:
            try:
                n = int(q.get("no"))
            except (TypeError, ValueError):
                continue
            if 1 <= n <= len(key):
                q["_answer"] = key[n - 1]
                hit += 1
        miss = [q for q in qs if "_answer" not in q]
        if miss:
            try:
                ai = ask_answers([{"no": i + 1, "prompt": q["prompt"],
                                   "options": q["options"]}
                                  for i, q in enumerate(miss)])
            except Exception as exc:      # noqa: BLE001
                report.append(f"{section} AI 答案失败: {exc}")
                ai = {}
            for i, q in enumerate(miss, start=1):
                v = ai.get(str(i), ai.get(i))
                try:
                    q["_answer"] = int(str(v)[0])
                except (TypeError, ValueError, IndexError):
                    q["_answer"] = 1
            report.append(f"{section}: {hit} 题用官方答案, {len(miss)} 题用 AI 答案")
        else:
            report.append(f"{section}: {hit} 题全部用官方答案")
        return qs

    def assemble(pages: list[int], section: str, group: str,
                 mode: str = "normal") -> list[dict]:
        """按页组装, 再按答案数量决定答案来源.

        文法・読解 里前几页是四选一文法题 (normal), 后面才是带文章的长文题
        (reading) —— 全部用 reading 模式会把语法题全漏掉 (实测 32 题只解出 8)。
        """
        qs = align(raw_assemble(pages, mode), section)
        items = []
        for i, q in enumerate(qs):
            prompt = q["prompt"]
            if q.get("passage"):
                prompt = f'【文章】{q["passage"]}\n【問】{prompt}'
            items.append({"prompt": prompt, "options": q["options"],
                          "answer": q.get("_answer", 1)})
        return items

    si = 0
    read_pages = parse_range(a.reading_pages)
    # 文法页用 normal, 长文页用 reading
    grammar_pages = read_pages[:max(1, len(read_pages) - 2)]
    passage_pages = read_pages[len(grammar_pages):]
    for section, pages_spec, group in (
            ("文字・語彙", a.text_pages, "文字・語彙"),
            ("文法・読解", a.reading_pages, "文法・読解")):
        if section == "文法・読解":
            qs = raw_assemble(grammar_pages, "normal")
            if passage_pages:
                qs += raw_assemble(passage_pages, "reading")
            qs = align(qs, section)
            items = []
            for q in qs:
                prompt = q["prompt"]
                if q.get("passage"):
                    prompt = f'【文章】{q["passage"]}\n【問】{prompt}'
                items.append({"prompt": prompt, "options": q["options"],
                              "answer": q.get("_answer", 1)})
        else:
            items = assemble(parse_range(pages_spec), section, group)
        if not items:
            continue
        si += 1
        for i, it in enumerate(items):
            it["id"] = f"Q{a.paper:02d}-S{si}-{i + 1}"
        sections.append({"no": si, "title": f"{section}（{len(items)} 题）",
                         "kind": "choice", "group": group, "items": items})

    # 聴解: 每一番一题, 配所在页的整页图
    lis = answers.get("聴解") or {}
    lis_pages = parse_range(a.listening_pages)
    import pypdfium2 as pdfium

    doc = pdfium.PdfDocument(str(pdf))
    page_imgs: dict[int, str] = {}
    for idx, pg in enumerate(lis_pages):
        name = f"p{a.paper:02d}-listen-p{pg}.png"
        path = out_root / "img" / name
        if not path.exists():
            doc[pg - 1].render(scale=2.4).to_pil().save(path)
        page_imgs[pg] = f"exams/{a.collection}/img/{name}"

    for gidx, (gname, values) in enumerate(
            sorted(lis.items(), key=lambda kv: int("".join(c for c in kv[0] if c.isdigit()) or 0))):
        pg = lis_pages[min(gidx, len(lis_pages) - 1)]
        si += 1
        items = [{
            "id": f"Q{a.paper:02d}-S{si}-{i + 1}",
            "prompt": f"第 {i + 1} 番（{gname}）",
            "options": ["①", "②", "③", "④"],
            "answer": ans,
            "image": page_imgs[pg],
        } for i, ans in enumerate(values)]
        sections.append({"no": si, "title": f"聴解 {gname[-1]}（{len(items)} 题）",
                         "kind": "choice", "group": "聴解", "items": items})
    if lis:
        report.append(f"聴解: {sum(len(v) for v in lis.values())} 题, 答案=官方答案表")

    if not sections:
        print("没产出任何题目")
        return 1

    path = exams.save_path(a.collection)
    bank = {"version": 2, "meta": {"id": a.collection, "name": "JLPT-N5",
                                   "kind": "jlpt", "desc": "日语能力考 N5 真题",
                                   "duration_min": a.minutes, "order": 20},
            "lessons": []}
    if path.exists():
        try:
            bank = json.loads(path.read_text(encoding="utf-8"))
        except Exception:      # noqa: BLE001
            pass
    lessons = [l for l in bank.get("lessons") or [] if l.get("lesson") != a.paper]
    lessons.append({"lesson": a.paper, "title": a.title,
                    "duration_min": a.minutes, "sections": sections})
    lessons.sort(key=lambda l: l["lesson"])
    bank["lessons"] = lessons
    bank.setdefault("meta", {"id": a.collection, "name": "JLPT-N5",
                             "kind": "jlpt", "duration_min": a.minutes})
    path.write_text(json.dumps(bank, ensure_ascii=False, indent=1), encoding="utf-8")

    total = sum(len(s["items"]) for s in sections)
    print(f"\n第 {a.paper} 套「{a.title}」: {len(sections)} 个大题 / {total} 题")
    for g in ("文字・語彙", "文法・読解", "聴解"):
        n = sum(len(s["items"]) for s in sections if s["group"] == g)
        print(f"  {g}: {n} 题")
    for r in report:
        print("  ·", r)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
