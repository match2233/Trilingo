"""启动同步: 重新读取桌面的两个 xlsx, 并入数据库并补全缺失内容.

xlsx 为只读数据源 —— 每次同步都会校验其 mtime/大小, 确认没有被本程序改动.
"""
from __future__ import annotations

import threading
from pathlib import Path

from . import config as C
from . import enrich as enrich_mod
from . import sources


def _fingerprint(path: Path | None):
    if path is None or not path.is_file():
        return None
    st = path.stat()
    return (st.st_mtime_ns, st.st_size)


def sync_all(db, *, enrich: bool = True, online: bool = True) -> dict:
    """读取两个源文件并同步到数据库."""
    en_path = C.en_source_path()
    jp_path = C.jp_source_path()

    before = {"en": _fingerprint(en_path), "jp": _fingerprint(jp_path)}

    stats: dict = {"en": {}, "jp": {}, "errors": []}

    if en_path:
        try:
            stats["en"] = db.sync_english(sources.parse_english(en_path))
        except Exception as exc:  # noqa: BLE001
            stats["errors"].append(f"词汇英.xlsx: {exc}")
    else:
        stats["errors"].append("未找到 词汇英.xlsx")

    if jp_path:
        try:
            stats["jp"] = db.sync_japanese(sources.parse_japanese(jp_path))
        except Exception as exc:  # noqa: BLE001
            stats["errors"].append(f"词汇日.xlsx: {exc}")
    else:
        stats["errors"].append("未找到 词汇日.xlsx")

    # 校验源文件未被改动
    after = {"en": _fingerprint(en_path), "jp": _fingerprint(jp_path)}
    for k in ("en", "jp"):
        if before[k] != after[k]:
            stats["errors"].append(f"{k} 源文件在读取期间发生变化")

    if enrich:
        stats["en_ipa"] = enrich_mod.enrich_english(db)
        stats["jp_enrich"] = enrich_mod.enrich_japanese(db, online=online)
    return stats


def startup_sync_async(db, widget, on_done) -> threading.Thread:
    """后台线程做同步与补全, 完成后回到 Tk 主线程回调 on_done(stats).

    widget 只用于 after() 调度; 线程设为 daemon, 关闭窗口时不会阻塞退出.
    """

    def worker():
        try:
            stats = sync_all(db)
        except Exception as exc:  # noqa: BLE001
            stats = {"errors": [str(exc)], "en": {}, "jp": {}}
        try:
            widget.after(0, lambda: on_done(stats))
        except Exception:
            pass

    t = threading.Thread(target=worker, name="trilingo-sync", daemon=True)
    t.start()
    return t


def summarize(stats: dict) -> str:
    en = stats.get("en") or {}
    jp = stats.get("jp") or {}
    bits = []
    if en.get("new"):
        bits.append(f"英语新增 {en['new']}")
    if jp.get("new"):
        bits.append(f"日语新增 {jp['new']}")
    if en.get("deactivated") or jp.get("deactivated"):
        bits.append(f"移出 {en.get('deactivated', 0) + jp.get('deactivated', 0)}")
    ipa_n = stats.get("en_ipa") or 0
    if ipa_n:
        bits.append(f"补音标 {ipa_n}")
    jp_en = stats.get("jp_enrich") or {}
    n = (jp_en.get("seed") or 0) + (jp_en.get("online") or 0) + (jp_en.get("ai") or 0)
    if n:
        bits.append(f"补日语释义 {n}" + (f"（AI {jp_en['ai']}）" if jp_en.get("ai") else ""))
    if jp_en.get("accent"):
        bits.append(f"补声调 {jp_en['accent']}")
    if not bits:
        bits.append("数据库已是最新，无需补全")
    if stats.get("errors"):
        bits.append("⚠ " + "；".join(stats["errors"]))
    return "　·　".join(bits)
