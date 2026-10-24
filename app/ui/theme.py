"""配色与字体."""
from __future__ import annotations

from ..config import jp_font_family, ui_font_family

BG = "#F4F5F9"
CARD = "#FFFFFF"
CARD_HOVER = "#FBFBFE"
BORDER = "#E3E5EE"
# 按钮/卡片的外框比分隔线深一档, 界面才立得住 —— 全用浅灰会糊成一片
BORDER_STRONG = "#D2D7E4"
BORDER_HOVER = "#BFC6D8"
SUNK = "#F7F8FC"

PRIMARY = "#E8622C"      # 主色 (取自图标橙红)
PRIMARY_DARK = "#C94E1D"
PRIMARY_SOFT = "#FDEDE6"
BLUE = "#4A6CF7"
BLUE_DARK = "#3A5BE0"
BLUE_SOFT = "#EBEFFE"

TEXT = "#1F2430"
TEXT_SOFT = "#3C4354"
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
