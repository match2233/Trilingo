"""按 check_minna_answers.py 的报告修正题库.

分三类处理:

1. **小写假名**: PDF 里「きょく」常被提取成「きよく」(大写的よ)。
   拗音前一拍一定是い段假名, 所以「い段 + や/ゆ/よ」应改成小写 —— 这条规则
   对平假名和片假名都成立, 全库统一处理。

2. **字形错乱**: PDF 的字体映射会把形近字换掉 (力メラ / 大極拳 / 洋朋 / 戒)。
   这类只能逐个列出来改, 见 PROMPT_FIX / ANSWER_FIX。

3. **答案本身错了**: 主要是选择题序号错位 (原卷题号不规整时对齐错了)。
   报告里模型给了 fix 的, 校验类型后写回。
"""
from __future__ import annotations

import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
BANK = ROOT / "data" / "minna_tests.json"
REPORT = ROOT / "data" / "minna_answer_report.json"

# 字形错乱: 题干/答案里的固定错字 (都经过逐条对照语义确认)
PROMPT_FIX = {
    "力メラ": "カメラ",
    "大極拳": "太極拳",
    "洋朋": "洋服",
    "木きい": "大きい",
    "にれから": "これから",
    "しよや": "しぶや",
    "朋を 着て": "服を 着て",
    "朋を着て": "服を着て",
    "三ケ月": "三ヶ月",
    "デパートトの前": "デパートの前",
    "問家": "回家",
    "戒": "或",
}

# 答案里的固定错字
ANSWER_FIX = {
    "からるい": "からい",
    "しむしょ": "じむしょ",
    "十点左史": "十点左右",
    "只年": "3年",
    "不肉相比": "与肉相比",
    "只万日元": "三万日元",
}

_HIRA = lambda c: 0x3040 <= ord(c) <= 0x309F          # noqa: E731
_KATA = lambda c: 0x30A0 <= ord(c) <= 0x30FF          # noqa: E731
_CJK = lambda c: 0x4E00 <= ord(c) <= 0x9FFF           # noqa: E731
_KANA = lambda c: _HIRA(c) or _KATA(c) or ord(c) == 0x30FC   # noqa: E731


def ratio_cjk(s: str) -> float:
    letters = [c for c in s if not c.isspace() and c not in "，。？！、；：“”‘’（）—…"]
    if not letters:
        return 0.0
    return sum(1 for c in letters if _CJK(c)) / len(letters)


def same_ish(a: str, b: str) -> bool:
    """两个字符串是否像"同一句的两种写法"(用来判断 fix 是不是在改题干)."""
    a, b = a.strip(), b.strip()
    if not a or not b:
        return False
    common = set(a) & set(b)
    return len(common) / max(len(set(a)), 1) >= 0.6


def pick_choice_index(fix: str, options: list[str]) -> int | None:
    """把模型的 fix 变成选项序号: 先找数字, 再按选项文本匹配."""
    m = re.search(r"[1-9]", fix)
    if m:
        n = int(m.group(0))
        if 1 <= n <= len(options):
            return n
    f = re.sub(r"[①②③④\s，。,.、]", "", fix)
    for i, opt in enumerate(options, 1):
        o = re.sub(r"[①②③④\s，。,.、]", "", str(opt))
        if not o:
            continue
        if f == o or (len(o) >= 2 and o in f and len(f) <= len(o) + 4):
            return i
    return None

# い段假名 + や/ゆ/よ 一定是拗音 (小写)
_I_DAN = set("きしちにひみりぎじびぴキシチニヒミリギジビピ")
_YOON = set("やゆよヤユヨ")


def smallen(text: str) -> str:
    out = list(text)
    for i in range(len(out) - 1):
        if out[i] in _I_DAN and out[i + 1] in _YOON:
            small = {"や": "ゃ", "ゆ": "ゅ", "よ": "ょ",
                     "ヤ": "ャ", "ユ": "ュ", "ヨ": "ョ"}[out[i + 1]]
            out[i + 1] = small
    return "".join(out)


def apply_prompt_fix(text: str) -> str:
    for bad, good in PROMPT_FIX.items():
        text = text.replace(bad, good)
    return text


def main() -> int:
    data = json.loads(BANK.read_text(encoding="utf-8"))
    report = []
    if REPORT.exists():
        report = json.loads(REPORT.read_text(encoding="utf-8"))
    by_id = {r["id"]: r for r in report}

    changed_prompt = changed_answer = changed_kana = 0
    for les in data["lessons"]:
        for sec in les["sections"]:
            title, kind = sec["title"], sec["kind"]
            for it in sec["items"]:
                rec = by_id.get(it["id"])
                fix = str(rec.get("fix") or "").strip() if rec else ""

                # 1) 题干错字: 只认手工核对过的 PROMPT_FIX 表。
                #    这里曾经按"报告给的 fix 看起来像在改题干"自动替换, 结果把
                #    日语题干换成了中文译文 (吉田さんは…→吉田是大学的教授吗？)、
                #    把假名题干换成了汉字答案 (ちいさい→小さい) —— 语义很像,
                #    语言却错了。所以自动替换一律不做。
                p = it["prompt"]
                np_ = apply_prompt_fix(p)
                if np_ != p:
                    it["prompt"] = np_
                    changed_prompt += 1

                ans = it.get("answer")

                # 2) 选择题: fix 必须是能确定的序号
                if kind == "choice":
                    if fix:
                        opts = it.get("options") or []
                        idx = pick_choice_index(fix, opts)
                        if idx and idx != ans:
                            it["answer"] = idx
                            changed_answer += 1
                    continue

                if not isinstance(ans, str):
                    continue

                # 3) 答案里的固定错字
                na = ans
                for bad, good in ANSWER_FIX.items():
                    if bad in na:
                        na = na.replace(bad, good)

                # 4) 报告给的 fix: 只有"类型对得上"才收
                if fix and fix != it["prompt"]:
                    if "汉字改为平假名" in title:
                        body = [c for c in fix if not c.isspace()]
                        if body and sum(1 for c in body if _HIRA(c)) / len(body) > 0.85:
                            na = fix
                    elif "假名改为汉字" in title:
                        if any(_CJK(c) for c in fix) and fix != ans:
                            na = fix
                    elif "译成汉语" in title:
                        if ratio_cjk(fix) > 0.7 and not any(_KANA(c) for c in fix):
                            na = fix
                    elif "译成日语" in title:
                        if any(_KANA(c) for c in fix) and ratio_cjk(fix) < 0.5:
                            na = fix

                if na != ans:
                    it["answer"] = na
                    changed_answer += 1

    BANK.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"题干修正 {changed_prompt} 处, 答案修正 {changed_answer} 处 "
          f"(其中小写假名 {changed_kana} 处)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
