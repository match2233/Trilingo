"""回归测试: 本地作答(尤其是错题本「立即复习」答对)的结果必须扛得住同步.

对应 bug（用户报告）:
    错题本显示「今日待复习 N 个」, 点「立即复习」把词并入今日、答对之后,
    错题本里这个词**还是**显示今日待复习, 反复复习都消不掉。

根因: `ghsync.apply_state_to_db` 用云端快照 base.mistakes **覆盖**了本机错题本
(`DELETE` + `INSERT`)。base 是冻结的旧快照, 不含本机此后任何一次复习, 于是
每同步一次就把刚答对推进的档位打回旧档位, 复习日跟着退回过去 —— 那个词就
永远到期。本机自维护的错题本表才是权威, 快照只能用来补本机**缺失**的条目。

跑法:  python _regress_review.py
"""
import json
import pathlib
import shutil
import sys

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from app import config as C  # noqa: E402
from app import ghsync  # noqa: E402
from app import sources  # noqa: E402
from app import sync_core as sc  # noqa: E402
from app.db import Database, today  # noqa: E402

REAL = ROOT / "trilingo.db"
TMP = pathlib.Path(__import__("tempfile").gettempdir())

PASS, FAIL = [], []


def check(cond, label, extra=""):
    (PASS if cond else FAIL).append(label)
    print(f"  [{'OK ' if cond else 'FAIL'}] {label}" + (f"   {extra}" if extra else ""))


pc_path = TMP / "trilingo_rev_pc.db"
ph_path = TMP / "trilingo_rev_phone.db"
for p in (pc_path, ph_path):
    if p.exists():
        p.unlink()
shutil.copy(REAL, pc_path)

pc = Database(pc_path)
ph = Database(ph_path)
t = today()


def pull(db, remote):
    """一次同步: 合并 -> 写回本地 base -> 应用到本地（与 ghsync.sync 同序）."""
    local = ghsync.state_from_db(db)
    merged = sc.merge(local, remote, prefer="local")
    db.set_base(merged["base"])
    db.import_events(merged["events"])
    ghsync.apply_state_to_db(db, merged)
    return merged


def mistake_of(db, lang, word):
    table = "en_words" if lang == "en" else "jp_words"
    return db.conn.execute(
        f"SELECT m.* FROM mistakes m JOIN {table} w ON w.id=m.word_id"
        " WHERE m.lang=? AND w.word=?", (lang, word)).fetchone()


def due_words(db, lang):
    """错题本里今天到期的词 —— 界面上「今日待复习」数的就是这些."""
    table = "en_words" if lang == "en" else "jp_words"
    return [r["word"] for r in db.conn.execute(
        f"SELECT w.word AS word FROM mistakes m JOIN {table} w ON w.id=m.word_id"
        " WHERE m.lang=? AND m.graduated=0 AND m.next_due<=? ORDER BY w.word",
        (lang, t))]


ph.sync_english(sources.parse_english(C.en_source_path()))
ph.sync_japanese(sources.parse_japanese(C.jp_source_path()))

print("=== 0) 准备: 电脑端同步一次, 让 base 冻结 ===")
remote = pull(pc, sc.empty_state())
frozen = json.loads(json.dumps(remote))
print(f"  电脑错题 {len(pc.open_mistakes('en'))} 英语 / {len(pc.open_mistakes('jp'))} 日语, "
      f"base.mistakes {len(remote['base']['mistakes'])} 条")

cands = []
for r in pc.conn.execute(
        "SELECT m.word_id AS wid, w.word AS word FROM mistakes m"
        " JOIN jp_words w ON w.id=m.word_id"
        " WHERE m.lang='jp' AND m.graduated=0 AND m.next_due<=?", (t,)):
    if f"jp:{r['word']}" in frozen["base"]["mistakes"]:
        cands.append((r["word"], r["wid"]))

if not cands:
    print("\n跳过: 库里没有「今日到期且已冻结进 base」的日语错题")
    pc.close()
    ph.close()
    sys.exit(0)

check(True, "存在一条「今日到期且已冻结进 base」的日语错题",
      f"{[c[0] for c in cands]}")
word, wid = cands[0]
print(f"  样本词: 「{word}」  base 里 = {frozen['base']['mistakes']['jp:' + word]}")

print()
print("=== 1) 点「立即复习」并入今日 ===")
pc.conn.execute("UPDATE mistakes SET next_due=? WHERE lang='jp' AND word_id=?", (t, wid))
pc.conn.commit()
pc.add_to_today("jp", wid)
check(word in due_words(pc, "jp"), "该词在今日待复习里")

