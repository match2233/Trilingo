"""按"语境"整段复查题库: 不再解析 PDF, 只看题目本身是否自洽.

和 check_minna_answers.py 的区别:
  * 那个是逐题核对答案对不对; 这个是**整段**发给模型 —— 同一大题的题干、
    选项、答案放在一起, 让它像老师通读一遍那样找问题:
      字形错乱 (力/カ、朋/服、戒/或 …)、假名拼写、题干与选项不匹配、
      没有正确答案 / 多个正确答案、对话轮次错乱 …
  * 按字段报问题 (prompt / options / answer), 便于分批校验后安全写回。

跑法:
    python tools/audit_minna_tests.py                # 全量, 只报告
    python tools/audit_minna_tests.py --lesson 1 2   # 只查几课
    python tools/audit_minna_tests.py --fix          # 校验通过后写回
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
REPORT = ROOT / "data" / "minna_audit_report.json"

_HIRA = lambda c: 0x3040 <= ord(c) <= 0x309F          # noqa: E731
_KATA = lambda c: 0x30A0 <= ord(c) <= 0x30FF          # noqa: E731
_CJK = lambda c: 0x4E00 <= ord(c) <= 0x9FFF           # noqa: E731
_KANA = lambda c: _HIRA(c) or _KATA(c) or ord(c) == 0x30FC   # noqa: E731

SYSTEM = """你是《新版中日交流标准日本语（初级上）同步测试卷》的审校老师。
我会把**一个大题**的题干、选项、答案整段给你，请像通读试卷一样找出问题。

重点找这几类错误（都来自原 PDF 的文字识别）：
1. **字形错乱**：形近字或假名被认错，例如
   力メラ(应为カメラ)、洋朋(洋服)、大極拳(太極拳)、戒(或)、
   三ケ月(三ヶ月)、朋を着て(服を着て)、きよく(きょく)。
2. **假名/汉字拼写错误**：长音、促音、浊音、小写拗音、送假名。
3. **题目本身不合理**：
   * 选择题的正确答案不在选项里，或有多个正确答案；
   * 题干与选项对不上（例如题干问"哪个"，选项却是地点）；
   * 对话的 A/B 轮次错乱、引号或标点明显缺失；
   * 填空题的答案与题干要求的词性/时态不符。
4. **答案与题干不符**：意思译反、漏译关键信息、答非所问。

判断题答一致性时请结合语境推理，不要只看表面形式。
**没有问题就不要报**，不要为了凑数挑细节（标点、空格差异不算问题）。

