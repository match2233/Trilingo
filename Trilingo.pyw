"""Trilingo 启动脚本 (无控制台窗口).

桌面快捷方式指向本文件, 由 pythonw.exe 运行.
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.main import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