print()
print("=== 2) 在词汇页答对 ===")
before = mistake_of(pc, "jp", word)
pc.mark_answered("jp", wid, True, t)
after = mistake_of(pc, "jp", word)
check(after["stage"] == before["stage"] + 1, "本地档位推进一档",
      f"{before['stage']} -> {after['stage']}")
check(after["next_due"] > t, "本地下次复习日已推后", f"{after['next_due']}")
check(word not in due_words(pc, "jp"), "答对后不再出现在今日待复习")
want_stage, want_due = after["stage"], after["next_due"]

print()
print("=== 3) 同步一次（云端 base 里这个词还是旧档位）===")
remote = pull(pc, frozen)
m = mistake_of(pc, "jp", word)
check(m is not None, "该词仍在错题本里")
if m is not None:
    check(m["stage"] == want_stage, "同步没有把档位打回去",
          f"期望 {want_stage}, 实际 {m['stage']}")
    check(m["next_due"] == want_due, "同步没有把复习日打回今天",
          f"期望 {want_due}, 实际 {m['next_due']}")
    check(word not in due_words(pc, "jp"),
          "同步后依然没有「今日待复习」", f"待复习={due_words(pc, 'jp')}")

print()
print("=== 4) 反复同步仍然稳定 ===")
for _ in range(3):
    remote = pull(pc, remote)
m = mistake_of(pc, "jp", word)
check(m is not None and m["stage"] == want_stage, "反复同步档位保持在推进后的值",
      f"实际 {m['stage'] if m else None}")

print()
print("=== 5) 手机自己的复习结果也不会被打回 ===")
ph_row = ph.conn.execute("SELECT id FROM jp_words WHERE word=?", (word,)).fetchone()
check(ph_row is not None, "手机词表里有这个词")
if ph_row is not None:
    ph.mark_answered("jp", ph_row["id"], False, t)
    ph.mark_answered("jp", ph_row["id"], True, t)
    ph_stage = mistake_of(ph, "jp", word)["stage"]
    pull(ph, remote)
    m2 = mistake_of(ph, "jp", word)
    check(m2 is not None and m2["stage"] == ph_stage, "手机复习结果没有被打回",
          f"期望 {ph_stage}, 实际 {m2['stage'] if m2 else None}")

print()
print("=== 6) 快照仍能补齐本机没有的历史词（只做加法）===")
only_base = None
for r in pc.conn.execute("SELECT id, word FROM jp_words WHERE active=1"):
    if mistake_of(pc, "jp", r["word"]) is None and \
            f"jp:{r['word']}" not in remote["base"]["mistakes"]:
        only_base = (r["word"], r["id"])
        break
if only_base is None:
    print("  [--] 跳过: 找不到只存在于快照的词")
else:
    w2, _wid2 = only_base
    fake = json.loads(json.dumps(remote))
    fake["base"]["mistakes"][f"jp:{w2}"] = {"a": t, "s": 1, "e": 2, "g": 0, "t": 0}
    pull(pc, fake)
    m3 = mistake_of(pc, "jp", w2)
    check(m3 is not None and m3["stage"] == 1, "快照里的历史词被补进本机错题本",
          f"{w2}: stage={m3['stage'] if m3 else None}")

print()
print("=== 7) 已毕业的词不会被快照拉回未毕业 ===")
target = pc.conn.execute(
    "SELECT m.word_id AS wid, w.word AS word FROM mistakes m JOIN jp_words w"
    " ON w.id=m.word_id WHERE m.lang='jp' AND m.graduated=0 AND m.stage>=4 LIMIT 1"
).fetchone()
if target is None:
    print("  [--] 跳过: 没有可推进到毕业的词")
else:
    for _ in range(len(C.REVIEW_OFFSETS) + 1):
        pc.mark_answered("jp", target["wid"], True, t)
    check(bool(mistake_of(pc, "jp", target["word"])["graduated"]), "已推进到毕业")
    pull(pc, remote)
    m5 = mistake_of(pc, "jp", target["word"])
    check(m5 is not None and bool(m5["graduated"]),
          "同步后依然毕业（没被快照拉回未毕业）",
          f"graduated={m5['graduated'] if m5 else None}")

print()
print(f"通过 {len(PASS)} 项, 失败 {len(FAIL)} 项")
for f in FAIL:
    print("   -", f)

pc.close()
ph.close()
sys.exit(1 if FAIL else 0)
