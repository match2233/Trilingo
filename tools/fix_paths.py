"""把 tools/ 里被历史改写牵连的本机绝对路径，统一改成"相对仓库"的写法.

filter-repo 清历史时把这些脚本里的 C:\\Users\\match 也替换成了 C:/Users/<user>，
本机就跑不起来了。这里把它们改成：
  * ROOT 一律用 __file__ 推出来；
  * 外部输入（Temp 里的 txt、桌面的 docx）放到可传参 / 默认指向仓库内的 data/import。
"""
from __future__ import annotations

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"

REPLACEMENTS = {
    "build_chujixia_ai.py": [
        ('TXT = pathlib.Path(r"C:/Users/<user>\\AppData\\Local\\Temp\\chujixia.txt")',
         'TXT = ROOT / "data" / "import" / "chujixia.txt"   # 由 docx 转出的纯文本'),
    ],
    "parse_chujixia.py": [
        ('TXT = pathlib.Path(r"C:/Users/<user>\\AppData\\Local\\Temp\\chujixia.txt")',
         'TXT = ROOT / "data" / "import" / "chujixia.txt"'),
        ('out = pathlib.Path(r"C:/Users/<user>\\Desktop\\trilingo\\data\\ocr\\chujixia_draft.json")',
         'out = ROOT / "data" / "ocr" / "chujixia_draft.json"'),
    ],
    "build_minna_tests.py": [
        ('default=r"C:/Users/<user>\\Downloads\\7054163164000012.pdf")',
         'default=None)'),
    ],
    "compare_redo.py": [
        ('ROOT = pathlib.Path(r"C:/Users/<user>\\Desktop\\trilingo")',
         'ROOT = pathlib.Path(__file__).resolve().parent.parent'),
    ],
    "import_all_n5.py": [
        ('N5 = pathlib.Path(r"C:/Users/<user>\\Desktop\\N5")',
         'N5 = pathlib.Path(__file__).resolve().parent.parent / "data" / "import" / "N5"'),
    ],
    "scan_layout.py": [
        ('N5 = pathlib.Path(r"C:/Users/<user>\\Desktop\\N5")',
         'N5 = pathlib.Path(__file__).resolve().parent.parent / "data" / "import" / "N5"'),
    ],
    "import_move_images.py": [
        ('DOCX = pathlib.Path(r"C:/Users/<user>\\Desktop\\新建 DOCX 文档.docx")',
         'DOCX = ROOT / "data" / "import" / "moves.docx"'),
        ('tmp = pathlib.Path(r"C:/Users/<user>\\AppData\\Local\\Temp\\docx_media")',
         'tmp = ROOT / "data" / "import" / "docx_media"'),
    ],
    "scan_all_objects.py": [
        ('ROOT = r"C:/Users/<user>\\Desktop\\trilingo"',
         'ROOT = str(pathlib.Path(__file__).resolve().parent.parent)'),
    ],
    "scan_personal_info.py": [
        ('ROOT = pathlib.Path(r"C:/Users/<user>\\Desktop\\trilingo")',
         'ROOT = pathlib.Path(__file__).resolve().parent.parent'),
        ('_prof = pathlib.Path(r"C:/Users/<user>\\Desktop\\trilingo\\data\\fit_profile.json")',
         '_prof = ROOT / "data" / "fit_profile.json"'),
    ],
}

changed = []
for name, pairs in REPLACEMENTS.items():
    p = TOOLS / name
    if not p.exists():
        print("跳过（不存在）:", name)
        continue
    s = p.read_text(encoding="utf-8")
    orig = s
    for old, new in pairs:
        if old in s:
            s = s.replace(old, new)
    if s != orig:
        p.write_text(s, encoding="utf-8")
        changed.append(name)

print("改过:", changed)
leftover = []
for p in TOOLS.glob("*.py"):
    text = p.read_text(encoding="utf-8", errors="ignore")
    if "C:/Users/<user>" in text or re.search(r"C:\\\\Users", text):
        leftover.append(p.name)
print("还剩绝对路径的脚本:", leftover or "无")
