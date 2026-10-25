---
name: import-exam-papers
description: 把一摞日语试卷 PDF 导入成 Trilingo 的"试卷集"（单元测试 / JLPT 真题）。当用户说"导入试卷""加一套 N4 真题""把桌面上的初级下试卷导进来"时使用。走 tools/import_papers.py，自动做质量体检、OCR、AI 整理与校对，不重复导入已有试卷。
---

# 导入试卷

把这个文件夹里的试卷变成 App 里可以做的题。所有活都由
`tools/import_papers.py` 干, 这个 skill 说明**怎么判断、怎么收尾**。

## 一条命令

```bash
python tools/import_papers.py --folder "C:/Users/<user>\Desktop\N5" --name "JLPT-N5"
```

常用参数：

| 参数 | 用途 |
|---|---|
| `--analyze-only` | 只体检、打分、列问题，不导入（先看这个） |
| `--limit N` | 本次最多导几套（先导 1 套看效果） |
| `--minutes 105` | 整卷时限（倒计时用），JLPT N5 是 105 分钟 |
| `--kind jlpt` / `unit` | 试卷集类型 |
| `--no-repair` | 跳过最后的 AI 校对 |

## 它会依次做这些事

1. **扫描**：按子文件夹分组，每组识别出「试题 PDF / 答案 PDF 或图片 / 听力音频」。
   文件名含 `真题 试题 试卷 問題` 的当试卷，含 `答案 解析 参考` 的当答案，
   其余 PDF 也当答案处理。
2. **体检打分**（满分 100）：

   | 项 | 分 | 说明 |
   |---|---|---|
   | 有可用文字层 | 45 | 判据是**假名占比 ≥ 12%**。很多 PDF 有文字层但字体映射坏了，提取出来是形近字乱码，这种按扫描件算 |
   | 带答案 | 30 | 没有答案时 AI 可以生成，但质量存疑 |
   | 带听力音频 | 15 | |
   | 页数 ≥ 8 | 10 | 页数太少通常是残卷 |

   **低于 40 分直接放弃**（省 token）。
3. **取文字**：有可用文字层直接读；否则把每页渲染成图，用 Windows OCR（日文引擎）识别，
   并把 OCR 切开的中文/假名单字空格合并回去。
4. **AI 整理**：整份试卷的文字一次交给模型，输出
   `{"sections":[{"no":1,"title":"問題1","kind":"choice","items":[{prompt,options,answer,image}]}]}`。
5. **AI 校对**：再通读一遍，只修 OCR 错字、假名、缺答案，不改写题目。
6. **去重**：按 PDF 的 sha1 比对全库已导入的 `source_sha`，重复的直接跳过。
7. **落库**：写进 `data/tests/<集>.json`，并在 `data/tests/index.json` 登记试卷集。

## 试卷集与编号

`data/tests/index.json` 里每条记录一个试卷集：

```json
{"id":"jlpt_n5","name":"JLPT-N5","kind":"jlpt","base":1001,
 "file":"jlpt_n5.json","desc":"日本语能力试验 N5 历年真题"}
```

`base` 决定编号段：单元测试 `1`，N5 `1001`，N4 `2001`，N3 `3001`……
**各段不重叠**，所以收藏夹、进度、成绩天然按试卷集分开，不需要改数据库。
新集由脚本自动分配 `base = 1001 + 1000 * 已有非单元测试集个数`。

## 收尾检查（每次导完都要跑）

```bash
python tools/verify_minna_tests.py        # 结构与答案自洽
python tools/audit_minna_tests.py --lesson <新编号>   # 语境复查, 报告问题
python tools/apply_audit_fixes.py         # 字形类问题自动写回
python tools/resolve_pending.py           # 需要判断的逐条定夺
```

导入后**一定要人工过一遍**这套检查：OCR 出来的题目错字率不低，
`audit → apply → resolve` 这条链路能把大部分修掉。

## 已知限制

* **听力题**：音频文件能找到，但还没有播放器。导入时听力部分会被整理成题目，
  但没有音频可放——需要先在 UI 里加播放器，见下一条。
* **图片题**：`item["image"]` 字段已预留（相对路径），AI 会标 `image: true`，
  但自动裁图尚未实现。目前含图的题只能靠文字题干作答。
* **扫描件质量决定上限**：OCR 把汉字认成形近字很常见（力/カ、朋/服、才/そ），
  所以第 5 步的 AI 校对和收尾的 audit 不能省。

## 什么时候别用

* 试卷是纯图片且分辨率低（< 150 DPI）：OCR 出来的东西修不如不修，直接放弃。
* 用户只想看某一套：用 `--limit 1`，别整批导。
