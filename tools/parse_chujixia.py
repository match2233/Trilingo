"""解析《新标日初级下》同步测试卷 .doc 的纯文本, 生成题库草稿.

文本特点 (见 chujixia.txt):
  * 每课一段标题 `新版中日交流标准日本语初级下同步测试卷（第25课）`;
  * 题目挤在 1-2 个长段落里, 大题用 一、二、…七、 分隔;
  * 答案也挤在 1-2 段里, 以 `一、1．じょゆう…` 开头;
  * 小题编号有 `1.` `1．` `１．` 多种写法, 选项是 ①②③④ (偶尔被识别成 1-4)。

输出 draft JSON: 每课 -> sections[{no,title,kind,items[]}], 同时打印无法解析的片段。
"""
from __future__ import annotations

import json
import re
import sys
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
TXT = ROOT / "data" / "import" / "chujixia.txt"

CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩"
CN_NUM = "一二三四五六七八九十"

TITLE_RE = re.compile(r"第\s*([0-9]{2})\s*[课課]")
# 大題分隔: 一、 二， 三, ... 允许全角逗号/顿号笔误
SEC_RE = re.compile(rf"(?:^|(?<=[。．.\s]))([{CN_NUM}])\s*[、，,]\s*")
# 小題编号: 1. / 1． / １． / 1、 —— 前后要有边界, 避免把 "3.5" 里的小数切开
NUM_RE = re.compile(r"(?<![0-9０-９])([0-9０-９]{1,2})\s*[.．、]\s*")

SEC_KIND = {
    "一": ("fill", "将下列汉字用平假名填入"),
    "二": ("fill", "将下划线部分的假名用汉字填入"),
    "三": ("choice", "选择正确答案"),
    "四": ("choice", "选择恰当答案"),
    "五": ("translate", "译成汉语"),
    "六": ("translate", "译成日语"),
    "七": ("choice", "阅读文章选择"),
}


def norm_num(s: str) -> int:
    return int(s.translate(str.maketrans("０１２３４５６７８９", "0123456789")))


def split_sections(text: str) -> dict[str, str]:
    """把一段文字按 一、二、… 切开, 返回 {大題字: 内容}."""
    parts: dict[str, str] = {}
    marks = [(m.start(), m.group(1)) for m in SEC_RE.finditer(text)]
    if not marks:
        return parts
    for i, (pos, ch) in enumerate(marks):
        end = marks[i + 1][0] if i + 1 < len(marks) else len(text)
        body = text[pos:end]
        body = SEC_RE.sub("", body, count=1)
        parts.setdefault(ch, "")
        parts[ch] += body
    return parts


def split_items(body: str) -> list[tuple[int, str]]:
    """按编号切成 [(序号, 内容)]."""
    marks = [(m.start(), norm_num(m.group(1)), m.end()) for m in NUM_RE.finditer(body)]
    out = []
    for i, (pos, num, end) in enumerate(marks):
        nxt = marks[i + 1][0] if i + 1 < len(marks) else len(body)
        out.append((num, body[end:nxt].strip()))
    return out


def parse_options(text: str) -> tuple[str, list[str]]:
    """把 `题干预 ①A②B③C④D` 拆成 (题干, 四个选项)."""
    idx = [text.find(c) for c in CIRCLED[:4]]
    if min(idx) < 0:
        return text.strip(), []
    stem = text[:min(idx)].strip()
    opts = []
    for i in range(4):
        start = text.find(CIRCLED[i])
        end = text.find(CIRCLED[i + 1]) if i < 3 else len(text)
        if start < 0:
            return stem, []
        opts.append(text[start + 1:end].strip(" 　。，、"))
    return stem, opts


def parse_lesson(title: str, q_paras: list[str], a_paras: list[str]) -> dict:
    m = TITLE_RE.search(title)
    no = int(m.group(1)) if m else 0
    qtext = "\n".join(q_paras)
    atext = "\n".join(a_paras)

    qsecs = split_sections(qtext)
    asecs = split_sections(atext)

    sections = []
    for si, ch in enumerate(CN_NUM[:7]):
        if ch not in qsecs:
            continue
        kind, desc = SEC_KIND.get(ch, ("choice", ""))
        qitems = split_items(qsecs[ch])
        aitems = split_items(asecs.get(ch, ""))
        ans_by_no = {n: t for n, t in aitems}

        items = []
        for num, body in qitems:
            ans = ans_by_no.get(num, "").strip()
            if kind == "choice":
                stem, opts = parse_options(body)
                # 答案里的 ①/② 或 1/2
                pick = None
                for i, c in enumerate(CIRCLED[:4]):
                    if c in ans:
                        pick = i + 1
                        break
                if pick is None:
                    dm = re.search(r"[1-4１-４]", ans)
                    pick = norm_num(dm.group(0)) if dm else None
                items.append({"no": num, "prompt": stem, "options": opts,
                              "answer": pick, "raw_answer": ans})
            else:
                items.append({"no": num, "prompt": body.strip(),
                              "options": [], "answer": ans, "raw_answer": ans})
        if items:
            sections.append({"no": si + 1, "letter": ch, "kind": kind,
                             "title": f"{ch}、{desc}", "items": items})
    return {"lesson": no, "title": title.strip(), "sections": sections}


def main() -> int:
    if len(sys.argv) > 1:
        path = pathlib.Path(sys.argv[1])
    else:
        path = TXT
    paras = [p.strip() for p in path.read_text(encoding="utf-8").split("\n")]

    lessons: list[dict] = []
    cur = None
    mode = "q"
    for p in paras:
        if not p:
            continue
        if TITLE_RE.search(p) and len(p) < 60:
            if cur:
                lessons.append(parse_lesson(cur["title"], cur["q"], cur["a"]))
            cur = {"title": p, "q": [], "a": []}
            mode = "q"
            continue
        if cur is None:
            continue
        # 答案段: 以 一、1 或 第N課一、 开头, 且不含"将/从/阅读"等题干提示
        looks_answer = bool(re.match(rf"^\s*(?:第\s*[0-9]+\s*[课課])?\s*[{CN_NUM}]\s*[、，,]\s*[0-9０-９I|]", p))
        if looks_answer and not re.search(r"将下列|从下列|阅读下列", p):
            mode = "a"
        cur[mode].append(p)

    if cur:
        lessons.append(parse_lesson(cur["title"], cur["q"], cur["a"]))

    lessons = [l for l in lessons if l["sections"]]
    print(f"解析出 {len(lessons)} 课")
    total = 0
    for l in lessons:
        kinds = {s["letter"]: len(s["items"]) for s in l["sections"]}
        n = sum(kinds.values())
        total += n
        print(f"  第{l['lesson']:2d}课: {kinds}  合计 {n}")
    print("题目总数:", total)

    out = ROOT / "data" / "ocr" / "chujixia_draft.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"lessons": lessons}, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    print("已写", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
