"""从《新版中日交流标准日本语(初级上)同步测试卷》PDF 生成题库 JSON.

用法:
    python tools/build_minna_tests.py [pdf路径] [-o 输出路径]

为什么需要清洗:
    PDF 内嵌字体的 ToUnicode 映射有缺陷, 一部分汉字/假名会被提取成"形近字"
    (丌/不, 叵/司, 叱/史, 癿/的, 迚/进, 夘/夜, 昢/昨 ...)。这些已逐字渲染
    原页人工核对过, 汇总在 GLYPH_FIX。剩下的属于原卷自身的错字(漏字、多余
    标点), 用 TEXT_FIX 定点修。

输出 (桌面与 PWA 共用同一份):
    {"version": 1, "source": "...", "lessons": [
      {"lesson": 1, "sections": [
        {"no": 1, "kind": "fill", "title": "...",
         "items": [{"id": "L01-S1-1", "prompt": "学生", "answer": "がくせい"}]},
        {"no": 3, "kind": "choice", "title": "...",
         "items": [{"id": ..., "prompt": "...", "options": [".."], "answer": 2}]},
        {"no": 5, "kind": "translate", "title": "...",
         "items": [{"id": ..., "prompt": "...", "answer": "..."}]}
      ]}]}
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

# ------------------------------------------------------------------ 字库修正
GLYPH_FIX = {
    "佒": "何", "癿": "的", "丌": "不", "夗": "多", "夘": "夜", "斱": "方",
    "叵": "司", "庨": "庭", "庩": "康", "飡": "饭", "飠": "饭", "叱": "史",
    "迚": "进", "朊": "朋", "忚": "快", "叴": "号", "忛": "念", "昢": "昨",
    "昡": "春", "兊": "克", "亍": "于", "皀": "白",
}

# 原卷自身的错字 / 漏字 / 多余标点
TEXT_FIX = [
    (r"儿点", "几点"),
    (r"一补", "一起"),
    (r"需要个小时", "需要一个小时"),
    (r"去哪儿\s*[rR]\s*？", "去哪儿？"),
    (r"史密斯\s*[.。]\s*考试", "史密斯，考试"),
    # 数字 0/1 被提取成字母 l / O (例如 "l0. ①" 其实是 "10. ①")
    (r"(?<![A-Za-z])l(?=\d)", "1"),
    (r"(?<=\d)O(?=[.．、\s])", "0"),
    # 第 2 课 大1 的答案行被字体损坏成 "2<乱码>纭?.しゃしん"。
    # 对照题干 2.辞書 / 3.写真, 正确内容是 "2.じしょ 3.しゃしん"。
    (r"2[^0-9]{0,6}?纭\?", "2.じしょ 3"),
    (r"丄|丂", ""),
]

# 片假名 リ / 小型 ィ 被当成平假名 り / 全角 イ
KANA_FIX = [
    (r"(?<=[\u3040-\u309f])リ", "り"),
    (r"リ(?=[\u3040-\u309f])", "り"),
    (r"リ(?=っぱ)", "り"),
    (r"ィギリス", "イギリス"),
    (r"ィタリア", "イタリア"),
    (r"タィ", "タイ"),
]

SECTION_NO = "一二三四五六七八九十"
# 大题号偶尔被提取成片假名/形近字 (ニ vs 二), 先归一化再匹配
SECTION_ALIAS = {"ニ": "二", "一": "一", "二": "二", "三": "三", "四": "四",
                 "五": "五", "六": "六", "七": "七", "八": "八", "九": "九", "十": "十"}
SECTION_RE = re.compile(r"^\s*([%s%s])、" % (SECTION_NO, "".join(SECTION_ALIAS)))
ANS_LINE = re.compile(r"^\s*答案\s*[:：]")
PAGE_NO = re.compile(r"^\s*-\s*\d+\s*-\s*$")
MARK = "①②③④⑤⑥"
CIRCLED = {c: i + 1 for i, c in enumerate(MARK)}
ITEM_SEP = r"[.．、：:,，]"
ITEM_FIND = re.compile(r"(?<!\d)(\d{1,2})\s*(?:%s\s*|\s+(?=[%s]))" % (ITEM_SEP, MARK))
# 宽松兜底: 题号后面既没标点也没 ①②③ (例如 "きっさてん 8 びょういん、9.でんわ")
ITEM_FIND_LOOSE = re.compile(r"(?<!\d)(\d{1,2})\s*(?:%s\s*|\s+)" % ITEM_SEP)


def clean(text: str) -> str:
    for bad, good in GLYPH_FIX.items():
        text = text.replace(bad, good)
    for pat, rep in KANA_FIX:
        text = re.sub(pat, rep, text)
    for pat, rep in TEXT_FIX:
        text = re.sub(pat, rep, text)
    return text


def restore_okurigana(prompt: str, answer: str) -> str:
    """补回被答案行砍掉的送假名.

    原卷答案常把送假名漏掉: 若い->わか, 難しい->むずか, 夏休み->なつやす。
    题干里保留着送假名, 所以"题干末尾的平假名串"就是要补回去的部分。
    """
    m = re.search(r"[\u3040-\u309f]+$", prompt)
    if not m or not answer:
        return answer
    tail = m.group(0)
    if answer.endswith(tail):
        return answer
    for k in range(len(tail), 0, -1):
        if answer.endswith(tail[:k]):
            return answer + tail[k:]
    return answer + tail


def kata_to_hira(s: str) -> str:
    """片假名 -> 平假名. 只用在"汉字改为平假名"的答案上."""
    out = []
    for c in s:
        o = ord(c)
        if 0x30A1 <= o <= 0x30F6:
            out.append(chr(o - 0x60))
        else:
            out.append(c)
    return "".join(out)


def norm(s: str) -> str:
    """字段级规整: 折行变空格, 收敛多余空白."""
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"\s*([，。？、；：!！?])", r"\1", s)
    return s.strip()


def norm_opt(s: str) -> str:
    """选项规整: 去掉误带的句点 (例如 "ほう.")."""
    s = norm(s)
    return re.sub(r"[.．]$", "", s).strip()


def split_numbered(text: str, max_n: int = 40, expect: int = 0,
                   regex: re.Pattern | None = None) -> list[str]:
    """按 1./2./3. … 的**顺序**把一段文字切成若干条.

    只按顺序找"下一个期望的数字", 所以题干里的普通数字 (10 兊、200 元)
    不会被误当成题号。少数答案块会把开头的 "1." 丢掉, 这时把第一段
    ("2." 之前的内容) 当成第 1 条。
    """
    finder = regex or ITEM_FIND
    marks: list[tuple[int, int, int]] = []      # (序号, 匹配起点, 正文起点)
    pos = 0
    for n in range(1, max_n + 1):
        hit = None
        for cand in finder.finditer(text, pos):
            v = int(cand.group(1))
            if v == n:
                hit = cand
                break
            if v > n:
                break
        if hit is None:
            break
        marks.append((n, hit.start(), hit.end()))
        pos = hit.end()
    if not marks:
        return []
    if marks[0][0] == 2 and text[: marks[0][1]].strip():
        marks.insert(0, (1, 0, 0))
    out = []
    for i, (_n, mstart, cstart) in enumerate(marks):
        end = marks[i + 1][1] if i + 1 < len(marks) else len(text)
        out.append(norm(text[cstart:end]))
    return out


def split_answers(body: str, expect: int) -> list[str]:
    """答案区切分: 先用严格规则, 条数不够再退回宽松规则."""
    got = split_numbered(body, expect or 60)
    if len(got) >= expect and expect:
        return got[:expect]
    loose = split_numbered(body, expect or 60, regex=ITEM_FIND_LOOSE)
    return loose if len(loose) > len(got) else got


# ------------------------------------------------------------------ 读 PDF
def read_pages(pdf_path: pathlib.Path) -> list[list[str]]:
    import pypdfium2 as pdfium  # noqa: PLC0415

    doc = pdfium.PdfDocument(str(pdf_path))
    pages = []
    for i in range(len(doc)):
        raw = doc[i].get_textpage().get_text_range()
        pages.append(raw.splitlines())
    return pages


def page_has_image(pdf_path: pathlib.Path) -> list[bool]:
    import pypdf  # noqa: PLC0415

    r = pypdf.PdfReader(str(pdf_path))
    out = []
    for p in r.pages:
        try:
            out.append(len(p.images) > 0)
        except Exception:  # noqa: BLE001
            out.append(False)
    return out


def collect_lines(pages: list[list[str]]) -> list[str]:
    """把正文按「第 N 课」切块, 返回 [(课号, 行列表)]."""
    blocks: dict[int, list[str]] = {}
    order: list[int] = []
    cur: int | None = None
    for idx, lines in enumerate(pages):
        if idx == 0:                     # 目录页
            continue
        for line in lines:
            if PAGE_NO.match(line):
                continue
            m = re.match(r"^\s*第\s*(\d{1,2})\s*课", line)
            if m:
                cur = int(m.group(1))
                if cur not in blocks:
                    blocks[cur] = []
                    order.append(cur)
                continue
            if cur is not None:
                blocks[cur].append(line)
    return [(n, blocks[n]) for n in sorted(blocks)]


def split_qa(lines: list[str]) -> tuple[list[str], list[str]]:
    for i, line in enumerate(lines):
        if ANS_LINE.match(line):
            return lines[:i], lines[i:]
    return lines, []


def sec_index(ch: str) -> int:
    """大题号字符 -> 1..10 (片假名 ニ 等别名算 二)."""
    ch = SECTION_ALIAS.get(ch, ch)
    return SECTION_NO.index(ch) + 1


def section_spans(lines: list[str]) -> list[tuple[int, int, str]]:
    """返回 [(大题号, 起始行, 标题)]."""
    out = []
    for i, line in enumerate(lines):
        m = SECTION_RE.match(line)
        if m:
            out.append((sec_index(m.group(1)), i, line.strip()))
    return out


def classify(head: str, body: str) -> str:
    if "择" in head or "选择" in head:
        return "choice"
    if "译成" in head:
        return "translate"
    if re.search(r"[%s]" % MARK, body[:200]) and head.rstrip().endswith(")"):
        return "choice"
    return "fill"


def build_section(no: int, head: str, body_lines: list[str]) -> dict | None:
    body = "\n".join(body_lines)
    head_clean = head
    title = re.sub(r"^[%s]、" % SECTION_NO, "", head).strip()
    title = re.sub(r"[（(][^）)]*[）)]\s*$", "", title).strip()
    kind = classify(head, body)

    if kind == "choice":
        chunks = split_numbered(body)
        items = []
        for ch in chunks:
            opts: list[str] = []
            positions = [i for i, c in enumerate(ch) if c in MARK]
            first = positions[0] if positions else len(ch)
            prompt = norm(ch[:first])
            rest = ch[first:]
            marks_here = [i for i, c in enumerate(rest) if c in MARK]
            for k, j in enumerate(marks_here):
                stop = marks_here[k + 1] if k + 1 < len(marks_here) else len(rest)
                opts.append(norm_opt(rest[j + 1:stop]))
            if not prompt and not opts:
                continue
            items.append({"prompt": prompt, "options": opts, "answer": None})
    else:
        chunks = split_numbered(body)
        items = [{"prompt": c, "answer": ""} for c in chunks if c]
    if not items:
        return None
    return {"no": no, "kind": kind, "title": norm(title), "items": items}


def answer_spans(lines: list[str]) -> list[tuple[int, int]]:
    spans = []
    for i, line in enumerate(lines):
        m = SECTION_RE.match(line)
        if m:
            spans.append((sec_index(m.group(1)), i))
    return spans


def parse_answers(lines: list[str], expect: dict[int, int]) -> dict[int, list[str]]:
    """解析答案区. expect 是 {大题号: 题数}, 用来在严格切分失效时退宽松规则."""
    spans = answer_spans(lines)
    out: dict[int, list[str]] = {}
    for k, (no, start) in enumerate(spans):
        end = spans[k + 1][1] if k + 1 < len(spans) else len(lines)
        body = "\n".join(lines[start:end])
        body = re.sub(r"^\s*[%s%s]、" % (SECTION_NO, "".join(SECTION_ALIAS)), "", body)
        out[no] = split_answers(body, expect.get(no, 0))
    return out


def build(pdf_path: pathlib.Path) -> tuple[dict, dict]:
    pages = read_pages(pdf_path)
    imgs = page_has_image(pdf_path)
    lessons = []
    stats = {"images": [i + 1 for i, v in enumerate(imgs) if v], "issues": []}

    for num, lines in collect_lines(pages):
        lines = [clean(l) for l in lines]
        q_lines, a_lines = split_qa(lines)
        q_spans = section_spans(q_lines)
        sections = []
        if not a_lines:
            stats["issues"].append(f"第{num}课: 找不到答案区")

        # 先切题干, 拿到每大题题数, 再据此解析答案
        for k, (no, start, head) in enumerate(q_spans):
            end = q_spans[k + 1][1] if k + 1 < len(q_spans) else len(q_lines)
            sec = build_section(no, head, q_lines[start + 1:end])
            if sec is None:
                stats["issues"].append(f"第{num}课 大{no}: 题干为空, 跳过")
                continue
            for i, it in enumerate(sec["items"]):
                it["id"] = f"L{num:02d}-S{no}-{i + 1}"
            sections.append(sec)

        expect = {s["no"]: len(s["items"]) for s in sections}
        answers = parse_answers([clean(l) for l in a_lines], expect)

        for sec in sections:
            no = sec["no"]
            ans = answers.get(no, [])
            for i, it in enumerate(sec["items"]):
                a = ans[i] if i < len(ans) else ""
                if sec["kind"] == "choice":
                    pick = None
                    for ch in a:
                        if ch in CIRCLED:
                            pick = CIRCLED[ch]
                            break
                    it["answer"] = pick
                    if pick is not None and pick > len(it["options"]):
                        stats["issues"].append(
                            f"{it['id']}: 答案 {pick} 超出选项数 {len(it['options'])}")
                else:
                    it["answer"] = norm(a)
                    # "汉字改为平假名"的答案必须全是平假名, 混进来的片假名(
                    # 例如 からル)一律折回平假名
                    if "汉字改为平假名" in sec["title"]:
                        it["answer"] = kata_to_hira(it["answer"])
                        it["answer"] = restore_okurigana(it["prompt"], it["answer"])
            if ans and len(ans) != len(sec["items"]):
                stats["issues"].append(
                    f"第{num}课 大{no}: 题目 {len(sec['items'])} 条 / 答案 {len(ans)} 条")

        # 整课都没有答案 (原卷缺失) —— 打标记, 界面会切到"自评"模式而不是逐题报错
        lesson_no_answer = not any(answers.values())
        missing = sum(
            1 for s in sections for it in s["items"]
            if (it.get("answer") in (None, "") ))
        if lesson_no_answer:
            stats["issues"].append(f"第{num}课: 原卷未附答案, 全课 {missing} 题改自评")
        else:
            miss_list = [it["id"] for s in sections for it in s["items"]
                         if it.get("answer") in (None, "")]
            if miss_list:
                stats["issues"].append(
                    f"第{num}课: {len(miss_list)} 题无答案 {miss_list[:6]}")

        present = {s["no"] for s in sections}
        expected = set(range(1, max(present) + 1)) if present else set()
        for miss in sorted(expected - present):
            has_ans = bool(answers.get(miss))
            stats["issues"].append(
                f"第{num}课 大{miss}: 题干缺失 (答案有 {len(answers.get(miss, []))} 条)"
                if has_ans else f"第{num}课 大{miss}: 整段缺失")
        lessons.append({"lesson": num, "sections": sections,
                        "no_answer": lesson_no_answer})

    return {"version": 1, "lessons": lessons}, stats


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf", nargs="?",
                    default=r"C:/Users/<user>\Downloads\7054163164000012.pdf")
    ap.add_argument("-o", "--out", default="data/minna_tests.json")
    args = ap.parse_args()

    pdf_path = pathlib.Path(args.pdf)
    if not pdf_path.is_file():
        print(f"PDF 不存在: {pdf_path}", file=sys.stderr)
        return 1
    data, stats = build(pdf_path)
    data["source"] = pdf_path.name

    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"{'课':>3}  大题(题型/题数)")
    total = 0
    for les in data["lessons"]:
        parts = "  ".join(
            f"{s['no']}{s['kind'][0]}{len(s['items'])}" for s in les["sections"])
        n = sum(len(s["items"]) for s in les["sections"])
        total += n
        print(f"{les['lesson']:>3}  {parts}   (={n})")
    print(f"\n总题数 {total}")
    if stats["images"]:
        print("含图片的页:", stats["images"])
    print(f"\n问题 {len(stats['issues'])} 条:")
    for s in stats["issues"][:40]:
        print("  -", s)
    print(f"\n输出 {out} ({out.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
