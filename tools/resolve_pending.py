"""逐条判定"待人工确认"的题目, 并写回题库.

上一轮 audit 报出的 48 处属于"需要判断"的类型 (答案不唯一、多解、题干缺字…),
这个脚本对每一条单独提问, 要求模型给出**唯一结论**, 原则是:

  1. 优先只改**答案序号** —— 选项原样保留, 以教材语法判定唯一正确项;
  2. 只有某个选项本身是乱码/非日语词/与另一项重复时, 才修那个选项,
     且个数、顺序不变;
  3. 只有当题干缺字/多字到无解时, 才修题干, 且保持原语言与原意。

每处都做类型校验, 通过才写回。
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
PENDING = ROOT / "data" / "minna_audit_pending.json"

_HIRA = lambda c: 0x3040 <= ord(c) <= 0x309F          # noqa: E731
_KATA = lambda c: 0x30A0 <= ord(c) <= 0x30FF          # noqa: E731
_CJK = lambda c: 0x4E00 <= ord(c) <= 0x9FFF           # noqa: E731
_KANA = lambda c: _HIRA(c) or _KATA(c) or ord(c) == 0x30FC   # noqa: E731

SYSTEM = """你是《新版中日交流标准日本语（初级上）》的命题老师，正在校订一份
从 PDF 转录来的练习卷。每道题都会告诉你题干、选项、题库记录的答案，
以及之前审校提出的疑点。请给出**唯一结论**。

判定原则（按优先级）：
1. **只改答案序号**：如果四个选项都正常、只是答案录错了，就把 answer 改成
   教材语法下的唯一正确项（1 起始）。
2. 只有当某个选项本身是**乱码、非日语词、或与另一个选项重复**时，才改选项；
   必须保持选项个数与顺序不变，只替换有问题的那个。
3. 只有当题干**缺字/多字到无法作答**时，才修题干；保持原语言、原意，改动最小。
4. 如果复核后认为题目本身没有问题（疑点不成立），action 用 "none"。

输出 JSON：
{"action":"answer"|"options"|"prompt"|"none",
 "answer":2,
 "options":["…","…","…"],
 "prompt":"…",
 "why":"一句话说明"}
