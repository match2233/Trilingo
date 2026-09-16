"""SQLite 数据层.

设计要点
  * 词汇英.xlsx / 词汇日.xlsx 只作为"输入源", 解析后并入本库, 源文件永不写回.
  * 每列都带 *_source 标记: 人工在【数据库】里改过的内容 (manual) 不会被
    自动补全覆盖.
  * 源文件里被删掉的词只置 active=0, 历史(错题/统计)保留.
"""
from __future__ import annotations

import datetime as dt
import sqlite3
from pathlib import Path

from .config import DB_PATH, EN_DAILY_NEW, JP_DAILY_NEW, REVIEW_OFFSETS

SCHEMA = """
CREATE TABLE IF NOT EXISTS en_words (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    word           TEXT NOT NULL,
    key            TEXT NOT NULL UNIQUE,
    meaning        TEXT NOT NULL DEFAULT '',
    ipa            TEXT NOT NULL DEFAULT '',
    meaning_source TEXT NOT NULL DEFAULT '',
    ipa_source     TEXT NOT NULL DEFAULT '',
    active         INTEGER NOT NULL DEFAULT 1,
    times_studied  INTEGER NOT NULL DEFAULT 0,
    last_studied   TEXT,
    created_at     TEXT,
    updated_at     TEXT
);

CREATE TABLE IF NOT EXISTS jp_words (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    word           TEXT NOT NULL UNIQUE,
    reading        TEXT NOT NULL DEFAULT '',
    meaning        TEXT NOT NULL DEFAULT '',
    accent         TEXT NOT NULL DEFAULT '',
    meaning_source TEXT NOT NULL DEFAULT '',
    accent_source  TEXT NOT NULL DEFAULT '',
    active         INTEGER NOT NULL DEFAULT 1,
    times_studied  INTEGER NOT NULL DEFAULT 0,
    last_studied   TEXT,
    created_at     TEXT,
    updated_at     TEXT
);

CREATE TABLE IF NOT EXISTS mistakes (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    lang          TEXT NOT NULL,
    word_id       INTEGER NOT NULL,
    anchor_date   TEXT NOT NULL,
    stage         INTEGER NOT NULL DEFAULT 0,
    next_due      TEXT NOT NULL,
    graduated     INTEGER NOT NULL DEFAULT 0,
    error_count   INTEGER NOT NULL DEFAULT 0,
    last_error_at TEXT,
    created_at    TEXT,
    UNIQUE(lang, word_id)
);

CREATE TABLE IF NOT EXISTS mistake_events (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    lang       TEXT NOT NULL,
    word_id    INTEGER NOT NULL,
    at         TEXT NOT NULL,
    wrong_input TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS daily_plan (
    day      TEXT NOT NULL,
    lang     TEXT NOT NULL,
    word_id  INTEGER NOT NULL,
    kind     TEXT NOT NULL,
    seq      INTEGER NOT NULL DEFAULT 0,
    answered INTEGER NOT NULL DEFAULT 0,
    correct  INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (day, lang, word_id)
);

CREATE TABLE IF NOT EXISTS daily_log (
    day       TEXT NOT NULL,
    lang      TEXT NOT NULL,
    total     INTEGER NOT NULL DEFAULT 0,
    answered  INTEGER NOT NULL DEFAULT 0,
    correct   INTEGER NOT NULL DEFAULT 0,
    completed INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (day, lang)
);

CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT);
"""


def today() -> str:
    return dt.date.today().isoformat()


def _now() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


def add_days(day: str, n: int) -> str:
    d = dt.date.fromisoformat(day)
    return (d + dt.timedelta(days=n)).isoformat()


