"""英语美式音标 (IPA) 生成.

数据来源: CMUdict (American English, 126k 词条, ARPAbet 音素).
本模块把 ARPAbet 转写为学习者词典常用的美式 IPA 形式, 并按
"最大音节首" 原则为每个重读元音定位重音符号位置.

输出风格参考朗文/牛津美式标注, 例如:
    conspiracy -> kənˈspɪrəsi
    instantaneous -> ˌɪnstənˈteɪniəs
"""
from __future__ import annotations

# ARPAbet 元音 -> IPA (带重音的数字会被剥离)
_VOWELS = {
    "AA": "ɑ",
    "AE": "æ",
    "AH": "ʌ",
    "AO": "ɔ",
    "AW": "aʊ",
    "AY": "aɪ",
    "EH": "e",
    "ER": "ɜr",
    "EY": "eɪ",
    "IH": "ɪ",
    "IY": "i",
    "OW": "oʊ",
    "OY": "ɔɪ",
    "UH": "ʊ",
    "UW": "u",
}

_CONSONANTS = {
    "B": "b",
    "CH": "tʃ",
    "D": "d",
    "DH": "ð",
    "F": "f",
    "G": "g",
    "HH": "h",
    "JH": "dʒ",
    "K": "k",
    "L": "l",
    "M": "m",
    "N": "n",
    "NG": "ŋ",
    "P": "p",
    "R": "r",
    "S": "s",
    "SH": "ʃ",
    "T": "t",
    "TH": "θ",
    "V": "v",
    "W": "w",
    "Y": "j",
    "Z": "z",
    "ZH": "ʒ",
}

# 合法的英语音节首辅音组合 (ARPAbet)
_ONSETS2 = {
    ("P", "L"), ("P", "R"), ("P", "Y"), ("B", "L"), ("B", "R"), ("B", "Y"),
    ("T", "R"), ("T", "W"), ("T", "Y"), ("D", "R"), ("D", "W"), ("D", "Y"),
    ("K", "L"), ("K", "R"), ("K", "W"), ("K", "Y"), ("G", "L"), ("G", "R"),
    ("G", "W"), ("G", "Y"), ("F", "L"), ("F", "R"), ("F", "Y"), ("V", "Y"),
    ("TH", "R"), ("TH", "W"), ("S", "L"), ("S", "M"), ("S", "N"), ("S", "P"),
    ("S", "T"), ("S", "K"), ("S", "W"), ("S", "Y"), ("S", "F"), ("SH", "R"),
    ("SH", "W"), ("HH", "Y"), ("M", "Y"), ("N", "Y"), ("L", "Y"), ("Z", "W"),
    ("CH", "R"), ("JH", "R"),
}
_ONSETS3 = {
    ("S", "P", "L"), ("S", "P", "R"), ("S", "T", "R"), ("S", "K", "R"),
    ("S", "K", "W"), ("S", "P", "Y"), ("S", "T", "Y"), ("S", "K", "Y"),
    ("S", "K", "L"),
}


def _is_vowel(ph: str) -> bool:
    return ph.rstrip("012") in _VOWELS


def _strip(ph: str) -> str:
    return ph.rstrip("012")


def _stress(ph: str) -> str:
    return ph[-1] if ph and ph[-1].isdigit() else "0"


def _max_onset_len(cluster: tuple[str, ...]) -> int:
    """返回该辅音序列中可作为音节首的最大长度 (0 表示整体作前一首节的韵尾)."""
    n = len(cluster)
    for k in range(min(n, 3), 0, -1):
        part = cluster[n - k:]
        if k == 1:
            if part[0] != "NG":
                return 1
        elif k == 2:
            if part in _ONSETS2:
                return 2
        else:
            if part in _ONSETS3:
                return 3
    return 0


