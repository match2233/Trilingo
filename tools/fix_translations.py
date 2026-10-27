"""翻译题参考译文的质检：让模型只凭语感判断"这个参考译文是否自然准确".

题库里的参考译文多数是当年从答案段抄来的，其中有些明显生硬（比如把
「冬休み、いつ…」写成「冬休みに いつ…」）。这里逐条让模型给出它自己的
译法，并判"参考译文能不能用"，不能用的直接替换。
"""
from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import llm  # noqa: E402

BATCH = 10
SYS = """你在校对日语教材翻译题的参考答案。

每题给你：原句、方向、现有参考译文。
请只凭语言本身判断（不要考虑"课本怎么写"）：
1. 现有参考译文是否自然、准确、无语法错？
2. 如果不自然或不准确，给出你认为更好的译文。

输出 JSON:
{"items":{"序号":{"ok":true/false,"better":"更好的译文(ok 时留空)"}}}"""


def call(lines: list[str]) -> dict:
    cfg = llm.load_config()
    url = cfg["base_url"].rstrip("/") + "/chat/completions"
    payload = {
        "model": cfg["model"],
        "messages": [{"role": "system", "content": SYS},
                     {"role": "user", "content": "\n".join(lines)}],
        "response_format": {"type": "json_object"},
        "temperature": 0,
        "stream": False,
    }
    data = llm._post(url, payload, cfg["api_key"], timeout=240)
    content = (data.get("choices") or [{}])[0].get("message", {}).get("content", "")
    obj = llm._extract_json(content)
    got = obj.get("items") if isinstance(obj.get("items"), dict) else obj
    return got if isinstance(got, dict) else {}


def main() -> int:
    banks = {
        "upper": ROOT / "data" / "minna_tests.json",
        "lower": ROOT / "data" / "exams" / "shinbunpo-2.json",
    }
    for name, path in banks.items():
        d = json.loads(path.read_text(encoding="utf-8"))
        items = []
        for les in d["lessons"]:
            for s in les["sections"]:
                if s["kind"] != "translate":
                    continue
                direction = "cn" if "汉语" in (s.get("title") or "") else "jp"
                for it in s["items"]:
                    items.append((les["lesson"], it, direction))
        print(f"{name}: {len(items)} 条翻译")

        changed = 0
        for i in range(0, len(items), BATCH):
            chunk = items[i:i + BATCH]
            lines = []
            for k, (_no, it, direction) in enumerate(chunk):
                lines.append(f'{k}|{"中译日" if direction=="jp" else "日译中"}|'
                             f'{it["prompt"]}|{it.get("answer")}')
            try:
                got = call(lines)
            except Exception as exc:      # noqa: BLE001
                print(f"  批次 {i} 失败: {exc}")
                continue
            for k, (no, it, _dir) in enumerate(chunk):
                rec = got.get(str(k))
                if not isinstance(rec, dict):
                    continue
                better = str(rec.get("better") or "").strip()
                if not rec.get("ok") and better and better != str(it.get("answer")):
                    it.setdefault("alt", [])
                    if it.get("answer") and it["answer"] not in it["alt"]:
                        it["alt"].append(it["answer"])
                    it["answer"] = better
                    changed += 1
            print(f"  {min(i+BATCH, len(items))}/{len(items)} 改 {changed} 条")

        path.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"{name}: 共修改 {changed} 条参考译文")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
