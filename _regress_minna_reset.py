"""回归测试: 新标日单元测试重置后, 不能被云端旧进度覆盖.

对应 bug（用户报告）:
    在电脑端重置某一课的作答记录后, 下次同步云端旧进度又被应用回来,
    表现就是"重置完再同步, 进度反复被云端覆盖"。

根因:
    minna_reset() 原来直接 DELETE 进度行。同步合并规则是"同试卷集+课取
    updated_at 较新的那份", 本机没有记录时, 云端旧记录就成了唯一一份,
    于是下一次同步必然把它带回来。

修法:
    重置改为保留一条 status='idle'、updated_at 最新的墓碑记录; 合并时它
    会淘汰云端旧进度, 另一台设备收到后也会把该课清空。

跑法:  python _regress_minna_reset.py
"""
import copy
import pathlib
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from app import ghsync  # noqa: E402
from app import sync_core as sc  # noqa: E402
from app.db import Database  # noqa: E402

PASS, FAIL = [], []


def check(cond, label):
    (PASS if cond else FAIL).append(label)
    print(f"  [{'OK ' if cond else 'FAIL'}] {label}")


def seed_done(db):
    """造一课已完成的进度与作答结果."""
    db.minna_start(1, 3)
    db.minna_mark(1, "q1", True)
    db.minna_mark(1, "q2", False)
    db.minna_finish(1, 100, 1, 3)
    assert db.minna_progress(1)["status"] == "done"
    assert db.minna_results(1) == {"q1": True, "q2": False}


tmp = pathlib.Path(tempfile.mkdtemp(prefix="trilingo_minna_reset_"))

print("=== 1) 本地重置 vs 云端旧进度 ===")
pc = Database(tmp / "pc.db")
seed_done(pc)
remote = ghsync.state_from_db(pc)          # 模拟云端仍是重置前的旧状态

pc.minna_reset(1)
local = ghsync.state_from_db(pc)
check(local["minna"]["1"]["status"] == "idle", "重置后本地导出 idle 墓碑")
check(local["minna"]["1"]["results"] == {}, "重置后本地作答结果为空")

merged = sc.merge(local, remote, prefer="local")
check(merged["minna"]["1"]["status"] == "idle", "合并后保留重置记录")
check(merged["minna"]["1"]["results"] == {}, "合并后作答结果仍为空")
check(ghsync._differs(remote, merged), "合并结果与云端不同 -> 会触发上传")

pc.set_base(merged["base"])
pc.import_events(merged["events"])
ghsync.apply_state_to_db(pc, merged)
check(pc.minna_progress(1)["status"] == "idle", "应用合并结果后本地仍是 idle")
check(pc.minna_results(1) == {}, "应用合并结果后本地结果仍为空")

again = sc.merge(ghsync.state_from_db(pc), remote, prefer="local")
check(again["minna"]["1"]["status"] == "idle", "再次合并旧云端数据也不会复活")
pc.close()

print("=== 2) 重置后立刻重做: 新进度要能压过旧记录 ===")
pc = Database(tmp / "pc2.db")
seed_done(pc)
old = ghsync.state_from_db(pc)
pc.minna_reset(1)
pc.minna_start(1, 3)
new = ghsync.state_from_db(pc)
check(new["minna"]["1"]["status"] == "doing", "重做后本地是 doing")
check(new["minna"]["1"]["updated_at"] > old["minna"]["1"]["updated_at"],
      "重做时间戳严格晚于旧记录")
merged = sc.merge(new, old, prefer="local")
check(merged["minna"]["1"]["status"] == "doing", "合并后保留新的 doing")
pc.close()

print("=== 3) 走完整 sync(): 云端必须收到 idle 墓碑 ===")
pc = Database(tmp / "pc3.db")
seed_done(pc)
stale = ghsync.state_from_db(pc)
pc.minna_reset(1)

pushed = {}


def fake_fetch(cfg=None):
    return copy.deepcopy(stale), "sha-old"


def fake_put(state, sha, cfg=None, message=""):
    pushed["state"] = copy.deepcopy(state)
    return "sha-new"


ghsync.is_configured = lambda: True
ghsync.fetch = fake_fetch
ghsync.put = fake_put

r1 = ghsync.sync(pc, device="test")
check("state" in pushed, "sync 确实写回了云端")
check(r1.get("pushed") is True, "返回值标记本次确实上传了")
check(pushed["state"]["minna"]["1"]["status"] == "idle",
      "写回云端的记录是 idle 墓碑")
check(pushed["state"]["minna"]["1"]["results"] == {}, "写回云端的结果为空")
check(pc.minna_progress(1)["status"] == "idle", "同步后本地仍是 idle")
check(pc.minna_results(1) == {}, "同步后本地结果为空")

# 第二次: 云端已经是墓碑, 不应再重复提交
stale = copy.deepcopy(pushed["state"])
pushed.clear()
r2 = ghsync.sync(pc, device="test")
check("state" not in pushed, "云端已是最新时不再重复提交")
check(r2.get("pushed") is False, "返回值标记本次没有上传")
pc.close()

print()
print(f"通过 {len(PASS)} 项, 失败 {len(FAIL)} 项")
sys.exit(0 if not FAIL else 1)
