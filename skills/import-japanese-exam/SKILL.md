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

### 2.5 扫描件/乱码: 先上 OCR

```bash
python tools/fetch_ocr_models.py                     # 一次性: 下日语模型(3.4MB)
python tools/ocr_paper.py <pdf> --pages 1-8 --scale 3.0
```

* rapidocr-onnxruntime 自带中文模型, **假名会被整个吞掉**, 必须换成日语
  rec 模型 (SWHL/RapidOCR 的 PP-OCRv1 japan_rec_crnn.onnx + PaddleOCR 的
  japan_dict.txt), 配置由 fetch_ocr_models.py 生成。
* 实测识别质量 (2016 N5): 「先週、デパートにかいものにいきました。」完全正确,
  假名偶有混淆 (さ/き、ぽ/ぼ、っ/。), 需要 AI 顺一遍。
* 速度 ~3-5 秒/页。

### 3. 解析成题目（实测可用的一条流水线）

```bash
# 1) OCR: PDF -> 逐页行文本(带坐标)
python tools/ocr_paper.py <pdf> --pages 1-8 --scale 2.2

# 2) AI 组装: 行 -> 四选一题目 (正则搞不定的版式交给模型)
python tools/assemble_questions.py <ocr.json> --out questions.json

# 3) 建卷: 题目 + 答案 -> 试卷集 lesson
python tools/build_exam_bank.py --questions questions.json \
    --collection jlpt-n5 --paper 1 --minutes 105 --answers answers.json
```

* **为什么用 AI 组装**：题号被 OCR 成 `ã2/ê5/30`、短假名选项被合成一行、
  题干到选项行距不固定 —— 规则写不赢版式，模型能"看懂"。实测 2016 卷
  8 页 → 50 题，且顺手改正了 `さんぼ→さんぽ`、`話きせて→話させて`。
* 组装时会**严格校验**：必须恰好 4 个选项、无重复、题干非空、含假名，
  不合格的整题丢掉（宁缺勿错）。
* **答案按"卷面题号"对齐**（模型组装时返回的 `no` 就是卷面题号），
  不要按"第几题"的位置对齐 —— 少解出一题就会整体串位。
  数量对不上时不要硬套，改用 AI 答案并标注来源。
* 答案表如果是一张干净的表格图片（如 2016 卷），**直接看图抄**比 OCR 靠谱
  （OCR 会把表格读成乱码）；抄成 `{"1":4,"2":2,…}` 存成 answers.json。
* 答案缺失时让 AI 生成答案（这是允许的降级路径）。
* **带插图的题**：`assemble_questions.py` 会让模型给每题打 `figure` 标记
  （只有题面真配图时才 true），再跑 `crop_figures.py`：
  ```bash
  python tools/crop_figures.py <pdf> --questions q.json --ocr ocr.json \
      --collection jlpt-n5 --paper 3
  ```
  它按"题干 y → 下一题 y"裁出页面区域，存 `data/exams/<id>/figures/`，
  并给题目写上 `image`；答题页会自动显示（`app/ui/minna_test.py: item_image`）。
  注意这些试卷的插图是**矢量绘制**的，PDF 里没有位图对象，只能按版面裁。
  另外别用关键词猜有没有图（「えき」「きょうなら」都会命中），必须让模型标。

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

### 5.5 三块合一（文字・語彙 / 文法・読解 / 聴解）

```bash
python tools/build_paper_full.py --paper 3 --title 2010年07月 \
    --pdf "<真题.pdf>" --answers data/ocr/answers_2010.json \
    --text-pages 3-4 --reading-pages 5-8 --listening-pages 9-11
```

12 页一套的版式是固定的: 1-2 封面说明, 3-4 文字・語彙, 5-8 文法・読解,
9-11 聴解, 12 参考答案。文法页要用 normal 模式组装, 只有长文页用 reading 模式
（全用 reading 会把语法题全漏掉, 实测 32 题只解出 8）。

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

