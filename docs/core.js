/* 同步核心 —— app/sync_core.py 的 JavaScript 等价实现。
 *
 * 两边必须算出逐位相同的结果：同样的历史必须得出同样的"今天该考哪些词"，
 * 否则电脑和手机会各自认为该背不同的词，同步也就失去意义。
 * 改动本文件时，务必同步修改 app/sync_core.py，并跑一遍同步测试。
 */

export const STATE_VERSION = 1;
export const REVIEW_OFFSETS = [1, 3, 7, 15, 30];
export const EN_DAILY_NEW = 7;
export const JP_DAILY_NEW = 15;
const KEEP_EVENT_DAYS = 90;

/* ------------------------------------------------------------------ 基础 */

/** 32 位 FNV-1a。Python 端逐字节实现同一算法，结果必须一致。 */
export function fnv1a(s) {
  let h = 0x811c9dc5;
  const bytes = new TextEncoder().encode(s);
  for (let i = 0; i < bytes.length; i++) {
    h ^= bytes[i];
    h = Math.imul(h, 0x01000193) >>> 0;
  }
  return h >>> 0;
}

export const keyOf = (lang, word) => `${lang}:${word}`;
export const splitKey = (key) => {
  const i = key.indexOf(':');
  return [key.slice(0, i), key.slice(i + 1)];
};

// 用 UTC 做日期加减，避开夏令时和时区偏移带来的偏差
export function addDays(day, n) {
  const [y, m, d] = day.split('-').map(Number);
  const dt = new Date(Date.UTC(y, m - 1, d + n));
  return dt.toISOString().slice(0, 10);
}

export function today() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

export const dailyTarget = (lang) => (lang === 'en' ? EN_DAILY_NEW : JP_DAILY_NEW);

export function emptyState() {
  return {
    v: STATE_VERSION,
    updated: '',
    words: { en: [], jp: [] },
    edits: {},
    base: { stats: {}, mistakes: {}, days: [], done: {}, dropped: {} },
    events: [],
  };
}

/* ------------------------------------------------------------------ 推导 */

/** 从 base + events 推导当前状态。字段含义见 sync_core.py 的文档。 */
export function derive(state) {
  const base = state.base || {};
  const stats = { ...(base.stats || {}) };
  const mistakes = {};
  for (const [k, v] of Object.entries(base.mistakes || {})) mistakes[k] = { ...v };
  const days = new Set(base.days || []);
  const daily = {};
  // 每天每门语言答了多少题。事件折叠进 base 后, 这是另一台设备唯一能知道
  // "今天做了多少"的依据 —— 光有 days 只能判断打卡, 判断不了进度。
  const done = {};
  for (const [d, langs] of Object.entries(base.done || {})) done[d] = { ...langs };
  // 人工移出错题本的词：{key: 移出时刻}。必须记在 base 里 ——
  // 只删派生出来的那份列表是删不掉的，下次推导又会还原回来。
  const dropped = { ...(base.dropped || {}) };

  const events = [...(state.events || [])].sort(
    (a, b) => (a.t || 0) - (b.t || 0) || (a.i < b.i ? -1 : a.i > b.i ? 1 : 0)
  );

  for (const e of events) {
    const lang = e.l || '';
    const word = e.w || '';
    if (!lang || !word) continue;
    const key = keyOf(lang, word);
    const ts = e.t || 0;
    const day = e.day || '';

    stats[key] = day;

    if (!daily[day]) daily[day] = {};
    if (!daily[day][lang]) daily[day][lang] = { answered: [], ok: 0 };
    const slot = daily[day][lang];
    if (!slot.answered.includes(word)) slot.answered.push(word);
    if (e.o) slot.ok += 1;

    // 移出之后又答错了，说明是真的不会，重新收进错题本
    if (key in dropped && ts > dropped[key]) delete dropped[key];

    const m = mistakes[key];
    if (!e.o) {
      // 答错：重置复习阶梯
      mistakes[key] = { a: day, s: 0, e: ((m && m.e) || 0) + 1, g: 0, t: ts };
    } else if (m && !m.g) {
      // 复习答对：推进一档，走完则毕业
      const s = (m.s || 0) + 1;
      mistakes[key] = s >= REVIEW_OFFSETS.length
        ? { ...m, s, g: 1, t: ts }
        : { ...m, s, t: ts };
    }
  }

  // 打卡：当天任一门语言答满该语言的目标题数
  for (const [day, langs] of Object.entries(daily)) {
    if (!done[day]) done[day] = {};
    for (const [lang, d] of Object.entries(langs)) {
      const n = d.answered.length;
      done[day][lang] = Math.max(done[day][lang] || 0, n);
      if (n >= dailyTarget(lang)) days.add(day);
    }
  }

  // 仍在"已移出"名单里的词，不进错题本
  for (const key of Object.keys(dropped)) delete mistakes[key];

  return { stats, mistakes, days, daily, done, dropped };
}

