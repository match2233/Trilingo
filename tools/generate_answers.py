"""用 AI 给四选一题目生成答案 (没有答案文件时的降级路径).

一次发 15 题给模型, 让它只回序号; 严格校验 1-4 的范围。
用法:
    python tools/generate_answers.py questions.json --out answers.json
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import llm  # noqa: E402

BATCH = 15

SYSTEM = """你在做日语能力考（JLPT）N5 的四选一题目, 只需给出正确选项的序号。

规则:
1. 每题恰好一个答案, 序号 1-4。
2. 题目可能有 OCR 残留错误, 按语义理解即可, 不要因此拒答。
3. 只输出 JSON: {"answers": {"题号": 序号, ...}}, 不要解释。"""


def ask(batch: list[dict]) -> dict:
    lines = []
    for q in batch:
        opts = "  ".join(f"{i + 1}.{o}" for i, o in enumerate(q["options"]))
        lines.append(f'题号 {q["no"]}：{q["prompt"]}  选项：{opts}')
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
    data = llm._post(url, payload, cfg["api_key"], timeout=120)
    content = (data.get("choices") or [{}])[0].get("message", {}).get("content", "")
    obj = llm._extract_json(content)
    got = obj.get("answers") if isinstance(obj.get("answers"), dict) else obj
    return got if isinstance(got, dict) else {}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("questions")
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    data = json.loads(pathlib.Path(args.questions).read_text(encoding="utf-8"))
    qs = data.get("questions") or []
    answers: dict[int, int] = {}
    for i in range(0, len(qs), BATCH):
        batch = qs[i:i + BATCH]
        try:
            got = ask(batch)
        except Exception as exc:      # noqa: BLE001
            print(f"  第 {i // BATCH + 1} 批失败: {exc}")
            continue
        for q, item in enumerate(batch, start=i + 1):
            # 用**题目在列表里的位置**当键: 卷面题号跨页会重复 (两页都从 1 开始),
            # 按题号映射答案会串位 —— 实测 2012 卷就这样把答案全错开了。
            v = got.get(str(item["no"]), got.get(item["no"]))
            try:
                n = int(str(v).strip()[0])
            except (ValueError, IndexError, TypeError):
                continue
            if 1 <= n <= 4:
                answers[q] = n
        print(f"  第 {i // BATCH + 1} 批: 累计 {len(answers)}/{len(qs)}")

    out = pathlib.Path(args.out) if args.out else pathlib.Path(args.questions).with_name(
        pathlib.Path(args.questions).stem + ".answers.json")
    out.write_text(json.dumps({"answers": {str(k): v for k, v in answers.items()}},
                              ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"写入 {out}: {len(answers)}/{len(qs)} 题有答案")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
