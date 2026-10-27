"""不看答案, 把题库从头到尾重做一遍, 并与现有答案比对.

三种任务分别用不同的提问方式:
  * kana     : 汉字 -> 平假名   (上册「将下列汉字改为平假名」/ 下册「一、」)
  * kanji    : 假名 -> 汉字     (上册「将下列假名改为汉字」/ 下册「二、」)
  * choice   : 题干 + 选项 -> 序号
  * translate: 原句 -> 译文 (只记录, 用来判断参考译文的质量)

结果写 data/ocr/redo_<bank>.json, 支持断点续跑 (已有结果的题跳过)。

用法:
    python tools/redo_bank.py --bank upper       # 上册 minna_tests.json
    python tools/redo_bank.py --bank lower       # 下册 shinbunpo-2.json
    python tools/redo_bank.py --bank lower --only choice
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

BANKS = {
    "upper": ROOT / "data" / "minna_tests.json",
    "lower": ROOT / "data" / "exams" / "shinbunpo-2.json",
}
BATCH = 20

SYS_KANA = """你在做日语词汇练习：把汉字词写成平假名（只写读音，不要汉字）。

输入每行 `序号|词`，输出 JSON: {"answers": {"序号": "读音"}}"""

SYS_KANJI = """你在做日语词汇练习：把假名词写成汉字（只写那个词的汉字写法）。

输入每行 `序号|假名`，输出 JSON: {"answers": {"序号": "汉字"}}"""

SYS_CHOICE = """你在做日语选择题。每题给你「文章（可能为空）/ 题目 / 选项」。

* 仔细读题；有文章时答案必须能在文章里找到依据；
* 三选一、四选一都按实际选项数作答；
* 只输出正确选项的序号（从 1 起）。

输出 JSON: {"answers": {"序号": 选项序号}}"""

SYS_TRANS = """你在做日语翻译题。把给出的句子译成目标语言。

输入每行 `序号|方向|句子`，方向 `cn` = 译成中文，`jp` = 译成日语。
要求自然、准确、符合教材风格。

输出 JSON: {"answers": {"序号": "译文"}}"""


def task_of(kind: str, title: str) -> str | None:
    t = title or ""
    if kind == "fill":
        if "平假名" in t or ("汉字" in t and "假名" in t and "改为平假名" in t):
            return "kana"
        if "汉字" in t:
            return "kanji"
        return "kanji"
    if kind == "choice":
        return "choice"
    if kind == "translate":
        return "translate"
    return None


def call(system: str, lines: list[str]) -> dict:
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
    data = llm._post(url, payload, cfg["api_key"], timeout=240)
    content = (data.get("choices") or [{}])[0].get("message", {}).get("content", "")
    obj = llm._extract_json(content)
    got = obj.get("answers") if isinstance(obj.get("answers"), dict) else obj
    return got if isinstance(got, dict) else {}


def norm_kana(s: str) -> str:
    s = re.sub(r"[\s　]", "", str(s or ""))
    return re.sub(r"[。、，,.!?！？「」（）()＿_・…]", "", s)


def kanji_only(s: str) -> str:
    return "".join(re.findall(r"[\u4e00-\u9fff]", str(s or "")))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bank", choices=list(BANKS), required=True)
    ap.add_argument("--only", default="", help="只跑某类任务: kana/kanji/choice/translate")
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()

    path = BANKS[a.bank]
    bank = json.loads(path.read_text(encoding="utf-8"))
    out_path = ROOT / "data" / "ocr" / f"redo_{a.bank}.json"
    done = {}
    if out_path.exists():
        done = json.loads(out_path.read_text(encoding="utf-8")).get("answers", {})
    print(f"{a.bank}: 已有 {len(done)} 题结果")

    jobs = []
    for les in bank["lessons"]:
        for sec in les["sections"]:
            task = task_of(sec["kind"], sec.get("title", ""))
            if not task or (a.only and task != a.only):
                continue
            for it in sec["items"]:
                if it["id"] in done:
                    continue
                jobs.append((task, it, sec))
    if a.limit:
        jobs = jobs[:a.limit]
    print(f"待做 {len(jobs)} 题")

    for i in range(0, len(jobs), BATCH):
        chunk = jobs[i:i + BATCH]
        by_task: dict[str, list] = {}
        for j in chunk:
            by_task.setdefault(j[0], []).append(j)
        for task, group in by_task.items():
            lines = []
            for k, (_t, it, sec) in enumerate(group):
                if task in ("kana", "kanji"):
                    lines.append(f"{k}|{it['prompt']}")
                elif task == "choice":
                    opts = " / ".join(f"{n+1}.{o}" for n, o in enumerate(it["options"]))
                    lines.append(f"{k}|{it['prompt']}|{opts}")
                else:
                    direction = "cn" if "汉语" in (sec.get("title") or "") else "jp"
                    lines.append(f"{k}|{direction}|{it['prompt']}")
            system = {"kana": SYS_KANA, "kanji": SYS_KANJI,
                      "choice": SYS_CHOICE, "translate": SYS_TRANS}[task]
            try:
                got = call(system, lines)
            except Exception as exc:      # noqa: BLE001
                print(f"  批次 {i} {task} 失败: {exc}")
                continue
            for k, (_t, it, _sec) in enumerate(group):
                v = got.get(str(k))
                if v is None:
                    continue
                if task == "choice":
                    try:
                        v = int(str(v).strip()[0])
                    except (ValueError, IndexError):
                        continue
                done[it["id"]] = {"task": task, "model": v}
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps({"answers": done}, ensure_ascii=False),
                            encoding="utf-8")
        print(f"  {min(i+BATCH, len(jobs))}/{len(jobs)}  已记录 {len(done)}")

    print(f"完成, 共 {len(done)} 题 -> {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
