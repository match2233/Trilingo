"""从 docx 里取动作示意图（用户提供的 17 张图），替换掉之前从大图上裁的版本.

docx 里 17 张图的顺序与标题一一对应：
  1上斜卧推 2卧推 3肩推 4侧平举 5颈后臂屈伸 6罗马尼亚硬拉 7俯身划船
  8单臂划船 9反向飞鸟 10面拉 11二头弯举 12高脚杯深蹲 13肩推(重复)
  14面拉(重复) 15侧平举(重复) 16卷腹 17臀桥

处理：
  * 去掉纯白边（按内容包围盒裁）；
  * 图 1 顶部带一条蓝色横幅，先把它切掉；
  * 统一贴到 360x210 白底画布，卡片里大小一致。
"""
from __future__ import annotations

import pathlib
import zipfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets" / "fitness"
DOCX = ROOT / "data" / "import" / "moves.docx"

# docx 图片序号 -> slug（重复的 13/14/15 用第一次出现的那张）
ORDER = [
    (1, "incline-press"), (2, "bench-press"), (3, "shoulder-press"),
    (4, "lateral-raise"), (5, "triceps-ext"), (6, "rdl"),
    (7, "bent-row"), (8, "single-row"), (9, "reverse-fly"),
    (10, "face-pull"), (11, "bicep-curl"), (12, "goblet-squat"),
    (16, "crunch"), (17, "hip-thrust"),
]

CANVAS = (360, 210)
WHITE = 242


def is_blue(r: int, g: int, b: int) -> bool:
    return b > 130 and b - r > 45 and b - g > 25


def trim(im):
    """裁掉白边，并切掉顶部的蓝色横幅。"""
    from PIL import Image
    im = im.convert("RGB")
    W, H = im.size
    px = im.load()

    # 1) 顶部蓝色横幅（只在第一张有）
    top = 0
    for y in range(min(H, 200)):
        row = [px[x, y] for x in range(0, W, 7)]
        if sum(1 for r, g, b in row if is_blue(r, g, b)) < len(row) * 0.25:
            top = y
            break
    if top:
        im = im.crop((0, top, W, H))
        px = im.load()
        W, H = im.size

    # 2) 内容包围盒
    x0, y0, x1, y1 = W, H, 0, 0
    for y in range(H):
        for x in range(W):
            r, g, b = px[x, y]
            if min(r, g, b) < WHITE:
                if x < x0:
                    x0 = x
                if x > x1:
                    x1 = x
                if y < y0:
                    y0 = y
                if y > y1:
                    y1 = y
    if x1 <= x0 or y1 <= y0:
        return im
    return im.crop((x0, y0, x1 + 1, y1 + 1))


def main() -> int:
    from PIL import Image

    if not DOCX.exists():
        print("找不到 docx:", DOCX)
        return 1
    z = zipfile.ZipFile(DOCX)
    tmp = ROOT / "data" / "import" / "docx_media"
    tmp.mkdir(exist_ok=True)

    made = 0
    for idx, slug in ORDER:
        raw = z.read(f"word/media/image{idx}.png")
        src = tmp / f"image{idx}.png"
        src.write_bytes(raw)
        im = trim(Image.open(src))
        im.thumbnail((CANVAS[0] - 10, CANVAS[1] - 10), Image.LANCZOS)
        canvas = Image.new("RGB", CANVAS, "#FFFFFF")
        canvas.paste(im, ((CANVAS[0] - im.width) // 2,
                          (CANVAS[1] - im.height) // 2))
        canvas.save(ASSETS / f"{slug}.png")
        made += 1
        print(f"  image{idx:<2d} -> {slug:18s} {im.size} -> {CANVAS}")
    print("共导入", made, "张")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
