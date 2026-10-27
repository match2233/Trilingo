"""用模型把《新标日初级下》每一课的原始文本结构化, 生成题库.

为什么不用正则: 这份 .doc 的排版很乱 —— 一课的七个大题挤在一两段里,
大题标记有时写成 "二，"、有时紧跟在小题后面, 选项还会被吞掉。
实测正则切分会让 20+20+10+10+5+5+5 的题量变成 "一、67 题"。
模型读得懂这种排版, 让它按固定 schema 输出更可靠。

用法:
    python tools/build_chujixia_ai.py [--lessons 25 26] [--out data/exams/shinbunpo-2.json]
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

TXT = ROOT / "data" / "import" / "chujixia.txt"   # 由 docx 转出的纯文本
TITLE_RE = re.compile(r"第\s*([0-9]{2})\s*[课課]")
CN_NUM = "一二三四五六七八九十"

SYSTEM = """你在把《新版中日交流标准日本语（初级下）同步测试卷》的文本整理成结构化题库。

输入是某一课的原始文本：先题目、后答案，排版很乱（大题挤在一起、编号写法不一）。
请输出这一课全部大题与小题的 JSON：

{"sections":[
  {"letter":"一","kind":"fill","items":[{"no":1,"prompt":"女優","answer":"じょゆう"}]},
  {"letter":"三","kind":"choice","items":[{"no":1,"prompt":"＿＿買ったCDを彼女にあげました。",
      "options":["フランスに","フランスで","フランスが","フランスへ"],"answer":4}]}
]}

规则：
1. `kind` 只有三种：`fill`（填假名/汉字，无选项）、`choice`（四选一）、`translate`（翻译）。
2. `choice` 的选项按原文 ①②③④ 顺序原样输出；`answer` 写 1-N（N=选项个数）。
   多数选择题是 4 个选项，但**阅读题（七）常只有 3 个**，这时就输出 3 个。
3. `fill` 的 `prompt` 是词本身，`answer` 是答案词；`translate` 的 `prompt` 是原句，
   `answer` 是参考答案。
4. 题目和答案要一一对应：答案段里的 `一、1．じょゆう 2．こんや…` 属于第几题，
   就填到第几题。答案缺失的题 `answer` 留空字符串。
5. 不要臆造题目；原文里没有的题不要出现。`letter` 用 一/二/三/四/五/六/七。
6. **七（阅读）有两种题型，务必分清**：
   a) 三选一/四选一：题号后面跟着 ①②③④ 选项 → `kind: choice`；
   b) 正误判断（`在正确答案数字号上画○`，题号后是 5 个陈述句、**没有选项**）：
      答案段写成 `七、1. 2. 5`，表示第 1、2、5 句是对的。
      这种请输出 `kind: choice`，每题 `options: ["○","×"]`，
      出现在答案列表里的写 `"answer": 1`（○），没出现的写 `"answer": 2`（×）。
7. 只输出 JSON。"""


def split_lessons(text: str) -> list[tuple[int, str]]:
    """按标题把全文切成 [(课号, 该课全文)]."""
    paras = [p.strip() for p in text.split("\n")]
    lessons, cur_no, cur = [], None, []
    for p in paras:
        if not p:
            continue
        m = TITLE_RE.search(p)
        if m and len(p) < 60:
            if cur_no is not None:
                lessons.append((cur_no, "\n".join(cur)))
            cur_no, cur = int(m.group(1)), []
            continue
        if cur_no is not None:
            cur.append(p)
    if cur_no is not None:
        lessons.append((cur_no, "\n".join(cur)))
    return lessons


def ask_lesson(no: int, body: str) -> list[dict]:
    cfg = llm.load_config()
    url = cfg["base_url"].rstrip("/") + "/chat/completions"
    payload = {
        "model": cfg["model"],
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": f"第 {no} 课的原始文本：\n\n{body}"},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0,
        "stream": False,
    }
    data = llm._post(url, payload, cfg["api_key"], timeout=180)
    content = (data.get("choices") or [{}])[0].get("message", {}).get("content", "")
    obj = llm._extract_json(content)
    secs = obj.get("sections")
    return secs if isinstance(secs, list) else []


def validate(secs: list[dict]) -> tuple[list[dict], list[str]]:
    """清洗: 只留合法题, 记录丢弃原因."""
    out, problems = [], []
    for s in secs:
        letter = str(s.get("letter") or "").strip()[:1]
        kind = str(s.get("kind") or "").strip()
        if letter not in CN_NUM or kind not in ("fill", "choice", "translate"):
            problems.append(f"跳过非法大题 {letter}/{kind}")
            continue
        items = []
        for it in s.get("items") or []:
            prompt = str(it.get("prompt") or "").strip()
            ans = it.get("answer")
            if not prompt:
                problems.append(f"{letter}: 空题干")
                continue
            if kind == "choice":
                opts = [str(o).strip() for o in (it.get("options") or [])]
                # 阅读题常只有 3 个选项, 判断题是 ○/× 两个 —— 2-4 个都收
                if not 2 <= len(opts) <= 4 or any(not o for o in opts):
                    problems.append(f"{letter}-{it.get('no')}: 选项 {len(opts)} 个")
                    continue
                try:
                    a = int(ans)
                except (TypeError, ValueError):
                    problems.append(f"{letter}-{it.get('no')}: 答案 {ans!r} 非数字")
                    continue
                if not 1 <= a <= len(opts):
                    problems.append(f"{letter}-{it.get('no')}: 答案 {a} 越界(共{len(opts)})")
                    continue
                items.append({"prompt": prompt, "options": opts, "answer": a})
            else:
                items.append({"prompt": prompt, "options": [],
                              "answer": str(ans or "").strip()})
        if items:
            out.append({"letter": letter, "kind": kind, "items": items})
    return out, problems


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lessons", nargs="*", type=int, default=None)
    ap.add_argument("--out", default=str(ROOT / "data" / "ocr" / "chujixia_ai.json"))
    a = ap.parse_args()

    text = TXT.read_text(encoding="utf-8")
    lessons = split_lessons(text)
    print(f"共 {len(lessons)} 课:", [n for n, _ in lessons])

    result, all_problems = [], []
    for no, body in lessons:
        if a.lessons and no not in a.lessons:
            continue
        try:
            secs = ask_lesson(no, body)
        except Exception as exc:      # noqa: BLE001
            print(f"  第{no}课 失败: {exc}")
            continue
        cleaned, problems = validate(secs)
        n = sum(len(s["items"]) for s in cleaned)
        kinds = {s["letter"]: (s["kind"], len(s["items"])) for s in cleaned}
        print(f"  第{no}课: {n} 题 {kinds}")
        for p in problems[:6]:
            print("     !", p)
        all_problems += [f"第{no}课 {p}" for p in problems]
        result.append({"lesson": no, "sections": cleaned})

    out = pathlib.Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"lessons": result, "problems": all_problems},
                              ensure_ascii=False, indent=1), encoding="utf-8")
    print("已写", out, "总题数",
          sum(len(s["items"]) for l in result for s in l["sections"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
