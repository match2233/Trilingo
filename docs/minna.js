/* 新标日测试 (PWA 版) —— 与电脑端同一份题库、同一套交互逻辑。
 *
 * 题库: minna_tests.json (由 tools/build_minna_tests.py 生成, 与桌面共用)
 * 进度: localStorage, 每台设备各记各的, 不参与同步
 *
 * 三种题型:
 *   fill      整大题一次列出 -> 显示答案 -> 逐题标对错(默认对) -> 下一大题
 *   choice    一题一屏, 选项按钮; 对 -> 5 秒自动下一题, 错 -> 手动下一题
 *   translate 一题一屏 -> 显示答案 -> 对/错
 */

const CORRECT_WAIT = 5000;

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
  $('mtBody').innerHTML = `
    <div class="mt-card">
      <div class="sub">${sec.no}、${esc(sec.title)}　·　第 ${idx + 1} / ${sec.items.length} 小题</div>
      <div class="mt-prompt">${esc(it.prompt)}</div>
      <div class="fill-ans" id="trAns" style="text-align:left;font-size:15px"></div>
      <div class="mt-judge" style="margin-top:14px">
        <button class="yes" id="trReveal">显示答案</button>
      </div>
      <div id="trJudge"></div>
      <div id="trHint" class="sub"></div>
    </div>`;
  $('trReveal').onclick = () => {
    $('trAns').textContent = it.answer || '（未提供答案）';
    $('trReveal').parentElement.style.display = 'none';
    $('trJudge').innerHTML =
      '<div class="mt-judge"><button class="yes" id="trYes">对</button><button class="no" id="trNo">错</button></div>';
    $('trYes').onclick = () => judgeTranslate(it, true);
    $('trNo').onclick = () => judgeTranslate(it, false);
  };
  if (M.noAnswer) $('trHint').textContent = '本题原卷未附答案，按自己的译文自评。';
}

function judgeTranslate(it, ok) {
  M.results[it.id] = ok;
  updateHead();
  $('trHint').textContent = ok ? '✅ 记为答对' : '❌ 记为答错';
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

  const html = secs.map((sec) => {
    const items = sec.items.map((it, i) => {
      const ok = M.results[it.id];
      let txt = esc(it.prompt);
      if (sec.kind === 'choice') {
        txt += '　' + (it.options || []).map((o, j) =>
          `${marks[j] || j + 1}${esc(o)}`).join(' ');
      }
      const ans = sec.kind === 'choice' && typeof it.answer === 'number'
        ? `答案 ${marks[it.answer - 1] || it.answer}`
        : (it.answer ? `答案 ${esc(it.answer)}` : '答案 —');
      return `<div class="paper-item ${ok === false ? 'bad' : ''}">
        <span>${i + 1}.</span><span class="pq">${txt}</span>
        ${ok === false ? '<span class="pmark">错</span>' : ''}
        <span class="pa">${ans}</span>
      </div>`;
    }).join('');
    return `<div class="paper-sec"><h3>${sec.no}、${esc(sec.title)}</h3>${items}</div>`;
  }).join('');

  $('mtBody').innerHTML = html + `
    <div class="mt-judge" style="margin:16px 0 30px">
      <button class="no" id="paperBack">返回列表</button>
      <button class="yes" id="paperRedo">重做这一课</button>
    </div>`;
  hideNext();
  $('paperBack').onclick = () => { renderList(); hooks.showView('minna'); };
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