export function nextDue(m) {
  if (!m || m.g) return null;
  const s = m.s || 0;
  if (s >= REVIEW_OFFSETS.length) return null;
  return addDays(m.a, REVIEW_OFFSETS[s]);
}

export const mistakeProgress = (m) =>
  m && m.g ? '已毕业' : `${(m && m.s) || 0}/${REVIEW_OFFSETS.length}`;

/* ------------------------------------------------------------------ 每日计划 */

/** 当天该考哪些词。纯函数 —— 两端算出的结果必须完全一致。 */
export function planFor(day, lang, words, der) {
  const stats = der.stats;
  const mistakes = der.mistakes;
  const target = dailyTarget(lang);

  const reviews = [];
  for (const [key, m] of Object.entries(mistakes)) {
    if (!key.startsWith(lang + ':')) continue;
    const due = nextDue(m);
    if (due && due <= day) reviews.push([splitKey(key)[1], due]);
  }
  reviews.sort((a, b) => (a[1] < b[1] ? -1 : a[1] > b[1] ? 1 : a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : 0));

  const chosen = reviews.map(([w, d]) => ({ w, kind: 'review', due: d }));
  const taken = new Set(chosen.map((c) => c.w));
  const active = words.filter((x) => x.w && !taken.has(x.w));

  const fresh = active.filter((x) => !(keyOf(lang, x.w) in stats));
  fresh.sort((a, b) => {
    const ha = fnv1a(`${day}|${lang}|${a.w}`);
    const hb = fnv1a(`${day}|${lang}|${b.w}`);
    return ha - hb || (a.w < b.w ? -1 : a.w > b.w ? 1 : 0);
  });

  let picks = fresh.slice(0, target);
  if (picks.length < target) {
    const rest = active.filter((x) => keyOf(lang, x.w) in stats);
    rest.sort((a, b) => {
      const sa = stats[keyOf(lang, a.w)];
      const sb = stats[keyOf(lang, b.w)];
      if (sa !== sb) return sa < sb ? -1 : 1;
      return fnv1a(`${day}|${lang}|${a.w}`) - fnv1a(`${day}|${lang}|${b.w}`);
    });
    picks = picks.concat(rest.slice(0, target - picks.length));
  }

  return chosen.concat(picks.map((x) => ({ w: x.w, kind: 'new', due: '' })));
}

/* ------------------------------------------------------------------ 合并 */

/** 合并两份状态.
 *
 * prefer = null      对等合并：逐字段取较新或求并集
 * prefer = 'local'   冲突时以本端为准   —— 电脑端用
 * prefer = 'remote'  冲突时以远端为准   —— 手机端用
 *
 * 事件始终求并集，不受 prefer 影响：答题记录是唯一不可再生的东西。
 * 受 prefer 影响的只是 base 里的派生状态（错题本、打卡、学习统计、每日进度），
 * 这些要么可重算，要么以电脑端为准才不会互相打架。
 */
