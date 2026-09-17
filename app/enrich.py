"""自动补全: 英语音标 / 日语中文释义 / 日语声调(几型).

原则
  * 只在缺失时补, 人工改过的 (manual) 一律不覆盖.
  * 完全离线优先: 音标走 CMUdict; 释义先查内置种子; 声调先查本地声调库.
  * 联网只作为最后的兜底, 失败不影响应用使用.
"""
from __future__ import annotations

import json
import logging
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

from . import ipa as ipa_mod
from .config import DATA_DIR

_SEED_FILE = DATA_DIR / "ja_seed.json"
_ACCENT_FILE = DATA_DIR / "ja_accent.json"          # 可选: 手工补充的 {"词": "3型"}
_KANJIUM_FILE = DATA_DIR / "kanjium_accents.txt"    # Kanjium 声调库 (CC BY-SA 4.0)

_zh_re = re.compile(r"[一-鿿]")

# 片假名 -> 平假名: 词典里读音可能写作 アメリカじん, 而词表写作 あめりかじん
_KATA2HIRA = {chr(c): chr(c - 0x60) for c in range(0x30A1, 0x30F7)}


def _norm_kana(s: str) -> str:
    return "".join(_KATA2HIRA.get(ch, ch) for ch in (s or ""))

_seed_cache: dict | None = None
_accent_cache: dict | None = None
_kanjium_cache: dict | None = None


# ------------------------------------------------------------------ 本地资源
def seed_meanings() -> dict[str, str]:
    global _seed_cache
    if _seed_cache is None:
        try:
            with open(_SEED_FILE, encoding="utf-8") as fh:
                _seed_cache = json.load(fh).get("meanings", {})
        except Exception:
            _seed_cache = {}
    return _seed_cache


def accent_table() -> dict[str, str]:
    """手工补充的声调表: {单词: "3型"} (优先级高于 Kanjium)."""
    global _accent_cache
    if _accent_cache is None:
        try:
            with open(_ACCENT_FILE, encoding="utf-8") as fh:
                raw = json.load(fh)
            _accent_cache = {
                k: v if str(v).endswith("型") else f"{v}型"
                for k, v in raw.items()
                if not k.startswith("_") and str(v) != ""
            }
        except Exception:
            _accent_cache = {}
    return _accent_cache


