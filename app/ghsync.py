"""通过 GitHub 私有仓库在两台设备之间同步学习数据.

用的是 Contents API (免费额度充足, 个人用量远远够):
    GET  /repos/{owner}/{repo}/contents/{path}   -> 读文件, 拿到 sha
    PUT  /repos/{owner}/{repo}/contents/{path}   -> 写文件, 需带 sha
sha 起到乐观锁的作用: 期间被另一台设备改过就会返回 409, 此时重新拉取、
合并、再提交。因为合并满足交换律, 重试一定能收敛。

配置存放在 data/sync.json (已 gitignore, 不会上传):
    {"token": "github_pat_...", "owner": "match2233",
     "repo": "Trilingo-data", "path": "state.json", "branch": "main"}
"""
from __future__ import annotations

import base64
import json
import logging
import urllib.error
import urllib.request
from pathlib import Path

from . import sync_core as sc
from .config import DATA_DIR

log = logging.getLogger("trilingo")

CONFIG_FILE = DATA_DIR / "sync.json"
API = "https://api.github.com"

DEFAULTS = {
    "token": "",
    "owner": "",
    "repo": "Trilingo-data",
    "path": "state.json",
    "branch": "main",
    "enabled": True,
}

MAX_FILE_BYTES = 900_000        # Contents API 单文件 1MB 上限, 留出余量


# ------------------------------------------------------------------ 配置
def load_config() -> dict:
    cfg = dict(DEFAULTS)
    try:
        with open(CONFIG_FILE, encoding="utf-8") as fh:
            data = json.load(fh)
        for k in DEFAULTS:
            if data.get(k) not in (None, ""):
                cfg[k] = data[k]
    except FileNotFoundError:
        pass
    except Exception as exc:  # noqa: BLE001
        log.warning("sync.json 读取失败: %s", exc)
    if not cfg["token"]:
        import os

        cfg["token"] = os.environ.get("TRILINGO_SYNC_TOKEN", "")
    return cfg


def save_config(**fields) -> None:
    cfg = load_config()
    cfg.update({k: v for k, v in fields.items() if v is not None})
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w", encoding="utf-8") as fh:
        json.dump(cfg, fh, ensure_ascii=False, indent=2)


def is_configured() -> bool:
    c = load_config()
    return bool(c["token"] and c["owner"] and c["repo"]) and c.get("enabled", True)


# ------------------------------------------------------------------ HTTP
class SyncError(RuntimeError):
    pass


