"""逐题验证: 不看答案, 让模型自己答一遍, 和题库里的答案比对.

比对规则 (宽松到"对就算对", 但不能放过真错):
  * fill-一 (汉字→假名): 两边都规范成平假名后比较, 允许 を/お、ず/づ 之类常见差异?
    不允许 —— 这些正是考点。只做全角/空格/标点归一。
  * fill-二 (假名→汉字): 题库答案常只写词干 (読 / 泊), 模型可能写 読む / 泊まる。
    采用"答案包含在模型答案里"即算对 (词干对就算对), 但反之不行。
  * choice: 序号必须一致。
  * translate: 不做严格比对, 只记录模型译文供人工抽查。

用法:
    python tools/verify_chujixia.py [--limit N] [--kinds fill choice]
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

BANK = ROOT / "data" / "exams" / "shinbunpo-2.json"
OUT = ROOT / "data" / "ocr" / "chujixia_verify.json"
BATCH = 20

KANA = re.compile(r"[\u3040-\u309f]+")
KANJI = re.compile(r"[\u4e00-\u9fff]+")

SYSTEM_FILL = """你在做日语词汇题, 只回答答案本身, 不要解释。

输入每行: `题号|题型|词`
* 题型 `kana` : 给出这个词的日语读音 (平假名)
* 题型 `kanji`: 把这个假名写成汉字 (只写那个词的汉字写法)

输出 JSON: {"answers": {"题号": "答案"}}"""

SYSTEM_CHOICE = """你在做日语选择题, 每题四选一或三选一。

输入每行: `题号|题干|①选项|②选项|...`
输出 JSON: {"answers": {"题号": 正确选项的序号(1起)}}"""


def ask(system: str, lines: list[str]) -> dict:
    cfg = llm.load_config()
    url = cfg["base_url"].rstrip("/") + "/chat/completions"
    payload = {
        "model": cfg["model"],
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": "\n".join(lines)}],
        "response_format": {"type": "json_object"},
        "temperature": 0,
        "stream": False,
    }
    data = llm._post(url, payload, cfg["api_key"], timeout=180)
    content = (data.get("choices") or [{}])[0].get("message", {}).get("content", "")
    obj = llm._extract_json(content)
    got = obj.get("answers") if isinstance(obj.get("answers"), dict) else obj
    return got if isinstance(got, dict) else {}


def norm_kana(s: str) -> str:
    s = str(s or "")
    s = s.replace(" ", "").replace("　", "")
    s = re.sub(r"[。、，,.!?！？「」（）()＿_・…]", "", s)
    return s


def kana_only(s: str) -> str:
    return "".join(KANA.findall(norm_kana(s)))


def kanji_only(s: str) -> str:
    return "".join(KANJI.findall(str(s or "")))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--kinds", nargs="*", default=["fill", "choice"])
    a = ap.parse_args()

    bank = json.loads(BANK.read_text(encoding="utf-8"))
    jobs = []      # (lesson, item, kind, letter)
    for les in bank["lessons"]:
        for sec in les["sections"]:
            letter = sec["title"][:1]
            kind = sec["kind"]
            if kind not in a.kinds:
                continue
            if kind == "fill" and letter not in ("一", "二"):
                continue
            for it in sec["items"]:
                jobs.append((les["lesson"], it, kind, letter))
    if a.limit:
        jobs = jobs[:a.limit]
    print(f"待验证 {len(jobs)} 题")

    results, bad = [], []
    for i in range(0, len(jobs), BATCH):
        chunk = jobs[i:i + BATCH]
        fills = [j for j in chunk if j[2] == "fill"]
        choices = [j for j in chunk if j[2] == "choice"]

        if fills:
            lines = []
            for k, (no, it, _kind, letter) in enumerate(fills):
                t = "kana" if letter == "一" else "kanji"
                lines.append(f"{k}|{t}|{it['prompt']}")
            try:
                got = ask(SYSTEM_FILL, lines)
            except Exception as exc:      # noqa: BLE001
                print(f"  批次 {i} fill 失败: {exc}")
                got = {}
            for k, (no, it, _kind, letter) in enumerate(fills):
                model = str(got.get(str(k), "")).strip()
                want = str(it["answer"]).strip()
                alts = [str(x) for x in (it.get("alt") or [])]
                if letter == "一":
                    ok = kana_only(model) == kana_only(want) and kana_only(want)
                else:
                    m, w = kanji_only(model), kanji_only(want)
                    ok = bool(w) and (w == m or w in m)
                    # 同音词: 课本写 捜, 用户写 探 也算对
                    if not ok and m:
                        ok = any(kanji_only(a) and
                                 (kanji_only(a) == m or kanji_only(a) in m)
                                 for a in alts)
                results.append({"id": it["id"], "letter": letter,
                                "prompt": it["prompt"], "want": want,
                                "model": model, "ok": bool(ok)})
                if not ok:
                    bad.append(results[-1])

        if choices:
            lines = []
            for k, (no, it, _kind, _l) in enumerate(choices):
                opts = "|".join(it["options"])
                lines.append(f"{k}|{it['prompt']}|{opts}")
            try:
                got = ask(SYSTEM_CHOICE, lines)
            except Exception as exc:      # noqa: BLE001
                print(f"  批次 {i} choice 失败: {exc}")
                got = {}
            for k, (no, it, _kind, _l) in enumerate(choices):
                try:
                    model = int(str(got.get(str(k), "")).strip()[0])
                except (ValueError, IndexError, TypeError):
                    model = None
                want = it["answer"]
                ok = model == want
                results.append({"id": it["id"], "letter": "选",
                                "prompt": it["prompt"], "want": want,
                                "model": model, "ok": bool(ok)})
                if not ok:
                    bad.append(results[-1])

        done = min(i + BATCH, len(jobs))
        print(f"  {done}/{len(jobs)}  累计不一致 {len(bad)}")

    OUT.write_text(json.dumps({"results": results, "bad": bad},
                              ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n完成: {len(results)} 题, 不一致 {len(bad)} 题")
    for b in bad[:20]:
        print(f"  {b['id']} [{b['letter']}] {b['prompt'][:26]} | 题库={b['want']} 模型={b['model']}")
    print("明细:", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