输出 JSON：
{"issues":[{"id":"L02-S3-3","field":"prompt|options|answer","why":"不超过25字的说明","fix":"修正后的内容"}]}
* field=options 时，fix 给出**完整的新选项数组**，例如 ["いつ","いつか","いつも"]，个数必须与原来一致。
* field=answer 时，选择题的 fix 给正确选项的序号（1、2、3…），其它题型给答案文本。
* field=prompt 时，fix 给完整题干（保持原来的语言：日语题干给日语）。"""

FIELD_OK = ("prompt", "options", "answer")


def ask(les_no: int, sec: dict) -> list[dict]:
    lines = []
    for it in sec["items"]:
        head = f'{it["id"]} | 题干：{it["prompt"]}'
        if sec["kind"] == "choice":
            opts = "  ".join(f"{i + 1}.{o}" for i, o in enumerate(it.get("options") or []))
            head += f" | 选项：{opts} | 题库答案：{it.get('answer')} 号"
        else:
            head += f' | 题库答案：{it.get("answer") or "（空）"}'
        lines.append(head)
    user = (f"第 {les_no} 课　大题 {sec['no']}：{sec['title']}"
            f"（题型：{sec['kind']}）\n\n" + "\n".join(lines) + "\n\n请整段审校。")
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
    data = llm._post(url, payload, cfg["api_key"], timeout=150)
    content = (data.get("choices") or [{}])[0].get("message", {}).get("content", "")
    obj = llm._extract_json(content)
    issues = obj.get("issues")
    return issues if isinstance(issues, list) else []


def script_class(text: str) -> str:
    """粗分语言: jp_kana / jp_mixed / zh。用来保证改完还是同一种语言。"""
    if not text:
        return "empty"
    kana = sum(1 for c in text if _KANA(c))
    han = sum(1 for c in text if _CJK(c))
    if kana and kana / max(kana + han, 1) > 0.35:
        return "jp"
    if han:
        return "zh"
    return "other"


def validate(sec: dict, it: dict, field: str, fix) -> tuple[bool, object, str]:
    """校验一条修正, 返回 (可用?, 处理后的值, 说明)."""
    if field == "options":
        if not isinstance(fix, list) or not all(isinstance(x, str) for x in fix):
            return False, None, "选项不是字符串数组"
        old = it.get("options") or []
        if len(fix) != len(old):
            return False, None, f"选项个数从 {len(old)} 变成 {len(fix)}"
        if any(not x.strip() for x in fix):
            return False, None, "有空选项"
        return True, fix, ""

    if not isinstance(fix, str) or not fix.strip():
        return False, None, "修正内容为空"
    fix = fix.strip()

    if field == "answer":
        if sec["kind"] == "choice":
            opts = it.get("options") or []
            m = re.search(r"[1-9]", fix)
            n = int(m.group(0)) if m else 0
            if not 1 <= n <= len(opts):
                # 也可能是直接给了选项文本
                for i, o in enumerate(opts, 1):
                    if o.strip() and o.strip() in fix:
                        return True, i, ""
                return False, None, "答案序号越界"
            return True, n, ""
        if "译成汉语" in sec["title"]:
            if any(_KANA(c) for c in fix):
                return False, None, "中文译文里混入假名"
        elif "译成日语" in sec["title"]:
            if not any(_KANA(c) for c in fix):
                return False, None, "日文译文里没有假名"
        elif "汉字改为平假名" in sec["title"]:
            body = [c for c in fix if not c.isspace()]
            if body and sum(1 for c in body if _HIRA(c)) / len(body) < 0.85:
                return False, None, "读音里混入汉字"
        elif "假名改为汉字" in sec["title"]:
            if not any(_CJK(c) for c in fix):
                return False, None, "答案里没有汉字"
        return True, fix, ""

    # field == "prompt"
    old = it["prompt"]
    if script_class(fix) != script_class(old):
        return False, None, f"题干语言变了({script_class(old)}→{script_class(fix)})"
    if not (0.6 <= len(fix) / max(len(old), 1) <= 1.6):
        return False, None, f"题干长度变化过大({len(old)}→{len(fix)})"
    return True, fix, ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lesson", type=int, nargs="*", default=None)
    ap.add_argument("--fix", action="store_true")
    args = ap.parse_args()

    data = json.loads(BANK.read_text(encoding="utf-8"))
    if not llm.is_configured():
        print("LLM 未配置", file=sys.stderr)
        return 1

    issues: list[dict] = []
    applied = 0
    rejected: list[dict] = []
    total_sec = 0
    for les in data["lessons"]:
        if args.lesson and les["lesson"] not in args.lesson:
            continue
        for sec in les["sections"]:
            total_sec += 1
            try:
                found = ask(les["lesson"], sec)
            except Exception as exc:      # noqa: BLE001
                print(f"  第{les['lesson']}课 大{sec['no']} 请求失败: {exc}")
                continue
            by_id = {it["id"]: it for it in sec["items"]}
            for f in found:
                qid = str(f.get("id", ""))
                field = str(f.get("field", "")).strip()
                if qid not in by_id or field not in FIELD_OK:
                    continue
                it = by_id[qid]
                ok, val, why = validate(sec, it, field, f.get("fix"))
                rec = {"lesson": les["lesson"], "section": sec["no"],
                       "id": qid, "field": field,
                       "why": str(f.get("why", ""))[:60],
                       "old": it["prompt"] if field == "prompt" else
                              (it.get("options") if field == "options" else it.get("answer")),
                       "fix": f.get("fix"), "ok": ok, "reject": why}
                if not ok:
                    rejected.append(rec)
                    continue
                issues.append(rec)
                mark = ""
                if args.fix:
                    if field == "prompt":
                        it["prompt"] = val
                    elif field == "options":
                        it["options"] = val
                    else:
                        it["answer"] = val
                    applied += 1
                    mark = "  ✔已改"
                print(f"  ! 第{les['lesson']}课 大{sec['no']} {qid} [{field}] "
                      f"{rec['why']}{mark}")
            print(f"· 第{les['lesson']}课 大{sec['no']} 完成 ({len(found)} 处)")

    print(f"\n审校 {total_sec} 个大题, 确认问题 {len(issues)} 处, "
          f"校验未通过 {len(rejected)} 处")
    REPORT.write_text(json.dumps({"issues": issues, "rejected": rejected},
                                 ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"报告: {REPORT}")
    if args.fix and applied:
        BANK.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"已写回题库 ({applied} 处)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