## 答案表就在试卷最后一页（关键发现）

大多数 N5 真题 PDF 的**最后一页**是完整的「参考答案」表格, 分三段:

    N5.言語知識(文字.語彙)   問題1 1番..12番 / 答案 2 3 2 3 1 3 …
    N5.言語知識(文法.読解)   問題1..問題6 (题号重新从 1 开始)
    N5.聴解                  聴解1..聴解4 (每组从 1番 开始)

**答案按"题号"对齐, 不是按"第几题"对齐**:
模型组装时返回的 `no` 就是卷面题号 (2010 文字語彙返回 1..33 但缺 20),
所以哪怕少解出几题, 答案照样能精确套上 —— 之前按"数量相等才套"总是差一两题,
一旦硬套就会整体错位 (2012 卷把「水をください」的答案给成了「みす」)。

## 聴解怎么处理

聴解没有文字题干, 模型没法代答。可行做法:

1. **裁剪**试过三种都不可靠: 按「N番」行坐标切 (OCR 行序和版面经常对不上,
   会把两番裁进一张)、纯空白带切 (密集页切不开)、轮廓检测 (小图会碎)。
2. 现在用**按番裁图**: 每页按"横向全白的分隔行"切成行带 (每块含一番的编号 + 图),
   块比题多就合并最近的相邻块; 块比题少**不硬拆** (拆出来是 90px 残图),
   宁可后面几题共用最后一块。裁完按非白像素裁掉四周白边, 界面里才够大。
   选项固定 ①②③④, 答案取答案表 `聴解N` 的第 k 个。
   配 `app/audio.py` (pygame.mixer) 的播放条: 播放/暂停、±10 秒、重头。
3. **重建卷子时记得保留 lesson 的 audio 字段** —— 建卷脚本会覆盖整个 lesson,
   一不小心播放条就没了 (踩过)。

## 版式解析的坑（还没完全解决）

`tools/parse_n5.py` 目前是启发式的: 题号行 → 题干 → 4 个选项。实测只对
**版式特别规整**的段落有效 (2016 卷 8 页里能稳定解出 10 题), 原因:

* 题号经常被 OCR 读成 `ã2`/`ê5`/`30`(其实是 3O), 边界就断了
* 短假名选项 (せんしゅう せんしゅ ぜんしゅ ぜんしゅう) 会被 OCR **合成一行**
* 同一题里"题干→选项"的行距不固定, 按 y 间距切块会把一题切成两块

下一步应该按**题号锚点 + 页面水平留白**做版面分析, 或者干脆按"每题一个矩形
区域"重新检测。临时的笨办法: OCR 出全部行 → 让 AI 按 4 选 1 的结构把
行重新组装成题目 (一次 20 行, 让它输出 JSON)。

## 现成结论（2025-10 实测）

`C:/Users/<user>\Desktop\N5` 的 10 套卷子**全部不能自动导入**：

* 8 套是扫描件（0 文字层）
* 2 套（2016、2024-07）有文字层，但字体映射错乱，提取出来是 `伈京寸` 这种
  —— 注意这是**变长替换**（の→"(J)"、で→"T!"），不是一对一，反推码表也麻烦

现在有 OCR 了，扫描件这条路已经打开: 2016 卷前 8 页 OCR 文本质量可用，
卡在"把行拼成题目"这一步（见上一节）。

要做这三件事之一才能导入：换「文字版/高清打印版」PDF、接 OCR
（如 PaddleOCR/tesseract）、或人工整理成 CSV 再转 JSON。

## 常见坑

* **别信 PDF 里提取出来的假名**：先算假名占比，低于 25% 直接判死。
* **别整段改写题干**：语言类别（日/中）一变就可能把日语题干换成中文译文
  —— 这类事故真发生过，见 `tools/apply_answer_fixes.py` 的注释。
* **id 必须稳定**：改了 id，用户的收藏和进度就对不上了。
* **答案个数 != 选项个数**：写回前必须校验，否则答题页会崩。
