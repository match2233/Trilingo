"""日语释义的 LLM 补全.

默认接 DeepSeek (OpenAI 兼容接口), 也可以指向任何兼容服务:
把 base_url 换成对应的地址即可。

配置存放在 data/llm.json:
    {"api_key": "sk-...", "base_url": "https://api.deepseek.com",
     "model": "deepseek-flash", "enabled": true}
也可以用环境变量 DEEPSEEK_API_KEY 提供密钥。

成本参考: 本应用一次只发没见过的生词, 每批 25 个词,
教材一课的词汇量约几分钱。
"""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from pathlib import Path

from .config import DATA_DIR

log = logging.getLogger("trilingo")

CONFIG_FILE = DATA_DIR / "llm.json"

DEFAULTS = {
    "api_key": "",
    "base_url": "https://api.deepseek.com",
    "model": "deepseek-flash",
    "enabled": True,
}

# 每批发多少个词: 太多会拉低单个词的稳定性, 太少则浪费往返
BATCH_SIZE = 25

SYSTEM_PROMPT = """你是《新版中日交流标准日本语》的编者，为课后生词表撰写中文释义。

规则：
1. 直接给出中文对应词，简洁准确。不要造句、不要解释词源、不要标假名读音。
2. 词性只在容易混淆时用中文括注在末尾，例如「休息；休假〔名词〕」。名词、形容词等一般不必标。
3. **意思相近的词要写得详细一些以便区分**；没有易混词的，从简，不要画蛇添足。
4. 需要说明用法或语体时，用〔〕补充，例如〔自谦说法，对别人提起自己父亲时用〕。
5. 只输出 JSON 对象，键为原词，值为释义。不要输出任何其它文字。

示例（注意近义词的区分方式，以及简单词就从简）：

学生 → 学生（泛指在校读书的人，多指大学生）
生徒 → 学生（特指小学、初中、高中的学生）
児童 → 儿童（特指小学阶段的学龄儿童）
幼児 → 幼儿（学龄前的孩子）
建物 → 建筑物，房子（泛指各类建筑）
ビル → 大楼，写字楼（高层建筑）
休み → 休息；休假〔名词〕
休む → 休息；请假〔动词〕
ちち → （我）父亲〔自谦说法，对别人提起自己父亲时用〕
猫 → 猫
明日 → 明天
～時 → ～点（钟）"""


# ------------------------------------------------------------------ 配置
def load_config() -> dict:
    cfg = dict(DEFAULTS)
    try:
        with open(CONFIG_FILE, encoding="utf-8") as fh:
            data = json.load(fh)
        for k in DEFAULTS:
            if k in data and data[k] != "":
                cfg[k] = data[k]
    except FileNotFoundError:
        pass
    except Exception as exc:  # noqa: BLE001
        log.warning("llm.json 读取失败: %s", exc)

    if not cfg["api_key"]:
        import os

        cfg["api_key"] = os.environ.get("DEEPSEEK_API_KEY", "")
    return cfg


def save_config(api_key: str, base_url: str = "", model: str = "") -> None:
    cfg = load_config()
    cfg["api_key"] = api_key.strip()
    if base_url.strip():
        cfg["base_url"] = base_url.strip()
    if model.strip():
        cfg["model"] = model.strip()
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w", encoding="utf-8") as fh:
        json.dump(cfg, fh, ensure_ascii=False, indent=2)


def is_configured() -> bool:
    c = load_config()
    return bool(c["api_key"]) and c.get("enabled", True)


# ------------------------------------------------------------------ 调用
def _post(url: str, payload: dict, api_key: str, timeout: int = 90) -> dict:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", "replace"))


def _extract_json(text: str) -> dict:
    """从模型回复里取出 JSON 对象 (容忍 ```json 包裹)."""
    t = (text or "").strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[-1]
        if t.rstrip().endswith("```"):
            t = t.rstrip()[:-3]
    t = t.strip()
    try:
        return json.loads(t)
    except Exception:
        pass
    # 退一步: 截取第一个 { 到最后一个 }
    i, j = t.find("{"), t.rfind("}")
    if 0 <= i < j:
        try:
            return json.loads(t[i : j + 1])
        except Exception:
            return {}
    return {}


def translate_words(pairs: list[tuple[str, str]]) -> dict[str, str]:
    """批量把 (单词, 假名读音) 译成中文释义. 失败返回已拿到的部分 (可能为空)."""
    cfg = load_config()
    if not cfg["api_key"] or not cfg.get("enabled", True) or not pairs:
        return {}

    url = cfg["base_url"].rstrip("/") + "/chat/completions"
    out: dict[str, str] = {}

    for i in range(0, len(pairs), BATCH_SIZE):
        batch = pairs[i : i + BATCH_SIZE]
        listing = "\n".join(
            f"{w}（{r}）" if r else w for w, r in batch
        )
        payload = {
            "model": cfg["model"],
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"请为下列生词写释义：\n\n{listing}"},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.3,
            "stream": False,
        }
        try:
            data = _post(url, payload, cfg["api_key"])
            content = (data.get("choices") or [{}])[0].get("message", {}).get("content", "")
            got = _extract_json(content)
            for w, r in batch:
                v = got.get(w) or got.get(f"{w}（{r}）") or ""
                v = str(v).strip()
                if v and len(v) <= 60:
                    out[w] = v
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = exc.read().decode("utf-8", "replace")[:200]
            except Exception:
                pass
            log.warning("LLM 请求失败 HTTP %s: %s", exc.code, detail)
        except Exception as exc:  # noqa: BLE001
            log.warning("LLM 请求失败: %s: %s", type(exc).__name__, exc)
    return out


def test_connection() -> tuple[bool, str]:
    """测试 API key 是否可用. 返回 (成功?, 说明文字)."""
    cfg = load_config()
    if not cfg["api_key"]:
        return False, "还没有填写 API key。"
    got = translate_words([("猫", "ねこ")])
    if got.get("猫"):
        return True, f"连接成功，模型 {cfg['model']} 返回：猫 → {got['猫']}"
    return False, "调用失败。请检查 API key、网络，或 base_url / 模型名是否正确。"
