"""跨设备同步的状态格式、合并与推导.

本模块是 PC 端与手机端共用的**唯一真相**。web/app.js 里的实现必须与之等价:
同样的输入必须算出同样的输出, 否则两台设备会各自认为"今天该考这些词"。

设计要点
--------
1. **事件流, 不是快照**。每答一题追加一条事件 {时间, 语言, 单词, 对错}。
   合并 = 按 id 求并集, 天然不会丢数据; 错题本、复习排期、打卡天数全部由
   事件推导而来, 而不是各自维护、互相对不上。
2. **每日抽词是确定性纯函数**。用 fnv1a(日期|语言|单词) 排序取前 N 个,
   两台设备算出的当日计划必然一致, 因此"计划"本身不需要同步。
3. **base 是压缩后的历史**。事件积累到一定量后, 把 90 天前的折叠进 base
   再丢弃, 避免文件无限增长。折叠规则同样确定, 两端会收敛到同一结果。

状态格式
--------
{
  "v": 1,
  "updated": "2026-09-18T20:00:00",
  "words": {"en": [{"w":..,"m":..,"ipa":..}, ...],
            "jp": [{"w":..,"r":..,"m":..,"ac":..}, ...]},
  "edits": {"en:shrug": {"m": "...", "ipa": "...", "t": 1758...}},
  "base": {
    "stats":    {"en:shrug": "2026-09-10"},          # 最后学习日
    "mistakes": {"jp:学生": {"a":"2026-09-14","s":1,"e":2,"g":0,"t":1758}},
    "days":     ["2026-09-14", "2026-09-15"],        # 已完成(打卡)的日期
    "done":     {"2026-09-14": {"en": 7, "jp": 15}}, # 当天各语言已答题数
    "dropped":  {"jp:学生": 1758}                    # 人工移出错题本的词 -> 何时移出的
  },
  "events": [{"i":"...","t":1758...,"d":"pc","l":"en","w":"shrug","o":1,"day":"2026-09-18"}]
}
"""
from __future__ import annotations

import datetime as dt

STATE_VERSION = 1
REVIEW_OFFSETS = (1, 3, 7, 15, 30)
EN_DAILY_NEW = 7
JP_DAILY_NEW = 15
KEEP_EVENT_DAYS = 90        # 超过这个天数的事件折叠进 base


# ------------------------------------------------------------------ 基础
def fnv1a(s: str) -> int:
    """32 位 FNV-1a 哈希. JS 用 Math.imul 实现同一算法, 结果必须逐位相同."""
    h = 0x811C9DC5
    for b in s.encode("utf-8"):
        h ^= b
        h = (h * 0x01000193) & 0xFFFFFFFF
    return h


def key_of(lang: str, word: str) -> str:
    return f"{lang}:{word}"


def split_key(key: str) -> tuple[str, str]:
    lang, _, word = key.partition(":")
    return lang, word


def add_days(day: str, n: int) -> str:
    return (dt.date.fromisoformat(day) + dt.timedelta(days=n)).isoformat()


def parse_day(d: str) -> dt.date:
    return dt.date.fromisoformat(d)


def daily_target(lang: str) -> int:
    return EN_DAILY_NEW if lang == "en" else JP_DAILY_NEW


def empty_state() -> dict:
    return {
        "v": STATE_VERSION,
        "updated": "",
        "words": {"en": [], "jp": []},
        "edits": {},
        "base": {"stats": {}, "mistakes": {}, "days": []},
        "events": [],
    }


