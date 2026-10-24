"""用 LLM 抽查题库答案是否正确.

题库前 23 课来自原卷答案页, 但有两个已知风险:
  * PDF 字形映射错乱可能让题干或答案串行 (最典型是选项被合并)
  * 答案序号与选项如果对不齐, 整题就是错的

这个脚本按大题分批把 (题干, 选项, 答案) 交给模型核对, 让它指出有问题
的题并给出正确值。默认只报告, 加 --fix 才写回。

跑法:
    python tools/check_minna_answers.py                 # 全量检查
    python tools/check_minna_answers.py --lesson 1 2 3  # 只查几课
    python tools/check_minna_answers.py --fix           # 把确认错误的改掉
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

BANK = ROOT / "data" / "minna_tests.json"
BATCH = 12

SYSTEM = """你是《新版中日交流标准日本语（初级上）同步测试卷》的审校老师。

我会给你一组题目，每题都有题干、选项（选择题才有）和题库里记录的答案。
请逐题核对答案是否正确，只指出**确实有问题**的题：

* 填空题：答案的读音/汉字与题干不匹配，或明显不是该词的标日初级上写法。
* 选择题：正确答案与题干语义/语法不符，或答案序号压根超出选项范围。
* 翻译题：译文与原文意思不符，或语法错误。

允许的差异（判为正确，不要报）：
* 填空答案带不带送假名（楽しい / 楽）、标点与空格差异
* 翻译的措辞不同但意思一致

只输出 JSON：{"bad":[{"id":"L01-S3-2","why":"不超过20字的说明","fix":"正确值"}]}
没有问题时输出 {"bad":[]}。"""


def ask(sec_title: str, kind: str, items: list[dict]) -> list[dict]:
    lines = []
    for it in items:
        head = f'{it["id"]} | 题干：{it["prompt"]}'
        if kind == "choice":
            opts = "  ".join(f"{i + 1}.{o}" for i, o in enumerate(it.get("options") or []))
            head += f" | 选项：{opts}"
            head += f" | 题库答案：{it['answer']} 号"
        else:
            head += f" | 题库答案：{it.get('answer') or '（空）'}"
        lines.append(head)
    user = f"题型：{sec_title}\n\n" + "\n".join(lines) + "\n\n请核对。"
    cfg = llm.load_config()
    url = cfg["base_url"].rstrip("/") + "/chat/completions"
    payload = {
        "model": cfg["model"],
        "messages": [{"role": "system", "content": SYSTEM},
                     {"role": "user", "content": user}],
        "response_format": {"type": "json_object"},
        "temperature": 0,
        "stream": False,
    }
    data = llm._post(url, payload, cfg["api_key"], timeout=120)
    content = (data.get("choices") or [{}])[0].get("message", {}).get("content", "")
    obj = llm._extract_json(content)
    bad = obj.get("bad")
    return bad if isinstance(bad, list) else []


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lesson", type=int, nargs="*", default=None)
    ap.add_argument("--fix", action="store_true")
    ap.add_argument("--bank", default=str(BANK))
    args = ap.parse_args()

    path = pathlib.Path(args.bank)
    data = json.loads(path.read_text(encoding="utf-8"))
    if not llm.is_configured():
        print("LLM 未配置", file=sys.stderr)
        return 1

    issues: list[dict] = []
    checked = 0
    for les in data["lessons"]:
        if args.lesson and les["lesson"] not in args.lesson:
            continue
        for sec in les["sections"]:
            items = [it for it in sec["items"] if it.get("answer") not in (None, "")]
            for i in range(0, len(items), BATCH):
                batch = items[i:i + BATCH]
                try:
                    bad = ask(sec["title"], sec["kind"], batch)
                except Exception as exc:      # noqa: BLE001
                    print(f"  第{les['lesson']}课 大{sec['no']} 请求失败: {exc}")
                    continue
                checked += len(batch)
                by_id = {it["id"]: it for it in batch}
                for b in bad:
                    qid = str(b.get("id", ""))
                    if qid not in by_id:
                        continue
                    rec = {"lesson": les["lesson"], "section": sec["no"],
                           "kind": sec["kind"], "title": sec["title"],
                           "id": qid, "prompt": by_id[qid]["prompt"],
                           "answer": by_id[qid].get("answer"),
                           "why": str(b.get("why", ""))[:60],
                           "fix": b.get("fix")}
                    issues.append(rec)
                    fill = ""
                    if args.fix and rec["fix"] not in (None, ""):
                        new = rec["fix"]
                        if sec["kind"] == "choice":
                            m = re.search(r"[1-9]", str(new))
                            if not m:
                                continue
                            new = int(m.group(0))
                            if not 1 <= new <= len(by_id[qid].get("options") or []):
                                continue
                        by_id[qid]["answer"] = new
                        fill = f"  -> 改为 {new}"
                    print(f"  ! 第{les['lesson']}课 大{sec['no']} {qid} "
                          f"{rec['prompt'][:20]} | 原答案 {rec['answer']}{fill} | {rec['why']}")

    print(f"\n共核对 {checked} 题, 发现问题 {len(issues)} 题")
    report = ROOT / "data" / "minna_answer_report.json"
    report.write_text(json.dumps(issues, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"报告写入 {report}")
    if args.fix and issues:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        print("已写回题库")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
