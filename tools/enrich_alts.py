"""给「假名→汉字」的填空题补上可接受答案 (alt), 并记录有争议的选择题.

为什么需要: 「二、将假名用汉字填入」列的是**裸假名词**, 天然有同音歧义 ——
なか 可以是 中/仲, かう 可以是 買う/飼う。课本按当课单词给答案, 但用户
（或 AI）写另一个同音词也是对的。把两者都记下来, 判分时不冤枉人。

输入: data/ocr/chujixia_verify.json 里第一轮验证的不一致清单。
输出: 直接改题库 JSON, 给 fill 题加 `alt`, 给争议选择题加 `note`。
"""
from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

BANK = ROOT / "data" / "exams" / "shinbunpo-2.json"
VER = ROOT / "data" / "ocr" / "chujixia_verify.json"

# 语法上两种都说得通的选择题, 标个备注提醒 (答案保持课本的)
AMBIGUOUS = {
    "のは": "「作るのが/のは楽しい」两种都成立，课本取「のは」",
    "ほとんど": "「ほとんど/たいてい この部屋を使います」都可，课本取「ほとんど」",
}


def main() -> int:
    bank = json.loads(BANK.read_text(encoding="utf-8"))
    ver = json.loads(VER.read_text(encoding="utf-8"))
    by = {it["id"]: it for les in bank["lessons"]
          for sec in les["sections"] for it in sec["items"]}

    added_alt = 0
    noted = 0
    for b in ver["bad"]:
        it = by.get(b["id"])
        if not it:
            continue
        model = str(b["model"] or "").strip()
        if b["letter"] == "二" and model and model != it["answer"]:
            alts = it.setdefault("alt", [])
            if model not in alts and model != it["answer"]:
                alts.append(model)
                added_alt += 1
        elif b["letter"] == "选":
            want_opt = it["options"][it["answer"] - 1] if it["options"] else ""
            if want_opt in AMBIGUOUS:
                it["note"] = AMBIGUOUS[want_opt]
                noted += 1

    BANK.write_text(json.dumps(bank, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"填空题补了 {added_alt} 个可接受答案, {noted} 道选择题加了歧义备注")
    sample = [it for les in bank["lessons"] for sec in les["sections"]
              for it in sec["items"] if it.get("alt")][:6]
    for it in sample:
        print(f'  {it["id"]} {it["prompt"]} -> {it["answer"]} / alt={it["alt"]}')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
