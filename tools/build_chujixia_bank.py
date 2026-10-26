"""把结构化草稿 (chujixia_ai.json) 落成题库文件 data/exams/shinbunpo-2.json.

schema 与「新标日初级上」一致: meta + lessons[].sections[].items[]
item: {id, prompt, options, answer}
  * fill: options 为空, answer 是字符串
  * choice: options 2-4 个, answer 是 1-based 序号
  * translate: options 为空, answer 是参考译文
"""
from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

SRC = ROOT / "data" / "ocr" / "chujixia_ai.json"
DST = ROOT / "data" / "exams" / "shinbunpo-2.json"

META = {
    "id": "shinbunpo-2",
    "name": "新标日初级下单元测试",
    "kind": "unit",
    "desc": "16 课同步测试卷（第 25-40 课）",
    "duration_min": 0,
    "order": 11,
}

SEC_TITLE = {
    "一": "将下列汉字用平假名填入",
    "二": "将下划线部分的假名用汉字填入",
    "三": "选择正确答案",
    "四": "选择恰当答案",
    "五": "将下列句子译成汉语",
    "六": "将下列句子译成日语",
    "七": "阅读下列文章",
}


def main() -> int:
    data = json.loads(SRC.read_text(encoding="utf-8"))
    lessons = []
    total = 0
    for les in data["lessons"]:
        no = int(les["lesson"])
        sections = []
        for si, sec in enumerate(les["sections"], start=1):
            items = []
            for i, it in enumerate(sec["items"], start=1):
                items.append({
                    "id": f"L{no:02d}-S{si}-{i}",
                    "prompt": it["prompt"],
                    "options": it.get("options") or [],
                    "answer": it["answer"],
                })
            if not items:
                continue
            sections.append({
                "no": si,
                "title": f'{sec["letter"]}、{SEC_TITLE.get(sec["letter"], "")}',
                "kind": sec["kind"],
                "items": items,
            })
            total += len(items)
        lessons.append({"lesson": no, "title": f"第 {no} 课",
                        "duration_min": 0, "sections": sections})

    bank = {"version": 2, "meta": META, "lessons": lessons}
    DST.write_text(json.dumps(bank, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"写入 {DST}: {len(lessons)} 课 / {total} 题")

    # 自检
    from collections import Counter
    kinds = Counter(s["kind"] for l in lessons for s in l["sections"])
    print("题型分布:", dict(kinds))
    bad = [it["id"] for l in lessons for s in l["sections"]
           for it in s["items"] if not it["prompt"] or it["answer"] in ("", None)]
    print("空题干/空答案:", len(bad), bad[:5])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
