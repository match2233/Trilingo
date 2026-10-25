"""把一个文件夹里的试卷 PDF 导入成"试卷集".

流程 (对应 .dsh/skills/import-exam-papers/SKILL.md):
  1. 扫描文件夹, 按考试分组成: 试题 PDF / 答案 PDF 或图片 / 听力音频
  2. 质量体检: 有没有文字层 (扫描件要 OCR)、有没有答案、有没有音频、页数是否完整
  3. 打分: <40 分直接放弃 (省 token); 部分缺失但 AI 能补的继续
  4. 取文字: 有文字层直接用, 扫描件渲染成图再用 Windows OCR
  5. 调 AI 把整页文字整理成题目 JSON (大题/小题/选项/答案/是否有图)
  6. 调 AI 通读一遍修错 (字形识别、假名拼写、答案缺失)
  7. 去重后写进 data/tests/<集>.json, 并在 index.json 里登记

用法:
    python tools/import_papers.py --folder "C:/Users/<user>\\Desktop\\N5" --name "JLPT-N5"
    python tools/import_papers.py --folder ... --name ... --analyze-only   # 只体检不导入
    python tools/import_papers.py --folder ... --name ... --limit 1        # 只导一套试试
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import llm  # noqa: E402

TESTS_DIR = ROOT / "data" / "tests"
INDEX = TESTS_DIR / "index.json"
WORK = pathlib.Path.home() / ".dsh" / "tmp" / "import_papers"

PAPER_HINT = re.compile(r"(真题|试题|试卷|問題|问题)")
ANSWER_HINT = re.compile(r"(答案|解析|参考)")
AUDIO_EXT = {".mp3", ".mp4", ".m4a", ".wav"}


# ------------------------------------------------------------------ 扫描
def scan(folder: pathlib.Path) -> list[dict]:
    """按"考试"分组: 每个子文件夹算一场(标题里带年份/月份)."""
    exams: dict[pathlib.Path, dict] = {}
    for p in sorted(folder.rglob("*")):
        if not p.is_file():
            continue
        ext = p.suffix.lower()
        key = p.parent
        e = exams.setdefault(key, {"dir": key, "papers": [], "answers": [],
                                   "audio": [], "images": []})
        if ext == ".pdf":
            if ANSWER_HINT.search(p.stem):
                e["answers"].append(p)
            elif PAPER_HINT.search(p.stem):
                e["papers"].append(p)
            else:
                e["answers"].append(p)
        elif ext in AUDIO_EXT:
            e["audio"].append(p)
        elif ext in {".jpg", ".jpeg", ".png"}:
            e["images"].append(p)

    out = []
    for key, e in exams.items():
        if not e["papers"]:
            continue
        # 同一场可能有很多 PDF, 取页数最多的那份当年试卷
        paper = max(e["papers"], key=lambda p: pdf_pages(p))
        out.append({"title": title_of(key), "dir": key, "paper": paper,
                    "answers": e["answers"], "audio": e["audio"],
                    "images": e["images"]})
    out.sort(key=lambda x: x["title"])
    return out


def title_of(d: pathlib.Path) -> str:
    name = d.name
    m = re.search(r"(\d{4})\s*年\s*(\d{1,2})\s*月", name)
    if m:
        return f"{m.group(1)}年{int(m.group(2)):02d}月"
    m = re.search(r"(\d{4})", name)
    return m.group(1) if m else name


def pdf_pages(path: pathlib.Path) -> int:
    try:
        import pypdfium2 as pdfium
        return len(pdfium.PdfDocument(str(path)))
    except Exception:      # noqa: BLE001
        return 0


# ------------------------------------------------------------------ 体检
def text_density(path: pathlib.Path) -> tuple[int, int]:
    """(平均每页字符数, 页数). 用来判断是扫描件还是电子版."""
    try:
        import pypdfium2 as pdfium
        doc = pdfium.PdfDocument(str(path))
        n = len(doc)
        if not n:
            return 0, 0
        total = 0
        for i in range(min(n, 6)):
            total += len(doc[i].get_textpage().get_text_range())
        return total // min(n, 6), n
    except Exception:      # noqa: BLE001
        return 0, 0


def readable_ratio(text: str) -> float:
    """假名占比. 正常日语里假名很多; 字体映射坏掉的乱码全是形近汉字, 假名极少."""
    body = [c for c in text if not c.isspace()]
    if not body:
        return 0.0
    kana = sum(1 for c in body
               if 0x3040 <= ord(c) <= 0x30FF or ord(c) == 0x30FC)
    return kana / len(body)


def inspect(exam: dict) -> dict:
    density, pages = text_density(exam["paper"])
    # 有文字层不代表能用: 乱码时按扫描件处理
    ratio = 0.0
    if density >= 8:
        try:
            import pypdfium2 as pdfium
            doc = pdfium.PdfDocument(str(exam["paper"]))
            sample = "".join(doc[i].get_textpage().get_text_range()
                             for i in range(min(3, len(doc))))
            ratio = readable_ratio(sample)
        except Exception:      # noqa: BLE001
            ratio = 0.0
    usable_text = density >= 80 and ratio >= 0.12
    has_ans = bool(exam["answers"])
    has_audio = bool(exam["audio"])
    score = 0
    reasons = []
    if usable_text:
        score += 45
        reasons.append("PDF 有可用文字层")
    elif density >= 8:
        score += 10
        reasons.append(f"文字层是乱码(日文占比{ratio:.0%}), 需 OCR")
    else:
        score += 10
        reasons.append("纯扫描件, 需 OCR")
    if has_ans:
        score += 30
        reasons.append("带答案")
    else:
        reasons.append("缺答案(可由 AI 生成)")
    if has_audio:
        score += 15
        reasons.append("带听力音频")
    if pages >= 8:
        score += 10
        reasons.append(f"{pages} 页")
    else:
        reasons.append(f"页数偏少({pages})")
    return {"density": density, "pages": pages, "has_answer": has_ans,
            "has_audio": has_audio, "score": score, "reasons": reasons,
            "text_usable": usable_text}


def sha1(path: pathlib.Path) -> str:
    h = hashlib.sha1()
    h.update(path.read_bytes())
    return h.hexdigest()


# ------------------------------------------------------------------ 取文字
def render_pages(path: pathlib.Path, out_dir: pathlib.Path,
                 scale: float = 2.4) -> list[pathlib.Path]:
    import pypdfium2 as pdfium

    out_dir.mkdir(parents=True, exist_ok=True)
    doc = pdfium.PdfDocument(str(path))
    files = []
    for i in range(len(doc)):
        img = doc[i].render(scale=scale).to_pil()
        f = out_dir / f"p{i + 1:03d}.png"
        img.save(f)
        files.append(f)
    return files


def ocr(png: pathlib.Path) -> str:
    script = ROOT / "tools" / "ocr_page.ps1"
    exe = pathlib.Path(r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe")
    try:
        r = subprocess.run([str(exe), "-NoProfile", "-ExecutionPolicy", "Bypass",
                            "-File", str(script), "-ImagePath", str(png)],
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=120)
        return tidy(r.stdout or "")
    except Exception as exc:      # noqa: BLE001
        print(f"    OCR 失败 {png.name}: {exc}")
        return ""


def tidy(text: str) -> str:
    """Windows OCR 会把日文按单字切词, 需要把字之间的空格去掉."""
    out = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        # 汉字/假名之间的空格剔除, 拉丁字母与数字之间保留
        line = re.sub(r"(?<=[^\x00-\x7F]) (?=[^\x00-\x7F])", "", line)
        out.append(line)
    return "\n".join(out)


def page_texts(pdf: pathlib.Path, cache: pathlib.Path) -> list[str]:
    density, pages = text_density(pdf)
    if density >= 60:
        import pypdfium2 as pdfium
        doc = pdfium.PdfDocument(str(pdf))
        raw = [doc[i].get_textpage().get_text_range() for i in range(len(doc))]
        if readable_ratio("".join(raw)) >= 0.12:
            return raw
        print("    文字层是乱码, 改走 OCR")
    if cache.exists():
        shutil.rmtree(cache)
    files = render_pages(pdf, cache)
    texts = []
    for f in files:
        texts.append(ocr(f))
        print(f"    OCR {f.name} ({len(texts[-1])} 字符)")
    return texts


# ------------------------------------------------------------------ AI
STRUCT_SYSTEM = """你是日语能力考试(JLPT)的排版助手。我会给你一份试卷若干页的 OCR 文字
(按页分隔, 文字里可能有个别识别错误)。请把这一份试卷整理成结构化 JSON。

