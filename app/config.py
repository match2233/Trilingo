"""Trilingo 全局配置与路径解析.

注意: 词汇英.xlsx / 词汇日.xlsx 为只读数据源, 任何情况下都不得写入.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "Trilingo"
APP_VERSION = "1.0.0"

# ---------------------------------------------------------------- 目录
APP_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = APP_DIR / "data"
LOG_PATH = APP_DIR / "trilingo.log"
DB_PATH = APP_DIR / "trilingo.db"
ICON_PATH = APP_DIR / "trilingo.ico"

# ---------------------------------------------------------------- 数据源
EN_XLSX_NAME = "词汇英.xlsx"
JP_XLSX_NAME = "词汇日.xlsx"


def _desktop_candidates() -> list[Path]:
    """用户桌面可能出现的所有位置 (含 OneDrive 重定向与中文桌面名)."""
    home = Path(os.path.expanduser("~"))
    cands: list[Path] = []
    # 本项目所在的桌面 (最可靠): trilingo 目录的上一级
    cands.append(APP_DIR.parent)
    cands.append(home / "Desktop")
    cands.append(home / "桌面")
    for sub in ("OneDrive", "OneDrive - Personal"):
        cands.append(home / sub / "Desktop")
        cands.append(home / sub / "桌面")
    # 注册表里记录的真实桌面路径 (最权威)
    try:
        import winreg

        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders",
        )
        val, _ = winreg.QueryValueEx(key, "Desktop")
        winreg.CloseKey(key)
        cands.insert(0, Path(os.path.expandvars(val)))
    except Exception:
        pass
    seen: set[str] = set()
    out: list[Path] = []
    for c in cands:
        k = str(c).lower()
        if k not in seen:
            seen.add(k)
            out.append(c)
    return out


def _search_dirs() -> list[Path]:
    """数据源文件的查找顺序.

    桌面优先, 且必须优先 —— 用户平时编辑的是桌面上的那份,
    仓库里自带的同名文件只是给 clone 下来的人做格式参考,
    只能在桌面找不到时兜底, 绝不能悄悄顶替掉用户正在维护的文件。
    """
    dirs = _desktop_candidates()
    # 兜底: 仓库自带的那份 (data/ 与项目根)
    for d in (APP_DIR / "data", APP_DIR):
        if d not in dirs:
            dirs.append(d)
    return dirs


def find_source_file(name: str, *, required: bool = True) -> Path | None:
    """按 桌面 → 仓库自带 的顺序定位数据源文件."""
    for d in _search_dirs():
        p = d / name
        if p.is_file():
            return p
    if required:
        raise FileNotFoundError(
            f"未找到数据源文件: {name}\n已查找: " + "\n".join(str(d) for d in _search_dirs())
        )
    return None


def en_source_path() -> Path | None:
    return find_source_file(EN_XLSX_NAME, required=False)


def jp_source_path() -> Path | None:
    return find_source_file(JP_XLSX_NAME, required=False)


def is_desktop_file(p: Path | None) -> bool:
    """该文件是否来自桌面 (即用户自己维护的那份).

    返回 False 说明用的是仓库自带的示例表 —— 用户往桌面加的词不会生效,
    界面需要把这种情况显示出来。
    """
    if p is None:
        return False
    return any(p.parent == d for d in _desktop_candidates())


# ---------------------------------------------------------------- 学习参数
EN_DAILY_NEW = 7      # 英语每天随机抽取的新词数
JP_DAILY_NEW = 15     # 日语每天随机抽取的新词数
CORRECT_DELAY_MS = 5000   # 拼写正确后停留 5 秒自动进入下一词

# 错题复习: day0 出错后必然出现在 day+1, +3, +7, +15, +30
REVIEW_OFFSETS = (1, 3, 7, 15, 30)

# ---------------------------------------------------------------- 生活记录
# 账本按币种分开记, 互不换算 (没有汇率来源, 换算只会引入假精度)。
CURRENCIES = ("CNY", "JPY", "USD")
CURRENCY_NAME = {"CNY": "人民币", "JPY": "日元", "USD": "美元"}
CURRENCY_SIGN = {"CNY": "¥", "JPY": "¥", "USD": "$"}

# 记鹿: 0/1/2/3 四档, 各自一个固定颜色, 月历按这个上色
DEER_LEVELS = (0, 1, 2, 3)
DEER_COLOR = {0: "#FFFFFF", 1: "#F5D547", 2: "#F0902B", 3: "#D64545"}
DEER_TEXT_COLOR = {0: "#7A8194", 1: "#7A6A12", 2: "#7A4712", 3: "#FFFFFF"}
DEER_LABEL = {0: "白", 1: "黄", 2: "橙", 3: "红"}


def fmt_money(cents: int, currency: str) -> str:
    """把整数分格式化成两位小数的金额 (不带符号)."""
    return f"{cents / 100:,.2f}"


def parse_money(text: str) -> int | None:
    """把用户输入解析成整数分; 非法或超过两位小数返回 None."""
    s = (text or "").strip().replace(",", "").replace("，", "")
    if not s:
        return None
    if s.count(".") > 1:
        return None
    body = s[1:] if s[:1] in "+-" else s
    if not body:
        return None
    if "." in body:
        int_part, _, frac = body.partition(".")
        if not int_part.isdigit() or len(frac) > 2 or (frac and not frac.isdigit()):
            return None
    elif not body.isdigit():
        return None
    try:
        val = float(s)
    except ValueError:
        return None
    if val < 0:
        return None
    return int(round(val * 100))

# ---------------------------------------------------------------- 字体
def ui_font_family() -> str:
    if sys.platform == "win32":
        return "Microsoft YaHei UI"
    return "TkDefaultFont"


def jp_font_family() -> str:
    """日语假名/汉字显示字体 (需覆盖假名)."""
    if sys.platform == "win32":
        return "Yu Gothic UI"
    return ui_font_family()
