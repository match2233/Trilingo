"""把 OCR 出来的行, 用 AI 组装成四选一题目.

为什么不用正则: 题号常被读成 ã2/ê5/30(其实是 3O), 短假名选项会被 OCR 合成
一行, 题干与选项的行距也不固定 —— 版面分析很难写死。模型能"看懂"版式,
让它按 4 选 1 的结构把行重排出来, 再严格校验, 比规则稳。

用法:
    python tools/assemble_questions.py <ocr.json> --out <questions.json> [--pages 1-8]
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

SYSTEM = """你在把日语能力考（JLPT）试卷的 OCR 结果**还原成题目**。

输入是一页试卷按阅读顺序排好的文字行（可能带 OCR 错误）。请把这一页里
**所有四选一题目**还原出来，输出 JSON：

{"questions":[{"no":1,"prompt":"題干","options":["A","B","C","D"],"figure":false}]}

规则：
1. 每题必须有 **恰好 4 个选项**；凑不齐 4 个的题**不要输出**。
2. `no` 用卷面上的题号；看不清就按出现顺序给连续编号（从 1 开始）。
3. `prompt` 是题干（可以含括号空位「（　）」），**不要**把选项混进题干。
4. 选项**必须按卷面顺序原样输出**（第 1 个就是 1、第 2 个就是 2…）：
   不要重排、不要按长短排序、不要改写、不要翻译。答案表是按这个顺序给的，
   一动顺序答案就全错了。
5. 明显是 OCR 错误的假名（如「さんぼ」应为「さんぽ」、「話きせて」应为
   「話させて」）可以顺手改正；**拿不准就保留原样**。
6. 阅读题的大段文章不要当题干；如果这一页只有文章没有题目，输出
   {"questions":[]}。
7. `figure`: 这道题是否**配了插图/照片/图表**（题面里有图、或题目要求看图作答）
   才填 true；纯文字题填 false。不要凭"絵/図"这类词猜。
8. 只输出 JSON，不要解释。"""


def page_text(page: dict) -> str:
    lines = sorted(page["lines"], key=lambda r: (r["y"], r["x"]))
    out = []
    for ln in lines:
        out.append(f'y{ln["y"]:>4} x{ln["x"]:>4}  {ln["text"]}')
    return "\n".join(out)


READING_SYSTEM = """你在把日语能力考（JLPT）**読解部分**的 OCR 结果还原成题目。

这一页可能有文章（本文）和若干道四选一题。请输出：
{"questions":[{"no":1,"passage":"文章","prompt":"第几問的题目","options":["A","B","C","D"]}]}

规则：
1. 每题恰好 4 个选项；凑不齐的不要输出。
2. `passage` 填这道题对应的文章（同一篇文章的多道题，passage 可以重复填）。
   文章原样照抄 OCR，**不要改写、不要翻译**；太长可以只保留与题目相关的部分。
3. `prompt` 只写问题本身（如「この文章によると、…はどれですか」）。
4. 只在**确实是阅读题**时才输出；只有文章没有问题就输出 {"questions":[]}。
5. 只输出 JSON。"""


def ask(page: dict, mode: str = "normal") -> list[dict]:
    cfg = llm.load_config()
    url = cfg["base_url"].rstrip("/") + "/chat/completions"
    payload = {
        "model": cfg["model"],
        "messages": [
            {"role": "system", "content": READING_SYSTEM if mode == "reading" else SYSTEM},
            {"role": "user", "content": f"第 {page['page']} 页：\n\n{page_text(page)}"},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0,
        "stream": False,
    }
    data = llm._post(url, payload, cfg["api_key"], timeout=120)
    content = (data.get("choices") or [{}])[0].get("message", {}).get("content", "")
    obj = llm._extract_json(content)
    qs = obj.get("questions")
    return qs if isinstance(qs, list) else []


KANA = re.compile(r"[\u3040-\u30ff]")


def valid(q: dict) -> tuple[bool, str]:
    opts = q.get("options")
    prompt = str(q.get("prompt") or "").strip()
    if not isinstance(opts, list) or len(opts) != 4:
        return False, f"选项 {len(opts) if isinstance(opts, list) else '?'} 个"
    opts = [str(o).strip() for o in opts]
    if any(not o for o in opts):
        return False, "有空选项"
    if len(set(opts)) < 4:
        return False, "选项重复"
    if len(prompt) < 2:
        return False, "题干为空"
    if not (KANA.search(prompt) or KANA.search("".join(opts))):
        return False, "没有假名"
    return True, ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("ocr")
    ap.add_argument("--out", default="")
    ap.add_argument("--pages", default="")
    ap.add_argument("--mode", default="normal", choices=("normal", "reading"))
    args = ap.parse_args()

    data = json.loads(pathlib.Path(args.ocr).read_text(encoding="utf-8"))
    pages = data["items"]
    if args.pages:
        a, _, b = args.pages.partition("-")
        lo, hi = int(a), int(b or a)
        pages = [p for p in pages if lo <= p["page"] <= hi]

    got, dropped = [], []
    seq = 0
    for page in pages:
        try:
            qs = ask(page, args.mode)
        except Exception as exc:      # noqa: BLE001
            print(f"  第 {page['page']} 页失败: {exc}")
            continue
        kept = 0
        for q in qs:
            ok, why = valid(q)
            if not ok:
                dropped.append({"page": page["page"], "why": why, "q": q})
                continue
            no = q.get("no")
            seq += 1
            got.append({
                "no": int(no) if isinstance(no, int) or str(no).isdigit() else seq,
                "page": page["page"],
                "prompt": str(q["prompt"]).strip(),
                "options": [str(o).strip() for o in q["options"]],
                "figure": bool(q.get("figure")),
                **({"passage": str(q["passage"]).strip()} if q.get("passage") else {}),
            })
            kept += 1
        print(f"  第 {page['page']} 页: 收 {kept} / {len(qs)}")

    print(f"\n共 {len(got)} 题, 丢弃 {len(dropped)}")
    for d in dropped[:6]:
        print(f"  × {d['why']}: {str(d['q'].get('prompt'))[:30]}")

    if args.out:
        out = pathlib.Path(args.out)
        out.write_text(json.dumps({"questions": got, "dropped": dropped},
                                  ensure_ascii=False, indent=1), encoding="utf-8")
        print("已写入", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
