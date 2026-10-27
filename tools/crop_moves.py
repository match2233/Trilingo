"""从三张训练计划图里裁出每个动作的示意图.

关键发现：每行的开头都有一个彩色圆形序号（DAY1 蓝圈，DAY2/DAY3 绿圈）。
圆形序号就是"行中心"，比猜行高稳得多：
  * 找接近品牌蓝/品牌绿的像素，按 y 聚簇 → 每行中心；
  * 每行裁 [中心-80, 中心+80]；
  * 横向用"平滑度"打分挑窗口：照片是平滑色块，标题文字边缘尖锐。
"""
from __future__ import annotations

import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets" / "fitness"

PLAN = {
    "day1.png": ["incline-press", "bench-press", "shoulder-press",
                 "lateral-raise", "triceps-ext"],
    "day2.png": ["rdl", "bent-row", "single-row",
                 "reverse-fly", "face-pull", "bicep-curl"],
    "day3.png": ["goblet-squat", "shoulder-press-b", "face-pull-b",
                 "lateral-raise-b", "crunch", "hip-thrust"],
}

# 每页页眉底边：第一行的裁剪不能压到这上面去（否则会带上标题横幅）
HEADER_BOTTOM = {"day1.png": 118, "day2.png": 58, "day3.png": 140}


def _is_badge(r: int, g: int, b: int) -> bool:
    """序号圆圈：品牌蓝（深浅都算）或品牌绿。"""
    blue = b > 120 and b - r > 60 and b - g > 35
    green = g > 110 and g - r > 40 and g - b > 25
    return blue or green


def badge_centers(im, H, W) -> list[int]:
    px = im.load()
    hits: dict[int, int] = {}
    for y in range(H):
        for x in range(0, min(W, 120)):
            r, g, b = px[x, y][:3]
            if _is_badge(r, g, b):
                hits[y] = hits.get(y, 0) + 1
    if not hits:
        return []
    ys = sorted(hits)
    clusters, cur = [], [ys[0]]
    for y in ys[1:]:
        if y - cur[-1] <= 12:
            cur.append(y)
        else:
            clusters.append(cur)
            cur = [y]
    clusters.append(cur)
    raw = [sum(c) // len(c) for c in clusters if sum(hits[y] for y in c) >= 60]
    # 去掉页眉/页脚里被误认的色块（<60 或 >980）
    raw = [c for c in raw if 60 <= c <= 980]
    # 相距 60px 以内视为同一个圆圈被切成了两段
    merged: list[int] = []
    for c in raw:
        if merged and c - merged[-1] <= 60:
            merged[-1] = (merged[-1] + c) // 2
        else:
            merged.append(c)
    return merged


def best_window(gray, y0, y1, win_ratio=0.40):
    W = len(gray[0])
    win = int(W * win_ratio)
    mid = [0] * W
    edge = [0] * W
    for y in range(max(0, y0), min(len(gray), y1)):
        row = gray[y]
        for x in range(W):
            v = row[x]
            if 60 < v < 240:
                mid[x] += 1
            if x and abs(v - row[x - 1]) > 55:
                edge[x] += 1
    best, best_score = 0, -1e18
    cur_mid = sum(mid[:win])
    cur_edge = sum(edge[:win])
    for x in range(0, W - win):
        if x:
            cur_mid += mid[x + win - 1] - mid[x - 1]
            cur_edge += edge[x + win - 1] - edge[x - 1]
        score = cur_mid - cur_edge * 6
        if score > best_score:
            best_score, best = score, x
    return best, min(W, best + win)


def main() -> int:
    from PIL import Image

    made = 0
    for fname, slugs in PLAN.items():
        path = ASSETS / fname
        im = Image.open(path).convert("RGB")
        W, H = im.size
        # DAY3 页眉带副标题，序号锚点会把它当成第一行，干脆按内容区均分
        centers = [] if fname == "day3.png" else badge_centers(im, H, W)
        print(f"{fname}: 序号圆心 y = {centers}")
        if len(centers) < len(slugs):
            print("  圆心不足，退化为均分行高")
            top, bottom = HEADER_BOTTOM.get(fname, 60), H - 16
            step = (bottom - top) / len(slugs)
            bands = [(int(top + i * step), int(top + (i + 1) * step))
                     for i in range(len(slugs))]
        else:
            hb = HEADER_BOTTOM.get(fname, 0)
            bands = [(max(hb, c - 80), min(H, c + 80)) for c in centers[:len(slugs)]]

        gray = list(im.convert("L").getdata())
        gray = [gray[y * W:(y + 1) * W] for y in range(H)]
        for slug, (y0, y1) in zip(slugs, bands):
            x0, x1 = best_window(gray, y0, y1)
            crop = im.crop((x0, y0, x1, y1))
            crop = crop.resize((int(crop.width * 1.45), int(crop.height * 1.45)),
                               Image.LANCZOS)
            crop.save(ASSETS / f"{slug}.png")
            made += 1
            print(f"  {slug:18s} y={y0}-{y1} x={x0}-{x1} -> {crop.size}")
    print("共裁出", made, "张")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
