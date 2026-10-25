"""把 assemble_questions.py 的产出 + 答案表, 组装成一个试卷集的 lesson.

用法:
    python tools/build_exam_bank.py --questions q2016.json --title 2016年 \
        --collection jlpt-n5 --paper 1 --minutes 105 --answers answers.json \
        --out data/exams/jlpt-n5.json
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import exams  # noqa: E402

META = {
    "jlpt-n5": {"id": "jlpt-n5", "name": "JLPT-N5", "kind": "jlpt",
                "desc": "日语能力考 N5 真题", "duration_min": 105, "order": 20},
}


def load_answers(path: str) -> dict[int, int]:
    """答案文件: {"1": 4, "2": 2, ...} 或 {"answers": {...}}。"""
    if not path:
        return {}
    data = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    if isinstance(data.get("answers"), dict):
        data = data["answers"]
    out = {}
    for k, v in data.items():
        try:
            out[int(k)] = int(v)
        except (TypeError, ValueError):
            continue
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--questions", required=True)
    ap.add_argument("--title", default="")
    ap.add_argument("--collection", default="jlpt-n5")
    ap.add_argument("--paper", type=int, default=1)
    ap.add_argument("--minutes", type=int, default=105)
    ap.add_argument("--answers", default="")
    ap.add_argument("--out", default="")
    ap.add_argument("--size", type=int, default=10, help="每个大题多少题")
    ap.add_argument("--append", action="store_true",
                    help="追加到已存在的这套卷子, 而不是覆盖")
    args = ap.parse_args()

    qs = json.loads(pathlib.Path(args.questions).read_text(encoding="utf-8"))
    qs = qs.get("questions") or []
    answers = load_answers(args.answers)

    used: list[dict] = []
    missing = 0
    for idx, q in enumerate(qs, start=1):
        no = int(q["no"])
        # 答案按题目顺序给 (题号跨页重复, 不可靠); 兼容老的按题号给的答案表
        ans = answers.get(idx, answers.get(no) if len(answers) > len(qs) else None)
        if answers and ans is None:
            missing += 1
            continue
        prompt = q["prompt"]
        if q.get("passage"):
            # 読解: 把文章放在题干前面, 用分隔标记, 界面照常换行显示
            prompt = f'【文章】{q["passage"]}\n【問】{prompt}'
        rec = {"no": no, "prompt": prompt, "options": q["options"],
               "answer": ans}
        if q.get("image"):
            rec["image"] = q["image"]
        used.append(rec)

    sections = []
    for i in range(0, len(used), args.size):
        chunk = used[i:i + args.size]
        lo, hi = chunk[0]["no"], chunk[-1]["no"]
        sections.append({
            "no": len(sections) + 1,
            "title": f"第 {lo}–{hi} 题" if lo != hi else f"第 {lo} 题",
            "kind": "choice",
            "items": [{
                "id": f"Q{args.paper:02d}-S{len(sections) + 1}-{j + 1}",
                "prompt": it["prompt"],
                "options": it["options"],
                "answer": it["answer"],
                **({"image": it["image"]} if it.get("image") else {}),
            } for j, it in enumerate(chunk)],
        })

    lesson = {"lesson": args.paper, "title": args.title or f"第 {args.paper} 套",
              "duration_min": args.minutes, "sections": sections}

    out = pathlib.Path(args.out) if args.out else exams.save_path(args.collection)
    bank = {"version": 2, "meta": META.get(args.collection,
                                           {"id": args.collection,
                                            "name": args.collection,
                                            "kind": "jlpt",
                                            "duration_min": args.minutes}),
            "lessons": []}
    if out.exists():
        try:
            bank = json.loads(out.read_text(encoding="utf-8"))
        except Exception:      # noqa: BLE001
            pass
    bank.setdefault("meta", META.get(args.collection, {"id": args.collection}))
    lessons = [l for l in bank.get("lessons") or [] if l.get("lesson") != args.paper]
    if args.append:
        old = [l for l in bank.get("lessons") or [] if l.get("lesson") == args.paper]
        if old:
            base = old[0]
            off = len(base["sections"])
            for s in sections:
                s["no"] = s["no"] + off
                for j, it in enumerate(s["items"], start=1):
                    it["id"] = f"Q{args.paper:02d}-S{s['no']}-{j}"
            lesson = dict(base)
            lesson["sections"] = base["sections"] + sections
    lessons.append(lesson)
    lessons.sort(key=lambda l: l["lesson"])
    bank["lessons"] = lessons
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(bank, ensure_ascii=False, indent=1), encoding="utf-8")

    total = sum(len(s["items"]) for s in sections)
    print(f"写入 {out}: 第 {args.paper} 套「{lesson['title']}」{total} 题, "
          f"{len(sections)} 个大题" + (f", 因缺答案跳过 {missing} 题" if missing else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
