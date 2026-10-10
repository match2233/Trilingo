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
    def refresh_mistakes(self) -> None:
        """按事件流重建错题本表.

        mistakes 表是**派生缓存**, 真相在事件流里。每次作答后重建, 才能保证
        「表里有的」和「推导出来的」永远一致 —— 否则旧代码路径写表、新代码路径
        写事件, 两边会分家, 表现为"错题到期了却不出现"。
        """
        der = self.derived_state()

        # 已经失效的"移出"记录要清掉: 推导时靠时间戳能绕过它, 但留着会越积越多
        base = self.get_base()
        if set(base.get("dropped") or {}) != set(der.get("dropped") or {}):
            base["dropped"] = der.get("dropped") or {}
            self.set_base(base)

        ids: dict[str, int] = {}
        for lang, table in (("en", "en_words"), ("jp", "jp_words")):
            for r in self.conn.execute(f"SELECT id, word FROM {table}"):
                ids[f"{lang}:{r['word']}"] = r["id"]

        self.conn.execute("DELETE FROM mistakes")
        from .sync_core import next_due

        for key, m in der["mistakes"].items():
            wid = ids.get(key)
            if wid is None:
                continue
            lang, _ = key.split(":", 1)
            self.conn.execute(
                "INSERT INTO mistakes (lang,word_id,anchor_date,stage,next_due,"
                "graduated,error_count,last_error_at,created_at)"
                " VALUES (?,?,?,?,?,?,?,?,?)",
                (lang, wid, m["a"], m["s"], next_due(m) or "",
                 1 if m.get("g") else 0, m.get("e", 0), "", _now()),
            )

    def record_wrong(self, lang: str, word_id: int, wrong_input: str = "") -> None:
        """答错. 记一条事件, 错题本与排期由事件流推导."""
        table = "en_words" if lang == "en" else "jp_words"
        row = self.conn.execute(f"SELECT word FROM {table} WHERE id=?", (word_id,)).fetchone()
        if row is None:
            return
        self.conn.execute(
            "INSERT INTO mistake_events (lang,word_id,at,wrong_input) VALUES (?,?,?,?)",
            (lang, word_id, _now(), wrong_input),
        )
        self.add_event(lang, row["word"], False)
        self.refresh_mistakes()
        self.conn.commit()

    def record_review_pass(self, lang: str, word_id: int) -> None:
        """错题复习答对. 同样记事件, 推进/毕业由推导决定."""
        table = "en_words" if lang == "en" else "jp_words"
        row = self.conn.execute(f"SELECT word FROM {table} WHERE id=?", (word_id,)).fetchone()
        if row is None:
            return
        key = f"{lang}:{row['word']}"
        m = self.derived_state()["mistakes"].get(key)
        if not m or m.get("g"):
            return
        self.add_event(lang, row["word"], True)
        self.refresh_mistakes()
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
        """把单词永久移出错题本.

        mistakes 表是**派生缓存**, 直接删表没有用 —— 下一次 refresh_mistakes
        就会把它从 base + 事件重建回来, 表现就是"移出后重开软件又回来了"。
        必须把"移出"这件事记进权威状态 base。
        """
        table = "en_words" if lang == "en" else "jp_words"
        row = self.conn.execute(f"SELECT word FROM {table} WHERE id=?", (word_id,)).fetchone()
        if row is None:
            return
        base = self.get_base()
        dropped = base.setdefault("dropped", {})
        # 必须用**毫秒**: 事件流的时间戳是毫秒, 这里若写秒, 推导里
        # 「事件时间 > 移出时间」会恒成立, 移出记录一写就失效。
        dropped[f"{lang}:{row['word']}"] = int(dt.datetime.now().timestamp() * 1000)
        self.set_base(base)
        self.refresh_mistakes()
        self.conn.commit()

    # ------------------------------------------------------------ 每日计划
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
        chosen = sc.plan_for(day, lang, words, self.derived_state())

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
        self.conn.execute(
            f"UPDATE {table} SET times_studied=times_studied+1, last_studied=? WHERE id=?",
            (day, word_id),
        )
        if row:
            self.add_event(lang, row["word"], correct, day, device)
            self.refresh_mistakes()      # 错题本是派生缓存, 随事件流刷新
        self._refresh_log(lang, day)
        self.conn.commit()

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
                if "done" not in base:
                    # 早期版本的快照没有 done 字段, 从当天计划补出来,
                    # 否则另一台设备看不到本机的完成进度
                    base["done"] = self._done_from_plan()
                    self.meta_set("sync_base", json.dumps(base, ensure_ascii=False))
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
        self.refresh_mistakes()
        self.conn.commit()
        return {"rolled": rolled, "events": n_ev}

    def repair_events_from_plan(self) -> int:
        """把「计划里已答、但事件流里没有」的记录补成事件.

        早期版本的作答没有写事件流, 于是错题本推不出这些作答的效果 ——
        表现就是"明明做完了, 错题本却毫无变化"。

        判断依据是**数量**, 不是日期: 逐 (日期, 语言) 比较「计划里已答多少」
        与「base 里记了多少」。只有当计划明显更多时, 才说明有作答没进事件流。
        按日期整体跳过是不对的 —— 同一天可能一部分作进了快照、另一部分没有。
        """
        base = self.get_base()
        base_done = base.get("done") or {}
        day = today()
        done_key = f"repaired:{day}"

        # 只处理当天, 且当天只补一次 —— 历史日期要么已在 base 里、要么已同步,
        # 反复补会把同一次作答算两遍。留个标记避免重复。
        if self.meta_get(done_key, "") == "1":
            return 0

        fixed = 0
        for lang, table in (("en", "en_words"), ("jp", "jp_words")):
            days = self.conn.execute(
                "SELECT day, COALESCE(SUM(answered), 0) a FROM daily_plan"
                " WHERE lang=? AND answered=1 AND day=? GROUP BY day",
                (lang, day),
            ).fetchall()
            for d in days:
                if (d["a"] or 0) <= int((base_done.get(day) or {}).get(lang) or 0):
                    continue      # 这一天的作答已经体现在 base 里了
                rows = self.conn.execute(
                    f"SELECT p.correct AS correct, w.word AS word"
                    f" FROM daily_plan p JOIN {table} w ON w.id = p.word_id"
                    " WHERE p.day=? AND p.lang=? AND p.answered=1"
                    "   AND NOT EXISTS (SELECT 1 FROM events e"
                    "                   WHERE e.day=p.day AND e.lang=p.lang AND e.word=w.word)",
                    (day, lang),
                ).fetchall()
                for r in rows:
                    self.add_event(lang, r["word"], bool(r["correct"]), day, device="repair")
                    fixed += 1

        self.meta_set(done_key, "1")
        if fixed:
            self.refresh_mistakes()
        self.conn.commit()
        return fixed

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

    def rebuild_from_state(self, der: dict) -> None:
        """按推导结果重建错题本、学习统计与打卡记录.

        词表与人工编辑不动 —— 那些由 apply_synced_* 单独处理。
        """
        # 单词 -> id 映射
        ids: dict[str, int] = {}
        for lang, table in (("en", "en_words"), ("jp", "jp_words")):
            for r in self.conn.execute(f"SELECT id, word FROM {table}"):
                ids[f"{lang}:{r['word']}"] = r["id"]

        # 1) 错题本
        self.conn.execute("DELETE FROM mistakes")
        for key, m in der["mistakes"].items():
            lang, word = key.split(":", 1)
            wid = ids.get(key)
            if wid is None:
                continue
            from .sync_core import next_due

            due = next_due(m) or ""
            self.conn.execute(
                "INSERT INTO mistakes (lang,word_id,anchor_date,stage,next_due,"
                "graduated,error_count,last_error_at,created_at)"
                " VALUES (?,?,?,?,?,?,?,?,?)",
                (lang, wid, m["a"], m["s"], due, 1 if m.get("g") else 0,
                 m.get("e", 0), "", _now()),
            )

        # 2) 最后学习日
        for key, day in der["stats"].items():
            lang, word = key.split(":", 1)
            table = "en_words" if lang == "en" else "jp_words"
            self.conn.execute(
                f"UPDATE {table} SET last_studied=? WHERE word=? AND"
                " (last_studied IS NULL OR last_studied<?)",
                (day, word, day),
            )

        # 3) 打卡(完成)日期
        self.conn.execute("DELETE FROM daily_log WHERE completed=1")
        for day in sorted(der["days"]):
            for lang in ("en", "jp"):
                self.conn.execute(
                    "INSERT INTO daily_log (day,lang,total,answered,correct,completed)"
                    " VALUES (?,?,0,0,0,1)"
                    " ON CONFLICT(day,lang) DO UPDATE SET completed=1",
                    (day, lang),
                )
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
        """连续打卡天数.

        与手机端同源: 从事件流推导 (当天任一门语言答满该语言目标题数即算打卡),
        而不是读 daily_log —— 否则两台设备会得出不同的天数。
        """
        from . import sync_core as sc

        return sc.streak(self.derived_state()["days"])

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
