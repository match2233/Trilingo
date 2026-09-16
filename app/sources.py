"""读取桌面的 词汇英.xlsx / 词汇日.xlsx.

*** 只读 ***  本模块只做解析, 绝不写入或保存这两个文件.
"""
from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

# 日语假名范围
_KANA = re.compile(r"[぀-ゟ゠-ヿー]")
_KANJI = re.compile(r"[㐀-䶿一-鿿]")


def has_kanji(s: str) -> bool:
    return bool(_KANJI.search(s or ""))


def has_kana(s: str) -> bool:
    return bool(_KANA.search(s or ""))


def is_kana_only(s: str) -> bool:
    s = (s or "").strip()
    return bool(s) and not has_kanji(s) and has_kana(s)


@dataclass
class EnEntry:
    word: str
    meaning: str
    row: int


@dataclass
class JpEntry:
    word: str          # 显示形式: 有汉字用汉字, 无汉字用假名
    reading: str       # 假名读音 (可能为空)
    row: int
    col: int
    alt_forms: list[str] = field(default_factory=list)  # 其他可接受答案
    sheet: int = 1     # 来自第几个工作表 (1-based)


# ------------------------------------------------------------------ 底层读取
def _sheet_files(z: zipfile.ZipFile) -> list[str]:
    """按 sheet1 / sheet2 / ... 的顺序返回工作表 xml 路径."""
    names = [
        n for n in z.namelist()
        if n.startswith("xl/worksheets/sheet") and n.endswith(".xml")
    ]

    def order(n: str) -> int:
        m = re.search(r"sheet(\d+)\.xml$", n)
        return int(m.group(1)) if m else 10 ** 9

    return sorted(names, key=order)


def _read_grids(path: Path, which="all") -> list[list[list[str]]]:
    """读取工作表, 返回 [二维表, ...].

    which="all" 读全部工作表; which=0/1/2... 只读对应下标的表.
    """
    try:
        return _read_grids_openpyxl(path, which)
    except ImportError:
        return _read_grids_stdlib(path, which)


def _read_grid(path: Path, sheet_index: int = 0) -> list[list[str]]:
    """只读某一张工作表 (英语词表用)."""
    grids = _read_grids(path, sheet_index)
    return grids[0] if grids else []


def _norm_row(values) -> list[str]:
    return ["" if c is None else str(c).strip() for c in values]


def _read_grids_openpyxl(path: Path, which) -> list[list[list[str]]]:
    import openpyxl

    # read_only + data_only: 只读句柄, 不占用写锁, 也不会修改文件
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        if which == "all":
            sheets = list(wb.worksheets)
        else:
            sheets = [wb.worksheets[which]] if which < len(wb.worksheets) else []
        return [[_norm_row(r) for r in ws.iter_rows(values_only=True)] for ws in sheets]
    finally:
        wb.close()


def _col_to_idx(ref: str) -> int:
    n = 0
    for ch in ref:
        if ch.isalpha():
            n = n * 26 + (ord(ch.upper()) - 64)
    return n - 1


def _read_grids_stdlib(path: Path, which) -> list[list[list[str]]]:
    """openpyxl 不可用时的纯标准库回退实现."""
    import xml.etree.ElementTree as ET

    M = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    with zipfile.ZipFile(path) as z:
        shared: list[str] = []
        if "xl/sharedStrings.xml" in z.namelist():
            root = ET.fromstring(z.read("xl/sharedStrings.xml"))
            for si in root.findall(f"{M}si"):
                shared.append("".join(t.text or "" for t in si.iter(f"{M}t")))

        files = _sheet_files(z)
        if which != "all":
            files = [files[which]] if which < len(files) else []

        out: list[list[list[str]]] = []
        for name in files:
            root = ET.fromstring(z.read(name))
            grid: list[list[str]] = []
            for row in root.iter(f"{M}row"):
                cells: dict[int, str] = {}
                for c in row.findall(f"{M}c"):
                    ref = c.get("r") or ""
                    t = c.get("t")
                    v = c.find(f"{M}v")
                    is_el = c.find(f"{M}is")
                    if is_el is not None:
                        val = "".join(x.text or "" for x in is_el.iter(f"{M}t"))
                    elif v is None:
                        val = ""
                    elif t == "s":
                        val = shared[int(v.text)]
                    else:
                        val = v.text or ""
                    val = val.strip()
                    if val:
                        cells[_col_to_idx(ref)] = val
                if cells:
                    width = max(cells) + 1
                    grid.append([cells.get(i, "") for i in range(width)])
                else:
                    grid.append([])
            out.append(grid)
        return out


