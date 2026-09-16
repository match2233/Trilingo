"""创建桌面快捷方式 Trilingo.lnk (图标用 trilingo.ico, 由微信图片转换而来).

用法:  python create_shortcut.py
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LAUNCHER = ROOT / "Trilingo.pyw"
ICON = ROOT / "trilingo.ico"
sys.path.insert(0, str(ROOT))


def desktop_dir() -> Path:
    from app.config import _desktop_candidates

    for d in _desktop_candidates():
        if d.is_dir():
            return d
    return Path.home() / "Desktop"


def pythonw() -> str:
    """优先用 pythonw.exe, 这样启动时不带黑色控制台窗口."""
    exe = Path(sys.executable)
    cand = exe.with_name("pythonw.exe")
    return str(cand if cand.is_file() else exe)


def ensure_icon() -> Path | None:
    """若 ico 不存在, 从项目里的 jpg 现场生成.

    仓库里只带 trilingo.ico, 不带原图; 若两者都没有则返回 None,
    快捷方式仍会创建, 只是用系统默认图标。
    """
    if ICON.is_file():
        return ICON
    src = next(ROOT.glob("*.jpg"), None)
    if src is None:
        print("提示：未找到 trilingo.ico 或原图，将使用系统默认图标。")
        return None

    from PIL import Image

    im = Image.open(src).convert("RGBA")
    w, h = im.size
    s = min(w, h)
    im = im.crop(((w - s) // 2, (h - s) // 2, (w - s) // 2 + s, (h - s) // 2 + s))
    im.save(ICON, format="ICO", sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])
    return ICON


def main() -> int:
    icon = ensure_icon()
    target = pythonw()
    lnk = desktop_dir() / "Trilingo.lnk"
    icon_line = f'$sc.IconLocation = "{icon}"' if icon else "# 无图标文件，沿用系统默认图标"

    ps = f"""
$ws = New-Object -ComObject WScript.Shell
$sc = $ws.CreateShortcut("{lnk}")
$sc.TargetPath = "{target}"
$sc.Arguments = '"{LAUNCHER}"'
$sc.WorkingDirectory = "{ROOT}"
{icon_line}
$sc.Description = "Trilingo - 英语/日语背单词"
$sc.Save()
Write-Output "OK"
"""
    # 用 -Command 传内联脚本: 不涉及脚本文件执行策略, 无需改动系统安全设置
    r = subprocess.run(
        ["powershell", "-NoProfile", "-Command", ps],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if r.returncode != 0 or "OK" not in (r.stdout or ""):
        print("创建快捷方式失败：", r.stdout, r.stderr)
        return 1
    print(f"桌面快捷方式已创建：{lnk}")
    print(f"  目标：{target} \"{LAUNCHER}\"")
    print(f"  图标：{icon if icon else '（默认）'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