只需要给你实际改动的那一项，其余字段可省略。"""


def ask(les_no: int, sec: dict, it: dict, doubt: str) -> dict:
    opts = it.get("options") or []
    opt_txt = "  ".join(f"{i + 1}.{o}" for i, o in enumerate(opts)) or "（无选项）"
    user = (f"第 {les_no} 课　大题 {sec['no']}：{sec['title']}\n"
            f"题型：{sec['kind']}\n\n"
            f"题干：{it['prompt']}\n"
            f"选项：{opt_txt}\n"
            f"题库记录的答案：{it.get('answer')}\n"
            f"此前审校提出的疑点：{doubt}\n\n"
            "请复核并给出结论。")
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
    return llm._extract_json(content)


def script_of(t: str) -> str:
    if not t:
        return "empty"
    kana = sum(1 for c in t if _KANA(c))
    han = sum(1 for c in t if _CJK(c))
    if kana and kana / max(kana + han, 1) > 0.35:
        return "jp"
    return "zh" if han else "other"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--ids", nargs="*", default=None,
                    help="只处理这些题目 id")
    args = ap.parse_args()

    data = json.loads(BANK.read_text(encoding="utf-8"))
    pending = json.loads(PENDING.read_text(encoding="utf-8"))
    if args.ids:
        pending = [p for p in pending if p["id"] in set(args.ids)]
    # 同一条题可能被报了多次 (options + answer), 合并疑点
    doubts: dict[str, list[str]] = {}
    for p in pending:
        doubts.setdefault(p["id"], []).append(f"[{p['field']}] {p['why']}")

    index = {}
    for les in data["lessons"]:
        for sec in les["sections"]:
            for it in sec["items"]:
                index[it["id"]] = (les["lesson"], sec, it)

    applied, unchanged, rejected = [], [], []
    for qid, why_list in doubts.items():
        if qid not in index:
            continue
        les_no, sec, it = index[qid]
        doubt = "；".join(why_list)
        try:
            ans = ask(les_no, sec, it, doubt)
        except Exception as exc:      # noqa: BLE001
            rejected.append((qid, f"请求失败 {exc}"))
            continue
        action = str(ans.get("action", "none")).lower()
        note = str(ans.get("why", ""))[:60]
        if action == "none":
            unchanged.append((qid, note or "复核认为没问题"))
            continue

        if action == "answer":
            opts = it.get("options") or []
            new = ans.get("answer")
            if sec["kind"] == "choice":
                try:
                    n = int(re.sub(r"[^0-9]", "", str(new)) or 0)
                except ValueError:
                    n = 0
                if not 1 <= n <= len(opts):
                    rejected.append((qid, f"答案序号越界 {new!r}"))
                    continue
                if n == it.get("answer"):
                    unchanged.append((qid, "答案本来就是这一项"))
                    continue
                old = it.get("answer")
                if args.dry_run:
                    applied.append((qid, f"答案 {old}→{n}", note))
                    continue
                it["answer"] = n
                applied.append((qid, f"答案 {old}→{n}", note))
            else:
                # 填空/翻译: answer 是文本, 按题型校验语言
                if not isinstance(new, str) or not new.strip():
                    rejected.append((qid, "答案不是文本"))
                    continue
                new = new.strip()
                title = sec["title"]
                if "译成汉语" in title and any(_KANA(c) for c in new):
                    rejected.append((qid, "中文译文混入假名"))
                    continue
                if "译成日语" in title and not any(_KANA(c) for c in new):
                    rejected.append((qid, "日文译文没有假名"))
                    continue
                if "假名改为汉字" in title and not any(_CJK(c) for c in new):
                    rejected.append((qid, "答案没有汉字"))
                    continue
                if "汉字改为平假名" in title:
                    body = [c for c in new if not c.isspace()]
                    if body and sum(1 for c in body if _HIRA(c)) / len(body) < 0.85:
                        rejected.append((qid, "读音混入汉字"))
                        continue
                old = it.get("answer")
                if new == old:
                    unchanged.append((qid, "答案未变"))
                    continue
                if args.dry_run:
                    applied.append((qid, f"答案：{old} → {new}", note))
                    continue
                it["answer"] = new
                applied.append((qid, f"答案：{old} → {new}", note))

        elif action == "options":
            opts = it.get("options") or []
            new = ans.get("options")
            if not isinstance(new, list) or len(new) != len(opts) \
                    or not all(isinstance(x, str) and x.strip() for x in new):
                rejected.append((qid, "选项不合法"))
                continue
            if new == opts:
                unchanged.append((qid, "选项未变"))
                continue
            diff = [f"{i + 1}.{a}→{b}" for i, (a, b) in enumerate(zip(opts, new)) if a != b]
            if args.dry_run:
                applied.append((qid, "选项 " + ", ".join(diff), note))
                continue
            it["options"] = new
            applied.append((qid, "选项 " + ", ".join(diff), note))

        elif action == "prompt":
            new = ans.get("prompt")
            if not isinstance(new, str) or not new.strip():
                rejected.append((qid, "题干为空"))
                continue
            old = it["prompt"]
            if script_of(new) != script_of(old):
                rejected.append((qid, f"题干语言变了 {script_of(old)}→{script_of(new)}"))
                continue
            if not 0.5 <= len(new) / max(len(old), 1) <= 1.8:
                rejected.append((qid, "题干长度变化过大"))
                continue
            if new == old:
                unchanged.append((qid, "题干未变"))
                continue
            if args.dry_run:
                applied.append((qid, f"题干：{old} → {new}", note))
                continue
            it["prompt"] = new
            applied.append((qid, f"题干：{old} → {new}", note))
        else:
            rejected.append((qid, f"未知 action {action}"))

    print(f"\n改动 {len(applied)} 条, 复核后无需改 {len(unchanged)} 条, "
          f"校验未过 {len(rejected)} 条\n")
    for qid, what, note in applied:
        print(f"  ✔ {qid}　{what}　— {note}")
    for qid, note in unchanged:
        print(f"  · {qid} 不变：{note}")
    for qid, why in rejected:
        print(f"  ✗ {qid} 跳过：{why}")

    if args.dry_run:
        print("\n[dry-run] 未写回")
        return 0
    BANK.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\n题库已更新")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
