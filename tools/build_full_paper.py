"""把一份 N5 试卷导入成完整形态: 文字・語彙 / 文法・読解 / 聴解.

关键改动: 按「問題N」分块导入, 而不是整页丢给模型。答案表就是按
`問題N + 顺序` 组织的, 只要题目在问题内按顺序编号, 答案就是精确对齐的。

聴解没有文字题干, 模型无法代答, 所以按"番"裁出卷面区域当题目图,
答案取答案表里 聴解N 的第 k 个。

用法:
    python tools/build_full_paper.py "<pdf>" --paper 3 \
        --answers data/ocr/answers_2010.json --title 2010年07月
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

TMP = ROOT / "data" / "ocr"
MONDAI = re.compile(r"^\s*問題\s*([0-9０-９]+)")
TR = str.maketrans("０１２３４５６７８９", "0123456789")
RENDER = 2.6


def load_ocr(pdf: pathlib.Path, paper: int) -> dict:
    cache = TMP / f"full_{paper}.ocr.json"
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))
    from tools.ocr_paper import ocr_pdf

    data = ocr_pdf(pdf, "", 2.2,
                   lambda i, hi, n: print(f"  OCR 第 {i}/{hi} 页 {n} 行", flush=True))
    cache.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return data


def page_section(texts: list[str]) -> str | None:
    j = "".join(texts)
    if "聴解" in j:
        return "聴解"
    if "読解" in j:
        return "文法・読解"
    if "語彙" in j or "文字" in j:
        return "文字・語彙"
    return None


def blocks(ocr: dict) -> list[dict]:
    out: list[dict] = []
    cur = None
    section = "文字・語彙"
    for page in ocr["items"]:
        sec = page_section([l["text"] for l in page["lines"]])
        if sec and sec != section:
            section, cur = sec, None
        for ln in page["lines"]:
            m = MONDAI.match(ln["text"])
            if m and len(ln["text"]) <= 45:
                num = int(str(m.group(1)).translate(TR))
                cur = {"section": section, "no": num, "lines": [],
                       "pages": [page["page"]], "scale": ocr.get("scale", 2.2)}
                out.append(cur)
                continue
            if cur is not None:
                cur["lines"].append(ln)
                if page["page"] not in cur["pages"]:
                    cur["pages"].append(page["page"])
    return [b for b in out if len(b["lines"]) >= 4]


BAN = re.compile(r"^[\s]*([0-9０-９]{1,2})\s*[-.．ー、]?\s*番")


def ban_marks(ocr: dict, pages: list[int]) -> list[tuple[int, float, float]]:
    """从 OCR 里取「N番」标记: [(页码, y, x)]."""
    out = []
    for page in ocr["items"]:
        if page["page"] not in pages:
            continue
        for ln in page["lines"]:
            m = BAN.match(ln["text"])
            if m:
                out.append((page["page"], float(ln["y"]), float(ln["x"])))
    return out


def crop_pages(pdf: pathlib.Path, pages: list[int], out_dir: pathlib.Path,
               prefix: str, count: int, ocr: dict | None = None) -> list[str]:
    """把这几页按"行带"切成 count 块, 返回图片相对路径列表."""
    import numpy as np
    import pypdfium2 as pdfium

    doc = pdfium.PdfDocument(str(pdf))
    imgs = []
    for pg in pages:
        imgs.append(doc[pg - 1].render(scale=RENDER).to_pil())

    # 优先用 OCR 的「N番」标记定纵切位置: 那些标记就是每一番的开头
    marks = ban_marks(ocr, pages) if ocr else []
    if len(marks) >= count:
        paths: list[str] = []
        K = RENDER / 2.2
        for pg in pages:
            if len(paths) >= count:
                break
            img = doc[pg - 1].render(scale=RENDER).to_pil()
            W, H = img.size
            ys = sorted(y for (p2, y, _x) in marks if p2 == pg)
            if not ys:
                continue
            for i, y in enumerate(ys):
                if len(paths) >= count:
                    break
                nxt = ys[i + 1] if i + 1 < len(ys) else H / K
                top = max(0.0, y - 12)
                bot = min(H / K, nxt - 4)
                if bot - top < 120:
                    bot = min(H / K, top + 240)
                name = f"{prefix}-{len(paths) + 1:02d}.png"
                img.crop((int(W * 0.03), int(top * K),
                          int(W * 0.97), int(bot * K))).save(out_dir / name)
                paths.append(name)
        if len(paths) >= count:
            return paths[:count]
        paths = []

    paths = []
    for img in imgs:
        if len(paths) >= count:
            break
        g = np.asarray(img.convert("L"))
        H, W = g.shape
        dark = g < 205
        prof = dark[:, int(W * 0.03):int(W * 0.97)].sum(axis=1)
        # 找连续的有内容行带
        thr = W * 0.004
        rows = prof > thr
        bands, start, blank = [], None, 0
        for y in range(H):
            if rows[y]:
                if start is None:
                    start = y
                blank = 0
            elif start is not None:
                blank += 1
                if blank >= 18:
                    if y - blank + 1 - start > 60:
                        bands.append((start, y - blank + 1))
                    start, blank = None, 0
        if start is not None and H - start > 60:
            bands.append((start, H))
        for (y0, y1) in bands:
            if len(paths) >= count:
                break
            name = f"{prefix}-{len(paths) + 1:02d}.png"
            img.crop((int(W * 0.03), max(0, y0 - 6),
                      int(W * 0.97), min(H, y1 + 6))).save(out_dir / name)
            paths.append(name)
    return paths


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("--paper", type=int, required=True)
    ap.add_argument("--collection", default="jlpt-n5")
    ap.add_argument("--answers", required=True)
    ap.add_argument("--title", default="")
    ap.add_argument("--minutes", type=int, default=105)
    a = ap.parse_args()

    from tools.assemble_questions import ask, valid

    pdf = pathlib.Path(a.pdf)
    ans = json.loads(pathlib.Path(a.answers).read_text(encoding="utf-8-sig"))
    ocr = load_ocr(pdf, a.paper)
    blks = blocks(ocr)
    print(f"识别到 {len(blks)} 个「問題」块: "
          f"{[(b['section'], b['no'], len(b['lines'])) for b in blks]}")

    out_root = ROOT / "data" / "exams" / a.collection
    (out_root / "img").mkdir(parents=True, exist_ok=True)

    sections, si = [], 0
    stat = {"ok": 0, "short": 0}
    for b in blks:
        sec_name = b["section"]
        key = f"問題{b['no']}" if sec_name != "聴解" else f"聴解{b['no']}"
        answers = (ans.get(sec_name) or {}).get(key) or []
        if not answers:
            print(f"  ! {sec_name} {key} 答案表里没有, 跳过")
            continue
        si += 1
        items = []
        if sec_name == "聴解":
            names = crop_pages(pdf, b["pages"], out_root / "img",
                               f"p{a.paper:02d}-l{b['no']}", len(answers), ocr)
            if len(names) < len(answers):
                stat["short"] += 1
                print(f"  ! 聴解{b['no']}: 只切出 {len(names)}/{len(answers)} 块")
            for i, name in enumerate(names):
                items.append({
                    "id": f"Q{a.paper:02d}-S{si}-{i + 1}",
                    "prompt": f"聴解　第 {i + 1} 番",
                    "options": ["①", "②", "③", "④"],
                    "answer": answers[i],
                    "image": f"exams/{a.collection}/img/{name}",
                })
        else:
            page = {"page": b["pages"][0], "lines": b["lines"]}
            try:
                qs = ask(page, "reading" if "読解" in sec_name else "normal")
            except Exception as exc:      # noqa: BLE001
                print(f"  ! {sec_name} {key} 组装失败: {exc}")
                continue
            kept = [q for q in qs if valid(q)[0]]
            if len(kept) < len(answers):
                stat["short"] += 1
                print(f"  ! {key}: 只组装出 {len(kept)}/{len(answers)} 题")
            for i, q in enumerate(kept[:len(answers)]):
                prompt = q["prompt"]
                if q.get("passage"):
                    prompt = f'【文章】{q["passage"]}\n【問】{prompt}'
                items.append({
                    "id": f"Q{a.paper:02d}-S{si}-{i + 1}",
                    "prompt": prompt,
                    "options": q["options"],
                    "answer": answers[i],
                })
        if not items:
            continue
        stat["ok"] += len(items)
        sections.append({"no": si, "title": f"{key}（{len(items)} 题）",
                         "kind": "choice", "group": sec_name, "items": items})

    if not sections:
        print("没有产出任何题目")
        return 1

    from app import exams

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
    lessons.append({"lesson": a.paper, "title": a.title or pdf.stem,
                    "duration_min": a.minutes, "sections": sections})
    lessons.sort(key=lambda l: l["lesson"])
    bank["lessons"] = lessons
    bank.setdefault("meta", {"id": a.collection, "name": "JLPT-N5",
                             "kind": "jlpt", "duration_min": a.minutes})
    path.write_text(json.dumps(bank, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n第 {a.paper} 套写入 {path}: {len(sections)} 个大题 / {stat['ok']} 题")
    print(f"  组装不足的大题: {stat['short']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
