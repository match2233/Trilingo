"""语义校验: 检查题库 JSON 里题型与答案是否自洽.

跑法:  python tools/verify_minna_tests.py [json路径]
"""
from __future__ import annotations

import json
import pathlib
import sys
import unicodedata

KANA = set(range(0x3040, 0x30A0)) | set(range(0x30A0, 0x3100)) | {0x30FC}
CJK = lambda c: 0x4E00 <= ord(c) <= 0x9FFF          # noqa: E731
HIRA = lambda c: 0x3040 <= ord(c) <= 0x309F         # noqa: E731
KATA = lambda c: 0x30A0 <= ord(c) <= 0x30FF         # noqa: E731


def ratio(s: str, pred) -> float:
    letters = [c for c in s if not c.isspace() and not unicodedata.category(c).startswith("P")]
    if not letters:
        return 0.0
    return sum(1 for c in letters if pred(c)) / len(letters)


def main() -> int:
    path = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "data/minna_tests.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    problems: list[str] = []
    warn: list[str] = []
    total = 0

    for les in data["lessons"]:
        num = les["lesson"]
        for sec in les["sections"]:
            title, kind = sec["title"], sec["kind"]
            for it in sec["items"]:
                total += 1
                qid = it["id"]
                prompt = it.get("prompt", "")
                ans = it.get("answer")
                if not prompt.strip():
                    problems.append(f"{qid}: 题干为空")
                if kind == "choice":
                    opts = it.get("options") or []
                    if len(opts) < 2:
                        problems.append(f"{qid}: 选项不足 ({len(opts)})")
                    elif any(not o.strip() for o in opts):
                        problems.append(f"{qid}: 有空白选项")
                    if ans is None:
                        if not les.get("no_answer"):
                            problems.append(f"{qid}: 选择题没有答案")
                    elif not (1 <= ans <= len(opts)):
                        problems.append(f"{qid}: 答案 {ans} 越界 (共 {len(opts)} 项)")
                    continue
                ans = ans or ""
                if "汉字改为平假名" in title:
                    if ratio(prompt, CJK) < 0.3:
                        warn.append(f"{qid}: 题干不像汉字 ({prompt})")
                    if ans and ratio(ans, HIRA) < 0.85:
                        problems.append(f"{qid}: 答案不像平假名 ({ans})")
                elif "假名改为汉字" in title:
                    if ratio(prompt, lambda c: HIRA(c) or KATA(c)) < 0.6:
                        warn.append(f"{qid}: 题干不像假名 ({prompt})")
                    if ans and ratio(ans, CJK) < 0.4:
                        problems.append(f"{qid}: 答案不像汉字 ({ans})")
                elif "译成汉语" in title:
                    if ans and (ratio(ans, CJK) < 0.5 or ratio(ans, lambda c: HIRA(c) or KATA(c)) > 0.3):
                        problems.append(f"{qid}: 译文不像汉语 ({ans})")
                elif "译成日语" in title:
                    if ans and (ratio(ans, lambda c: HIRA(c) or KATA(c)) < 0.15
                                and ratio(ans, CJK) > 0.9):
                        problems.append(f"{qid}: 译文不像日语 ({ans})")
                if not ans.strip() and not les.get("no_answer"):
                    problems.append(f"{qid}: 答案为空")

    # 残留的可疑字形 (GLYPH_FIX 里的错字一个都不该剩下)
    blob = json.dumps(data, ensure_ascii=False)
    residual = {}
    for ch in "佒癿丌夗夘斱叵庨飡飠叱迚朊忚叴忛昢昡兊亍皀纭":
        if ch in blob:
            residual[ch] = blob.count(ch)
    if residual:
        problems.append(f"仍有错字残留: {residual}")

    print(f"题数 {total}, 课数 {len(data['lessons'])}")
    print(f"问题 {len(problems)} 条, 提示 {len(warn)} 条")
    for p in problems[:30]:
        print("  ✗", p)
    for w in warn[:10]:
        print("  ·", w)
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