# ------------------------------------------------------------------ 推导
def derive(state: dict) -> dict:
    """从 base + events 推导出当前状态.

    返回:
      stats     {key: 最后学习日}
      mistakes  {key: {a,s,e,g,t}}       a=day0 s=已过档位 e=出错次数 g=已毕业
      days      set(已完成日期)
      daily     {day: {lang: {"answered": [词...], "ok": 答对数}}}
    """
    base = state.get("base") or {}
    stats = dict(base.get("stats") or {})
    mistakes = {k: dict(v) for k, v in (base.get("mistakes") or {}).items()}
    days = set(base.get("days") or [])
    daily: dict[str, dict[str, dict]] = {}
    # 每天每门语言答了多少题。事件被折叠进 base 后, 这些计数是另一台设备
    # 唯一能知道"今天做了多少"的依据 —— 光有 days 只能判断打卡, 判断不了进度。
    done: dict[str, dict[str, int]] = {
        d: {k: int(v) for k, v in (langs or {}).items()}
        for d, langs in (base.get("done") or {}).items()
    }
    # 人工移出错题本的词: {key: 移出时刻}. 它必须记在 base 里 ——
    # 只删 mistakes 表是删不掉它的, 那张表由本函数重建, 下次就会被还原回来。
    dropped: dict[str, int] = dict(base.get("dropped") or {})

    events = sorted(
        state.get("events") or [],
        key=lambda e: (e.get("t", 0), e.get("i", "")),
    )

    for e in events:
        lang, word = e.get("l", ""), e.get("w", "")
        if not lang or not word:
            continue
        key = key_of(lang, word)
        ts = e.get("t", 0)
        day = e.get("day", "")

        stats[key] = day

        slot = daily.setdefault(day, {}).setdefault(lang, {"answered": [], "ok": 0})
        if word not in slot["answered"]:
            slot["answered"].append(word)
        if e.get("o"):
            slot["ok"] += 1

        # 移出之后又答错了, 说明它是真的不会, 重新收进错题本
        if key in dropped and ts > dropped[key]:
            dropped.pop(key, None)

        m = mistakes.get(key)
        if not e.get("o"):
            # 答错: 重置复习阶梯
            mistakes[key] = {
                "a": day, "s": 0, "e": (m or {}).get("e", 0) + 1, "g": 0, "t": ts,
            }
        elif m and not m.get("g"):
            # 复习答对: 推进一档, 走完则毕业
            s = m.get("s", 0) + 1
            if s >= len(REVIEW_OFFSETS):
                mistakes[key] = {**m, "s": s, "g": 1, "t": ts}
            else:
                mistakes[key] = {**m, "s": s, "t": ts}

    # 打卡: 当天任一门语言答满该语言的目标题数
    for day, langs in daily.items():
        slot = done.setdefault(day, {})
        for lang, d in langs.items():
            n = len(d["answered"])
            slot[lang] = max(slot.get(lang, 0), n)
            if n >= daily_target(lang):
                days.add(day)

    # 仍在"已移出"名单里的词, 不进错题本
    for key in dropped:
        mistakes.pop(key, None)

    return {"stats": stats, "mistakes": mistakes, "days": days,
            "daily": daily, "done": done, "dropped": dropped}


def next_due(m: dict) -> str | None:
    """错题的下次复习日; 已毕业返回 None."""
    if not m or m.get("g"):
        return None
    s = m.get("s", 0)
    if s >= len(REVIEW_OFFSETS):
        return None
    return add_days(m["a"], REVIEW_OFFSETS[s])


def mistake_progress(m: dict) -> str:
    if m.get("g"):
        return "已毕业"
    return f"{m.get('s', 0)}/{len(REVIEW_OFFSETS)}"


