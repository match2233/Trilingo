"""把 audit_minna_tests.py 的报告写回题库.

只写回"字形/拼写"这一类的修正 (误识、形近字、送假名、浊音、长音、拗音…),
因为这类有明确的对错; "答案不唯一 / 两个选项都通顺"之类需要人判断的,
只列出来不自动改 —— 改错了比不改更害人。

跑法:
    python tools/apply_audit_fixes.py --dry-run
    python tools/apply_audit_fixes.py
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
BANK = ROOT / "data" / "minna_tests.json"
REPORT = ROOT / "data" / "minna_audit_report.json"

# 有明确对错的信号
FIXABLE = re.compile("误识|识别|字形|形近|错字|送假名|浊音|长音|拗音|拼写|"
                     "误认|乱码|OCR|认错|误写|误作|应为|改作|缺.*假名|漏写")
# 需要人来定的信号
SUBJECTIVE = re.compile("多解|唯一|也成句|重复|矛盾|不成句|两个正确|多个正确|"
                        "漏译|多译|不准确|不当|不自然")

_HIRA = lambda c: 0x3040 <= ord(c) <= 0x309F          # noqa: E731
_KATA = lambda c: 0x30A0 <= ord(c) <= 0x30FF          # noqa: E731
_CJK = lambda c: 0x4E00 <= ord(c) <= 0x9FFF           # noqa: E731
_KANA = lambda c: _HIRA(c) or _KATA(c) or ord(c) == 0x30FC   # noqa: E731


def script_of(t: str) -> str:
    if not t:
        return "empty"
    kana = sum(1 for c in t if _KANA(c))
    han = sum(1 for c in t if _CJK(c))
    if kana and kana / max(kana + han, 1) > 0.35:
        return "jp"
    return "zh" if han else "other"


def check(sec: dict, it: dict, field: str, fix) -> tuple[bool, object, str]:
    if field == "options":
        if not isinstance(fix, list) or len(fix) != len(it.get("options") or []):
            return False, None, "选项个数变了"
        if not all(isinstance(x, str) and x.strip() for x in fix):
            return False, None, "存在空选项"
        return True, fix, ""
    if not isinstance(fix, str) or not fix.strip():
        return False, None, "修正为空"
    fix = fix.strip()
    if field == "answer":
        if sec["kind"] == "choice":
            m = re.search(r"[1-9]", fix)
            n = int(m.group(0)) if m else 0
            if not 1 <= n <= len(it.get("options") or []):
                return False, None, "序号越界"
            return True, n, ""
        if "译成汉语" in sec["title"] and any(_KANA(c) for c in fix):
            return False, None, "中文里混入假名"
        if "译成日语" in sec["title"] and not any(_KANA(c) for c in fix):
            return False, None, "日文里没有假名"
        if "假名改为汉字" in sec["title"] and not any(_CJK(c) for c in fix):
            return False, None, "答案没有汉字"
        if "汉字改为平假名" in sec["title"]:
            body = [c for c in fix if not c.isspace()]
            if body and sum(1 for c in body if _HIRA(c)) / len(body) < 0.85:
                return False, None, "读音里混入汉字"
        return True, fix, ""
    # prompt
    old = it["prompt"]
    if script_of(fix) != script_of(old):
        return False, None, f"语言变了({script_of(old)}→{script_of(fix)})"
    if not 0.5 <= len(fix) / max(len(old), 1) <= 1.8:
        return False, None, "长度变化过大"
    return True, fix, ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    data = json.loads(BANK.read_text(encoding="utf-8"))
    rep = json.loads(REPORT.read_text(encoding="utf-8"))
    by_id = {}
    for les in data["lessons"]:
        for sec in les["sections"]:
            for it in sec["items"]:
                by_id[it["id"]] = (sec, it)

    applied, skipped, deferred = 0, [], []
    for iss in rep["issues"]:
        qid, field = iss["id"], iss["field"]
        if qid not in by_id:
            continue
        sec, it = by_id[qid]
        why = iss["why"]
        if SUBJECTIVE.search(why) and not re.search("误识|形近|送假名|错字|拼写|浊音|长音", why):
            deferred.append(iss)
            continue
        if not FIXABLE.search(why):
            deferred.append(iss)
            continue
        ok, val, why_rej = check(sec, it, field, iss.get("fix"))
        if not ok:
            skipped.append({**iss, "reject": why_rej})
            continue
        if args.dry_run:
            applied += 1
            continue
        if field == "prompt":
            it["prompt"] = val
        elif field == "options":
            it["options"] = val
        else:
            it["answer"] = val
        applied += 1

    print(f"写回 {applied} 处, 校验未通过 {len(skipped)} 处, 留待人工 {len(deferred)} 处")
    for s in skipped:
        print(f"  跳过 {s['id']} [{s['field']}] {s['reject']}")
    if args.dry_run:
        return 0
    BANK.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    (ROOT / "data" / "minna_audit_pending.json").write_text(
        json.dumps(deferred, ensure_ascii=False, indent=1), encoding="utf-8")
    print("题库已更新; 待人工确认的写在 data/minna_audit_pending.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
