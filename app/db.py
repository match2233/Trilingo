"""SQLite 数据层.

设计要点
  * 词汇英.xlsx / 词汇日.xlsx 只作为"输入源", 解析后并入本库, 源文件永不写回.
  * 每列都带 *_source 标记: 人工在【数据库】里改过的内容 (manual) 不会被
    自动补全覆盖.
  * 源文件里被删掉的词只置 active=0, 历史(错题/统计)保留.
"""
from __future__ import annotations

import datetime as dt
import json
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

-- 答题事件流: 跨设备同步的唯一真相
-- 用单词字符串而非自增 id 作键, 这样两台设备的事件可以直接合并
CREATE TABLE IF NOT EXISTS events (
    id     TEXT PRIMARY KEY,
    ts     INTEGER NOT NULL,
    device TEXT NOT NULL DEFAULT 'pc',
    lang   TEXT NOT NULL,
    word   TEXT NOT NULL,
    ok     INTEGER NOT NULL,
    day    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_day ON events(day);
CREATE INDEX IF NOT EXISTS idx_events_word ON events(lang, word);

-- 哪些事件已经应用到本机错题本表了。事件流只用于同步, 本机绝不重复应用。
CREATE TABLE IF NOT EXISTS applied_events (
    id TEXT PRIMARY KEY
);

-- 人工移出错题本的词。错题本表本身是权威, 但"移出"这个意图要随同步带给
-- 另一台设备, 所以单独记一份。
CREATE TABLE IF NOT EXISTS dropped_words (
    lang TEXT NOT NULL,
    word TEXT NOT NULL,
    at   INTEGER NOT NULL,
    PRIMARY KEY (lang, word)
);

-- ---------------------------------------------------------------- 生活记录
-- 这两张表**只在电脑端本地使用, 不参与跨设备同步**:
-- 它们不放进 events / base, state_from_db 也不会导出它们。
-- 金额一律存整数"分", 避免浮点误差；显示时再除以 100。

CREATE TABLE IF NOT EXISTS ledger (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    day        TEXT NOT NULL,
    at         TEXT NOT NULL,          -- 提交时刻 ISO, 明细里显示到秒
    kind       TEXT NOT NULL,          -- income / expense
    source     TEXT NOT NULL DEFAULT '',
    currency   TEXT NOT NULL,          -- CNY / JPY / USD
    cents      INTEGER NOT NULL,       -- 金额(分), 恒为正
    created_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_ledger_day ON ledger(day, currency);

CREATE TABLE IF NOT EXISTS deer (
    day        TEXT PRIMARY KEY,       -- 一天一条
    level      INTEGER NOT NULL,       -- 0..3
    at         TEXT NOT NULL
);

-- ---------------------------------------------------------------- 新标日测试
-- 题库本身是 data/minna_tests.json (桌面与 PWA 共用同一份), 这里只存进度。
-- 进度**不参与跨设备同步**: 每台设备各记各的, 避免再动那套脆弱的事件同步。
CREATE TABLE IF NOT EXISTS minna_progress (
    lesson      INTEGER PRIMARY KEY,
    status      TEXT NOT NULL DEFAULT 'idle',   -- idle / doing / done
    section     INTEGER NOT NULL DEFAULT 0,     -- 当前在第几大题 (恢复用)
    idx         INTEGER NOT NULL DEFAULT 0,     -- 该大题内第几小题
    seconds     INTEGER NOT NULL DEFAULT 0,     -- 用时(秒)
    score       INTEGER NOT NULL DEFAULT 0,     -- 答对数
    total       INTEGER NOT NULL DEFAULT 0,     -- 总题数
    started_at  TEXT,
    finished_at TEXT,
    updated_at  TEXT
);

-- 每道题的判定结果: 1 对 / 0 错。未答的题没有行。
CREATE TABLE IF NOT EXISTS minna_result (
    lesson  INTEGER NOT NULL,
    qid     TEXT NOT NULL,            -- 题库里的稳定 id: L01-S1-3
    ok      INTEGER NOT NULL,
    PRIMARY KEY (lesson, qid)
);
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
        """答错: 就地重置该词的复习阶梯."""
        table = "en_words" if lang == "en" else "jp_words"
        row = self.conn.execute(f"SELECT word FROM {table} WHERE id=?", (word_id,)).fetchone()
        if row is None:
            return
        self.conn.execute(
            "INSERT INTO mistake_events (lang,word_id,at,wrong_input) VALUES (?,?,?,?)",
            (lang, word_id, _now(), wrong_input),
        )
        eid, ts = self._write_event(lang, row["word"], False, today(), "pc")
        self.conn.execute("INSERT OR IGNORE INTO applied_events (id) VALUES (?)", (eid,))
        self._apply_event(lang, row["word"], False, today(), ts)
        self.conn.commit()


    def record_review_pass(self, lang: str, word_id: int) -> None:
        """复习答对: 就地推进一档, 走完毕业."""
        table = "en_words" if lang == "en" else "jp_words"
        row = self.conn.execute(f"SELECT word FROM {table} WHERE id=?", (word_id,)).fetchone()
        if row is None:
            return
        eid, ts = self._write_event(lang, row["word"], True, today(), "pc")
        self.conn.execute("INSERT OR IGNORE INTO applied_events (id) VALUES (?)", (eid,))
        self._apply_event(lang, row["word"], True, today(), ts)
        self.conn.commit()


    # ------------------------------------------------------------ 每日计划
    def local_derived(self) -> dict:
        """供每日抽词用的**本地**状态.

        直接读错题本表和学习记录 —— 本地自成闭环, 不经过事件推导。
        抽词算法本身仍是确定性的 (见 sync_core.plan_for), 所以两台设备算出的
        当日计划一致; 变的只是喂给它的数据来源: 本地表, 而不是快照+事件。
        """
        stats: dict[str, str] = {}
        mistakes: dict[str, dict] = {}
        for lang, table in (("en", "en_words"), ("jp", "jp_words")):
            for r in self.conn.execute(
                f"SELECT word, last_studied FROM {table} WHERE last_studied IS NOT NULL"
            ):
                stats[f"{lang}:{r['word']}"] = r["last_studied"]
            for r in self.conn.execute(
                f"SELECT w.word AS word, m.anchor_date AS a, m.stage AS s,"
                f" m.error_count AS e, m.graduated AS g"
                f" FROM mistakes m JOIN {table} w ON w.id = m.word_id WHERE m.lang=?",
                (lang,),
            ):
                mistakes[f"{lang}:{r['word']}"] = {
                    "a": r["a"], "s": r["s"], "e": r["e"], "g": r["g"], "t": 0,
                }
        days = {
            r["day"] for r in
            self.conn.execute("SELECT DISTINCT day FROM daily_log WHERE completed=1")
        }
        return {"stats": stats, "mistakes": mistakes, "days": days,
                "daily": {}, "done": {}, "dropped": {}}

    def derived_state(self) -> dict:
        """从 base + 本地事件推导当前状态.

        与手机端用的是同一套算法 (sync_core), 因此两台设备对"今天该考哪些词"
        的判断必然一致。
        """
        from . import sync_core as sc

        state = sc.empty_state()
        state["base"] = self.get_base()
        state["events"] = [
            dict(r) for r in self.conn.execute(
                "SELECT id AS i, ts AS t, device AS d, lang AS l, word AS w, ok AS o, day FROM events"
            )
        ]
        return sc.derive(state)

    def ensure_plan(self, lang: str, day: str | None = None) -> list[sqlite3.Row]:
        """生成/读取当天的学习清单: 新词 + 到期错题复习.

        抽词是**确定性**的 (按 fnv1a(日期|语言|单词) 排序取前 N 个),
        所以电脑和手机各自算出的当日计划完全相同, 计划本身不需要同步。
        """
        from . import sync_core as sc

        day = day or today()
        have = self.conn.execute(
            "SELECT COUNT(*) c FROM daily_plan WHERE day=? AND lang=?", (day, lang)
        ).fetchone()["c"]
        if have:
            return self.plan(lang, day)

        table = "en_words" if lang == "en" else "jp_words"
        words = [{"w": r["word"]} for r in
                 self.conn.execute(f"SELECT word FROM {table} WHERE active=1")]
        chosen = sc.plan_for(day, lang, words, self.local_derived())

        id_of = {r["word"]: r["id"] for r in
                 self.conn.execute(f"SELECT id, word FROM {table}")}
        for seq, c in enumerate(chosen):
            wid = id_of.get(c["w"])
            if wid is None:
                continue
            self.conn.execute(
                "INSERT OR IGNORE INTO daily_plan (day,lang,word_id,kind,seq)"
                " VALUES (?,?,?,?,?)",
                (day, lang, wid, c["kind"], seq),
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

    def mark_answered(self, lang: str, word_id: int, correct: bool, day: str | None = None,
                      device: str = "pc") -> None:
        day = day or today()
        table = "en_words" if lang == "en" else "jp_words"
        row = self.conn.execute(f"SELECT word FROM {table} WHERE id=?", (word_id,)).fetchone()
        self.conn.execute(
            "UPDATE daily_plan SET answered=1, correct=? WHERE day=? AND lang=? AND word_id=?",
            (1 if correct else 0, day, lang, word_id),
        )
        if row:
            # 本地: 就地更新错题本与学习统计, 立即生效, 不依赖网络, 不经过任何推导
            eid, ts = self._write_event(lang, row["word"], correct, day, device)
            self.conn.execute("INSERT OR IGNORE INTO applied_events (id) VALUES (?)", (eid,))
            self._apply_event(lang, row["word"], correct, day, ts)
        self._refresh_log(lang, day)
        self.conn.commit()

    # ------------------------------------------------------------ 错题本就地更新
    def _apply_event(self, lang: str, word: str, ok: bool, day: str,
                     ts: int | None = None) -> None:
        """把一条作答**就地**应用到错题本表.

        这是同步功能之前的老逻辑, 也是唯一正确的本地逻辑: 错题本是一张自己
        维护的表, 不是从别处推导出来的。推导有个致命弱点 —— 一旦作为输入的
        快照和事件对不上, 整个错题本跟着错。本机必须自成闭环。
        """
        table = "en_words" if lang == "en" else "jp_words"
        row = self.conn.execute(f"SELECT id FROM {table} WHERE word=?", (word,)).fetchone()
        if row is None:
            return
        wid = row["id"]

        # 学习统计也要就地更新: 每日抽词靠 times_studied/last_studied 区分
        # "从没学过"和"学过但生疏", 漏了这一步两台设备会抽出不同的词。
        self.conn.execute(
            f"UPDATE {table} SET times_studied=times_studied+1, last_studied=? WHERE id=?",
            (day, wid),
        )

        # 人工移出过的词: 只有当这次作答晚于移出时刻, 才重新收进来
        if ts is not None:
            d = self.conn.execute(
                "SELECT at FROM dropped_words WHERE lang=? AND word=?", (lang, word)
            ).fetchone()
            if d is not None:
                if ts <= d["at"]:
                    return
                self.conn.execute(
                    "DELETE FROM dropped_words WHERE lang=? AND word=?", (lang, word)
                )

        m = self.conn.execute(
            "SELECT * FROM mistakes WHERE lang=? AND word_id=?", (lang, wid)
        ).fetchone()
        if not ok:
            nxt = add_days(day, REVIEW_OFFSETS[0])
            if m is None:
                self.conn.execute(
                    "INSERT INTO mistakes (lang,word_id,anchor_date,stage,next_due,"
                    "graduated,error_count,last_error_at,created_at)"
                    " VALUES (?,?,?,0,?,0,1,?,?)",
                    (lang, wid, day, nxt, _now(), _now()),
                )
            else:
                self.conn.execute(
                    "UPDATE mistakes SET anchor_date=?, stage=0, next_due=?, graduated=0,"
                    " error_count=error_count+1, last_error_at=? WHERE id=?",
                    (day, nxt, _now(), m["id"]),
                )
        else:
            if m is None or m["graduated"]:
                return
            stage = m["stage"] + 1
            if stage >= len(REVIEW_OFFSETS):
                self.conn.execute(
                    "UPDATE mistakes SET stage=?, graduated=1, next_due='' WHERE id=?",
                    (stage, m["id"]),
                )
            else:
                self.conn.execute(
                    "UPDATE mistakes SET stage=?, next_due=? WHERE id=?",
                    (stage, add_days(m["anchor_date"], REVIEW_OFFSETS[stage]), m["id"]),
                )

    def apply_remote_events(self, events: list[dict], since_ts: int = 0,
                            folded: dict | None = None) -> int:
        """把另一台设备的作答**就地**应用到本机错题本.

        只处理本机还没应用过的事件 (applied_events 里没有的), 所以同一批作答
        绝不会被算两遍。不做整表重建 —— 那会把本机的人工修改和立即复习一起抹掉。

        since_ts: 对方的快照已覆盖到的时间点。早于它的事件效果已经在那份快照里,
        再播一遍就是重复计算 —— 表现是档位莫名其妙偏高。
        """
        applied = {r["id"] for r in self.conn.execute("SELECT id FROM applied_events")}
        folded = folded or {}
        seen: dict[str, int] = {}
        todo = []
        for e in events:
            if not e.get("i") or e["i"] in applied:
                continue
            if int(e.get("t") or 0) <= since_ts:
                continue
            # 对方快照已按「日期|语言」记下覆盖了前 N 条, 这 N 条不再重播
            pair = f"{e.get('day', '')}|{e.get('l', '')}"
            k = seen.get(pair, 0)
            seen[pair] = k + 1
            if k < int(folded.get(pair) or 0):
                continue
            todo.append(e)
        todo.sort(key=lambda e: (e.get("t", 0), e.get("i", "")))
        n = 0
        for e in todo:
            self._apply_event(e.get("l", ""), e.get("w", ""), bool(e.get("o")),
                              e.get("day", ""), int(e.get("t", 0)))
            self.conn.execute("INSERT OR IGNORE INTO applied_events (id) VALUES (?)", (e["i"],))
            n += 1
        if n:
            self.conn.commit()
        return n

    def _write_event(self, lang: str, word: str, ok: bool, day: str,
                     device: str) -> tuple[str, int]:
        """写一条作答事件 (仅用于同步导出), 返回 (事件 id, 时间戳)。"""
        import uuid

        ts = int(dt.datetime.now().timestamp() * 1000)
        eid = f"{ts:013d}{uuid.uuid4().hex[:8]}"
        self.conn.execute(
            "INSERT OR IGNORE INTO events (id,ts,device,lang,word,ok,day) VALUES (?,?,?,?,?,?,?)",
            (eid, ts, device, lang, word, 1 if ok else 0, day),
        )
        return eid, ts

    # ------------------------------------------------------------ 事件流
    def add_event(self, lang: str, word: str, ok: bool, day: str | None = None,
                  device: str = "pc") -> None:
        """记录一次作答. 跨设备同步以事件流为准, 错题本与打卡由它推导.

        时间戳用**毫秒**: 连续答题常常落在同一秒内, 用秒级时间戳会让事件
        顺序退化成按 id (随机) 排, 于是"答错重置"和"复习推进"的先后会被打乱。
        id 再带上时间前缀, 同一毫秒内也能确定性排序。
        """
        import uuid

        day = day or today()
        ts = int(dt.datetime.now().timestamp() * 1000)
        eid = f"{ts:013d}{uuid.uuid4().hex[:8]}"
        self.conn.execute(
            "INSERT OR IGNORE INTO events (id,ts,device,lang,word,ok,day) VALUES (?,?,?,?,?,?,?)",
            (eid, ts, device, lang, word, 1 if ok else 0, day),
        )

    def import_events(self, events: list[dict]) -> int:
        """把远端事件并入本地, 已存在的按 id 跳过."""
        n = 0
        for e in events:
            cur = self.conn.execute(
                "INSERT OR IGNORE INTO events (id,ts,device,lang,word,ok,day)"
                " VALUES (?,?,?,?,?,?,?)",
                (e.get("i"), e.get("t", 0), e.get("d", "?"), e.get("l", ""),
                 e.get("w", ""), 1 if e.get("o") else 0, e.get("day", "")),
            )
            n += cur.rowcount
        self.conn.commit()
        return n

    # ------------------------------------------------------------ 同步用
    def get_base(self) -> dict:
        """同步基准. 首次调用时做一次引导快照, 之后冻结、只由压缩更新.

        引导时必须同时清空已有事件: 快照读的是**当前**错题本, 里面已经包含
        了那些事件的效果。若不清空, 推导时会把它们再叠加一遍 —— 错一次的
        词会变成错两次。
        """
        from . import sync_core as sc

        raw = self.meta_get("sync_base", "")
        if raw:
            try:
                base = json.loads(raw)
                changed = False
                if "done" not in base:
                    # 早期版本的快照没有 done 字段, 从当天计划补出来,
                    # 否则另一台设备看不到本机的完成进度
                    base["done"] = self._done_from_plan()
                    changed = True
                if not base.get("folded") and not base.get("folded_ts"):
                    # 旧格式快照既没有折叠点也没有按天计数, 与现存事件互相重叠,
                    # 同一次作答会被算两遍 —— 第二次遇到"答错"就把档位打了回去。
                    # 用 done 补出"每天每语言已并入快照多少条", 正好描述其覆盖范围。
                    # 今天要排除在外: 快照的 done 记了今天的作答数, 但 mistakes
                    # 里未必反映了它们(两者会自相矛盾)。排除今天, 让补齐逻辑
                    # 去补今天的缺失事件, 才能真正把进度推进回来。
                    today = dt.date.today().isoformat()
                    base["folded"] = {
                        f"{d}|{lang}": int(c or 0)
                        for d, langs in (base.get("done") or {}).items()
                        if d != today
                        for lang, c in (langs or {}).items()
                        if c
                    }
                    changed = True
                if changed:
                    self.meta_set("sync_base", json.dumps(base, ensure_ascii=False))
                    self.conn.commit()
                return base
            except Exception:
                pass

        # 快照现有的全部状态。**不删事件**: 靠 folded_ts 让推导跳过它们即可
        # —— 删掉的事件是不可再生的, 一旦快照重建就永久丢失。
        row = self.conn.execute("SELECT COALESCE(MAX(ts), 0) t FROM events").fetchone()
        base = sc.build_base_from_db(self, folded_ts=int(row["t"] or 0))
        self.meta_set("sync_base", json.dumps(base, ensure_ascii=False))
        self.conn.commit()
        return base

    def reset_today(self, day: str | None = None) -> dict:
        """清空"今天", 回到今天开始前的状态.

        错题本是从事件流推导的, 删掉今天的事件就会自动回退。但快照 base 是在
        今天作答**之后**才拍的, "复习答对 -> 档位 +1" 记在里面, 事件流里没有,
        所以这一部分要照着当日计划的 kind='review' 逐条退回去。
        """
        from . import sync_core as sc

        day = day or today()
        base = self.get_base()

        rolled = 0
        for lang, table in (("en", "en_words"), ("jp", "jp_words")):
            # 必须限定 answered=1: 计划里当天没做过的词也在表里,
            # 不加这个条件会把它们的档位一并重置, 属于损坏数据。
            rows = self.conn.execute(
                f"SELECT w.word AS word, p.correct AS correct"
                f" FROM daily_plan p JOIN {table} w ON w.id = p.word_id"
                " WHERE p.day=? AND p.lang=? AND p.kind='review' AND p.answered=1",
                (day, lang),
            ).fetchall()
            for r in rows:
                m = base["mistakes"].get(f"{lang}:{r['word']}")
                if not m or m.get("g"):
                    continue
                if r["correct"]:
                    m["s"] = max(0, (m.get("s") or 0) - 1)
                else:
                    m["a"] = sc.add_days(day, -1)
                    m["s"] = 0
                rolled += 1

        # 今天首答就错的词也会写进 base, 把 day0 挪回去让它重新到期
        for m in base["mistakes"].values():
            if m.get("a") == day and not m.get("g"):
                m["a"] = sc.add_days(day, -1)
                rolled += 1

        base["days"] = [d for d in base.get("days", []) if d != day]
        (base.get("done") or {}).pop(day, None)
        self.set_base(base)

        n_ev = self.conn.execute("DELETE FROM events WHERE day=?", (day,)).rowcount
        self.conn.execute("DELETE FROM daily_plan WHERE day=?", (day,))
        self.conn.execute("DELETE FROM daily_log WHERE day=?", (day,))
        self.conn.commit()
        return {"rolled": rolled, "events": n_ev}


    def _done_from_plan(self) -> dict:
        """每天每门语言已答多少题 —— 从当日计划统计."""
        out: dict[str, dict[str, int]] = {}
        for r in self.conn.execute(
            "SELECT day, lang, SUM(answered) a FROM daily_plan GROUP BY day, lang"
        ):
            if r["a"]:
                out.setdefault(r["day"], {})[r["lang"]] = int(r["a"])
        return out

    def set_base(self, base: dict) -> None:
        self.meta_set("sync_base", json.dumps(base, ensure_ascii=False))

    def get_edits(self) -> dict:
        """人工改过的词条 —— 同步时优先级最高, 不会被自动内容覆盖."""
        edits: dict[str, dict] = {}
        for r in self.conn.execute(
            "SELECT word,meaning,ipa,meaning_source,ipa_source FROM en_words"
        ):
            if r["meaning_source"] != "manual" and r["ipa_source"] != "manual":
                continue
            e: dict = {}
            if r["meaning_source"] == "manual":
                e["m"] = r["meaning"]
            if r["ipa_source"] == "manual":
                e["ipa"] = r["ipa"]
            edits[f"en:{r['word']}"] = e
        for r in self.conn.execute(
            "SELECT word,reading,meaning,accent,meaning_source,accent_source FROM jp_words"
        ):
            if r["meaning_source"] != "manual" and r["accent_source"] != "manual":
                continue
            e = {}
            if r["meaning_source"] == "manual":
                e["m"] = r["meaning"]
            if r["accent_source"] == "manual":
                e["ac"] = r["accent"]
            if r["reading"]:
                e["r"] = r["reading"]
            edits[f"jp:{r['word']}"] = e
        return edits

    def apply_synced_en(self, rec: dict) -> None:
        self._apply_synced("en_words", "word", rec, {"m": "meaning", "ipa": "ipa"})

    def apply_synced_jp(self, rec: dict) -> None:
        self._apply_synced("jp_words", "word", rec,
                           {"m": "meaning", "ac": "accent", "r": "reading"})

    def _apply_synced(self, table: str, key: str, rec: dict, mapping: dict) -> None:
        """把同步来的字段写入本地词条. 本地人工编辑过的不覆盖."""
        row = self.conn.execute(f"SELECT * FROM {table} WHERE {key}=?", (rec.get("w"),)).fetchone()
        if row is None:
            return
        sets, params = [], []
        for src, col in mapping.items():
            val = rec.get(src)
            if val in (None, ""):
                continue
            if col in ("meaning", "accent") and row[f"{col}_source"] == "manual":
                continue
            if row[col] == val:
                continue
            sets.append(f"{col}=?")
            params.append(val)
        if sets:
            sets.append("updated_at=?")
            params += [_now(), row["id"]]
            self.conn.execute(f"UPDATE {table} SET {','.join(sets)} WHERE id=?", params)
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
        """重新抽取当天单词 (会丢弃当天已答记录, 仅在用户明确要求时使用)."""
        day = day or today()
        self.conn.execute("DELETE FROM daily_plan WHERE day=? AND lang=?", (day, lang))
        self.conn.execute("DELETE FROM daily_log WHERE day=? AND lang=?", (day, lang))
        self.conn.commit()



    def mistake_words(self) -> set[tuple[str, str]]:
        """本机错题本里已有的 (语言, 单词). 供同步判断事件要不要重播."""
        out: set[tuple[str, str]] = set()
        for lang, table in (("en", "en_words"), ("jp", "jp_words")):
            for r in self.conn.execute(
                f"SELECT w.word AS word FROM mistakes m JOIN {table} w"
                " ON w.id = m.word_id WHERE m.lang=?", (lang,)
            ):
                out.add((lang, r["word"]))
        return out

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


    def remove_mistake(self, lang: str, word_id: int) -> None:
        """把单词移出错题本.

        错题本表就是权威, 直接从表里删掉即可 —— 不存在"下次刷新又回来"。
        另外记一份到 dropped_words: 移出这个**意图**要随同步带给另一台设备。
        """
        table = "en_words" if lang == "en" else "jp_words"
        row = self.conn.execute(f"SELECT word FROM {table} WHERE id=?", (word_id,)).fetchone()
        if row is None:
            return
        self.conn.execute("DELETE FROM mistakes WHERE lang=? AND word_id=?", (lang, word_id))
        self.conn.execute(
            "INSERT INTO dropped_words (lang,word,at) VALUES (?,?,?)"
            " ON CONFLICT(lang,word) DO UPDATE SET at=excluded.at",
            (lang, row["word"], int(dt.datetime.now().timestamp() * 1000)),
        )
        self.conn.commit()

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



    def add_to_today(self, lang: str, word_id: int, kind: str = "review",
                     day: str | None = None) -> None:
        """把某个词补进当天计划, 不触碰其它词已有的作答记录."""
        day = day or today()
        have = self.conn.execute(
            "SELECT COUNT(*) c FROM daily_plan WHERE day=? AND lang=?", (day, lang)
        ).fetchone()["c"]
        if not have:
            self.ensure_plan(lang, day)      # 当天还没计划, 正常生成
            return

        row = self.conn.execute(
            "SELECT answered FROM daily_plan WHERE day=? AND lang=? AND word_id=?",
            (day, lang, word_id),
        ).fetchone()
        if row is None:
            nxt = self.conn.execute(
                "SELECT COALESCE(MAX(seq), -1) + 1 s FROM daily_plan WHERE day=? AND lang=?",
                (day, lang),
            ).fetchone()["s"]
            self.conn.execute(
                "INSERT INTO daily_plan (day,lang,word_id,kind,seq) VALUES (?,?,?,?,?)",
                (day, lang, word_id, kind, nxt),
            )
        elif row["answered"]:
            # 今天已考过, 重置为未答让它重新出现 (当天只影响这一个词)
            self.conn.execute(
                "UPDATE daily_plan SET answered=0, correct=0"
                " WHERE day=? AND lang=? AND word_id=?",
                (day, lang, word_id),
            )
        self._refresh_log(lang, day)
        self.conn.commit()

    def remove_from_today(self, lang: str, word_id: int, day: str | None = None) -> None:
        """只把某个词移出当天计划, 其它词的进度不受影响."""
        day = day or today()
        self.conn.execute(
            "DELETE FROM daily_plan WHERE day=? AND lang=? AND word_id=?",
            (day, lang, word_id),
        )
        self._refresh_log(lang, day)
        self.conn.commit()

    # ------------------------------------------------------------ 备份
    def backup(self, keep: int = 10) -> Path | None:
        """把当前数据库快照存到 backups/, 保留最近 keep 份.

        用 SQLite 自己的备份接口, 运行中也能安全复制。
        """
        try:
            import datetime as _dt

            bdir = self.path.parent / "backups"
            bdir.mkdir(exist_ok=True)
            stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
            dest = bdir / f"trilingo-{stamp}.db"

            target = sqlite3.connect(str(dest))
            try:
                self.conn.backup(target)
            finally:
                target.close()

            # 只保留最近 keep 份
            old = sorted(bdir.glob("trilingo-*.db"))
            for f in old[:-keep]:
                f.unlink(missing_ok=True)
            return dest
        except Exception:
            return None

    # ------------------------------------------------------------ 打卡
    def streak(self) -> int:
        """连续打卡天数 (完成当天任一门语言的全部单词即算打卡).

        直接读本机的 daily_log —— 本地自成闭环, 不经过事件推导。
        """
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

    # ------------------------------------------------------------ 学习概况
    def studied_count(self, lang: str) -> tuple[int, int]:
        """(已学词条数, 全部在用词条数).

        已学 = 学习次数 > 0。这个计数由 _apply_event 就地维护, 与错题本同步,
        不会因为网络或事件重播而漂移。
        """
        table = "en_words" if lang == "en" else "jp_words"
        r = self.conn.execute(
            f"SELECT COUNT(*) total, SUM(CASE WHEN times_studied>0 THEN 1 ELSE 0 END) done"
            f" FROM {table} WHERE active=1"
        ).fetchone()
        return int(r["done"] or 0), int(r["total"] or 0)

    # ------------------------------------------------------------ 生活记录
    # 全部只写本机 SQLite, 不进 events / base, 因此天然不参与跨设备同步。

    def ledger_add(self, kind: str, source: str, currency: str, cents: int,
                   day: str | None = None) -> int:
        """记一笔收支, 返回新记录 id. 同一天可以提交任意多次."""
        now = dt.datetime.now()
        cur = self.conn.execute(
            "INSERT INTO ledger (day,at,kind,source,currency,cents,created_at)"
            " VALUES (?,?,?,?,?,?,?)",
            (day or now.date().isoformat(), now.isoformat(timespec="seconds"),
             kind, source, currency, int(cents), _now()),
        )
        self.conn.commit()
        return int(cur.lastrowid or 0)

    def ledger_del(self, entry_id: int) -> None:
        self.conn.execute("DELETE FROM ledger WHERE id=?", (entry_id,))
        self.conn.commit()

    def ledger_all(self, currency: str) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM ledger WHERE currency=? ORDER BY at DESC, id DESC",
            (currency,),
        ).fetchall()

    def ledger_totals(self, currency: str) -> dict:
        """某币种的总收入 / 总支出 / 总余额."""
        r = self.conn.execute(
            "SELECT"
            " COALESCE(SUM(CASE WHEN kind='income'  THEN cents END),0) inc,"
            " COALESCE(SUM(CASE WHEN kind='expense' THEN cents END),0) exp"
            " FROM ledger WHERE currency=?",
            (currency,),
        ).fetchone()
        inc, exp = int(r["inc"]), int(r["exp"])
        return {"income": inc, "expense": exp, "balance": inc - exp}

    def ledger_daily(self, currency: str, start: str, end: str) -> dict[str, dict]:
        """[start,end] 内按天汇总: {day: {inc, exp}}."""
        out: dict[str, dict] = {}
        for r in self.conn.execute(
            "SELECT day,"
            " COALESCE(SUM(CASE WHEN kind='income'  THEN cents END),0) inc,"
            " COALESCE(SUM(CASE WHEN kind='expense' THEN cents END),0) exp"
            " FROM ledger WHERE currency=? AND day BETWEEN ? AND ?"
            " GROUP BY day",
            (currency, start, end),
        ):
            out[r["day"]] = {"inc": int(r["inc"]), "exp": int(r["exp"])}
        return out

    def ledger_month(self, currency: str, year: int, month: int) -> dict:
        """某月总收支."""
        pre = f"{year:04d}-{month:02d}"
        r = self.conn.execute(
            "SELECT"
            " COALESCE(SUM(CASE WHEN kind='income'  THEN cents END),0) inc,"
            " COALESCE(SUM(CASE WHEN kind='expense' THEN cents END),0) exp,"
            " COUNT(*) n"
            " FROM ledger WHERE currency=? AND day LIKE ?",
            (currency, pre + "%"),
        ).fetchone()
        inc, exp = int(r["inc"]), int(r["exp"])
        return {"income": inc, "expense": exp, "balance": inc - exp, "count": int(r["n"])}

    # ------------------------------------------------------------ 记鹿
    def deer_set(self, day: str, level: int) -> None:
        """记下某天的鹿次数. 一天只留一条 —— 再按就是覆盖当天的值."""
        level = max(0, min(3, int(level)))
        self.conn.execute(
            "INSERT INTO deer (day,level,at) VALUES (?,?,?)"
            " ON CONFLICT(day) DO UPDATE SET level=excluded.level, at=excluded.at",
            (day, level, _now()),
        )
        self.conn.commit()

    def deer_del(self, day: str) -> None:
        self.conn.execute("DELETE FROM deer WHERE day=?", (day,))
        self.conn.commit()

    def deer_get(self, day: str) -> int | None:
        r = self.conn.execute("SELECT level FROM deer WHERE day=?", (day,)).fetchone()
        return int(r["level"]) if r else None

    def deer_month(self, year: int, month: int) -> dict[str, int]:
        pre = f"{year:04d}-{month:02d}"
        return {
            r["day"]: int(r["level"]) for r in self.conn.execute(
                "SELECT day, level FROM deer WHERE day LIKE ?", (pre + "%",)
            )
        }

    # ------------------------------------------------------------ 新标日测试
    def minna_all_progress(self) -> dict[int, sqlite3.Row]:
        """每课进度, 按课号索引."""
        return {
            int(r["lesson"]): r
            for r in self.conn.execute("SELECT * FROM minna_progress")
        }

    def minna_progress(self, lesson: int) -> sqlite3.Row | None:
        return self.conn.execute(
            "SELECT * FROM minna_progress WHERE lesson=?", (lesson,)).fetchone()

    def minna_start(self, lesson: int, total: int) -> None:
        """开始一课: 计时起点, 清掉该课上一次作答结果."""
        now = _now()
        self.conn.execute("DELETE FROM minna_result WHERE lesson=?", (lesson,))
        self.conn.execute(
            "INSERT INTO minna_progress"
            " (lesson,status,section,idx,seconds,score,total,started_at,finished_at,updated_at)"
            " VALUES (?,?,0,0,0,0,?,?,NULL,?)"
            " ON CONFLICT(lesson) DO UPDATE SET"
            " status='doing', section=0, idx=0, seconds=0, score=0,"
            " total=excluded.total, started_at=excluded.started_at,"
            " finished_at=NULL, updated_at=excluded.updated_at",
            (lesson, "doing", total, now, now),
        )
        self.conn.commit()

    def minna_save_cursor(self, lesson: int, section: int, idx: int,
                          seconds: int, score: int) -> None:
        """中途退出时保存位置 (不改 status, 仍是 doing)."""
        self.conn.execute(
            "UPDATE minna_progress SET section=?, idx=?, seconds=?, score=?,"
            " updated_at=? WHERE lesson=?",
            (section, idx, seconds, score, _now(), lesson),
        )
        self.conn.commit()

    def minna_mark(self, lesson: int, qid: str, ok: bool) -> None:
        self.conn.execute(
            "INSERT INTO minna_result (lesson,qid,ok) VALUES (?,?,?)"
            " ON CONFLICT(lesson,qid) DO UPDATE SET ok=excluded.ok",
            (lesson, qid, 1 if ok else 0),
        )
        self.conn.commit()

    def minna_finish(self, lesson: int, seconds: int, score: int, total: int) -> None:
        now = _now()
        self.conn.execute(
            "UPDATE minna_progress SET status='done', seconds=?, score=?, total=?,"
            " finished_at=?, updated_at=? WHERE lesson=?",
            (seconds, score, total, now, now, lesson),
        )
        self.conn.commit()

    def minna_results(self, lesson: int) -> dict[str, bool]:
        return {
            r["qid"]: bool(r["ok"]) for r in self.conn.execute(
                "SELECT qid, ok FROM minna_result WHERE lesson=?", (lesson,))
        }

    def minna_reset(self, lesson: int) -> None:
        """重做这一课: 清空进度与结果."""
        self.conn.execute("DELETE FROM minna_result WHERE lesson=?", (lesson,))
        self.conn.execute("DELETE FROM minna_progress WHERE lesson=?", (lesson,))
        self.conn.commit()

    # ------------------------------------------------------------ 同步用 (生活记录 / 测试)
    def export_life(self) -> dict:
        """生活记录打包成可同步的结构. 只增不删, 合并时按内容去重."""
        ledger = [
            {"at": r["at"], "day": r["day"], "kind": r["kind"],
             "source": r["source"], "currency": r["currency"],
             "cents": int(r["cents"])}
            for r in self.conn.execute("SELECT * FROM ledger ORDER BY at, id")
        ]
        deer = {
            r["day"]: {"lv": int(r["level"]), "at": r["at"] or ""}
            for r in self.conn.execute("SELECT day, level, at FROM deer")
        }
        return {"ledger": ledger, "deer": deer}

    def apply_life(self, life: dict) -> int:
        """把同步来的生活记录并入本机. 返回新增条数."""
        added = 0
        for e in (life or {}).get("ledger") or []:
            if not isinstance(e, dict):
                continue
            row = self.conn.execute(
                "SELECT 1 FROM ledger WHERE at=? AND kind=? AND currency=?"
                " AND cents=? AND source=?",
                (e.get("at", ""), e.get("kind", ""), e.get("currency", ""),
                 int(e.get("cents") or 0), e.get("source", "")),
            ).fetchone()
            if row:
                continue
            self.conn.execute(
                "INSERT INTO ledger (day,at,kind,source,currency,cents,created_at)"
                " VALUES (?,?,?,?,?,?,?)",
                (e.get("day", ""), e.get("at", ""), e.get("kind", ""),
                 e.get("source", ""), e.get("currency", ""),
                 int(e.get("cents") or 0), _now()),
            )
            added += 1
        for day, rec in ((life or {}).get("deer") or {}).items():
            if not isinstance(rec, dict):
                continue
            cur = self.conn.execute(
                "SELECT at FROM deer WHERE day=?", (day,)).fetchone()
            at = str(rec.get("at", ""))
            if cur is not None and str(cur["at"] or "") > at:
                continue                      # 本机这份更新
            self.conn.execute(
                "INSERT INTO deer (day,level,at) VALUES (?,?,?)"
                " ON CONFLICT(day) DO UPDATE SET level=excluded.level, at=excluded.at",
                (day, max(0, min(3, int(rec.get("lv") or 0))), at or _now()),
            )
            added += 1
        if added:
            self.conn.commit()
        return added

    def export_minna(self) -> dict:
        """每课进度 + 该课每题的判定结果."""
        out: dict[str, dict] = {}
        for r in self.conn.execute("SELECT * FROM minna_progress"):
            les = int(r["lesson"])
            results = {
                x["qid"]: bool(x["ok"])
                for x in self.conn.execute(
                    "SELECT qid, ok FROM minna_result WHERE lesson=?", (les,))
            }
            out[str(les)] = {
                "status": r["status"], "section": int(r["section"] or 0),
                "idx": int(r["idx"] or 0), "seconds": int(r["seconds"] or 0),
                "score": int(r["score"] or 0), "total": int(r["total"] or 0),
                "updated_at": r["updated_at"] or "", "results": results,
            }
        return out

    def apply_minna(self, minna: dict) -> int:
        """并入另一台设备的测试进度: 每课取较新的那份."""
        added = 0
        for key, rec in (minna or {}).items():
            if not isinstance(rec, dict):
                continue
            try:
                les = int(key)
            except (TypeError, ValueError):
                continue
            cur = self.conn.execute(
                "SELECT updated_at FROM minna_progress WHERE lesson=?",
                (les,)).fetchone()
            cur_at = str(cur["updated_at"] or "") if cur else ""
            new_at = str(rec.get("updated_at") or "")
            if cur_at and new_at < cur_at:
                continue
            if cur_at and new_at == cur_at:
                continue                      # 同一时刻, 以本机为准
            self.conn.execute(
                "INSERT INTO minna_progress"
                " (lesson,status,section,idx,seconds,score,total,started_at,finished_at,updated_at)"
                " VALUES (?,?,?,?,?,?,?,NULL,NULL,?)"
                " ON CONFLICT(lesson) DO UPDATE SET status=excluded.status,"
                " section=excluded.section, idx=excluded.idx, seconds=excluded.seconds,"
                " score=excluded.score, total=excluded.total, updated_at=excluded.updated_at",
                (les, rec.get("status", "idle"), int(rec.get("section") or 0),
                 int(rec.get("idx") or 0), int(rec.get("seconds") or 0),
                 int(rec.get("score") or 0), int(rec.get("total") or 0), new_at or _now()),
            )
            self.conn.execute("DELETE FROM minna_result WHERE lesson=?", (les,))
            for qid, ok in (rec.get("results") or {}).items():
                self.conn.execute(
                    "INSERT OR REPLACE INTO minna_result (lesson,qid,ok) VALUES (?,?,?)",
                    (les, qid, 1 if ok else 0),
                )
            added += 1
        if added:
            self.conn.commit()
        return added