def _request(method: str, url: str, cfg: dict, payload: dict | None = None,
             timeout: int = 45) -> dict:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload else None
    req = urllib.request.Request(
        url,
        data=body,
        method=method,
        headers={
            "Authorization": f"Bearer {cfg['token']}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "Trilingo/1.0",
            **({"Content-Type": "application/json"} if body else {}),
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", "replace")
            return json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = json.loads(exc.read().decode("utf-8", "replace")).get("message", "")
        except Exception:
            pass
        raise SyncError(f"GitHub 返回 HTTP {exc.code}: {detail or exc.reason}") from None
    except Exception as exc:  # noqa: BLE001
        raise SyncError(f"无法连接 GitHub: {type(exc).__name__}") from None


def fetch(cfg: dict | None = None) -> tuple[dict, str]:
    """读取远端状态. 文件不存在时返回 (空状态, "") —— 首次同步即新建."""
    cfg = cfg or load_config()
    url = f"{API}/repos/{cfg['owner']}/{cfg['repo']}/contents/{cfg['path']}?ref={cfg['branch']}"
    try:
        data = _request("GET", url, cfg)
    except SyncError as exc:
        if "404" in str(exc):
            return sc.empty_state(), ""
        raise

    sha = data.get("sha", "")
    content = data.get("content", "")
    if not content:
        raise SyncError("远端文件过大，超出了 Contents API 的读取上限")
    raw = base64.b64decode(content)
    try:
        return json.loads(raw.decode("utf-8")), sha
    except Exception:
        raise SyncError("远端 state.json 解析失败，可能被其他程序改坏了") from None


def put(state: dict, sha: str, cfg: dict | None = None, message: str = "") -> str:
    """写入远端状态, 返回新的 sha. sha 过期会抛 SyncError(409)."""
    cfg = cfg or load_config()
    raw = json.dumps(state, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(raw) > MAX_FILE_BYTES:
        raise SyncError(
            f"同步文件已达 {len(raw)/1024:.0f}KB，接近 GitHub 单文件上限，需要压缩历史"
        )
    payload = {
        "message": message or "sync",
        "content": base64.b64encode(raw).decode("ascii"),
        "branch": cfg["branch"],
    }
    if sha:
        payload["sha"] = sha
    url = f"{API}/repos/{cfg['owner']}/{cfg['repo']}/contents/{cfg['path']}"
    data = _request("PUT", url, cfg, payload)
    return (data.get("content") or {}).get("sha", "")


# ------------------------------------------------------------------ 状态导出 / 导入
def state_from_db(db, words_en: bool = True) -> dict:
    """把本地 SQLite 组装成同步状态."""
    state = sc.empty_state()
    state["base"] = db.get_base()
    state["words"] = {
        "en": [
            {"w": r["word"], "m": r["meaning"] or "", "ipa": r["ipa"] or "",
             "u": 1 if r["meaning_source"] == "manual" or r["ipa_source"] == "manual" else 0}
            for r in db.conn.execute(
                "SELECT word,meaning,ipa,meaning_source,ipa_source FROM en_words WHERE active=1"
            )
        ],
        "jp": [
            {"w": r["word"], "r": r["reading"] or "", "m": r["meaning"] or "",
             "ac": r["accent"] or "",
             "u": 1 if r["meaning_source"] == "manual" or r["accent_source"] == "manual" else 0}
            for r in db.conn.execute(
                "SELECT word,reading,meaning,accent,meaning_source,accent_source FROM jp_words WHERE active=1"
            )
        ],
    }
    state["edits"] = db.get_edits()
    state["events"] = [dict(r) for r in db.conn.execute(
        "SELECT id AS i, ts AS t, device AS d, lang AS l, word AS w, ok AS o, day FROM events"
    )]
    return state


def apply_state_to_db(db, state: dict) -> None:
    """把合并后的状态写回 SQLite (重建错题本、学习统计、打卡记录)."""
    sc.apply_edits(state)
    der = sc.derive(state)

    # 词条: 合并进来的释义/音标/声调 (人工编辑优先, 不覆盖本地 manual)
    for rec in state["words"].get("en") or []:
        db.apply_synced_en(rec)
    for rec in state["words"].get("jp") or []:
        db.apply_synced_jp(rec)

    db.rebuild_from_state(der)


# ------------------------------------------------------------------ 主流程
def sync(db, device: str = "pc", message: str = "") -> dict:
    """拉取 -> 合并 -> 提交 -> 应用. 失败抛 SyncError."""
    cfg = load_config()
    if not is_configured():
        raise SyncError("尚未配置同步（需要 GitHub token 与仓库名）")

    local = state_from_db(db)
    remote, sha = fetch(cfg)
    merged = sc.merge(local, remote)
    merged["updated"] = _now()

    # 合并没有变化就不必写回, 省一次提交
    changed = _differs(local, merged)

    new_sha = sha
    if changed or not sha:
        try:
            new_sha = put(merged, sha, cfg, message or f"sync from {device}")
        except SyncError as exc:
            if "409" not in str(exc):
                raise
            # 期间被另一端改过: 重拉、重合并、再试一次
            remote2, sha2 = fetch(cfg)
            merged = sc.merge(merged, remote2)
            merged["updated"] = _now()
            new_sha = put(merged, sha2, cfg, message or f"sync from {device} (retry)")

    # 合并后的 base 要写回本地: 压缩就是在这时候发生的
    db.set_base(merged["base"])
    db.import_events(merged["events"])
    apply_state_to_db(db, merged)
    return {
        "changed": changed,
        "events": len(merged["events"]),
        "mistakes": len(der_count(merged)),
        "days": len(sc.derive(merged)["days"]),
        "sha": new_sha[:8],
    }


def push_state(db, message: str = "") -> dict:
    """用本机状态**覆盖**云端, 不做合并.

    普通同步是求并集, 因此本机删掉的东西会被云端带回来。重置进度、或本机
    才是权威时, 需要这个"以本机为准"的写入。
    """
    cfg = load_config()
    if not is_configured():
        raise SyncError("尚未配置同步（需要 GitHub token 与仓库名）")

    state = state_from_db(db)
    state["updated"] = _now()
    try:
        _, sha = fetch(cfg)
    except SyncError:
        sha = ""
    new_sha = put(state, sha, cfg, message or "overwrite from pc")
    return {"sha": (new_sha or "")[:8], "events": len(state["events"]),
            "words": len(state["words"]["en"]) + len(state["words"]["jp"])}


def der_count(state: dict) -> dict:
    return sc.derive(state)["mistakes"]


def _now() -> str:
    import datetime as dt

    return dt.datetime.now().isoformat(timespec="seconds")


def _differs(a: dict, b: dict) -> bool:
    """忽略 updated 字段后比较, 判断合并是否带来了新内容."""
    x = {k: v for k, v in a.items() if k != "updated"}
    y = {k: v for k, v in b.items() if k != "updated"}
    return json.dumps(x, sort_keys=True, ensure_ascii=False) != json.dumps(y, sort_keys=True, ensure_ascii=False)


def test_connection() -> tuple[bool, str]:
    cfg = load_config()
    if not cfg["token"]:
        return False, "还没有填写 GitHub token。"
    if not (cfg["owner"] and cfg["repo"]):
        return False, "还没有填写仓库名（形如 用户名/Trilingo-data）。"
    try:
        me = _request("GET", f"{API}/user", cfg, timeout=20)
        url = f"{API}/repos/{cfg['owner']}/{cfg['repo']}"
        repo = _request("GET", url, cfg, timeout=20)
        vis = "私有" if repo.get("private") else "公开"
        return True, f"连接成功：以 {me.get('login')} 身份访问到{vis}仓库 {cfg['repo']}"
    except SyncError as exc:
        return False, str(exc)
