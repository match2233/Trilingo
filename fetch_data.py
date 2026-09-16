"""下载日语声调库 (Kanjium accents.txt, CC BY-SA 4.0).

首次使用前跑一次即可；仓库里不附带这个文件。
下载失败也不影响应用运行 —— 声调会显示「声调待补」。

用法:  python fetch_data.py
"""
from __future__ import annotations

import ssl
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DEST = ROOT / "data" / "kanjium_accents.txt"

RAW = ("https://raw.githubusercontent.com/mifunetoshiro/kanjium/master/"
       "data/source_files/raw/accents.txt")

# 国内直连 GitHub 常常不通，多试几个镜像
MIRRORS = [
    "https://ghfast.top/{url}",
    "https://ghproxy.net/{url}",
    "{url}",
]

EXPECTED_LINES = 120_000     # 完整文件约 124,137 行，用来判断是否被截断


def try_download(url: str) -> bytes | None:
    ctx = ssl._create_unverified_context()
    req = urllib.request.Request(url, headers={"User-Agent": "Trilingo/1.0"})
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=120) as resp:
            return resp.read()
    except Exception as exc:  # noqa: BLE001
        print(f"    失败: {type(exc).__name__}: {str(exc)[:80]}")
        return None


def main() -> int:
    if DEST.is_file() and DEST.stat().st_size > 1_000_000:
        print(f"已存在，跳过：{DEST}  ({DEST.stat().st_size / 1e6:.1f} MB)")
        return 0

    DEST.parent.mkdir(parents=True, exist_ok=True)

    for tpl in MIRRORS:
        url = tpl.format(url=RAW)
        print(f"尝试 {url.split('/')[2]} …")
        data = try_download(url)
        if not data:
            continue

        lines = data.count(b"\n")
        # 有的镜像会静默截断，检查一下行数
        if lines < EXPECTED_LINES:
            print(f"    只拿到 {lines} 行（应约 {EXPECTED_LINES} 行），疑似被截断，换下一个镜像")
            continue

        DEST.write_bytes(data)
        print(f"完成：{DEST}  ({len(data) / 1e6:.1f} MB, {lines} 行)")
        return 0

    print("\n全部镜像都失败了。")
    print("可以开代理后重试，或手动下载后保存到：")
    print(f"  {DEST}")
    print(f"  来源: {RAW}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
