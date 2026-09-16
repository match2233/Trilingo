# 第三方数据来源与许可

本应用本身只做数据处理与界面展示，词库来自以下第三方来源。

## Kanjium 声调库 — `data/kanjium_accents.txt`

* 来源：<https://github.com/mifunetoshiro/kanjium>
  文件 `data/source_files/raw/accents.txt`
* 内容：124,137 条日语词的声调（アクセント型），格式为
  `汉字形 <TAB> 假名读音 <TAB> 声调[,声调...]`
* 许可：**CC BY-SA 4.0**（Creative Commons 署名-相同方式共享 4.0）
* 用途：日语单词的「几型」显示

> 若你修改并再分发本文件，需继续以 CC BY-SA 4.0 授权并保留署名。

## 日语声调补录 — `data/ja_accent.json`

* 来源：<https://github.com/KittichoteKamalapirat/jp-pitch-accent-db>
  文件 `assets/output/output.csv`（330,990 行）
* **许可：该仓库未声明任何许可证**，内容据分析为 NHK 日本語発音アクセント新辞典
  等来源的衍生数据（NHK 词典为商业出版物）
* 用途：仅用于补齐 Kanjium 未收录的 **10 个词**，供**个人学习自用**
* ⚠️ **请勿再分发** `data/ja_accent.json`，也不要将本项目整体发布。
  如日后需要分享，请删掉该文件——删掉后这 10 个词会显示「声调待补」，应用其余功能不受影响

交叉校验（2026-09-14）：与 Kanjium 重叠的 151 个词中，149 个一致（99%）；
仅 `名古屋`（Kanjium 1型 / 本库 0型）、`高校生`（Kanjium 3型 / 本库 0型）不一致，
经核对为 Kanjium 正确，本库这两处有误——但这两个词不在本项目的补录范围内。

## CMUdict — 英语发音词典

* 来源：Carnegie Mellon University Pronouncing Dictionary
  （通过 PyPI 包 `cmudict` 读取，126,052 词条）
* 许可：BSD 2-Clause
* 用途：英语美式音标。程序把 CMUdict 的 ARPAbet 音素转写为 IPA，
  并按「最大音节首」原则定位重音符号

## DeepSeek API（可选，联网，需自备密钥）

* 来源：<https://platform.deepseek.com>
* 用途：为**内置词表未覆盖的新增日语单词**生成中文释义。
  提示词与内置释义风格一致，结果写入本地数据库后不再重复请求
* 仅在你填入自己的 API key 后启用；密钥以明文保存在 `data/llm.json`，
  也可以改用环境变量 `DEEPSEEK_API_KEY`
* 不配置时应用完全离线可用

## MyMemory 翻译接口（可选，联网）

* 来源：<https://mymemory.translated.net/>
* 用途：仅为**内置词表未覆盖的新增日语单词**提供中文释义的兜底翻译，
  结果写入本地数据库后不再重复请求。不使用该功能时应用完全离线可用。

## 未使用的来源（备查）

* `jp-pitch-accent-db` 中除上述 10 个补录词外的全部内容（许可证不明，不作分发）

* 日本語教育用アクセント辞典（OJAD，东京大学）— 服务器从本机网络不可达
* Wadoku（和独辞典）— CC BY-SA，本项目未采用其数据
* `unidic-lite` / `pyopenjtalk` — 其词典不含逐词声调型字段