要求：
1. 按大问 (問題1、問題2…) 分组, 每组给出 kind:
   * "choice" —— 四选一题；
   * "fill"   —— 需要填写的(如汉字读音、语境填空)也可归入 choice；
   * "translate" —— 翻译/写作题(能力考一般没有)。
2. 每道题给出: prompt(题干原文, 保留日语与下划线)、options(四个选项, 没有则省略)、
   answer(正确答案序号 1-4 或文本; 试卷里没有答案就留空)、image(题目是否需要看图,
   true/false)。
3. 只整理**题目本身**, 去掉「試験問題」「注意事項」等卷面说明页。
4. 不要臆造题目; OCR 里看不清就按能辨认的部分整理, 不要编。
5. 只输出 JSON: {"sections":[{"no":1,"title":"問題1","kind":"choice","items":[...]}]}"""


def structure(title: str, texts: list[str]) -> dict:
    body = "\n\n".join(f"=== 第 {i + 1} 页 ===\n{t}" for i, t in enumerate(texts) if t)
    cfg = llm.load_config()
    url = cfg["base_url"].rstrip("/") + "/chat/completions"
    payload = {
        "model": cfg["model"],
        "messages": [{"role": "system", "content": STRUCT_SYSTEM},
                     {"role": "user", "content": f"试卷: {title}\n\n{body}"}],
        "response_format": {"type": "json_object"},
        "temperature": 0.1,
        "stream": False,
    }
    data = llm._post(url, payload, cfg["api_key"], timeout=300)
    content = (data.get("choices") or [{}])[0].get("message", {}).get("content", "")
    return llm._extract_json(content)


REPAIR_SYSTEM = """你是日语老师, 正在校对一份从扫描件整理出来的试卷 JSON。