export function merge(local, remote, prefer = null) {
  if (!remote || !Object.keys(remote).length) return normalize(local);
  if (!local || !Object.keys(local).length) return normalize(remote);

  const out = emptyState();
  out.words = mergeWords(local.words || {}, remote.words || {}, prefer);
  out.edits = mergeEdits(local.edits || {}, remote.edits || {}, prefer);

  const lb = local.base || {};
  const rb = remote.base || {};
  out.base = {
    stats: mergeStats(lb.stats || {}, rb.stats || {}, prefer),
    mistakes: mergeMistakes(lb.mistakes || {}, rb.mistakes || {}, prefer),
    days: mergeDays(lb.days || [], rb.days || [], prefer),
    done: mergeDone(lb.done || {}, rb.done || {}, prefer),
    dropped: mergeDropped(lb.dropped || {}, rb.dropped || {}, prefer),
  };

  const seen = {};
  for (const e of [...(local.events || []), ...(remote.events || [])]) {
    if (e.i && !seen[e.i]) seen[e.i] = e;
  }
  out.events = Object.values(seen).sort(
    (a, b) => (a.t || 0) - (b.t || 0) || (a.i < b.i ? -1 : a.i > b.i ? 1 : 0)
  );

  return compact(normalize(out));
}

/** 按 prefer 返回 [优先方, 另一方] */
const sides = (a, b, prefer) => (prefer === 'local' ? [a, b] : [b, a]);

function mergeWords(a, b, prefer) {
  const out = { en: [], jp: [] };
  const [first, second] = prefer ? sides(a, b, prefer) : [a, b];
  for (const lang of ['en', 'jp']) {
    const by = {};
    // 优先方放在后面，时间戳相同时它会胜出
    for (const rec of [...(second[lang] || []), ...(first[lang] || [])]) {
      if (!rec || !rec.w) continue;
      const old = by[rec.w];
      if (!old || (rec.u || 0) >= (old.u || 0)) by[rec.w] = rec;
    }
    out[lang] = Object.values(by).sort((x, y) => (x.w < y.w ? -1 : x.w > y.w ? 1 : 0));
  }
  return out;
}

function mergeEdits(a, b, prefer) {
  const out = {};
  for (const key of new Set([...Object.keys(a), ...Object.keys(b)])) {
    const ra = a[key], rb = b[key];
    if (!rb) { out[key] = ra; continue; }
    if (!ra) { out[key] = rb; continue; }
    let merged;
    if (prefer) {
      const [first, second] = sides(ra, rb, prefer);
      merged = { ...second, ...first };     // 优先方逐字段覆盖
    } else {
      merged = { ...ra };
      for (const [f, v] of Object.entries(rb)) {
        if (f === 't') continue;
        if (v !== ra[f] && (rb.t || 0) >= (ra.t || 0)) merged[f] = v;
      }
    }
    merged.t = Math.max(ra.t || 0, rb.t || 0);
    out[key] = merged;
  }
  return out;
}

function mergeStats(a, b, prefer) {
  if (prefer) {
    const [first, second] = sides(a, b, prefer);
    return { ...second, ...first };          // 优先方说了算，包括把日期改早
  }
  const out = {};
  for (const k of new Set([...Object.keys(a), ...Object.keys(b)])) {
    out[k] = (a[k] || '') >= (b[k] || '') ? a[k] || '' : b[k] || '';
  }
  return out;
}

/** 打卡日期。指定 prefer 时整份替换而非求并集 —— 否则一端删掉的会被另一端带回来 */
function mergeDays(a, b, prefer) {
  if (prefer === 'local') return [...new Set(a)].sort().length ? [...new Set(a)].sort() : [...new Set(b)].sort();
  if (prefer === 'remote') return [...new Set(b)].sort().length ? [...new Set(b)].sort() : [...new Set(a)].sort();
  return [...new Set([...a, ...b])].sort();
}

