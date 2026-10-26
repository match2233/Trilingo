"""把 N5 试卷建成完整形态 (支持"没有答案表"的卷子).

三种情况:
  * 有答案表 -> 按题号套官方答案
  * 没有答案表 -> 文字/文法用 AI 答案
  * 聴解 -> 没有答案表时生成"自评"题 (answer=None), 用户听完自己判对错

用法:
    python tools/build_paper_full.py --paper 11 --title 2017年07月 \
        --pdf "<pdf>" [--answers data/ocr/answers_2017.json] \
        --text-pages 1-5 --reading-pages 6-9 --listening-pages 10-14
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

TMP = ROOT / "data" / "ocr"
RENDER_L = 2.6


def flatten(table: dict) -> list[int]:
    out: list[int] = []
    for key in sorted(table, key=lambda k: int("".join(c for c in k if c.isdigit()) or 0)):
        out.extend(table[key])
    return out


def parse_range(s: str) -> list[int]:
    """支持 3-8 以及 3-8,50-58 这种多段写法."""
    out: list[int] = []
    for part in str(s).split(","):
        part = part.strip()
        if not part:
            continue
        lo, _, hi = part.partition("-")
        out.extend(range(int(lo), int(hi or lo) + 1))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--paper", type=int, required=True)
    ap.add_argument("--title", required=True)
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--answers", default="")
    ap.add_argument("--ocr", default="", help="直接指定 OCR 缓存 (分卷 PDF 时用)")
    ap.add_argument("--collection", default="jlpt-n5")
    ap.add_argument("--text-pages", required=True)
    ap.add_argument("--reading-pages", required=True)
    ap.add_argument("--listening-pages", required=True)
    ap.add_argument("--minutes", type=int, default=105)
    ap.add_argument("--groups", default="",
                    help="只重建这些分区, 逗号分隔: 文字・語彙,文法・読解,聴解")
    ap.add_argument("--groups", default="",
                    help="只重建这些分区, 逗号分隔: 文字・語彙,文法・読解,聴解")
    ap.add_argument("--groups", default="",
                    help="只重建这些分区, 逗号分隔: 文字・語彙,文法・読解,聴解")
    ap.add_argument("--groups", default="",
                    help="只重建这些分区, 逗号分隔: 文字・語彙,文法・読解,聴解")
    ap.add_argument("--groups", default="",
                    help="只重建这些分区, 逗号分隔: 文字・語彙,文法・読解,聴解")
    ap.add_argument("--groups", default="",
                    help="只重建这些分区, 逗号分隔: 文字・語彙,文法・読解,聴解")
    ap.add_argument("--groups", default="",
                    help="只重建这些分区, 逗号分隔: 文字・語彙,文法・読解,聴解")
    ap.add_argument("--groups", default="",
                    help="只重建这些分区, 逗号分隔: 文字・語彙,文法・読解,聴解")
    a = ap.parse_args()

    from app import exams
    from tools.assemble_questions import ask, valid
    from tools.generate_answers import ask as ask_answers

    pdf = pathlib.Path(a.pdf)
    answers = {}
    if a.answers and pathlib.Path(a.answers).exists():
        answers = json.loads(pathlib.Path(a.answers).read_text(encoding="utf-8-sig"))

    import re as _re
    key = _re.sub(r"[^0-9A-Za-z]+", "_", a.title)[:12]
    if a.ocr:
        ocr_path = pathlib.Path(a.ocr)
    else:
        cands = sorted(TMP.glob("lay_*.json"), key=lambda p: len(p.stem), reverse=True)
        ocr_path = next((c for c in cands if key and key[:7] in c.stem), None)
    if ocr_path is None:
        raise SystemExit(f"找不到 {a.title} 的 OCR 缓存 (key={key})")
    ocr = json.loads(ocr_path.read_text(encoding="utf-8"))
    print("OCR 缓存:", ocr_path.name)

    out_root = ROOT / "data" / "exams" / a.collection
    (out_root / "img").mkdir(parents=True, exist_ok=True)
    report: list[str] = []

    def raw_assemble(pages: list[int], mode: str = "normal") -> list[dict]:
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
        table = answers.get(section) or {}
        key_ans = flatten(table)
        hit = 0
        for q in qs:
            try:
                n = int(q.get("no"))
            except (TypeError, ValueError):
                continue
            if key_ans and 1 <= n <= len(key_ans):
                q["_answer"] = key_ans[n - 1]
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
            report.append(f"{section}: {hit} 题官方答案 / {len(miss)} 题 AI 答案")
        else:
            report.append(f"{section}: {hit} 题官方答案")
        return qs

    want = [g.strip() for g in a.groups.split(",") if g.strip()]
    if not want:
        want = ["文字・語彙", "文法・読解", "聴解"]

    want = [g.strip() for g in a.groups.split(",") if g.strip()]
    if not want:
        want = ["文字・語彙", "文法・読解", "聴解"]

    want = [g.strip() for g in a.groups.split(",") if g.strip()]
    if not want:
        want = ["文字・語彙", "文法・読解", "聴解"]

    want = [g.strip() for g in a.groups.split(",") if g.strip()]
    if not want:
        want = ["文字・語彙", "文法・読解", "聴解"]

    want = [g.strip() for g in a.groups.split(",") if g.strip()]
    if not want:
        want = ["文字・語彙", "文法・読解", "聴解"]

    want = [g.strip() for g in a.groups.split(",") if g.strip()]
    if not want:
        want = ["文字・語彙", "文法・読解", "聴解"]

    want = [g.strip() for g in a.groups.split(",") if g.strip()]
    if not want:
        want = ["文字・語彙", "文法・読解", "聴解"]

    want = [g.strip() for g in a.groups.split(",") if g.strip()]
    if not want:
        want = ["文字・語彙", "文法・読解", "聴解"]

    want = [g.strip() for g in a.groups.split(",") if g.strip()]
    if not want:
        want = ["文字・語彙", "文法・読解", "聴解"]

    sections: list[dict] = []
    si = 0
    read_pages = parse_range(a.reading_pages)
    grammar_pages = read_pages[:max(1, len(read_pages) - 2)]
    passage_pages = read_pages[len(grammar_pages):]

    for section, pages_spec in (("文字・語彙", a.text_pages),
                                ("文法・読解", a.reading_pages)):
        if section not in want:
            continue
        if section not in want:
            continue
        if section not in want:
            continue
        if section not in want:
            continue
        if section not in want:
            continue
        if section not in want:
            continue
        if section not in want:
            continue
        if section not in want:
            continue
        if section not in want:
            continue
        if section == "文法・読解":
            qs = raw_assemble(grammar_pages, "normal") + \
                raw_assemble(passage_pages, "reading")
        else:
            qs = raw_assemble(parse_range(pages_spec), "normal")
        qs = align(qs, section)
        items = []
        for q in qs:
            prompt = q["prompt"]
            if q.get("passage"):
                prompt = f'【文章】{q["passage"]}\n【問】{prompt}'
            items.append({"prompt": prompt, "options": q["options"],
                          "answer": q.get("_answer", 1)})
        if not items:
            continue
        si += 1
        for i, it in enumerate(items):
            it["id"] = f"Q{a.paper:02d}-S{si}-{i + 1}"
        sections.append({"no": si, "title": f"{section}（{len(items)} 题）",
                         "kind": "choice", "group": section, "items": items})

    # ---------------- 聴解 ----------------
    import numpy as np
    import pypdfium2 as pdfium

    doc = pdfium.PdfDocument(str(pdf))

    def bands_of(img, min_h=90, gap=16):
        g = np.asarray(img.convert("L"))
        H, W = g.shape
        prof = g[:, int(W * 0.03):int(W * 0.97)].min(axis=1)
        has = prof < 205
        out, start, blank = [], None, 0
        for y in range(H):
            if has[y]:
                if start is None:
                    start = y
                blank = 0
            elif start is not None:
                blank += 1
                if blank >= gap:
                    if y - blank + 1 - start >= min_h:
                        out.append((start, y - blank + 1))
                    start, blank = None, 0
        if start is not None and H - start >= min_h:
            out.append((start, H))
        return out

    def trim(crop):
        g = np.asarray(crop.convert("L"))
        m = g < 235
        if not m.any():
            return crop
        ys, xs = np.where(m)
        pad = 6
        return crop.crop((max(0, int(xs.min()) - pad), max(0, int(ys.min()) - pad),
                          min(crop.width, int(xs.max()) + pad),
                          min(crop.height, int(ys.max()) + pad)))

    lis_table = answers.get("聴解") or {}
    do_lis = "聴解" in want
    do_lis = "聴解" in want
    do_lis = "聴解" in want
    do_lis = "聴解" in want
    do_lis = "聴解" in want
    do_lis = "聴解" in want
    do_lis = "聴解" in want
    do_lis = "聴解" in want
    do_lis = "聴解" in want
    groups = sorted(lis_table.items(),
                    key=lambda kv: int("".join(c for c in kv[0] if c.isdigit()) or 0))
    lis_flat = flatten(lis_table)
    lis_counts = [len(v) for _k, v in groups]

    boxes: list = []
    for pg in (parse_range(a.listening_pages) if do_lis else []):
        img = doc[pg - 1].render(scale=RENDER_L).to_pil()
        for (y0, y1) in bands_of(img):
            boxes.append((img, y0, y1))

    target = sum(lis_counts) if lis_counts else len(boxes)
    if target and len(boxes) > target:
        keep, step = [], len(boxes) / target
        for i in range(target):
            lo = int(i * step)
            hi = max(lo + 1, int((i + 1) * step))
            keep.append((boxes[lo][0], boxes[lo][1], boxes[min(hi, len(boxes)) - 1][2]))
        boxes = keep

    if not groups:
        groups = [("聴解", [None] * len(boxes))]

    idx = 0
    for gname, values in groups:
        si += 1
        items = []
        for i in range(len(values)):
            if idx >= len(boxes):
                break
            im, y0, y1 = boxes[idx]
            W, H = im.size
            name = f"p{a.paper:02d}-l{idx + 1:02d}.png"
            crop = trim(im.crop((int(W * 0.03), max(0, y0 - 8),
                                 int(W * 0.97), min(H, y1 + 8))))
            crop.save(out_root / "img" / name)
            items.append({
                "id": f"Q{a.paper:02d}-S{si}-{i + 1}",
                "prompt": f"第 {i + 1} 番（{gname}）",
                "options": ["①", "②", "③", "④"],
                "answer": lis_flat[idx] if lis_flat else None,
                "image": f"exams/{a.collection}/img/{name}",
            })
            idx += 1
        if items:
            sections.append({"no": si, "title": f"聴解 {gname[-1]}（{len(items)} 题）",
                             "kind": "choice", "group": "聴解", "items": items})
    if idx:
        report.append(f"聴解: {idx} 题"
                      + ("（官方答案）" if lis_flat else "（无答案表 -> 自评）"))

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
    old = [l for l in bank.get("lessons") or [] if l.get("lesson") == a.paper]
    lessons = [l for l in bank.get("lessons") or [] if l.get("lesson") != a.paper]
    if old:
        # 只重建了部分分区时, 把没重建的分区原样接回来
        # 只保留"已知分区且这次没重建"的; group 为空的旧格式分区一律丢掉,
        # 否则新旧题目会重复混在一起 (2017 卷就踩过: 20 道旧题挂着空 group)
        known = ("文字・語彙", "文法・読解", "聴解")
        kept = [s for s in old[0].get("sections") or []
                if s.get("group") in known and s.get("group") not in want]
        if kept:
            sections = kept + sections
            sections.sort(key=lambda s: 0 if s.get("group") == "文字・語彙"
                          else (1 if s.get("group") == "文法・読解" else 2))
            for i, s in enumerate(sections, start=1):
                s["no"] = i
                for j, it in enumerate(s["items"], start=1):
                    it["id"] = f"Q{a.paper:02d}-S{i}-{j}"
    lesson = {"lesson": a.paper, "title": a.title,
              "duration_min": a.minutes, "sections": sections}
    if old and old[0].get("audio"):
        lesson["audio"] = old[0]["audio"]
    lessons.append(lesson)
    lessons.sort(key=lambda l: l["lesson"])
    bank["lessons"] = lessons
    bank.setdefault("meta", {"id": a.collection, "name": "JLPT-N5",
                             "kind": "jlpt", "duration_min": a.minutes})
    path.write_text(json.dumps(bank, ensure_ascii=False, indent=1), encoding="utf-8")

    total = sum(len(s["items"]) for s in sections)
    print(f"\n第 {a.paper} 套「{a.title}」: {len(sections)} 个大题 / {total} 题")
    for g in ("文字・語彙", "文法・読解", "聴解"):
        n = sum(len(s["items"]) for s in sections if s.get("group") == g)
        print(f"  {g}: {n} 题")
    for r in report:
        print("  ·", r)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
