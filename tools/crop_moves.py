"""从三张训练计划图里裁出每个动作的示意图.

自动检测在这三张图上不稳（浅灰卡片底、彩色标题都在干扰），所以**坐标写死**：
按 50px 网格量好每个动作照片的矩形，直接裁。三张图都是 768x1024，坐标固定。
换图时重新量一遍即可。
"""
from __future__ import annotations

import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets" / "fitness"

# slug: (图, x0, y0, x1, y1)
BOXES = {
    # DAY1 推日：照片在右半区
    "incline-press": ("day1.png", 280, 128, 675, 294),
    "bench-press": ("day1.png", 280, 300, 675, 470),
    "shoulder-press": ("day1.png", 280, 486, 675, 662),
    "lateral-raise": ("day1.png", 300, 672, 685, 836),
    "triceps-ext": ("day1.png", 300, 846, 675, 986),
    # DAY2 拉日：照片在左半区
    "rdl": ("day2.png", 78, 136, 345, 294),
    "bent-row": ("day2.png", 78, 298, 350, 444),
    "single-row": ("day2.png", 78, 448, 352, 588),
    "reverse-fly": ("day2.png", 82, 596, 352, 724),
    "face-pull": ("day2.png", 82, 726, 352, 824),
    "bicep-curl": ("day2.png", 78, 836, 345, 964),
    # DAY3 腿日：照片在右侧
    "goblet-squat": ("day3.png", 318, 106, 748, 264),
    "shoulder-press-b": ("day3.png", 318, 273, 748, 414),
    "face-pull-b": ("day3.png", 318, 426, 748, 564),
    "lateral-raise-b": ("day3.png", 318, 570, 748, 704),
    "crunch": ("day3.png", 318, 716, 748, 834),
    "hip-thrust": ("day3.png", 318, 840, 748, 964),
}


def main() -> int:
    from PIL import Image

    made = 0
    for slug, (fname, x0, y0, x1, y1) in BOXES.items():
        path = ASSETS / fname
        im = Image.open(path).convert("RGB")
        W, H = im.size
        inset_t, inset_b = 12, 8
        box = (max(0, x0), max(0, y0 + inset_t), min(W, x1), min(H, y1 - inset_b))
        crop = im.crop(box)
        crop.thumbnail((360, 210), Image.LANCZOS)
        crop.save(ASSETS / f"{slug}.png")
        made += 1
        print(f"  {slug:18s} {fname} {box} -> {crop.size}")
    print("共裁出", made, "张")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
