/* 可选的 AI 判分 (翻译题用).
 *
 * 密钥只存在本机 localStorage, 不上传、不写进同步状态 —— 同步仓库是公开的。
 * 没配置时 minna.js 会退回"显示答案 + 自己对/错"。
 */

const CFG_KEY = 'trilingo.llm.cfg';

export function loadConfig() {
  try {
    return JSON.parse(localStorage.getItem(CFG_KEY) || '{}');
  } catch (e) {
    return {};
  }
}

export function saveConfig(cfg) {
  localStorage.setItem(CFG_KEY, JSON.stringify(cfg || {}));
}

export function ready() {
  const c = loadConfig();
  return Boolean(c.key && c.base_url);
}

const SYSTEM = `你是日语教师，正在批改《新版中日交流标准日本语（初级上）》的翻译题。

判断学生的译文是否正确。判定规则：
1. 意思等同、语法正确、表达自然 → correct。不要因为和参考译文措辞不同就判错。
2. 允许：近义表达、语序调整、敬体/简体的合理选择。
3. 判 wrong：关键意思遗漏或译反、语法错误、用词明显不当、只写了个别词。
4. 学生译文若是罗马字、拼音、或照抄原句，一律 wrong。

只输出 JSON：{"verdict":"correct" 或 "wrong","reason":"不超过30字的中文说明"}`;

/** 返回 {ok: true|false|null, reason}；ok=null 表示没判成 */
export async function judge(prompt, userAnswer, reference, toJapanese) {
  const cfg = loadConfig();
  if (!ready()) return { ok: null, reason: '未配置 AI' };
  const url = `${String(cfg.base_url).replace(/\/+$/, '')}/chat/completions`;
  const body = {
    model: cfg.model || 'deepseek-flash',
    messages: [
      { role: 'system', content: SYSTEM },
      {
        role: 'user',
        content: `题型：${toJapanese ? '把汉语译成日语' : '把日语译成汉语'}\n`
          + `原题：${prompt}\n参考译文：${reference || '（无）'}\n`
          + `学生译文：${userAnswer}\n\n请判定学生译文。`,
      },
    ],
    response_format: { type: 'json_object' },
    temperature: 0,
    stream: false,
  };
  try {
    const res = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${cfg.key}`,
      },
      body: JSON.stringify(body),
    });
    if (!res.ok) return { ok: null, reason: `AI 请求失败（HTTP ${res.status}）` };
    const data = await res.json();
    const text = (((data.choices || [])[0] || {}).message || {}).content || '';
    let obj = {};
    try {
      obj = JSON.parse(text);
    } catch (e) {
      const i = text.indexOf('{');
      const j = text.lastIndexOf('}');
      if (i >= 0 && j > i) { try { obj = JSON.parse(text.slice(i, j + 1)); } catch (e2) { obj = {}; } }
    }
    const verdict = String(obj.verdict || '').toLowerCase();
    const reason = String(obj.reason || '').slice(0, 60);
    if (verdict === 'correct') return { ok: true, reason };
    if (verdict === 'wrong') return { ok: false, reason };
    return { ok: null, reason: 'AI 返回内容无法解析' };
  } catch (e) {
    return { ok: null, reason: '网络错误，AI 判分不可用' };
  }
}