请**只修错误**, 不要改写题目:
* 修 OCR 造成的错字/假名错误 (形近字、浊音、长音、促音、小写拗音)；
* 修明显不通的句子, 依据上下文推断原意；
* 选项个数保持不变, 答案必须是有效序号；
* 缺答案且能根据语法判断的, 补上答案。

输出与原 JSON 完全同构的对象, 不要解释。"""


def repair(paper: dict) -> dict:
    cfg = llm.load_config()
    url = cfg["base_url"].rstrip("/") + "/chat/completions"
    payload = {
        "model": cfg["model"],
        "messages": [{"role": "system", "content": REPAIR_SYSTEM},
                     {"role": "user", "content": json.dumps(paper, ensure_ascii=False)}],
        "response_format": {"type": "json_object"},
        "temperature": 0,
        "stream": False,
    }
    data = llm._post(url, payload, cfg["api_key"], timeout=300)
    content = (data.get("choices") or [{}])[0].get("message", {}).get("content", "")
    obj = llm._extract_json(content)
    return obj if isinstance(obj.get("sections"), list) else paper


# ------------------------------------------------------------------ 落库
def load_index() -> dict:
    try:
        return json.loads(INDEX.read_text(encoding="utf-8"))
    except Exception:      # noqa: BLE001
        return {"collections": []}


def collection_file(col: dict) -> pathlib.Path:
    return TESTS_DIR / col["file"]


def existing_hashes() -> dict[str, str]:
    """全库已导入过的试卷: {源文件 sha1: 试卷标题}"""
    out: dict[str, str] = {}
    for f in TESTS_DIR.glob("*.json"):
        if f.name == "index.json":
            continue
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except Exception:      # noqa: BLE001
            continue
        if not isinstance(data, dict):      # import_report.json 之类是列表
            continue
        for les in data.get("lessons") or []:
            if les.get("source_sha"):
                out[les["source_sha"]] = les.get("title", "")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--folder", required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--kind", default="jlpt")
    ap.add_argument("--minutes", type=int, default=105, help="整卷时限(分钟)")
    ap.add_argument("--analyze-only", action="store_true")
    ap.add_argument("--limit", type=int, default=0, help="本次最多导入几套")
    ap.add_argument("--no-repair", action="store_true")
    args = ap.parse_args()

    folder = pathlib.Path(args.folder)
    if not folder.is_dir():
        print(f"文件夹不存在: {folder}")
        return 1
    exams = scan(folder)
    print(f"发现 {len(exams)} 场考试\n")

    rows = []
    for e in exams:
        info = inspect(e)
        rows.append((e, info))
        print(f"· {e['title']:<14} 评分 {info['score']:>3}  "
              f"{e['paper'].name[:38]:<40} {'; '.join(info['reasons'])}")
    print()

    good = [(e, i) for e, i in rows if i["score"] >= 40]
    bad = [(e, i) for e, i in rows if i["score"] < 40]
    print(f"可导入 {len(good)} 场, 放弃 {len(bad)} 场 (质量太差, 省 token)")
    if args.analyze_only:
        (TESTS_DIR / "import_report.json").write_text(
            json.dumps([{"title": e["title"], "file": e["paper"].name, **i}
                        for e, i in rows], ensure_ascii=False, indent=1),
            encoding="utf-8")
        print("体检报告: data/tests/import_report.json")
        return 0

    if not llm.is_configured():
        print("LLM 未配置, 无法整理题目")
        return 1

    idx = load_index()
    col = next((c for c in idx["collections"] if c["name"] == args.name), None)
    if col is None:
        used = {c["id"] for c in idx["collections"]}
        cid = re.sub(r"[^a-z0-9]+", "_", args.name.lower()).strip("_")
        base = 1001 + 1000 * len([c for c in idx["collections"] if c["kind"] != "unit"])
        while cid in used:
            cid += "x"
        col = {"id": cid, "name": args.name, "kind": args.kind,
               "base": base, "file": f"{cid}.json",
               "desc": f"{args.name} 试卷", "minutes": args.minutes}
        idx["collections"].append(col)
        INDEX.write_text(json.dumps(idx, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"新建试卷集: {col['name']} (id={cid}, 起编号 {base})")

    path = collection_file(col)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:      # noqa: BLE001
        data = {"id": col["id"], "name": col["name"], "kind": col["kind"], "lessons": []}
    have = existing_hashes()
    next_no = max([l["lesson"] for l in data["lessons"]] or [col["base"] - 1]) + 1

    done = 0
    for e, info in good:
        if args.limit and done >= args.limit:
            break
        digest = sha1(e["paper"])
        if digest in have:
            print(f"跳过(已导入过): {e['title']} -> {have[digest]}")
            continue
        print(f"\n导入 {e['title']} …")
        texts = page_texts(e["paper"], WORK / e["title"])
        joined = "\n".join(texts)
        if len(joined) < 200:
            print("  文字太少, 放弃")
            continue
        print(f"  取到 {len(joined)} 字符, 交给 AI 整理…")
        obj = structure(e["title"], texts)
        secs = obj.get("sections") or []
        if not secs:
            print("  AI 没能整理出题目, 放弃")
            continue
        les = {"lesson": next_no, "title": e["title"], "minutes": args.minutes,
               "source_sha": digest, "source": str(e["paper"]), "sections": secs}
        n_items = sum(len(s.get("items") or []) for s in secs)
        print(f"  整理出 {len(secs)} 个大题 / {n_items} 题")
        if not args.no_repair:
            print("  AI 校对错字…")
            fixed = repair(les)
            if sum(len(s.get("items") or []) for s in fixed.get("sections") or []) >= n_items:
                les = {**les, **{k: v for k, v in fixed.items() if k != "lesson"}}
        data["lessons"].append(les)
        have[digest] = e["title"]
        next_no += 1
        done += 1
        path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"  已写入 {path.name}")

    print(f"\n完成 {done} 套 -> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