# ------------------------------------------------------------------ 每日计划
def plan_for(day: str, lang: str, words: list[dict], der: dict) -> list[dict]:
    """当天该考哪些词. 纯函数 —— 两端算出的结果必须完全一致.

    返回 [{"w": 单词, "kind": "review"|"new", "due": 到期日}]
    """
    stats = der["stats"]
    mistakes = der["mistakes"]
    target = daily_target(lang)

    # 1) 到期错题 —— 必须出现
    reviews: list[tuple[str, str]] = []
    for key, m in mistakes.items():
        if not key.startswith(lang + ":"):
            continue
        due = next_due(m)
        if due and due <= day:
            reviews.append((split_key(key)[1], due))
    reviews.sort(key=lambda t: (t[1], t[0]))
    chosen = [{"w": w, "kind": "review", "due": d} for w, d in reviews]
    taken = {c["w"] for c in chosen}

    active = [w for w in words if w.get("w") and w["w"] not in taken]

    # 2) 没学过的新词
    fresh = [w for w in active if key_of(lang, w["w"]) not in stats]
    fresh.sort(key=lambda w: (fnv1a(f"{day}|{lang}|{w['w']}"), w["w"]))
    picks = fresh[:target]

    # 3) 不够就用最久没复习的补足
    if len(picks) < target:
        rest = [w for w in active if key_of(lang, w["w"]) in stats]
        rest.sort(key=lambda w: (stats[key_of(lang, w["w"])], fnv1a(f"{day}|{lang}|{w['w']}")))
        picks += rest[: target - len(picks)]

    chosen += [{"w": w["w"], "kind": "new", "due": ""} for w in picks]
    return chosen


# ------------------------------------------------------------------ 合并
def merge(local: dict, remote: dict, prefer: str | None = None) -> dict:
    """合并两份状态.

    prefer=None     对等合并: 逐字段取较新或求并集
    prefer="local"  冲突时以本端为准    —— 电脑端同步时用
    prefer="remote" 冲突时以远端为准    —— 手机端同步时用

    **事件始终求并集, 不受 prefer 影响**: 答题记录是唯一不可再生的东西,
    丢一条就是真丢了。受 prefer 影响的只是 base 里的派生状态(错题本、打卡、
    学习统计、每日进度)以及词表和人工编辑 —— 这些要么可重算, 要么以电脑端
    为准才不会互相打架。
    """
    if not remote:
        return _normalize(local)
    if not local:
        return _normalize(remote)

    out = empty_state()
    out["words"] = _merge_words(local.get("words") or {}, remote.get("words") or {}, prefer)
    out["edits"] = _merge_edits(local.get("edits") or {}, remote.get("edits") or {}, prefer)

    lb, rb = local.get("base") or {}, remote.get("base") or {}
    out["base"] = {
        "stats": _merge_stats(lb.get("stats") or {}, rb.get("stats") or {}, prefer),
        "mistakes": _merge_mistakes(lb.get("mistakes") or {}, rb.get("mistakes") or {}, prefer),
        "days": _merge_days(lb.get("days") or [], rb.get("days") or [], prefer),
        "done": _merge_done(lb.get("done") or {}, rb.get("done") or {}, prefer),
        "dropped": _merge_dropped(lb.get("dropped") or {}, rb.get("dropped") or {}, prefer),
    }

    # 事件按 id 去重后取并集
    seen: dict[str, dict] = {}
    for e in list(local.get("events") or []) + list(remote.get("events") or []):
        i = e.get("i")
        if i and i not in seen:
            seen[i] = e
    out["events"] = sorted(seen.values(), key=lambda e: (e.get("t", 0), e.get("i", "")))

    return _compact(_normalize(out))


def _sides(a, b, prefer):
    """按 prefer 返回 (优先方, 另一方)."""
    return (a, b) if prefer == "local" else (b, a)


def _merge_words(a: dict, b: dict, prefer: str | None = None) -> dict:
    """词表按 (语言, 单词) 取并集; 重复时保留 updated 较新的那份."""
    out = {"en": [], "jp": []}
    first, second = _sides(a, b, prefer) if prefer else (a, b)
    for lang in ("en", "jp"):
        by_word: dict[str, dict] = {}
        # 优先方放在后面, 时间戳相同时它会胜出
        for rec in list(second.get(lang) or []) + list(first.get(lang) or []):
            w = rec.get("w")
            if not w:
                continue
            old = by_word.get(w)
            if old is None or rec.get("u", 0) >= old.get("u", 0):
                by_word[w] = rec
        out[lang] = sorted(by_word.values(), key=lambda r: r["w"])
    return out


