/* 新标日测试 (PWA 版) —— 与电脑端同一份题库、同一套交互逻辑。
 *
 * 题库: minna_tests.json (由 tools/build_minna_tests.py 生成, 与桌面共用)
 * 进度: localStorage, 每台设备各记各的, 不参与同步
 *
 * 三种题型:
 *   fill      整大题一次列出 -> 显示答案 -> 逐题标对错(默认对) -> 下一大题
 *   choice    一题一屏, 选项按钮; 对 -> 5 秒自动下一题, 错 -> 手动下一题
 *   translate 一题一屏 -> 自己写译文 -> AI 判分 (没配 AI 就显示答案自评)
 */

import * as Llm from './llm.js';

const CORRECT_WAIT = 5000;
const KIND_NAME = { fill: '填空', choice: '选择', translate: '翻译' };

export const M = {
  bank: null,
  lesson: null,
  sections: [],
  results: {},
  secI: 0,
  itemI: 0,
  startedAt: 0,
  timerId: null,
  mode: 'test',
  noAnswer: false,
  fillShown: false,
  choiceDone: false,
};

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s == null ? '' : s).replace(/[&<>"]/g, (c) =>
  ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

let hooks = { showView: () => {}, toast: () => {} };

/* ------------------------------------------------------------------ 存储 */

// 进度直接放在同步状态里 (state.minna), 随同步一起走, 不再单独存 localStorage
let getState = () => ({ minna: {} });
let onChange = () => {};

function allProgress() {
  const st = getState() || {};
  if (!st.minna || typeof st.minna !== 'object') st.minna = {};
  return st.minna;
}

function prog(n) { return allProgress()[n] || null; }

function patchProg(n, patch) {
  const all = allProgress();
  all[n] = Object.assign({
    status: 'idle', section: 0, idx: 0, seconds: 0,
    score: 0, total: 0, results: {}, updated_at: '',
  }, all[n] || {}, patch, { updated_at: new Date().toISOString().slice(0, 19) });
  onChange();
  return all[n];
}

export function progressMap() { return allProgress(); }

/* ------------------------------------------------------------------ 收藏 */

/** 收藏存在同步状态里 (state.fav), 结构 { "L01-S1-3": {note, at} } */
function allFav() {
  const st = getState() || {};
  if (!st.fav || typeof st.fav !== 'object') st.fav = {};
  return st.fav;
}

export function isFav(qid) { return Boolean(allFav()[qid]); }

function toggleFav(qid) {
  const fav = allFav();
  if (fav[qid]) delete fav[qid];
  else fav[qid] = { note: '', at: new Date().toISOString().slice(0, 19) };
  onChange();
  return Boolean(fav[qid]);
}

function setFavNote(qid, note) {
  const fav = allFav();
  fav[qid] = { note: String(note || ''), at: new Date().toISOString().slice(0, 19) };
  onChange();
}

function dropFav(qid) {
  delete allFav()[qid];
  onChange();
}

/** 收藏夹: 按课、题号排序, 并把题库里对应的题目找回来 */
export function favList() {
  const fav = allFav();
  const out = [];
  for (const [qid, rec] of Object.entries(fav)) {
    const m = /^L(\d+)-S(\d+)-(\d+)$/.exec(qid);
    if (!m) continue;
    const les = lessons().find((l) => Number(l.lesson) === Number(m[1]));
    if (!les) continue;
    const sec = (les.sections || []).find((s) => Number(s.no) === Number(m[2]));
    const it = sec && (sec.items || []).find((x) => x.id === qid);
    out.push({
      qid, lesson: Number(m[1]), secNo: Number(m[2]),
      kind: sec ? sec.kind : '', title: sec ? sec.title : '',
      prompt: it ? it.prompt : '（题目已不在题库里）',
      answer: it ? it.answer : '',
      options: it ? (it.options || []) : [],
      note: (rec && rec.note) || '',
    });
  }
  out.sort((a, b) => a.lesson - b.lesson || a.secNo - b.secNo
    || a.qid.localeCompare(b.qid));
  return out;
}

function favAnswer(f) {
  if (f.answer === null || f.answer === undefined || f.answer === '') return '（未提供答案）';
  if (f.kind === 'choice' && typeof f.answer === 'number') {
    const mark = '①②③④⑤⑥'[f.answer - 1] || f.answer;
    return `${mark} ${f.options[f.answer - 1] || ''}`.trim();
  }
  return String(f.answer);
}

/** 收藏夹列表 */
export function renderFav() {
  const list = $('favList');
  if (!list) return;
  const favs = favList();
  const withNote = favs.filter((f) => (f.note || '').trim()).length;
  $('favSummary').textContent = `共 ${favs.length} 题`
    + (withNote ? `　·　${withNote} 题有笔记` : '');
  if (!favs.length) {
    list.innerHTML = '<div class="minna-row"><span class="sub">还没有收藏。'
      + '看试卷时点题目左边的 ☆ 就能收藏，收藏后可以写笔记。</span></div>';
    return;
  }
  list.innerHTML = favs.map((f) => `
    <div class="fav-card" data-qid="${f.qid}">
      <div class="fav-top">
        <span class="sub">第 ${f.lesson} 课　大${f.secNo}　${KIND_NAME[f.kind] || ''}</span>
        <button class="ghost fav-edit" data-qid="${f.qid}">编辑笔记</button>
        <button class="ghost fav-del" data-qid="${f.qid}">取消收藏</button>
      </div>
      <div class="fav-q">${esc(f.prompt)}</div>
      <div class="fav-a">${esc(favAnswer(f))}</div>
      ${f.note ? `<div class="fav-note">笔记：${esc(f.note)}</div>`
    : '<div class="sub" style="margin-top:6px">（还没有笔记）</div>'}
    </div>`).join('');
  list.querySelectorAll('.fav-edit').forEach((b) => {
    b.onclick = () => {
      const qid = b.dataset.qid;
      const cur = (allFav()[qid] || {}).note || '';
      const txt = window.prompt('写点什么（这句话为什么错 / 记哪个用法）', cur);
      if (txt === null) return;
      setFavNote(qid, txt.trim());
      renderFav();
    };
  });
  list.querySelectorAll('.fav-del').forEach((b) => {
    b.onclick = () => { dropFav(b.dataset.qid); renderFav(); };
  });
}

/* ------------------------------------------------------------------ 题库 */

export async function loadBank() {
  if (M.bank && (M.bank.lessons || []).length) return M.bank;
  // 1) 优先用随应用部署的那份 (公开仓库里不放题库, 见 README)
  try {
    const r = await fetch('minna_tests.json', { cache: 'force-cache' });
    if (r.ok) {
      const j = await r.json();
      if ((j.lessons || []).length) { M.bank = j; cacheBank(j); return M.bank; }
    }
  } catch (e) { /* 继续尝试私有仓库 */ }

  // 2) 从私有数据仓库取 (题库是教辅原题, 只放在自己的私有仓库里)
  try {
    const j = await fetchBankFromDataRepo();
    if (j && (j.lessons || []).length) { M.bank = j; cacheBank(j); return M.bank; }
  } catch (e) { /* 忽略 */ }

  // 3) 离线时用上次缓存的
  const cached = readCachedBank();
  if (cached) { M.bank = cached; return M.bank; }

  M.bank = { lessons: [] };
  return M.bank;
}

const BANK_KEY = 'trilingo.minna.bank';

function cacheBank(j) {
  try { localStorage.setItem(BANK_KEY, JSON.stringify(j)); } catch (e) { /* 空间不足忽略 */ }
}

function readCachedBank() {
  try {
    const raw = localStorage.getItem(BANK_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch (e) { return null; }
}

async function fetchBankFromDataRepo() {
  let cfg = {};
  try { cfg = JSON.parse(localStorage.getItem('trilingo.sync.cfg') || '{}'); } catch (e) { return null; }
  if (!cfg.token || !cfg.owner || !cfg.repo) return null;
  const url = `https://api.github.com/repos/${cfg.owner}/${cfg.repo}/contents/minna_tests.json`;
  const res = await fetch(url, {
    headers: {
      Authorization: `Bearer ${cfg.token}`,
      Accept: 'application/vnd.github+json',
    },
  });
  if (!res.ok) return null;
  const data = await res.json();
  const b64 = String(data.content || '').replace(/\s/g, '');
  if (!b64) return null;
  const bin = atob(b64);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i += 1) bytes[i] = bin.charCodeAt(i);
  return JSON.parse(new TextDecoder('utf-8').decode(bytes));
}

function lessons() { return (M.bank && M.bank.lessons) || []; }

function totalItems(les) {
  return (les.sections || []).reduce((n, s) => n + (s.items || []).length, 0);
}

export function fmtSec(sec) {
  if (!sec) return '—';
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  const h = Math.floor(m / 60);
  return h ? `${h}:${String(m % 60).padStart(2, '0')}:${String(s).padStart(2, '0')}`
    : `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}

/* ------------------------------------------------------------------ 列表页 */

export function renderList() {
  const all = allProgress();
  const les = lessons();
  let done = 0;
  const rows = les.map((l) => {
    const p = all[l.lesson];
    const total = totalItems(l) || 1;
    let ratio = 0;
    let barCls = '';
    let pctTxt = '未开始';
    let score = '—';
    let scoreCls = '';
    let time = '—';
    if (p) {
      const got = Object.keys(p.results || {}).length;
      ratio = Math.min(1, got / total);
      pctTxt = `${got}/${total}`;
      time = fmtSec(p.seconds);
      if (p.status === 'doing') {
        barCls = 'doing';
        score = '进行中';
        scoreCls = 'doing';
      } else if (p.status === 'done') {
        barCls = 'done';
        done += 1;
        const t = p.total || total;
        score = `${p.score}/${t}`;
        scoreCls = p.score * 2 >= t ? 'ok' : 'bad';
      }
    }
    return `<button class="minna-row" data-n="${l.lesson}">
      <span class="mno">第 ${l.lesson} 课</span>
      <span>
        <span class="minna-bar"><i class="${barCls}" style="width:${(ratio * 100).toFixed(1)}%"></i></span>
        <span class="sub" style="margin:2px 0 0">${pctTxt}</span>
      </span>
      <span class="mscore ${scoreCls}">${score}</span>
      <span class="mtime">${time}</span>
    </button>`;
  });
  $('minnaList').innerHTML = rows.join('') ||
    '<div class="empty">题库未加载<br>请确认 minna_tests.json 已随应用部署</div>';
  $('minnaSummary').textContent =
    `共 ${les.length} 课　已完成 ${done} 课`
    + (les.some((l) => l.no_answer) ? '　·　第 24 课原卷未附答案，按自评计' : '');
  $('minnaList').querySelectorAll('.minna-row').forEach((b) => {
    b.onclick = () => openLesson(Number(b.dataset.n));
  });
}

/* ------------------------------------------------------------------ 进入一课 */

export function openLesson(n, review) {
  const les = lessons().find((l) => l.lesson === n);
  if (!les) { hooks.toast('题库里没有这一课'); return; }
  clearTimer();
  M.lesson = n;
  M.noAnswer = !!les.no_answer;
  M.sections = (les.sections || []).filter((s) => (s.items || []).length);
  const p = prog(n);
  M.results = (p && p.results) || {};

  const isReview = review !== undefined ? review : (p && p.status === 'done');
  if (isReview) {
    M.mode = 'paper';
    hooks.showView('minnaTest');
    renderPaper();
    return;
  }
  // 继续未完成的课, 否则重开
  const resume = p && p.status === 'doing';
  if (!resume) {
    M.results = {};
    M.secI = 0;
    M.itemI = 0;
    M.startedAt = Date.now();
    patchProg(n, { status: 'doing', section: 0, idx: 0, seconds: 0,
      score: 0, total: totalItems(les), results: {}, startedAt: M.startedAt });
  } else {
    M.secI = Math.min(p.section || 0, M.sections.length - 1);
    M.itemI = p.idx || 0;
    M.startedAt = p.startedAt || Date.now();
    patchProg(n, { status: 'doing' });
  }
  M.mode = 'test';
  hooks.showView('minnaTest');
  tick();
  renderSection();
}

export function leave() {
  if (M.mode === 'test' && M.lesson) {
    patchProg(M.lesson, {
      status: 'doing', section: M.secI, idx: M.itemI,
      seconds: elapsed(), score: Object.values(M.results).filter(Boolean).length,
      results: M.results,
    });
  }
  clearTimer();
  renderList();
  hooks.showView('minna');
}

/* ------------------------------------------------------------------ 计时 */

function elapsed() {
  return M.startedAt ? Math.max(0, Math.floor((Date.now() - M.startedAt) / 1000)) : 0;
}

function clearTimer() {
  if (M.timerId) { clearInterval(M.timerId); M.timerId = null; }
}

function tick() {
  clearTimer();
  const upd = () => { $('mtTimer').textContent = fmtClock(elapsed()); };
  upd();
  M.timerId = setInterval(upd, 1000);
}

/* ------------------------------------------------------------------ 渲染 */

function cur() { return M.sections[M.secI] || null; }

function updateHead() {
  const total = M.sections.reduce((a, s) => a + s.items.length, 0) || 1;
  const done = Object.keys(M.results).length;
  $('mtTitle').textContent = `第 ${M.lesson} 课`;
  $('mtSub').textContent = `${done}/${total} 已判定`;
  $('mtBar').style.width = `${Math.min(100, (done / total) * 100)}%`;
}

function setNext(label, fn) {
  const b = $('mtNext');
  b.textContent = label;
  b.onclick = fn;
  b.style.display = '';
}

function hideNext() { $('mtNext').style.display = 'none'; }

export function renderSection() {
  const sec = cur();
  if (!sec) { finish(); return; }
  M.fillShown = false;
  M.choiceDone = false;
  updateHead();
  hideNext();
  $('mtHint').textContent = '';
  if (sec.kind === 'choice') renderChoice(sec);
  else if (sec.kind === 'translate') renderTranslate(sec);
  else renderFill(sec);
}

/* ---------------------------------------------------------------- 填空 */

function renderFill(sec) {
  const n = sec.items.length;
  const cols = Math.min(n, 5);
  const cells = sec.items.map((it, i) => `
    <div class="fill-cell">
      <div class="fn">${i + 1}</div>
      <div>${esc(it.prompt)}</div>
      <div class="fill-ans" data-ans="${i}"></div>
      <button class="fill-toggle" data-tog="${i}" style="display:none">对</button>
    </div>`).join('');
  $('mtBody').innerHTML = `
    <div class="mt-card">
      <h3>${sec.no}、${esc(sec.title)}　<span class="sub">共 ${n} 小题</span></h3>
      <div class="fill-grid" style="grid-template-columns:repeat(${cols},1fr)">${cells}</div>
      <div class="mt-judge" style="margin-top:14px">
        <button class="yes" id="revealBtn">显示答案</button>
      </div>
    </div>`;
  $('mtHint').textContent = '点【显示答案】核对；再逐题点按钮标记答错的，默认为答对';
  $('revealBtn').onclick = () => revealFill(sec);
}

function revealFill(sec) {
  if (M.fillShown) { hideFill(); return; }
  M.fillShown = true;
  sec.items.forEach((it, i) => {
    const a = document.querySelector(`[data-ans="${i}"]`);
    if (a) a.textContent = it.answer || '（未提供答案）';
    const t = document.querySelector(`[data-tog="${i}"]`);
    if (t) {
      const ok = M.results[it.id] === undefined ? true : !!M.results[it.id];
      if (M.results[it.id] === undefined) M.results[it.id] = true;
      t.style.display = '';
      paintToggle(t, ok);
      t.onclick = () => toggleFill(it.id, t);
    }
  });
  $('revealBtn').textContent = '重新隐藏';
  updateHead();
  setNext('下一大题', nextSection);
}

function hideFill() {
  M.fillShown = false;
  document.querySelectorAll('[data-ans]').forEach((e) => { e.textContent = ''; });
  document.querySelectorAll('[data-tog]').forEach((e) => { e.style.display = 'none'; });
  $('revealBtn').textContent = '显示答案';
  hideNext();
}

function paintToggle(el, ok) {
  el.textContent = ok ? '对' : '错';
  el.classList.toggle('bad', !ok);
}

function toggleFill(qid, el) {
  const v = !M.results[qid];
  M.results[qid] = v;
  paintToggle(el, v);
  updateHead();
}

/* ---------------------------------------------------------------- 选择 */

function renderChoice(sec) {
  const idx = Math.min(M.itemI, sec.items.length - 1);
  const it = sec.items[idx];
  const known = typeof it.answer === 'number' && it.answer >= 1;
  const marks = '①②③④⑤⑥';
  const opts = (it.options || []).map((o, j) =>
    `<button class="opt-btn" data-j="${j + 1}">${marks[j] || j + 1}　${esc(o)}</button>`).join('');
  $('mtBody').innerHTML = `
    <div class="mt-card">
      <div class="sub">${sec.no}、${esc(sec.title)}　·　第 ${idx + 1} / ${sec.items.length} 小题</div>
      <div class="mt-prompt">${esc(it.prompt)}</div>
      ${opts}
      <div id="chHint" class="sub"></div>
      ${known ? '' : '<div class="mt-judge"><button class="yes" id="sjYes">对</button><button class="no" id="sjNo">错</button></div>'}
    </div>`;
  if (!known) {
    $('chHint').textContent = '本题原卷未附答案，先选一个，再自己判断对错：';
    $('sjYes').onclick = () => selfJudge(it, true);
    $('sjNo').onclick = () => selfJudge(it, false);
  }
  $('mtBody').querySelectorAll('.opt-btn').forEach((b) => {
    b.onclick = () => {
      if (!known) {
        // 没有标准答案时选项只做"选中"标记, 不判分
        $('mtBody').querySelectorAll('.opt-btn').forEach((x) =>
          x.classList.toggle('ok', x === b));
        return;
      }
      pickChoice(sec, it, Number(b.dataset.j));
    };
  });
}

function pickChoice(sec, it, pick) {
  if (M.choiceDone) return;
  const want = it.answer;
  if (typeof want !== 'number') return;
  M.choiceDone = true;
  const ok = pick === want;
  M.results[it.id] = ok;
  const marks = '①②③④⑤⑥';
  $('mtBody').querySelectorAll('.opt-btn').forEach((b) => {
    const j = Number(b.dataset.j);
    if (j === want) b.classList.add('ok');
    else if (j === pick) b.classList.add('bad');
    b.disabled = true;
  });
  updateHead();
  if (ok) {
    $('chHint').textContent = '✅ 正确，5 秒后自动进入下一题…';
    $('chHint').style.color = '#1f9d55';
    setTimeout(() => { if (M.choiceDone) advanceChoice(); }, CORRECT_WAIT);
  } else {
    $('chHint').textContent = `❌ 答错了，正确答案是 ${marks[want - 1]} ${it.options[want - 1]}`;
    $('chHint').style.color = '#d64545';
    setNext('下一题', advanceChoice);
  }
}

function selfJudge(it, ok) {
  if (M.choiceDone) return;
  M.choiceDone = true;
  M.results[it.id] = ok;
  updateHead();
  $('chHint').textContent = ok ? '✅ 记为答对' : '❌ 记为答错';
  $('chHint').style.color = ok ? '#1f9d55' : '#d64545';
  setNext('下一题', advanceChoice);
}

function advanceChoice() {
  if (M.mode !== 'test') return;        // 已经退出/交卷, 别再改状态
  const sec = cur();
  M.itemI += 1;
  if (!sec || M.itemI >= sec.items.length) { gotoNextSection(); return; }
  renderSection();
}

/* ---------------------------------------------------------------- 翻译 */

function renderTranslate(sec) {
  const idx = Math.min(M.itemI, sec.items.length - 1);
  const it = sec.items[idx];
  const toJp = /日语/.test(sec.title);
  $('mtBody').innerHTML = `
    <div class="mt-card">
      <div class="sub">${sec.no}、${esc(sec.title)}　·　第 ${idx + 1} / ${sec.items.length} 小题</div>
      <div class="mt-prompt">${esc(it.prompt)}</div>
      <div class="sub" style="margin:12px 0 6px">请写出${toJp ? '日语' : '汉语'}的译文：</div>
      <textarea id="trInput" rows="3"></textarea>
      <div class="mt-judge" style="margin-top:12px">
        <button class="yes" id="trSubmit">提交</button>
        <button class="no" id="trReveal" style="background:#fff;color:var(--text)">不会，看答案</button>
      </div>
      <div class="fill-ans" id="trAns" style="text-align:left;font-size:15px;display:none"></div>
      <div id="trJudge"></div>
      <div id="trHint" class="sub"></div>
    </div>`;
  const showRef = () => {
    $('trAns').style.display = '';
    $('trAns').textContent = `参考译文：${it.answer || '（未提供答案）'}`;
  };
  $('trSubmit').onclick = async () => {
    const text = ($('trInput').value || '').trim();
    if (!text) { $('trHint').textContent = '先写一句译文再提交，或点「不会，看答案」。'; return; }
    if (!Llm.ready()) {
      $('trHint').textContent = '没配置 AI，改为自己对照答案判分。';
      trSelfJudge(it, showRef);
      return;
    }
    $('trSubmit').disabled = true;
    $('trHint').textContent = 'AI 正在判分…';
    $('trHint').style.color = 'var(--muted)';
    const r = await Llm.judge(it.prompt, text, it.answer || '', toJp);
    showRef();
    $('trJudge').innerHTML = '';
    $('trSubmit').parentElement.style.display = 'none';
    if (r.ok === null) {
      $('trHint').textContent = `${r.reason}，请自己对照答案判断：`;
      trSelfJudge(it, null);
      return;
    }
    judgeTranslate(it, r.ok, r.reason);
  };
  $('trReveal').onclick = () => {
    showRef();
    $('trSubmit').parentElement.style.display = 'none';
    $('trHint').textContent = '对照答案自评：';
    trSelfJudge(it, null);
  };
  if (M.noAnswer) $('trHint').textContent = '本题原卷未附答案，按自己的译文自评。';
}

function trSelfJudge(it, after) {
  if (after) after();
  $('trJudge').innerHTML =
    '<div class="mt-judge"><button class="yes" id="trYes">对</button><button class="no" id="trNo">错</button></div>';
  $('trYes').onclick = () => judgeTranslate(it, true, '');
  $('trNo').onclick = () => judgeTranslate(it, false, '');
}

function judgeTranslate(it, ok, reason) {
  M.results[it.id] = ok;
  updateHead();
  $('trHint').textContent = (ok ? '✅ 判为正确' : '❌ 判为错误') + (reason ? `　${reason}` : '');
  $('trHint').style.color = ok ? '#1f9d55' : '#d64545';
  setNext('下一题', advanceTranslate);
}

function advanceTranslate() {
  const sec = cur();
  M.itemI += 1;
  if (!sec || M.itemI >= sec.items.length) { gotoNextSection(); return; }
  renderSection();
}

/* ---------------------------------------------------------------- 流转 */

function nextSection() { gotoNextSection(); }

function gotoNextSection() {
  hideNext();
  M.secI += 1;
  M.itemI = 0;
  if (M.lesson) {
    patchProg(M.lesson, { section: M.secI, idx: 0, seconds: elapsed(),
      score: Object.values(M.results).filter(Boolean).length, results: M.results });
  }
  renderSection();
}

function finish() {
  clearTimer();
  const total = M.sections.reduce((a, s) => a + s.items.length, 0);
  const score = Object.values(M.results).filter(Boolean).length;
  patchProg(M.lesson, { status: 'done', seconds: elapsed(), score, total,
    finishedAt: Date.now(), results: M.results });
  M.mode = 'paper';
  renderPaper(true);
}

/* ---------------------------------------------------------------- 试卷 */

function renderPaper(justFinished) {
  clearTimer();
  const secs = M.sections;
  const total = secs.reduce((a, s) => a + s.items.length, 0) || 1;
  const score = Object.values(M.results).filter(Boolean).length;
  const p = prog(M.lesson) || {};
  const marks = '①②③④⑤⑥';

  $('mtTitle').textContent = `第 ${M.lesson} 课 · 试卷`;
  $('mtSub').textContent = `${score}/${p.total || total} 题答对　用时 ${fmtSec(p.seconds || 0)}`;
  $('mtBar').style.width = `${(score / (p.total || total)) * 100}%`;
  $('mtHint').textContent = justFinished
    ? '本课已完成，下面是整张试卷，上下滑动翻看，错题已标红'
    : '已完成的课直接显示整张试卷，上下滑动翻看';

  // 与电脑端一致的排版: 填空四列、选择题一行(题干→选项→正确项)、
  // 翻译一行(题干→译文)，不再出现"答案"二字
  const html = secs.map((sec) => {
    const items = sec.items.map((it, i) => {
      const ok = M.results[it.id];
      const bad = ok === false ? ' bad' : '';
      const star = `<span class="pstar" data-qid="${it.id}">${isFav(it.id) ? '★' : '☆'}</span>`;
      if (sec.kind === 'fill') {
        const ans = it.answer || '—';
        return `<div class="paper-cell${bad}">${star}<b>${i + 1}</b>`
          + `<span class="pq">${esc(it.prompt)}</span>`
          + `<span class="pa">${esc(ans)}</span></div>`;
      }
      if (sec.kind === 'choice') {
        const opts = (it.options || []).map((o, j) =>
          `${marks[j] || j + 1}${esc(o)}`).join(' ');
        const want = typeof it.answer === 'number'
          ? `(${marks[it.answer - 1] || it.answer})` : '';
        return `<div class="paper-line choice${bad}">${star}`
          + `<span class="pno">${i + 1}.</span>`
          + `<span class="pq">${esc(it.prompt)}</span>`
          + `<span class="pa">${bad ? '✗ ' : ''}${want}</span>`
          + `<span class="popt">${opts}</span></div>`;
      }
      // 翻译: 题干一行, 译文单独一行
      return `<div class="paper-line trans${bad}">`
        + `<div class="thead">${star}<span class="pno">${i + 1}.</span>`
        + `<span class="pq">${esc(it.prompt)}</span></div>`
        + `<span class="pa">${bad ? '✗ ' : ''}${esc(it.answer || '—')}</span></div>`;
    }).join('');
    const cls = sec.kind === 'fill' ? 'paper-fill' : 'paper-rows';
    return `<div class="paper-sec"><h3>${sec.no}、${esc(sec.title)}</h3>`
      + `<div class="${cls}">${items}</div></div>`;
  }).join('');

  $('mtBody').innerHTML = html + `
    <div class="mt-judge" style="margin:16px 0 30px">
      <button class="no" id="paperFav">收藏夹</button>
      <button class="no" id="paperBack">返回列表</button>
      <button class="yes" id="paperRedo">重做这一课</button>
    </div>`;
  hideNext();
  $('mtBody').querySelectorAll('.pstar').forEach((el) => {
    el.onclick = () => {
      toggleFav(el.dataset.qid);
      el.textContent = isFav(el.dataset.qid) ? '★' : '☆';
      el.classList.toggle('on', isFav(el.dataset.qid));
    };
  });
  $('paperBack').onclick = () => { renderList(); hooks.showView('minna'); };
  $('paperFav').onclick = () => { renderFav(); hooks.showView('minnaFav'); };
  $('paperRedo').onclick = () => {
    if (!confirm('清空这一课的作答记录，重新开始？')) return;
    delete allProgress()[M.lesson];
    onChange();
    openLesson(M.lesson, false);
  };
  window.scrollTo(0, 0);
}

/* ------------------------------------------------------------------ 外部挂钩 */
export function initMinna(h) {
  hooks = h;
  if (h.getState) getState = h.getState;
  if (h.onChange) onChange = h.onChange;
}
export function bankLessons() { return lessons(); }

/** 计时器/用时专用: 永远给出 00:00 形式 (fmtSec 在 0 时返回 "—", 适合"无记录") */
export function fmtClock(sec) {
  const s = Math.max(0, Math.floor(sec || 0));
  const m = Math.floor(s / 60);
  const h = Math.floor(m / 60);
  return h
    ? `${h}:${String(m % 60).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`
    : `${String(m).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`;
}