def _kanjium() -> dict:
    """加载 Kanjium 声调库.

    文件格式 (TSV):  汉字形 <TAB> 假名读音 <TAB> 声调[,声调...]
    返回 {"pair": {(词,读音): 声调}, "word": {词: 声调}, "reading": {读音: 声调}}
    """
    global _kanjium_cache
    if _kanjium_cache is not None:
        return _kanjium_cache

    pair: dict[tuple[str, str], str] = {}
    word: dict[str, str] = {}
    word_readings: dict[str, set[str]] = {}
    reading_votes: dict[str, dict[str, int]] = {}

    def blank():
        return {"pair": {}, "word": {}, "reading": {}, "word_readings": {}}

    try:
        with open(_KANJIUM_FILE, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                parts = line.rstrip("\n").split("\t")
                if len(parts) < 3:
                    continue
                kanji = parts[0].strip()
                read = _norm_kana(parts[1].strip())
                acc = parts[2].strip()
                if not acc:
                    continue
                if kanji and read:
                    pair.setdefault((kanji, read), acc)
                if kanji:
                    word.setdefault(kanji, acc)
                    if read:
                        word_readings.setdefault(kanji, set()).add(read)
                if read:
                    reading_votes.setdefault(read, {})
                    reading_votes[read][acc] = reading_votes[read].get(acc, 0) + 1
    except FileNotFoundError:
        _kanjium_cache = blank()
        return _kanjium_cache
    except Exception:
        _kanjium_cache = blank()
        return _kanjium_cache

    reading: dict[str, str] = {}
    for read, votes in reading_votes.items():
        # 同一读音对应多个汉字形时, 取出现最多的声调; 并列则取先出现的
        reading[read] = max(votes.items(), key=lambda kv: kv[1])[0]

    _kanjium_cache = {
        "pair": pair, "word": word, "reading": reading, "word_readings": word_readings,
    }
    return _kanjium_cache


def _fmt_accents(raw: str) -> str:
    """"0,2" -> "0型・2型"; "(名)1型,(副)1型" -> "1型"."""
    seen: list[str] = []
    for v in re.findall(r"\d+", raw or ""):
        if v not in seen:
            seen.append(v)
    return "・".join(f"{v}型" for v in seen)


def _kanjium_lookup(word: str, reading: str) -> str:
    """一次 Kanjium 查询 (不处理变体)."""
    k = _kanjium()
    reading = _norm_kana(reading)
    if word and reading and (word, reading) in k["pair"]:
        return _fmt_accents(k["pair"][(word, reading)])
    # 读音才是决定声调的依据: 有读音时优先按读音查
    if reading and reading in k["reading"]:
        return _fmt_accents(k["reading"][reading])
    if word:
        # 词形回退: 只有当这个词形在词典里只有唯一读音时才安全,
        # 否则可能张冠李戴 (如 月 有 つき/げつ/がつ 三种读法)
        if word in k["word"] and len(k["word_readings"].get(word, ())) <= 1:
            return _fmt_accents(k["word"][word])
        # 纯假名词: 词本身就是读音
        if not reading and word in k["reading"]:
            return _fmt_accents(k["reading"][word])
    return ""


def _accent_variants(word: str, reading: str) -> list[tuple[str, str]]:
    """派生可查变体: 原本写法 → 去 ～ 前缀 → 去 する 后缀.

    去掉 ～ 只对「读音也随之确定」的情况安全: 因为变体里读音一并去掉 ～,
    若读音在词典里查不到就不会回退到按汉字形查, 不会张冠李戴。
    """
    out = [(word, reading)]
    if word.startswith(("～", "~")) or reading.startswith(("～", "~")):
        out.append((word.lstrip("～~"), reading.lstrip("～~")))
    if word.endswith("する") and len(word) > 2:
        stem_r = reading[: -2] if reading.endswith("する") else reading
        out.append((word[:-2], stem_r))
    return out


def lookup_accent(word: str, reading: str = "") -> tuple[str, str]:
    """查日语声调(几型). 返回 (声调, 来源); 查不到返回 ("", "")."""
    if not word and not reading:
        return "", ""

    # 1) 补充表 (内置缺口补录 / 人工)
    manual = accent_table()
    for key in (word, reading):
        if key and key in manual:
            return manual[key], "supplement"

    # 2) Kanjium 声调库 (含变体回退)
    for w, r in _accent_variants(word, reading):
        a = _kanjium_lookup(w, r)
        if a:
            return a, "kanjium"
    return "", ""


def normalize_accent(value: str) -> str:
    v = (value or "").strip()
    if not v:
        return ""
    m = re.match(r"^\[?(\d+)\]?", v)
    if m:
        return f"{m.group(1)}型"
    return v


# ------------------------------------------------------------------ 英语
def enrich_english(db) -> int:
    rows = db.conn.execute(
        "SELECT id, word, ipa, ipa_source FROM en_words WHERE active=1"
    ).fetchall()
    n = 0
    for r in rows:
        if r["ipa"] and r["ipa_source"] == "manual":
            continue
        if r["ipa"]:
            continue
        p = ipa_mod.phonetics(r["word"])
        if p:
            db.set_enrich("en", r["id"], sources={"ipa": "cmudict"}, ipa=p)
            n += 1
    return n


# ------------------------------------------------------------------ 日语
def enrich_japanese(db, *, online: bool = True, max_online: int = 60) -> dict:
    seed = seed_meanings()
    rows = db.conn.execute(
        "SELECT id, word, reading, meaning, meaning_source, accent, accent_source"
        " FROM jp_words WHERE active=1"
    ).fetchall()

    stats = {"seed": 0, "accent": 0, "ai": 0, "online": 0, "online_failed": 0}
    todo_online: list = []

    for r in rows:
        fields: dict[str, str] = {}
        src: dict[str, str] = {}

        if r["accent_source"] != "manual":
            a, a_src = lookup_accent(r["word"], r["reading"])
            if a and a != r["accent"]:
                fields["accent"] = a
                src["accent"] = a_src or "auto"
                stats["accent"] += 1
                if a_src == "supplement":
                    stats["accent_supplement"] = stats.get("accent_supplement", 0) + 1

        if r["meaning_source"] != "manual" and not r["meaning"]:
            m = seed.get(r["word"])
            if m:
                fields["meaning"] = m
                src["meaning"] = "seed"
                stats["seed"] += 1
            elif online:
                todo_online.append(r)

        if fields:
            db.set_enrich("jp", r["id"], sources=src, **fields)

    # 种子未覆盖的新词: 优先用 LLM 批量翻译(质量接近内置),
    # 没配 API key 或调用失败时, 才退回免费的 MyMemory 接口。
    if todo_online and online:
        todo_online = todo_online[:max_online]

        ai_done: dict[str, str] = {}
        try:
            from . import llm as llm_mod

            if llm_mod.is_configured():
                ai_done = llm_mod.translate_words(
                    [(r["word"], r["reading"]) for r in todo_online]
                )
        except Exception as exc:  # noqa: BLE001
            logging.getLogger("trilingo").warning("LLM 补全失败: %s", exc)

        # 逐个写入: 任何一个词出问题都不该中断其余的补全
        for r in todo_online:
            try:
                zh = ai_done.get(r["word"])
                source = "ai"
                if not zh:
                    zh = translate_ja_zh(r["word"])
                    source = "auto"
                    time.sleep(0.4)     # 对公共接口保持礼貌
                if zh:
                    db.set_enrich("jp", r["id"], sources={"meaning": source}, meaning=zh)
                    key = "ai" if source == "ai" else "online"
                    stats[key] = stats.get(key, 0) + 1
                else:
                    stats["online_failed"] = stats.get("online_failed", 0) + 1
            except Exception as exc:  # noqa: BLE001
                logging.getLogger("trilingo").warning(
                    "补全 %s 失败: %s", r["word"], exc)
                stats["online_failed"] = stats.get("online_failed", 0) + 1
    return stats


# ------------------------------------------------------------------ 联网兜底
def _http_json(url: str, timeout: int = 8):
    req = urllib.request.Request(url, headers={"User-Agent": "Trilingo/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", "replace"))


def translate_ja_zh(text: str) -> str | None:
    """日语 -> 中文 (MyMemory 公共接口). 失败返回 None, 不抛异常."""
    text = (text or "").strip()
    if not text:
        return None
    q = urllib.parse.quote(text)
    url = f"https://api.mymemory.translated.net/get?q={q}&langpair=ja|zh-CN"
    try:
        data = _http_json(url)
    except Exception:
        return None
    if str(data.get("responseStatus")) != "200":
        return None
    out = (data.get("responseData") or {}).get("translatedText") or ""
    out = out.strip()
    if not out:
        return None
    low = out.lower()
    if "mymemory" in low or "quota" in low or "invalid" in low:
        return None
    # 必须真的含中文, 且不是原样返回
    if out == text or not _zh_re.search(out):
        return None
    if len(out) > 40:
        return None
    return out


def translate_en_zh(text: str) -> str | None:
    text = (text or "").strip()
    if not text:
        return None
    q = urllib.parse.quote(text)
    url = f"https://api.mymemory.translated.net/get?q={q}&langpair=en|zh-CN"
    try:
        data = _http_json(url)
    except Exception:
        return None
    if str(data.get("responseStatus")) != "200":
        return None
    out = ((data.get("responseData") or {}).get("translatedText") or "").strip()
    if not out or not _zh_re.search(out) or out.lower() == text.lower():
        return None
    return out
