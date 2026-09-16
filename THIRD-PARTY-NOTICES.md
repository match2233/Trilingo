# 第三方数据来源与许可

本项目只做数据处理与界面展示，词库来自以下第三方来源。

## Kanjium 声调库

* 文件：`data/kanjium_accents.txt`，由 `fetch_data.py` 下载，不随仓库分发
* 来源：<https://github.com/mifunetoshiro/kanjium>
  文件 `data/source_files/raw/accents.txt`
* 内容：124,137 条日语词的声调（アクセント型），格式为
  `汉字形 <TAB> 假名读音 <TAB> 声调[,声调...]`
* 许可：**CC BY-SA 4.0**（Creative Commons 署名-相同方式共享 4.0）
* 用途：日语词条的「几型」显示

> 修改并再分发本文件时，需继续以 CC BY-SA 4.0 授权并保留署名。

## 日语声调补录（不随仓库分发）

* 文件：`data/ja_accent.json`
* 来源：<https://github.com/KittichoteKamalapirat/jp-pitch-accent-db>
  文件 `assets/output/output.csv`（330,990 行）
* **许可：该仓库未声明任何许可证**，内容据分析为 NHK 日本語発音アクセント新辞典
  等来源的衍生数据，NHK 词典为商业出版物
* 用途：补齐 Kanjium 未收录的少量词条

**该文件不在本仓库中**，`.gitignore` 已将其排除。本机若存在该文件，程序会读取；
缺失时相关词条显示「声调待补」，其余功能不受影响。基于上述许可状况，该文件不宜再分发。

交叉校验（2026-09-14）：与 Kanjium 重叠的 151 个词中 149 个一致（99%）。
不一致的两处为 `名古屋`（Kanjium 1型 / 该库 0型）与 `高校生`（Kanjium 3型 / 该库 0型），
经核对为 Kanjium 正确。

## CMUdict 英语发音词典

* 来源：Carnegie Mellon University Pronouncing Dictionary
  （通过 PyPI 包 `cmudict` 读取，126,052 词条）
* 许可：BSD 2-Clause
* 用途：英语美式音标。程序将 CMUdict 的 ARPAbet 音素转写为 IPA，
  并按最大音节首原则定位重音符号

## DeepSeek API（可选，联网，需自备密钥）

* 来源：<https://platform.deepseek.com>
* 用途：为内置词表未覆盖的新增日语词条生成中文释义。
  提示词与内置释义风格一致，结果写入本地数据库后不再重复请求
* 仅在配置 API key 后启用。密钥以明文保存在 `data/llm.json`，
  也可改用环境变量 `DEEPSEEK_API_KEY` 而不写入文件
* 未配置时程序完全离线可用

## MyMemory 翻译接口（可选，联网）

* 来源：<https://mymemory.translated.net/>
* 用途：为内置词表未覆盖的新增日语词条提供中文释义的兜底翻译，
  结果写入本地数据库后不再重复请求。不使用该功能时程序完全离线可用。

## 未采用的数据来源（备查）

* `jp-pitch-accent-db` 中除上述补录词外的全部内容（许可不明，不作分发）
* 日本語教育用アクセント辞典（OJAD，东京大学）— 服务器不可达
* Wadoku（和独辞典）— CC BY-SA，本项目未采用其数据
* `unidic-lite` / `pyopenjtalk` — 其词典不含逐词声调型字段
