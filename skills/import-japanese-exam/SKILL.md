---
name: import-japanese-exam
description: 把一个文件夹里的日语试卷（PDF/答案/听力）体检、评分、解析成 Trilingo 的题库 JSON，并做 AI 补答案与错字修补；用于新增「新标日初级下」「JLPT-N4/N3」等试卷集时。当用户说「导入这套卷子 / 加一套真题 / 这个文件夹里有试卷」时使用。
---

# 导入日语试卷（Trilingo）

把一整套卷子（真题 PDF、答案、听力音频可能分散在子目录）变成
`data/exams/<id>.json`，桌面端和手机端立刻能用。

## 什么时候用

* 用户往 `C:/Users/<user>\Desktop\N5` 这类文件夹里丢了一套新卷子，说「导入」
* 要新增试卷集：新标日初级下、JLPT-N4/N3
* 要复查某套卷子的答案/错字（只跑第 5、6 步）

## 数据结构（先看这个）

一个试卷集 = 一个 JSON：

```json
{
  "version": 2,
  "meta": {"id": "jlpt-n5", "name": "JLPT-N5", "kind": "jlpt",
           "desc": "2010-2025 真题", "duration_min": 105, "order": 20},
  "lessons": [
    {"lesson": 1, "title": "2010年07月", "duration_min": 105,
     "sections": [
       {"no": 1, "title": "漢字の読み方", "kind": "choice",
        "items": [{"id": "Q01-S1-1", "prompt": "…",
                   "options": ["…","…","…","…"], "answer": 2,
                   "image": "exams/jlpt-n5/2010-07/q01-1.png"}]}
     ]}
  ]
}
```

* `kind`：`choice` 四选一；`fill` 填空；`translate` 翻译
* `duration_min`：卷面限时，>0 时答题页右上角变**倒计时**，时间到自动交卷
* `image`：题目配图，相对于 `data/`；图片从 PDF 里按题裁出来
* 题目 `id` 必须稳定（`Q<卷号>-S<大题号>-<小题号>`），收藏与进度都靠它

## 工作流

### 1. 体检与评分（先跑，别急着烧 token）

```bash
python -c "from app.exam_import import report; import json,pathlib; \
print(json.dumps(report(pathlib.Path(r'C:/Users/<user>\Desktop\N5')), ensure_ascii=False, indent=1))"
```

每份卷子会给出：页数、文字层是否可用、有没有答案、有没有音频、分数。
**分数 < 55 或文字层不可用的，一律不导入。**

判定「文字层不可用」的两种典型：

| 现象 | 含义 | 处理 |
|---|---|---|
| 前几页 0 字符 | 纯扫描件 | 需要 OCR，当前不能自动导入 |
| 有字但假名占比 < 25%（如 `伈京寸` 其实是 `です`） | PDF 字体映射损坏 | 同上；硬解出来的都是乱码 |

### 2. 去重

`app.exam_import.report()` 里的 `duplicate` 字段来自 `known_titles()`：
同名卷子已经在任何试卷集里出现过，就跳过。
新增试卷集前也检查一下 `meta.id` 是否重复。

### 3. 解析成题目

* 有正常文字层的 PDF：按页取文字，按「問題1/問題2…」或题号分组，
  四选一题取题干 + 4 个选项，答案从答案文件对。
* 答案文件是图片/扫描件：把题目文字（已解析出来的）批量发给 LLM，
  让它给出每题答案 —— 这是「缺答案但 AI 能解决」的情况。
* 题目里带插图：用 `pypdfium2` 把该页渲染成 PNG（`render(scale=2)`），
  按题目所在区域裁切，存到 `data/exams/<id>/<卷>/`，写进 `image` 字段。

### 4. AI 补答案 / 补解析

批量发题（一次 10-15 题）给 `app.llm`：

```python
from app import llm
llm._post(url, payload, key)   # 或者直接用 tools/fill_minna_answers.py 里的 ask()
```

只补**答案**，解析可有可无。补完必须校验：选择题答案必须是 1..4。

### 5. 全卷 AI 复查（必做）

```bash
python tools/audit_minna_tests.py --lesson 1 2 3     # 整段审校, 只报告
python tools/apply_audit_fixes.py                    # 只写回"字形/拼写"类
```

审校按**大题**整段发，能发现：字形错乱（力/カ、朋/服、才/そ）、
假名拼写、题干与选项不匹配、无解/多解、对话轮次错乱。
写回只接受"有明确对错"的修正；多解类只报告，人工判断。

### 6. 落地与自检

```bash
python tools/verify_minna_tests.py       # 结构/语言自洽
python tools/check_pwa.py                # PWA 接线
```

然后同步给手机端：

```bash
cp data/exams/jlpt-n5.json docs/exams/jlpt-n5.json     # 若 PWA 需要
# 改 docs/sw.js 的 CACHE 版本号
```

## 现成结论（2025-10 实测）

`C:/Users/<user>\Desktop\N5` 的 10 套卷子**全部不能自动导入**：

* 8 套是扫描件（0 文字层）
* 2 套（2016、2024-07）有文字层，但字体映射错乱，提取出来是 `伈京寸` 这种

要做这三件事之一才能导入：换「文字版/高清打印版」PDF、接 OCR
（如 PaddleOCR/tesseract）、或人工整理成 CSV 再转 JSON。

## 常见坑

* **别信 PDF 里提取出来的假名**：先算假名占比，低于 25% 直接判死。
* **别整段改写题干**：语言类别（日/中）一变就可能把日语题干换成中文译文
  —— 这类事故真发生过，见 `tools/apply_answer_fixes.py` 的注释。
* **id 必须稳定**：改了 id，用户的收藏和进度就对不上了。
* **答案个数 != 选项个数**：写回前必须校验，否则答题页会崩。
