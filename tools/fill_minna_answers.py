"""用 LLM 补全题库里缺失的答案 (目前只有第 24 课: 原卷没附答案).

跑法:
    python tools/fill_minna_answers.py              # 补所有缺答案的题
    python tools/fill_minna_answers.py --lesson 24  # 只补某一课
    python tools/fill_minna_answers.py --dry-run     # 只打印, 不写回

设计:
  * 按"大题"分组提问, 让模型的上下文保持一致 (同一课的题型、难度一致)
  * 每类题型单独校验: 平假名题必须是平假名, 汉字题必须有汉字,
    选择题的答案必须是 1..N 的序号 —— 不合格的条目会再问一次
  * 只填空着的答案, 已有的绝不动
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import llm  # noqa: E402

BANK = ROOT / "data" / "minna_tests.json"

HIRA = lambda c: 0x3040 <= ord(c) <= 0x309F        # noqa: E731
KATA = lambda c: 0x30A0 <= ord(c) <= 0x30FF        # noqa: E731
CJK = lambda c: 0x4E00 <= ord(c) <= 0x9FFF         # noqa: E731
KANA = lambda c: HIRA(c) or KATA(c) or ord(c) == 0x30FC   # noqa: E731


def ratio(s: str, pred) -> float:
    letters = [c for c in s if not c.isspace() and not c.isascii() or
               (c.isascii() and c.isalpha())]
    letters = [c for c in s if not c.isspace()]
    if not letters:
        return 0.0
    return sum(1 for c in letters if pred(c)) / len(letters)


SYSTEM = """你是《新版中日交流标准日本语（初级上）》的资深日语教师，正在为同步测试卷编写标准答案。

要求：
1. 严格按题型作答：
   - 「将下列汉字改为平假名」→ 只给平假名读音，不要汉字，不要罗马字。
   - 「将下列假名改为汉字」→ 只给对应的汉字书写（含必要的送假名，例如 ひろい→広い）。
   - 「选择」题 → 只给正确选项的序号（1、2、3、4），不要文字。
   - 「将下列句子译成汉语」→ 给自然、准确的中文译文。
   - 「将下列汉语译成日语」→ 给自然的日语译文（用标准日语书写，不要罗马字）。
2. 词汇和语法必须符合《新标准日本语》初级上的范围。
3. 只输出一个 JSON 对象：键是题目编号（如 "L24-S1-3"），值是答案字符串或序号。
   不要输出任何解释、不要用代码块包裹以外的文字。"""


def ask(kind: str, title: str, items: list[dict]) -> dict:
    """把一批题发给模型, 返回 {id: answer}."""
    lines = []
    for it in items:
        head = f'{it["id"]} | 题干：{it["prompt"]}'
        if kind == "choice":
            opts = "  ".join(f"{i + 1}.{o}" for i, o in enumerate(it.get("options") or []))
            head += f" | 选项：{opts}"
        lines.append(head)
    user = f"题型：{title}\n\n" + "\n".join(lines) + "\n\n请给出答案。"
    cfg = llm.load_config()
    url = cfg["base_url"].rstrip("/") + "/chat/completions"
    payload = {
        "model": cfg["model"],
        "messages": [{"role": "system", "content": SYSTEM},
                     {"role": "user", "content": user}],
        "response_format": {"type": "json_object"},
        "temperature": 0.2,
        "stream": False,
    }
    data = llm._post(url, payload, cfg["api_key"], timeout=120)
    content = (data.get("choices") or [{}])[0].get("message", {}).get("content", "")
    return llm._extract_json(content)


def valid(kind: str, title: str, it: dict, ans) -> tuple[bool, str]:
    """校验一条答案, 返回 (合格?, 规范化后的值)."""
    if ans is None:
        return False, ""
    s = str(ans).strip()
    if not s:
        return False, ""
    if kind == "choice":
        m = re.search(r"[1-9]", s)
        n = int(m.group(0)) if m else 0
        opts = it.get("options") or []
        return (1 <= n <= len(opts)), str(n)
    if "汉字改为平假名" in title:
        s = "".join(chr(ord(c) - 0x60) if KATA(c) else c for c in s)
        s = re.sub(r"[（(].*?[）)]", "", s).strip()
        return (ratio(s, HIRA) > 0.9 and bool(s)), s
    if "假名改为汉字" in title:
        s = re.sub(r"[（(].*?[）)]", "", s).strip()
        return (any(CJK(c) for c in s)), s
    if "译成汉语" in title:
        return (sum(1 for c in s if CJK(c)) >= 2, s)
    if "译成日语" in title:
        return (any(KANA(c) for c in s), s)
    return True, s


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lesson", type=int, default=0)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--bank", default=str(BANK))
    args = ap.parse_args()

    path = pathlib.Path(args.bank)
    data = json.loads(path.read_text(encoding="utf-8"))
    if not llm.is_configured():
        print("LLM 未配置: 需要 data/llm.json 里的 api_key", file=sys.stderr)
        return 1

    filled = 0
    failed: list[str] = []
    for les in data["lessons"]:
        if args.lesson and les["lesson"] != args.lesson:
            continue
        for sec in les["sections"]:
            todo = [it for it in sec["items"]
                    if it.get("answer") in (None, "")]
            if not todo:
                continue
            title, kind = sec["title"], sec["kind"]
            print(f"第 {les['lesson']} 课 大{sec['no']} [{kind}] {title} —— 缺 {len(todo)} 条")
            for round_no in range(2):
                if not todo:
                    break
                got = ask(kind, title, todo)
                still = []
                for it in todo:
                    ok, val = valid(kind, title, it, got.get(it["id"]))
                    if ok:
                        it["answer"] = int(val) if kind == "choice" else val
                        filled += 1
                        print(f"   {it['id']}  {it['prompt'][:24]:24s} -> {it['answer']}")
                    else:
                        still.append(it)
                todo = still
                if todo and round_no == 0:
                    print(f"   （{len(todo)} 条未通过校验，重试一次）")
            for it in todo:
                failed.append(it["id"])
                print(f"   !! {it['id']} 仍无法确定答案")

    if args.dry_run:
        print(f"\n[dry-run] 本可补 {filled} 条, 未写回")
        return 0

    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    # 整课都补上了就把 no_answer 标记去掉
    for les in data["lessons"]:
        missing = sum(1 for s in les["sections"] for it in s["items"]
                      if it.get("answer") in (None, ""))
        if les.get("no_answer") and missing == 0:
            les["no_answer"] = False
            print(f"第 {les['lesson']} 课答案已补齐, 取消 no_answer 标记")
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"\n补全 {filled} 条, 失败 {len(failed)} 条")
    if failed:
        print("未完成:", ", ".join(failed[:20]))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