class Database:
    def __init__(self, path: Path | str = DB_PATH):
        self.path = Path(path)
        self.conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def close(self) -> None:
        try:
            self.conn.commit()
            # 合并 WAL 并释放缓存, 关闭窗口时调用
            self.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        except Exception:
            pass
        finally:
            self.conn.close()

    # ------------------------------------------------------------ 同步源文件
    def sync_english(self, entries) -> dict:
        """把 xlsx 解析结果并入数据库, 返回统计."""
        cur = self.conn
        stats = {"new": 0, "updated": 0, "deactivated": 0}
        seen_keys: set[str] = set()
        for e in entries:
            key = e.word.lower()
            seen_keys.add(key)
            row = cur.execute("SELECT * FROM en_words WHERE key=?", (key,)).fetchone()
            if row is None:
                cur.execute(
                    "INSERT INTO en_words (word,key,meaning,meaning_source,active,"
                    "created_at,updated_at) VALUES (?,?,?,'xlsx',1,?,?)",
                    (e.word, key, e.meaning, _now(), _now()),
                )
                stats["new"] += 1
            else:
                updates, params = [], []
                if row["word"] != e.word and row["meaning_source"] != "manual":
                    updates.append("word=?")
                    params.append(e.word)
                # 人工改过的释义不动, 其余跟随源文件
                if row["meaning_source"] != "manual" and e.meaning and row["meaning"] != e.meaning:
                    updates.append("meaning=?")
                    params.append(e.meaning)
                    updates.append("meaning_source='xlsx'")
                if not row["active"]:
                    updates.append("active=1")
                if updates:
                    updates.append("updated_at=?")
                    params.append(_now())
                    params.append(row["id"])
                    cur.execute(
                        f"UPDATE en_words SET {','.join(updates)} WHERE id=?", params
                    )
                    stats["updated"] += 1
        rows = cur.execute("SELECT id,key FROM en_words WHERE active=1").fetchall()
        for r in rows:
            if r["key"] not in seen_keys:
                cur.execute("UPDATE en_words SET active=0, updated_at=? WHERE id=?", (_now(), r["id"]))
                stats["deactivated"] += 1
        cur.commit()
        return stats

    def sync_japanese(self, entries) -> dict:
        cur = self.conn
        stats = {"new": 0, "updated": 0, "deactivated": 0}
        seen: set[str] = set()
        for e in entries:
            seen.add(e.word)
            row = cur.execute("SELECT * FROM jp_words WHERE word=?", (e.word,)).fetchone()
            if row is None:
                cur.execute(
                    "INSERT INTO jp_words (word,reading,active,created_at,updated_at)"
                    " VALUES (?,?,1,?,?)",
                    (e.word, e.reading, _now(), _now()),
                )
                stats["new"] += 1
            else:
                updates, params = [], []
                if e.reading and row["reading"] != e.reading:
                    updates.append("reading=?")
                    params.append(e.reading)
                if not row["active"]:
                    updates.append("active=1")
                if updates:
                    updates.append("updated_at=?")
                    params.append(_now())
                    params.append(row["id"])
                    cur.execute(f"UPDATE jp_words SET {','.join(updates)} WHERE id=?", params)
                    stats["updated"] += 1
        rows = cur.execute("SELECT id,word FROM jp_words WHERE active=1").fetchall()
        for r in rows:
            if r["word"] not in seen:
                cur.execute("UPDATE jp_words SET active=0, updated_at=? WHERE id=?", (_now(), r["id"]))
                stats["deactivated"] += 1
        cur.commit()
        return stats

    # ------------------------------------------------------------ 查询
    def en_words(self, active_only: bool = True) -> list[sqlite3.Row]:
        sql = "SELECT * FROM en_words"
        if active_only:
            sql += " WHERE active=1"
        sql += " ORDER BY key COLLATE NOCASE"
        return self.conn.execute(sql).fetchall()

    def jp_words(self, active_only: bool = True) -> list[sqlite3.Row]:
        sql = "SELECT * FROM jp_words"
        if active_only:
            sql += " WHERE active=1"
        sql += " ORDER BY word"
        return self.conn.execute(sql).fetchall()

    def get_word(self, lang: str, word_id: int):
        table = "en_words" if lang == "en" else "jp_words"
        return self.conn.execute(f"SELECT * FROM {table} WHERE id=?", (word_id,)).fetchone()

    def missing_enrichment(self, lang: str) -> list[sqlite3.Row]:
        """返回仍缺自动补全内容的词 (音标 / 释义 / 声调)."""
        if lang == "en":
            return self.conn.execute(
                "SELECT * FROM en_words WHERE active=1 AND (ipa='' OR meaning='')"
            ).fetchall()
        return self.conn.execute(
            "SELECT * FROM jp_words WHERE active=1 AND (meaning='' OR accent='')"
        ).fetchall()

    # ------------------------------------------------------------ 人工编辑
    def update_en(self, word_id: int, *, word=None, meaning=None, ipa=None) -> None:
        sets, params = [], []
        if word is not None:
            sets += ["word=?", "key=?"]
            params += [word, word.lower()]
        if meaning is not None:
            sets += ["meaning=?", "meaning_source='manual'"]
            params.append(meaning)
        if ipa is not None:
            sets += ["ipa=?", "ipa_source='manual'"]
            params.append(ipa)
        if not sets:
            return
        sets.append("updated_at=?")
        params += [_now(), word_id]
        self.conn.execute(f"UPDATE en_words SET {','.join(sets)} WHERE id=?", params)
        self.conn.commit()

    def update_jp(self, word_id: int, *, word=None, reading=None, meaning=None, accent=None) -> None:
        sets, params = [], []
        if word is not None:
            sets.append("word=?")
            params.append(word)
        if reading is not None:
            sets.append("reading=?")
            params.append(reading)
        if meaning is not None:
            sets += ["meaning=?", "meaning_source='manual'"]
            params.append(meaning)
        if accent is not None:
            sets += ["accent=?", "accent_source='manual'"]
            params.append(accent)
        if not sets:
            return
        sets.append("updated_at=?")
        params += [_now(), word_id]
        self.conn.execute(f"UPDATE jp_words SET {','.join(sets)} WHERE id=?", params)
        self.conn.commit()

    def set_enrich(self, lang: str, word_id: int, sources: dict | None = None, **fields) -> None:
        """自动补全写入: 不覆盖 manual 内容."""
        table = "en_words" if lang == "en" else "jp_words"
        sources = sources or {}
        row = self.conn.execute(f"SELECT * FROM {table} WHERE id=?", (word_id,)).fetchone()
        if row is None:
            return
        sets, params = [], []
        for k, v in fields.items():
            if not v:
                continue
            src = f"{k}_source"
            if src in row.keys() and row[src] == "manual":
                continue
            if row[k] == v:
                continue
            sets.append(f"{k}=?")
            params.append(v)
            if src in row.keys():
                sets.append(f"{src}=?")
                params.append(sources.get(k, "auto"))
        if not sets:
            return
        sets.append("updated_at=?")
        params += [_now(), word_id]
        self.conn.execute(f"UPDATE {table} SET {','.join(sets)} WHERE id=?", params)
        self.conn.commit()

    # ------------------------------------------------------------ 错题本
    def record_wrong(self, lang: str, word_id: int, wrong_input: str = "") -> None:
        """答错: day0 = 今天, 重置整个复习阶梯."""
        day = today()
        self.conn.execute(
            "INSERT INTO mistake_events (lang,word_id,at,wrong_input) VALUES (?,?,?,?)",
            (lang, word_id, _now(), wrong_input),
        )
        row = self.conn.execute(
            "SELECT * FROM mistakes WHERE lang=? AND word_id=?", (lang, word_id)
        ).fetchone()
        nxt = add_days(day, REVIEW_OFFSETS[0])
        if row is None:
            self.conn.execute(
                "INSERT INTO mistakes (lang,word_id,anchor_date,stage,next_due,graduated,"
                "error_count,last_error_at,created_at) VALUES (?,?,?,0,?,0,1,?,?)",
                (lang, word_id, day, nxt, _now(), _now()),
            )
        else:
            self.conn.execute(
                "UPDATE mistakes SET anchor_date=?, stage=0, next_due=?, graduated=0,"
                " error_count=error_count+1, last_error_at=? WHERE id=?",
                (day, nxt, _now(), row["id"]),
            )
        self.conn.commit()

    def record_review_pass(self, lang: str, word_id: int) -> None:
        """错题复习答对: 推进到下一档; 走完 day+30 则毕业."""
        row = self.conn.execute(
            "SELECT * FROM mistakes WHERE lang=? AND word_id=?", (lang, word_id)
        ).fetchone()
        if row is None or row["graduated"]:
            return
        stage = row["stage"] + 1
        if stage >= len(REVIEW_OFFSETS):
            # 5 档全部通过 => 30 天内没有再错, 移出错题本
            self.conn.execute(
                "UPDATE mistakes SET stage=?, graduated=1, next_due='' WHERE id=?",
                (stage, row["id"]),
            )
        else:
            nxt = add_days(row["anchor_date"], REVIEW_OFFSETS[stage])
            self.conn.execute(
                "UPDATE mistakes SET stage=?, next_due=? WHERE id=?", (stage, nxt, row["id"])
            )
        self.conn.commit()

    def due_mistakes(self, lang: str, day: str | None = None) -> list[sqlite3.Row]:
        day = day or today()
        return self.conn.execute(
            "SELECT * FROM mistakes WHERE lang=? AND graduated=0 AND next_due<=?"
            " ORDER BY next_due, id",
            (lang, day),
        ).fetchall()

    def open_mistakes(self, lang: str) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM mistakes WHERE lang=? AND graduated=0 ORDER BY next_due, id",
            (lang,),
        ).fetchall()

    def graduated_mistakes(self, lang: str) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM mistakes WHERE lang=? AND graduated=1 ORDER BY last_error_at DESC",
            (lang,),
        ).fetchall()

    def mistake_event_count(self, lang: str, word_id: int) -> int:
        r = self.conn.execute(
            "SELECT COUNT(*) c FROM mistake_events WHERE lang=? AND word_id=?", (lang, word_id)
        ).fetchone()
        return r["c"] if r else 0

    def remove_mistake(self, lang: str, word_id: int) -> None:
        self.conn.execute("DELETE FROM mistakes WHERE lang=? AND word_id=?", (lang, word_id))
        self.conn.commit()

    # ------------------------------------------------------------ 每日计划
    def ensure_plan(self, lang: str, day: str | None = None) -> list[sqlite3.Row]:
        """生成/读取当天的学习清单: 新词 + 到期错题复习."""
        day = day or today()
        have = self.conn.execute(
            "SELECT COUNT(*) c FROM daily_plan WHERE day=? AND lang=?", (day, lang)
        ).fetchone()["c"]
        if have:
            return self.plan(lang, day)

        table = "en_words" if lang == "en" else "jp_words"
        target = EN_DAILY_NEW if lang == "en" else JP_DAILY_NEW

        # 1) 到期错题 —— 必须出现
        due = self.due_mistakes(lang, day)
        chosen: list[tuple[int, str]] = [(r["word_id"], "review") for r in due]

        # 2) 新词: 优先从未学过的, 不足时用最久没复习的补足
        exclude = {wid for wid, _ in chosen}
        rows = self.conn.execute(
            f"SELECT id, times_studied, last_studied FROM {table} WHERE active=1"
        ).fetchall()
        fresh = [r["id"] for r in rows if r["id"] not in exclude and r["times_studied"] == 0]
        old = sorted(
            (r for r in rows if r["id"] not in exclude and r["times_studied"] > 0),
            key=lambda r: (r["last_studied"] or "", r["id"]),
        )
        import random

        random.shuffle(fresh)
        need = max(0, target - len([c for c in chosen if c[1] == "new"]))
        picks = fresh[:need]
        if len(picks) < need:
            picks += [r["id"] for r in old[: need - len(picks)]]
        chosen += [(wid, "new") for wid in picks]

        for seq, (wid, kind) in enumerate(chosen):
            self.conn.execute(
                "INSERT OR IGNORE INTO daily_plan (day,lang,word_id,kind,seq)"
                " VALUES (?,?,?,?,?)",
                (day, lang, wid, kind, seq),
            )
        self._refresh_log(lang, day)
        self.conn.commit()
        return self.plan(lang, day)

    def plan(self, lang: str, day: str | None = None) -> list[sqlite3.Row]:
        day = day or today()
        table = "en_words" if lang == "en" else "jp_words"
        return self.conn.execute(
            f"SELECT p.*, w.* , p.word_id AS wid FROM daily_plan p"
            f" JOIN {table} w ON w.id = p.word_id"
            f" WHERE p.day=? AND p.lang=? ORDER BY p.seq",
            (day, lang),
        ).fetchall()

    def mark_answered(self, lang: str, word_id: int, correct: bool, day: str | None = None) -> None:
        day = day or today()
        table = "en_words" if lang == "en" else "jp_words"
        self.conn.execute(
            "UPDATE daily_plan SET answered=1, correct=? WHERE day=? AND lang=? AND word_id=?",
            (1 if correct else 0, day, lang, word_id),
        )
        self.conn.execute(
            f"UPDATE {table} SET times_studied=times_studied+1, last_studied=? WHERE id=?",
            (day, word_id),
        )
        self._refresh_log(lang, day)
        self.conn.commit()

    def _refresh_log(self, lang: str, day: str) -> None:
        r = self.conn.execute(
            "SELECT COUNT(*) total, SUM(answered) answered, SUM(correct) correct"
            " FROM daily_plan WHERE day=? AND lang=?",
            (day, lang),
        ).fetchone()
        total = r["total"] or 0
        answered = r["answered"] or 0
        correct = r["correct"] or 0
        completed = 1 if total > 0 and answered >= total else 0
        self.conn.execute(
            "INSERT INTO daily_log (day,lang,total,answered,correct,completed)"
            " VALUES (?,?,?,?,?,?)"
            " ON CONFLICT(day,lang) DO UPDATE SET total=excluded.total,"
            " answered=excluded.answered, correct=excluded.correct,"
            " completed=excluded.completed",
            (day, lang, total, answered, correct, completed),
        )

    def reset_plan(self, lang: str, day: str | None = None) -> None:
        """重新抽取当天单词."""
        day = day or today()
        self.conn.execute("DELETE FROM daily_plan WHERE day=? AND lang=?", (day, lang))
        self.conn.execute("DELETE FROM daily_log WHERE day=? AND lang=?", (day, lang))
        self.conn.commit()

    # ------------------------------------------------------------ 打卡
    def streak(self) -> int:
        """连续打卡天数 (完成当天任一门语言的全部单词即算打卡)."""
        rows = self.conn.execute(
            "SELECT DISTINCT day FROM daily_log WHERE completed=1 ORDER BY day DESC"
        ).fetchall()
        days = {r["day"] for r in rows}
        if not days:
            return 0
        t = dt.date.today()
        # 今天还没学完不算断签, 从昨天起算
        cur = t if t.isoformat() in days else t - dt.timedelta(days=1)
        n = 0
        while cur.isoformat() in days:
            n += 1
            cur -= dt.timedelta(days=1)
        return n

    def today_status(self, lang: str, day: str | None = None) -> tuple[int, int]:
        day = day or today()
        r = self.conn.execute(
            "SELECT COUNT(*) total, SUM(answered) answered FROM daily_plan"
            " WHERE day=? AND lang=?",
            (day, lang),
        ).fetchone()
        return (r["answered"] or 0, r["total"] or 0)

    def meta_get(self, key: str, default: str = "") -> str:
        r = self.conn.execute("SELECT v FROM meta WHERE k=?", (key,)).fetchone()
        return r["v"] if r else default

    def meta_set(self, key: str, value: str) -> None:
        self.conn.execute(
            "INSERT INTO meta (k,v) VALUES (?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v",
            (key, value),
        )
        self.conn.commit()
