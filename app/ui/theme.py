"""配色与字体."""
from __future__ import annotations

from ..config import jp_font_family, ui_font_family

BG = "#F4F5F9"
CARD = "#FFFFFF"
CARD_HOVER = "#FBFBFE"
BORDER = "#E3E5EE"

PRIMARY = "#E8622C"      # 主色 (取自图标橙红)
PRIMARY_DARK = "#C94E1D"
PRIMARY_SOFT = "#FDEDE6"
BLUE = "#4A6CF7"
BLUE_SOFT = "#EBEFFE"

TEXT = "#1F2430"
MUTED = "#7A8194"
SUCCESS = "#1F9D55"
SUCCESS_SOFT = "#E8F7EE"
ERROR = "#D64545"
ERROR_SOFT = "#FCECEC"

FAMILY = ui_font_family()
JP_FAMILY = jp_font_family()
IPA_FAMILY = "Segoe UI"


def f(size=11, weight="normal", family=None):
    return (family or FAMILY, size, weight)


def jp(size=11, weight="normal"):
    return (JP_FAMILY, size, weight)


def ipa(size=11, weight="normal"):
    return (IPA_FAMILY, size, weight)