# ------------------------------------------------------------------ 英语
# 英语表结构: A=序号  B=单词  C=中文意思
def parse_english(path: Path) -> list[EnEntry]:
    grid = _read_grid(path)
    out: list[EnEntry] = []
    seen: set[str] = set()
    _HEADER = {"word", "words", "单词", "英文", "english", "vocabulary", "序号", "index", "no"}
    for i, row in enumerate(grid):
        cells = [c for c in row if c != ""]
        if not cells:
            continue
        word = ""
        meaning = ""
        # 常见布局: 第1列序号, 第2列单词, 第3列释义; 也兼容无序号布局
        if len(row) >= 2 and re.fullmatch(r"\d+(\.0)?", row[0] or ""):
            word = row[1] if len(row) > 1 else ""
            meaning = row[2] if len(row) > 2 else ""
        else:
            non_num = [c for c in row if c and not re.fullmatch(r"\d+(\.0)?", c)]
            if non_num:
                word = non_num[0]
                meaning = " ".join(non_num[1:])
        word = (word or "").strip()
        if not word or not re.search(r"[A-Za-z]", word):
            continue
        # 表头行 (如 "word | 中文意思")
        if i == 0 and word.lower().strip(" .:") in _HEADER:
            continue
        key = word.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(EnEntry(word=word, meaning=meaning.strip(), row=i + 1))
    return out


# ------------------------------------------------------------------ 日语
# 表结构: 每 3 列一组, 前两列是 (词, 假名读音), 第三列为空列分隔
def _pairs_for_grid(grid: list[list[str]]) -> list[tuple[int, int | None]]:
    """在一张表里找出 (词列, 读音列) 配对.

    表结构为每 3 列一组: 前两列是 (词, 假名读音), 第三列为空列分隔。
    """
    width = max((len(r) for r in grid), default=0)
    # 找出全局非空列, 按连续段分组
    filled_cols = [c for c in range(width) if any(r[c] for r in grid if c < len(r))]
    runs: list[list[int]] = []
    for c in filled_cols:
        if runs and c == runs[-1][-1] + 1:
            runs[-1].append(c)
        else:
            runs.append([c])

    pairs: list[tuple[int, int | None]] = []
    for run in runs:
        i = 0
        while i < len(run):
            wc = run[i]
            rc = run[i + 1] if i + 1 < len(run) else None
            # 若"读音列"里出现汉字, 说明那是另一个词列, 分开处理
            if rc is not None:
                vals = [r[rc] for r in grid if rc < len(r) and r[rc]]
                if vals and sum(1 for v in vals if has_kanji(v)) > len(vals) / 2:
                    rc = None
            pairs.append((wc, rc))
            i += 2 if rc is not None else 1
    return pairs


def parse_japanese(path: Path) -> list[JpEntry]:
    """读取【全部工作表】(Sheet1、Sheet2、Sheet3 …), 格式相同则一并收录."""
    out: list[JpEntry] = []
    seen: set[str] = set()

    for sheet_no, grid in enumerate(_read_grids(path, "all"), start=1):
        if not grid:
            continue
        for wc, rc in _pairs_for_grid(grid):
            for row in grid:
                if wc >= len(row):
                    continue
                word = (row[wc] or "").strip()
                if not word:
                    continue
                reading = ""
                if rc is not None and rc < len(row):
                    reading = (row[rc] or "").strip()
                # 读音单元格若非假名(比如误放汉字)则忽略
                if reading and has_kanji(reading):
                    reading = ""

                # 跨表去重: 同一个词只收录第一次出现的
                if word in seen:
                    continue
                seen.add(word)

                alts: list[str] = []
                if reading:
                    alts.append(reading)
                    # 复合读音 "げつ、か、すい…" 允许整体连写
                    if "、" in reading or "，" in reading:
                        alts.append(re.sub(r"[、，]", "", reading))
                out.append(
                    JpEntry(
                        word=word,
                        reading=reading,
                        row=0,
                        col=wc + 1,
                        alt_forms=alts,
                        sheet=sheet_no,
                    )
                )
    return out
