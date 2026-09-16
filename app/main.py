"""Trilingo 启动入口."""
from __future__ import annotations

import logging
import sys
import traceback
from pathlib import Path

from . import config as C
from . import sync as sync_mod
from .db import Database


def _setup_logging() -> None:
    logging.basicConfig(
        filename=str(C.LOG_PATH),
        level=logging.INFO,
        format="%(asctime)s  %(levelname)s  %(message)s",
        encoding="utf-8",
    )


def main() -> int:
    _setup_logging()
    log = logging.getLogger("trilingo")
    log.info("=== Trilingo 启动 ===")

    # 保证以本文件所在项目根为 import 根
    root = Path(__file__).resolve().parent.parent
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    from .ui.app import TrilingoApp

    db = Database(C.DB_PATH)

    app = TrilingoApp(db)

    def report(exc, val, tb):
        log.error("界面异常: %s", "".join(traceback.format_exception(exc, val, tb)))
        try:
            from tkinter import messagebox

            messagebox.showerror("Trilingo 出错", f"{val}")
        except Exception:
            pass

    app.report_callback_exception = report

    def on_sync_done(stats) -> None:
        log.info("同步完成: %s", stats)
        app.set_enrich_notice(sync_mod.summarize(stats))
        app.refresh_menu()

    # 每次打开应用都重新读取两个 xlsx, 补全缺失内容 (后台线程, 不阻塞界面)
    sync_mod.startup_sync_async(db, app, on_sync_done)

    try:
        app.mainloop()
    finally:
        log.info("=== Trilingo 退出 ===")
        try:
            db.close()
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
