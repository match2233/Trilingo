"""PWA 静态接线检查: JS 里引用的元素 id / data-* 是否都在 index.html 里."""
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"

html = (DOCS / "index.html").read_text(encoding="utf-8")
ids = set(re.findall(r'id="([^"]+)"', html))
classes = set(re.findall(r'class="([^"]*)"', html))
all_cls = set()
for c in classes:
    all_cls |= set(c.split())

missing = []
# 运行时由 innerHTML 生成的 id 也算存在, 先在 JS 源码里收集一遍
dynamic = set()
srcs = {}
for name in ("app.js", "minna.js", "life.js"):
    src = (DOCS / name).read_text(encoding="utf-8")
    srcs[name] = src
    dynamic |= set(re.findall(r'id="([^"$]+)"', src))

for name, src in srcs.items():
    refs = set(re.findall(r"\$\('([^']+)'\)", src))
    refs |= set(re.findall(r"getElementById\('([^']+)'\)", src))
    for r in sorted(refs):
        if r not in ids and r not in dynamic:
            missing.append((name, r))

print(f"index.html 里的 id 共 {len(ids)} 个, JS 动态生成的 id {len(dynamic)} 个")
if missing:
    print(f"引用了但到处都找不到的 id: {len(missing)}")
    for name, r in missing:
        print(f"  {name}: #{r}")
else:
    print("所有 $()/getElementById() 引用都能找到对应元素 ✓")

# 反过来: HTML 里有 id 但没人引用 (只提示, 不算错)
used = set()
for name in ("app.js", "minna.js", "life.js"):
    src = (DOCS / name).read_text(encoding="utf-8")
    used |= set(re.findall(r"\$\('([^']+)'\)", src))
unused = sorted(ids - used)
print(f"HTML 里定义了但 JS 未引用的 id: {len(unused)}")
if unused:
    print("  ", ", ".join(unused[:20]))

# 题库 JSON 结构是否符合 JS 期望
import json
bank = json.loads((DOCS / "minna_tests.json").read_text(encoding="utf-8"))
les = bank.get("lessons") or []
bad = []
for l in les:
    if "lesson" not in l or "sections" not in l:
        bad.append(l.get("lesson"))
        continue
    for s in l["sections"]:
        for it in s.get("items") or []:
            for k in ("id", "prompt"):
                if k not in it:
                    bad.append(f"L{l['lesson']}S{s['no']} 缺 {k}")
            if s["kind"] == "choice":
                if "options" not in it:
                    bad.append(f"{it.get('id')} 缺 options")
                elif not isinstance(it.get("answer"), int) and not l.get("no_answer"):
                    bad.append(f"{it.get('id')} 答案不是序号")
print(f"题库: {len(les)} 课, 结构问题 {len(bad)} 处")
for b in bad[:10]:
    print("  -", b)
sys.exit(1 if (missing or bad) else 0)