def _merge_edits(a: dict, b: dict, prefer: str | None = None) -> dict:
    out: dict[str, dict] = {}
    for key in set(a) | set(b):
        ra, rb = a.get(key) or {}, b.get(key) or {}
        if not rb:
            out[key] = ra; continue
        if not ra:
            out[key] = rb; continue
        if prefer:
            first, second = _sides(ra, rb, prefer)
            merged = dict(second)
            merged.update(first)         # 优先方逐字段覆盖
        else:
            # 逐字段按时间戳取胜, 而不是整条覆盖
            merged = dict(ra)
            for f, v in rb.items():
                if f == "t":
                    continue
                if v != ra.get(f) and rb.get("t", 0) >= ra.get("t", 0):
                    merged[f] = v
        merged["t"] = max(ra.get("t", 0), rb.get("t", 0))
        out[key] = merged
    return out


def _merge_stats(a: dict, b: dict, prefer: str | None = None) -> dict:
    if prefer:
        first, second = _sides(a, b, prefer)
        out = dict(second)
        out.update(first)                # 优先方说了算, 包括"把日期改早"
        return out
    return {k: max(a.get(k, ""), b.get(k, "")) for k in set(a) | set(b)}


def _merge_days(a: list, b: list, prefer: str | None = None) -> list:
    """打卡日期. 指定 prefer 时以该端为准 (整份替换, 而不是求并集) ——
    否则一端删掉的打卡记录会被另一端带回来."""
    if prefer == "local":
        return sorted(set(a)) if a else sorted(set(b))
    if prefer == "remote":
        return sorted(set(b)) if b else sorted(set(a))
    return sorted(set(a) | set(b))


def _merge_done(a: dict, b: dict, prefer: str | None = None) -> dict:
    """每天每语言答了多少题."""
    out: dict[str, dict[str, int]] = {}
    for day in set(a) | set(b):
        la, lb = a.get(day) or {}, b.get(day) or {}
        if prefer:
            first, second = _sides(la, lb, prefer)
            slot = {k: int(second[k] or 0) for k in second}
            slot.update({k: int(v or 0) for k, v in first.items()})
            out[day] = slot
        else:
            out[day] = {
                k: max(int(la.get(k) or 0), int(lb.get(k) or 0))
                for k in set(la) | set(lb)
            }
    return out


def _merge_dropped(a: dict, b: dict, prefer: str | None = None) -> dict:
    """人工移出错题本的名单, 取两端并集 (任一端移出过就算移出)."""
    if prefer:
        first, second = _sides(a, b, prefer)
        out = dict(second)
        out.update(first)
        return out
    out = dict(b)
    out.update(a)
    return out


def _merge_mistakes(a: dict, b: dict, prefer: str | None = None) -> dict:
    out: dict[str, dict] = {}
    for key in set(a) | set(b):
        ra, rb = a.get(key), b.get(key)
        if ra is None:
            out[key] = rb
        elif rb is None:
            out[key] = ra
        elif prefer:
            out[key] = ra if prefer == "local" else rb
        else:
            out[key] = rb if rb.get("t", 0) >= ra.get("t", 0) else ra
    return out


def _normalize(state: dict) -> dict:
    """补齐缺失字段, 保证结构完整."""
    out = empty_state()
    out.update({k: v for k, v in (state or {}).items() if k in out})
    out["v"] = STATE_VERSION
    out.setdefault("edits", {})
    base = out.get("base") or {}
    out["base"] = {
        "stats": base.get("stats") or {},
        "mistakes": base.get("mistakes") or {},
        "days": sorted(set(base.get("days") or [])),
        "done": base.get("done") or {},
        "dropped": base.get("dropped") or {},
    }
    for lang in ("en", "jp"):
        out["words"].setdefault(lang, [])
    out["events"] = out.get("events") or []
    return out