/** 每天每语言答了多少题 */
function mergeDone(a, b, prefer) {
  const out = {};
  for (const day of new Set([...Object.keys(a), ...Object.keys(b)])) {
    const la = a[day] || {}, lb = b[day] || {};
    if (prefer) {
      const [first, second] = sides(la, lb, prefer);
      const slot = {};
      for (const k of Object.keys(second)) slot[k] = Number(second[k]) || 0;
      for (const [k, v] of Object.entries(first)) slot[k] = Number(v) || 0;
      out[day] = slot;
    } else {
      const slot = {};
      for (const k of new Set([...Object.keys(la), ...Object.keys(lb)])) {
        slot[k] = Math.max(Number(la[k]) || 0, Number(lb[k]) || 0);
      }
      out[day] = slot;
    }
  }
  return out;
}

/** 人工移出错题本的名单，取两端并集（任一端移出过就算移出） */
function mergeDropped(a, b, prefer) {
  if (prefer) {
    const [first, second] = sides(a, b, prefer);
    return { ...second, ...first };
  }
  return { ...b, ...a };
}

function mergeMistakes(a, b, prefer) {
  const out = {};
  for (const k of new Set([...Object.keys(a), ...Object.keys(b)])) {
    const ra = a[k], rb = b[k];
    if (!ra) out[k] = rb;
    else if (!rb) out[k] = ra;
    else if (prefer) out[k] = prefer === 'local' ? ra : rb;
    else out[k] = (rb.t || 0) >= (ra.t || 0) ? rb : ra;
  }
  return out;
}

function normalize(state) {
  const out = emptyState();
  for (const k of Object.keys(out)) {
    if (state && state[k] !== undefined && state[k] !== null) out[k] = state[k];
  }
  out.v = STATE_VERSION;
  out.edits = out.edits || {};
  const base = out.base || {};
  out.base = {
    stats: base.stats || {},
    mistakes: base.mistakes || {},
    days: [...new Set(base.days || [])].sort(),
    done: base.done || {},
    dropped: base.dropped || {},
  };
  out.words = out.words || { en: [], jp: [] };
  out.words.en = out.words.en || [];
  out.words.jp = out.words.jp || [];
  out.events = out.events || [];
  return out;
}

/** 把 90 天前的事件折进 base 并丢弃，避免文件无限增长。 */
function compact(state, todayStr) {
  const t = todayStr || today();
  const cutoff = addDays(t, -KEEP_EVENT_DAYS);
  const old = state.events.filter((e) => (e.day || '9999') < cutoff);
  if (!old.length) return state;

  const keep = state.events.filter((e) => (e.day || '9999') >= cutoff);
  const der = derive({ ...emptyState(), base: state.base, events: old });
  state.base = {
    stats: der.stats,
    mistakes: der.mistakes,
    days: [...der.days].sort(),
    done: der.done,           // 折叠后仍要保留"每天做了多少"
    dropped: der.dropped,     // 人工移出的名单同样要保留
  };
  state.events = keep;
  return state;
}

export function applyEdits(state) {
  const byKey = {};
  for (const lang of ['en', 'jp']) {
    for (const rec of state.words[lang] || []) byKey[keyOf(lang, rec.w)] = rec;
  }
  for (const [key, edit] of Object.entries(state.edits || {})) {
    const rec = byKey[key];
    if (!rec) continue;
    if ('m' in edit) rec.m = edit.m;
    if ('ipa' in edit) rec.ipa = edit.ipa;
    if ('ac' in edit) rec.ac = edit.ac;
    if ('r' in edit) rec.r = edit.r;
    rec.manual = 1;
  }
}

export function streak(days, todayStr) {
  const t = todayStr || today();
  const set = days instanceof Set ? days : new Set(days || []);
  if (!set.size) return 0;
  let cur = set.has(t) ? t : addDays(t, -1);
  let n = 0;
  while (set.has(cur)) { n += 1; cur = addDays(cur, -1); }
  return n;
}
