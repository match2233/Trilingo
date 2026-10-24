"""Trilingo 启动入口."""
from __future__ import annotations

import logging
import sys
import traceback
from pathlib import Path

from . import config as C
from . import sync as sync_mod
from .db import Database


def _enable_dpi_awareness() -> None:
    """让 Windows 按物理像素渲染, 否则高分屏上 Tk 会被系统拉伸而发虚.

    这是"文字模糊"的根因: 没有 DPI 感知时, 系统把整个窗口位图放大 1.25/1.5 倍,
    字就被插值糊掉了。声明感知后由我们按真实像素排版, 字体自然锐利。
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes

        try:                      # Win8.1+: 每显示器 DPI 感知
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:         # noqa: BLE001
            ctypes.windll.user32.SetProcessDPIAware()
    except Exception:             # noqa: BLE001
        pass


def _setup_logging() -> None:
    logging.basicConfig(
        filename=str(C.LOG_PATH),
        level=logging.INFO,
        format="%(asctime)s  %(levelname)s  %(message)s",
        encoding="utf-8",
    )


def main() -> int:
    _enable_dpi_awareness()
    _setup_logging()
    log = logging.getLogger("trilingo")
    log.info("=== Trilingo 启动 ===")

    # 保证以本文件所在项目根为 import 根
    root = Path(__file__).resolve().parent.parent
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    from .ui.app import TrilingoApp

    db = Database(C.DB_PATH)

    # 启动时留一份当日快照, 万一数据被误删还能找回来
    snap = db.backup()
    if snap:
        log.info("数据库快照: %s", snap)

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
        # 词表就绪后再做跨设备同步, 保证手机端拿到的是最新的词
        app.auto_sync(on_done=app.refresh_menu)

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
