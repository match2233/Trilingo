import pathlib
import re
import subprocess

ROOT = pathlib.Path(__file__).resolve().parent.parent

STRICT = {
    "身高+cm": r"1[5-9]\d\s*cm",
    "生日字面量": r"(19|20)\d{2}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])",
    "邮箱": r"[\w.+-]+@(?!example|test)[\w-]+\.[\w.]{2,}",
    "手机号": r"(?<!\d)1[3-9]\d{9}(?!\d)",
    "身份证": r"(?<!\d)\d{17}[\dXx](?!\d)",
}
# 生日字面量里 2026-xx-xx 这类文档/注释日期是正常的，排除 2025/2026
OK_YEARS = ("2025", "2026")

# 只在历史检查里用的"线索串"，从本机资料文件读，避免把真实数值写进源码
_prof = ROOT / "data" / "fit_profile.json"
try:
    import json as _json
    _d = _json.loads(_prof.read_text(encoding="utf-8"))
    HEIGHT_HINT = f"{_d.get('height_cm', '')}cm" if _d.get("height_cm") else ""
    BIRTH_HINT = str(_d.get("birth") or "")
except Exception:
    HEIGHT_HINT = BIRTH_HINT = ""

tracked = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True,
                         text=True, encoding="utf-8").stdout.splitlines()

hits = []
for f in tracked:
    p = ROOT / f
    if not p.is_file() or p.suffix.lower() not in (
            ".py", ".js", ".json", ".md", ".html", ".css", ".txt", ".bat",
            ".sql", ".pyw", ".yml", ".toml"):
        continue
    try:
        text = p.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        continue
    for name, pat in STRICT.items():
        for m in re.finditer(pat, text):
            val = m.group(0)
            if name == "生日字面量" and val[:4] in OK_YEARS:
                continue      # 文档里的日期不算
            line = text.count("\n", 0, m.start()) + 1
            hits.append((name, f, line, val))

print("=== 严格扫描结果 ===")
if not hits:
    print("  没有发现身高/生日/邮箱/手机号/身份证 之类的真实标识")
for h in hits[:20]:
    print(f"  [{h[0]}] {h[1]}:{h[2]}  {h[3]}")

print("\n=== git 全历史 ===")
# 注意: 这里不要写死具体的身高/生日数值 —— 扫描器自己也会被提交进仓库
for pat in filter(None, (HEIGHT_HINT, BIRTH_HINT)):
    out = subprocess.run(["git", "log", "--oneline", "-S", pat, "--all"],
                         cwd=ROOT, capture_output=True, text=True,
                         encoding="utf-8").stdout.strip()
    print(f"  `{pat}`: {'无' if not out else '(仍有)'}")

print("\n=== 暴露时间窗 ===")
for rev in ("8be50ef", "7689a4b"):
    out = subprocess.run(["git", "log", "-1", "--format=%h %ci %s", rev],
                         cwd=ROOT, capture_output=True, text=True,
                         encoding="utf-8").stdout.strip()
    print("  ", out[:100])
