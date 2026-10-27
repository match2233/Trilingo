import json
import pathlib
import re
import sys

ROOT = pathlib.Path(r"C:/Users/<user>\Desktop\trilingo")
BANKS = {
    "upper": ROOT / "data" / "minna_tests.json",
    "lower": ROOT / "data" / "exams" / "shinbunpo-2.json",
}


def norm_kana(s: str) -> str:
    s = re.sub(r"[\s　]", "", str(s or ""))
    return re.sub(r"[。、，,.!?！？「」（）()＿_・…]", "", s)


def kanji_only(s: str) -> str:
    return "".join(re.findall(r"[\u4e00-\u9fff]", str(s or "")))


def compare(bank_key: str) -> None:
    bank = json.loads(BANKS[bank_key].read_text(encoding="utf-8"))
    redo_path = ROOT / "data" / "ocr" / f"redo_{bank_key}.json"
    if not redo_path.exists():
        print("还没有重做结果")
        return
    done = json.loads(redo_path.read_text(encoding="utf-8"))["answers"]
    by = {it["id"]: (les, sec, it)
          for les in bank["lessons"] for sec in les["sections"] for it in sec["items"]}

    stats = {"kana": [0, 0], "kanji": [0, 0], "choice": [0, 0], "translate": [0, 0]}
    bad = []
    for iid, rec in done.items():
        if iid not in by:
            continue
        les, sec, it = by[iid]
        task, model = rec["task"], rec["model"]
        want = it.get("answer")
        if task == "translate":
            stats["translate"][0] += 1
            continue
        ok = False
        if task == "choice":
            ok = model == want
        elif task == "kana":
            ok = norm_kana(model) == norm_kana(want)
        else:
            m, w = kanji_only(model), kanji_only(want)
            ok = bool(w) and (w == m or w in m)
            if not ok:
                alts = [kanji_only(x) for x in (it.get("alt") or [])]
                ok = any(al and (al == m or al in m) for al in alts)
        stats[task][0] += 1
        if ok:
            stats[task][1] += 1
        else:
            bad.append({"id": iid, "task": task, "want": want, "model": model,
                        "prompt": it.get("prompt"), "options": it.get("options"),
                        "lesson": les["lesson"], "title": sec.get("title")})

    print(f"== {bank_key} ==")
    for t, (n, ok) in stats.items():
        if n:
            print(f"  {t:9s} {ok}/{n} 一致  ({ok/n*100:.1f}%)")
    print(f"  不一致 {len(bad)} 题")
    out = ROOT / "data" / "ocr" / f"redo_{bank_key}_diffs.json"
    out.write_text(json.dumps(bad, ensure_ascii=False, indent=1), encoding="utf-8")
    for b in bad[:15]:
        print(f'    {b["id"]} 题库={b["want"]!r} 模型={b["model"]!r} | {str(b["prompt"])[:36]}')


if __name__ == "__main__":
    for k in (sys.argv[1:] or ["lower"]):
        compare(k)
