"""把 git 里**每一个历史对象**都翻一遍，找可能的个人信息.

不做 --all 的逐提交 grep（那样只查路径可达的差异），而是枚举 rev-list --objects
拿到的全部 blob，逐个看内容，这样连"曾经存在过、后来删掉"的文件也能覆盖。

检查项：
  * 身高（150-199cm / 150-199 cm）
  * 生日 / 出生（19xx-/20xx- 的日期 + 出生/生日字样，排除 2025/2026 文档日期）
  * 邮箱、手机号、身份证号
  * 已知的两个具体串（、）
"""
from __future__ import annotations

import re
import subprocess

ROOT = r"C:/Users/<user>\Desktop\trilingo"

PATTERNS = {
    "身高": re.compile(r"1[5-9]\d\s*(cm|CM|厘米)"),
    "出生/生日": re.compile(r"(出生|生日|生于)"),
    "生日日期": re.compile(r"(19[6-9]\d|200[0-9])-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])"),
    "邮箱": re.compile(r"[\w.+-]+@[\w-]+\.[\w.]{2,}"),
    "手机号": re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"),
    "身份证": re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)"),
}
IGNORE_EMAIL_DOMAINS = ("example.com", "users.noreply.github.com",
                        "github.com", "anthropic.com")


def git(*args: str, binary: bool = False) -> bytes | str:
    out = subprocess.run(["git", *args], cwd=ROOT, capture_output=True)
    return out.stdout if binary else out.stdout.decode("utf-8", "ignore")


def main() -> int:
    objs = git("rev-list", "--objects", "--all").splitlines()
    print(f"历史对象总数: {len(objs)}")

    findings: dict[str, list[str]] = {}
    checked = 0
    for line in objs:
        sha, _, path = line.partition(" ")
        kind = git("cat-file", "-t", sha).strip()
        if kind != "blob":
            continue
        if path and re.search(r"\.(png|jpg|jpeg|ico|gif|zip|woff2?|mp3)$", path):
            continue
        data = git("cat-file", "blob", sha, binary=True)
        if b"\x00" in data[:1024]:
            continue
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            continue
        checked += 1
        for name, pat in PATTERNS.items():
            for m in pat.finditer(text):
                val = m.group(0)
                if name == "邮箱" and any(d in val for d in IGNORE_EMAIL_DOMAINS):
                    continue
                if name == "出生/生日":
                    line_txt = text[max(0, m.start() - 30):m.end() + 30]
                    if "说明" in line_txt or "注释" in line_txt:
                        continue
                findings.setdefault(f"{name}: {val}", []).append(
                    f"{sha[:8]} {path or '(无路径)'}")

    print(f"检查过 {checked} 个文本对象")
    if not findings:
        print("没有发现个人信息")
        return 0
    print("\n=== 命中 ===")
    for key, where in sorted(findings.items()):
        print(f"  {key}")
        for w in where[:4]:
            print(f"      {w}")
        if len(where) > 4:
            print(f"      ...共 {len(where)} 处")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