def _compact(state: dict, today: str | None = None) -> dict:
    """把 KEEP_EVENT_DAYS 天前的事件折叠进 base 并丢弃.

    折叠结果只依赖事件本身的顺序, 因此两端各自折叠会得到相同状态。
    """
    today = today or dt.date.today().isoformat()
    cutoff = add_days(today, -KEEP_EVENT_DAYS)
    old = [e for e in state["events"] if (e.get("day") or "9999") < cutoff]
    if not old:
        return state

    keep = [e for e in state["events"] if (e.get("day") or "9999") >= cutoff]
    folded = _normalize({**empty_state(), "base": state["base"], "events": old})
    der = derive(folded)

    state["base"] = {
        "stats": der["stats"],
        "mistakes": der["mistakes"],
        "days": sorted(der["days"]),
        "done": der["done"],           # 折叠后仍要保留"每天做了多少"
        "dropped": der["dropped"],     # 人工移出的名单同样要保留
    }
    state["events"] = keep
    return state


# ------------------------------------------------------------------ 应用编辑
def apply_edits(state: dict) -> None:
    """把 edits 覆盖到 words 上 (就地修改)."""
    by_key: dict[str, dict] = {}
    for lang in ("en", "jp"):
        for rec in state["words"].get(lang) or []:
            by_key[key_of(lang, rec["w"])] = rec
    for key, edit in (state.get("edits") or {}).items():
        rec = by_key.get(key)
        if rec is None:
            continue
        if "m" in edit:
            rec["m"] = edit["m"]
        if "ipa" in edit:
            rec["ipa"] = edit["ipa"]
        if "ac" in edit:
            rec["ac"] = edit["ac"]
        if "r" in edit:
            rec["r"] = edit["r"]
        rec["manual"] = 1


def build_base_from_db(db, today: str | None = None) -> dict:
    """把 PC 现有 SQLite 状态压成 base, 用于首次同步的引导.

    历史答题的逐条记录无法还原, 因此已有的错题本与学习次数直接作为起点,
    此后产生的答题才走事件流。
    """
    stats: dict[str, str] = {}
    mistakes: dict[str, dict] = {}

    for row in db.conn.execute(
        "SELECT word, last_studied FROM en_words WHERE last_studied IS NOT NULL"
    ):
        stats[key_of("en", row["word"])] = row["last_studied"]
    for row in db.conn.execute(
        "SELECT word, last_studied FROM jp_words WHERE last_studied IS NOT NULL"
    ):
        stats[key_of("jp", row["word"])] = row["last_studied"]

    for row in db.conn.execute("SELECT * FROM mistakes"):
        table = "en_words" if row["lang"] == "en" else "jp_words"
        w = db.conn.execute(f"SELECT word FROM {table} WHERE id=?", (row["word_id"],)).fetchone()
        if not w:
            continue
        mistakes[key_of(row["lang"], w["word"])] = {
            "a": row["anchor_date"],
            "s": row["stage"],
            "e": row["error_count"],
            "g": 1 if row["graduated"] else 0,
            "t": 0,
        }

    days = [
        r["day"] for r in db.conn.execute(
            "SELECT DISTINCT day FROM daily_log WHERE completed=1"
        )
    ]

    # 每天每语言已答多少 —— 供另一台设备显示进度
    done: dict[str, dict[str, int]] = {}
    for r in db.conn.execute(
        "SELECT day, lang, SUM(answered) a FROM daily_plan GROUP BY day, lang"
    ):
        if r["a"]:
            done.setdefault(r["day"], {})[r["lang"]] = int(r["a"])

    return {"stats": stats, "mistakes": mistakes,
            "days": sorted(set(days)), "done": done, "dropped": {}}


def streak(days: set[str], today: str | None = None) -> int:
    """连续打卡天数. 今天还没学完不算断签, 从昨天起算."""
    today = today or dt.date.today().isoformat()
    if not days:
        return 0
    cur = parse_day(today) if today in days else parse_day(today) - dt.timedelta(days=1)
    n = 0
    while cur.isoformat() in days:
        n += 1
        cur -= dt.timedelta(days=1)
    return n