def arpabet_to_ipa(phones: list[str]) -> str:
    """把单个发音 (ARPAbet 列表) 转成带重音符号的 IPA 字符串."""
    if not phones:
        return ""

    phones = [_strip(p) if _stress(p) == "0" else p for p in phones]
    # 元音下标
    vowel_idx = [i for i, p in enumerate(phones) if _is_vowel(p)]
    if not vowel_idx:
        return "".join(_CONSONANTS.get(p, "") for p in phones)

    # 每个元音所属音节的起始下标
    onset_start: dict[int, int] = {}
    onset_start[vowel_idx[0]] = 0
    for a, b in zip(vowel_idx, vowel_idx[1:]):
        cluster = tuple(phones[a + 1 : b])
        k = _max_onset_len(cluster) if cluster else 0
        onset_start[b] = b - k

    # 重音符号落在重读元音所在音节的起始位置 (即音节首之前)
    marks: dict[int, str] = {}
    for v, st_idx in onset_start.items():
        st = _stress(phones[v])
        if st == "1":
            marks[st_idx] = "ˈ"
        elif st == "2":
            marks[st_idx] = "ˌ"

    out: list[str] = []
    for i, ph in enumerate(phones):
        if i in marks:
            out.append(marks[i])
        if _is_vowel(ph):
            base = _strip(ph)
            if base == "AH" and _stress(ph) == "0":
                out.append("ə")
            elif base == "ER" and _stress(ph) == "0":
                out.append("ər")
            else:
                out.append(_VOWELS[base])
        else:
            out.append(_CONSONANTS.get(_strip(ph), ""))
    return "".join(out)


# --------------------------------------------------------------- 词库
_dict: dict[str, list[list[str]]] | None = None


def _load_cmudict() -> dict[str, list[list[str]]]:
    global _dict
    if _dict is None:
        try:
            from cmudict import dict as _cd

            _dict = _cd()
        except Exception:
            _dict = {}
            path = _fallback_dict_path()
            if path and path.is_file():
                _dict = _parse_cmudict_file(path)
    return _dict


def _fallback_dict_path():
    from .config import DATA_DIR

    return DATA_DIR / "cmudict.dict"


def _parse_cmudict_file(path) -> dict[str, list[list[str]]]:
    entries: dict[str, list[list[str]]] = {}
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.split("#", 1)[0].strip()
            if not line:
                continue
            head, _, rest = line.partition(" ")
            key = head.split("(", 1)[0].strip().lower()
            if not key or not rest.strip():
                continue
            entries.setdefault(key, []).append(rest.split())
    return entries


def _lookup(word: str) -> list[str] | None:
    d = _load_cmudict()
    key = word.strip().lower()
    prons = d.get(key)
    if not prons:
        return None
    return prons[0]


def phonetics(word: str) -> str | None:
    """返回单词的美式 IPA, 查不到返回 None.

    支持连字符/空格复合词 (逐段拼接), 例如 walkie-talkie.
    """
    if not word:
        return None
    direct = _lookup(word)
    if direct:
        return arpabet_to_ipa(direct)

    # 复合词: 按非字母字符切分后拼接
    import re

    parts = [p for p in re.split(r"[^A-Za-z']+", word) if p]
    if len(parts) > 1:
        chunks = []
        for p in parts:
            pr = _lookup(p)
            if not pr:
                return None
            chunks.append(arpabet_to_ipa(pr))
        return " ".join(chunks)

    # 简单屈折变化回退: 去 e / 去尾字母
    lowered = word.lower()
    for suffix, repl in (("s", ""), ("es", ""), ("ed", ""), ("ing", "")):
        if lowered.endswith(suffix) and len(lowered) > len(suffix) + 2:
            base = lowered[: -len(suffix)]
            if suffix == "ing":
                for cand in (base, base + "e"):
                    pr = _lookup(cand)
                    if pr:
                        return arpabet_to_ipa(pr)
            pr = _lookup(base + repl)
            if pr:
                return arpabet_to_ipa(pr)
    return None
