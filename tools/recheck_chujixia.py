"""对验证不一致的题做一次"带上下文"的复核.

第一轮验证只给了题干和选项, 阅读题 (七) 没有文章, 模型当然答不对。
这里按题定位到原文: 阅读题补上文章, 其他题补上该大题前后的上下文,
再让模型答一次。仍然不一致的, 基本就是**题库数据本身有问题**。
"""
from __future__ import annotations

import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import llm  # noqa: E402
from tools.build_chujixia_ai import split_lessons, TXT  # noqa: E402

BANK = ROOT / "data" / "exams" / "shinbunpo-2.json"
VER = ROOT / "data" / "ocr" / "chujixia_verify.json"
OUT = ROOT / "data" / "ocr" / "chujixia_recheck.json"

CN = "一二三四五六七"

SYSTEM = """你在做日语试卷的题目, 会给你一段原文(可能为空)、题目和选项。

只回答正确选项的序号(1 起)。输出 JSON: {"answers": {"题号": 序号}}"""


def section_text(body: str, letter: str) -> str:
    """取某一课里某个大题的原始文本(题目部分)."""
    idx = body.find(f"{letter}、")
    if idx < 0:
        idx = body.find(f"{letter}，")
    if idx < 0:
        return ""
    # 到下一个大题或答案段为止
    rest = body[idx:]
    for nxt in CN:
        if nxt == letter:
            continue
        pos = rest.find(f"{nxt}、", 3)
        if pos > 0:
            rest = rest[:pos]
    # 砍掉答案段 (以"第N課 一、"开头的那种)
    for marker in ("第", "\n一、 1", "\n一、1"):
        p = rest.find(marker)
        if p > 0:
            rest = rest[:p]
    return rest.strip()


def main() -> int:
    bank = json.loads(BANK.read_text(encoding="utf-8"))
    ver = json.loads(VER.read_text(encoding="utf-8"))
    lessons = dict(split_lessons(TXT.read_text(encoding="utf-8")))

    by_id = {it["id"]: (les, sec, it)
             for les in bank["lessons"] for sec in les["sections"]
             for it in sec["items"]}

    bad = ver["bad"]
    print(f"复核 {len(bad)} 题")

    lines, metas = [], []
    for k, b in enumerate(bad):
        les, sec, it = by_id[b["id"]]
        letter = sec["title"][:1]
        ctx = ""
        if letter == "七":
            raw = section_text(lessons[les["lesson"]], "七")
            # 文章 = 题干之前的那段
            pos = raw.find(str(it["prompt"])[:10])
            ctx = raw[:pos].strip() if pos > 0 else raw[:400]
        opts = " / ".join(f"{i+1}.{o}" for i, o in enumerate(it["options"]))
        lines.append(f"{k}|{ctx[-600:] if ctx else '（无原文）'}|{it['prompt']}|{opts}")
        metas.append(b)

    cfg = llm.load_config()
    url = cfg["base_url"].rstrip("/") + "/chat/completions"
    payload = {
        "model": cfg["model"],
        "messages": [{"role": "system", "content": SYSTEM},
                     {"role": "user", "content": "\n".join(lines)}],
        "response_format": {"type": "json_object"},
        "temperature": 0,
        "stream": False,
    }
    data = llm._post(url, payload, cfg["api_key"], timeout=240)
    content = (data.get("choices") or [{}])[0].get("message", {}).get("content", "")
    got = llm._extract_json(content)
    ans = got.get("answers") if isinstance(got.get("answers"), dict) else got

    still = []
    for k, b in enumerate(metas):
        v = ans.get(str(k))
        try:
            n = int(str(v).strip()[0])
        except (ValueError, IndexError, TypeError):
            n = None
        if n == b["want"]:
            b["recheck"] = "ok"
        else:
            b["recheck"] = f"still {n}"
            still.append(b)

    OUT.write_text(json.dumps({"fixed": len(metas) - len(still), "still": still,
                               "all": metas}, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    print(f"带上下文复核后: 一致 {len(metas) - len(still)} 题, 仍不一致 {len(still)} 题")
    for b in still:
        print(f'  {b["id"]} 题库={b["want"]} 复核={b["recheck"]} {b["prompt"][:30]}')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
