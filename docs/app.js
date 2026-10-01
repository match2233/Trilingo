/* Trilingo PWA 主逻辑 —— 复刻桌面端的功能：
 * 每日抽词测验、错题本、数据库查看，并通过 GitHub 与电脑端同步。
 */

import * as C from './core.js';
import * as gh from './gh.js';

const CORRECT_DELAY = 2500;   // 答对后停留多久再跳下一题（毫秒）

const S = {
  state: gh.loadLocalState(),
  der: null,
  quiz: null,
  lang: 'en',
};

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s == null ? '' : s).replace(/[&<>"]/g, (c) =>
  ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

/* ------------------------------------------------------------------ 词表 */

function words(lang) {
  return (S.state.words && S.state.words[lang]) || [];
}

function wordRec(lang, w) {
  return words(lang).find((x) => x.w === w);
}

function refreshDerived() {
  S.der = C.derive(S.state);
}

function todayEvents(lang) {
  const t = C.today();
  return S.state.events.filter((e) => e.l === lang && e.day === t);
}

/* ------------------------------------------------------------------ 作答 */

function addEvent(lang, word, ok) {
  const now = Date.now();
  S.state.events.push({
    i: `${String(now).padStart(13, '0')}${Math.random().toString(16).slice(2, 10)}`,
    t: now,
    d: 'iphone',
    l: lang,
    w: word,
    o: ok ? 1 : 0,
    day: C.today(),
  });
  refreshDerived();
  gh.saveLocalState(S.state);
  gh.markPending(true);
}

/* ------------------------------------------------------------------ 判题 */

const normEn = (s) => (s || '').trim().toLowerCase().replace(/[\s\-'’,.]+/g, '');

const KATA = (() => {
  const m = {};
  for (let c = 0x30a1; c < 0x30f7; c++) m[String.fromCharCode(c)] = String.fromCharCode(c - 0x60);
  return m;
})();

function normJp(s) {
  s = (s || '').trim();
  s = [...s].map((ch) => KATA[ch] || ch).join('');
  return s.replace(/[\s　～~、，,。.・ー]+/g, '').toLowerCase();
}

function checkAnswer(raw, rec, lang) {
  if (lang === 'en') return normEn(raw) === normEn(rec.w);
  const set = new Set([normJp(rec.w)]);
  if (rec.r) {
    set.add(normJp(rec.r));
    set.add(normJp(rec.r.replace(/[、，]/g, '')));
  }
  return set.has(normJp(raw));
}

/* ------------------------------------------------------------------ 测验 */

function startQuiz(lang) {
  S.lang = lang;
  const plan = C.planFor(C.today(), lang, words(lang), S.der);
  const answered = new Set(todayEvents(lang).map((e) => e.w));
  S.quiz = { lang, plan, idx: 0, answered, revealed: false, timer: null };
  // 跳到第一道还没答的
  while (S.quiz.idx < plan.length && answered.has(plan[S.quiz.idx].w)) S.quiz.idx++;

  // 另一台设备已经把今天的任务做完了 -> 直接显示完成页, 不要让人重做一遍
  const synced = ((S.der.done || {})[C.today()] || {})[lang] || 0;
  if (plan.length > 0 && synced >= plan.length) S.quiz.idx = plan.length;

  showView('quiz');
  renderQuiz();   // 之前漏了这一步 —— 进入测验页永远是空白
}

function renderQuiz() {
  const q = S.quiz;
  if (!q) return;
  const total = q.plan.length;
  const done = q.answered.size;

  $('bar').style.width = total ? `${Math.min(100, (done / total) * 100)}%` : '0%';

  // 今天已经背完: 显示完成页, 而不是留一个空白的答题界面
  const finished = q.idx >= total;
  $('quizBody').style.display = finished ? 'none' : 'flex';
  $('quizDone').classList.toggle('show', finished);

  if (finished) {
    const label = q.lang === 'en' ? '英语' : '日语';
    const evs = todayEvents(q.lang);
    const ok = evs.filter((e) => e.o).length;
    const pct = evs.length ? Math.round((ok / evs.length) * 100) : 0;
    $('quizTitle').textContent = `${label} · 已完成`;
    $('doneStats').innerHTML =
      `今日 ${total} 个词已全部过完<br>答对 ${ok} 个　正确率 ${pct}%` +
      (q.answered.size < total ? '<br><span style="color:var(--faint)">（含此前已完成的）</span>' : '');
    return;
  }
  $('quizTitle').textContent =
    `${q.lang === 'en' ? '英语' : '日语'} · ${q.idx + 1}/${total}`;

  const item = q.plan[q.idx];
  const rec = wordRec(q.lang, item.w);
  $('meaning').className = 'meaning';
  $('meaning').textContent = (rec && rec.m) || '（缺释义，请在数据库补充）';
  $('badge').textContent = item.kind === 'review' ? '错题复习' : '新词';
  $('badge').className = 'badge' + (item.kind === 'review' ? ' review' : '');

  const inp = $('answer');
  inp.disabled = false;
  inp.value = '';
  inp.className = '';
  inp.setAttribute('autocapitalize', q.lang === 'en' ? 'none' : 'off');
  inp.setAttribute('autocorrect', 'off');
  inp.setAttribute('spellcheck', 'false');
  setResult([], '');
  $('nextBtn').style.display = 'none';
  q.revealed = false;
}

function setResult(lines, cls) {
  const box = $('result');
  box.innerHTML = lines.map((l) => `<div class="${l.cls || ''}">${esc(l.text)}</div>`).join('');
  if (cls) box.className = 'result ' + cls;
  else box.className = 'result';
}

function submitAnswer() {
  const q = S.quiz;
  if (!q || q.revealed || q.idx >= q.plan.length) return;
  const inp = $('answer');
  const raw = inp.value.trim();
  if (!raw) return;

  const item = q.plan[q.idx];
  const rec = wordRec(q.lang, item.w) || { w: item.w, m: '' };
  const ok = checkAnswer(raw, rec, q.lang);

  q.revealed = true;
  inp.disabled = true;
  inp.className = ok ? 'ok' : 'bad';
  addEvent(q.lang, item.w, ok);
  q.answered.add(item.w);

  const detail = q.lang === 'en'
    ? (rec.ipa || '（缺音标）')
    : [rec.ac || '声调待补', rec.r || ''].filter(Boolean).join('　');

  if (ok) {
    setResult([
      { text: '✓ 拼写正确', cls: 'main ok-text' },
      { text: detail, cls: 'ipa' },
    ]);
    $('nextBtn').style.display = 'none';
    q.timer = setTimeout(nextWord, CORRECT_DELAY);
    const secs = Math.round(CORRECT_DELAY / 1000);
    setResult([
      { text: '✓ 拼写正确', cls: 'main ok-text' },
      { text: detail, cls: 'ipa' },
      { text: `${secs} 秒后进入下一个…`, cls: 'hint' },
    ]);
  } else {
    setResult([
      { text: `✗ 正确拼写：${rec.w}${q.lang === 'jp' && rec.r ? '（' + rec.r + '）' : ''}`, cls: 'main bad-text' },
      { text: detail, cls: 'ipa' },
    ]);
    $('nextBtn').style.display = 'block';
  }

  $('bar').style.width = `${Math.min(100, (q.answered.size / q.plan.length) * 100)}%`;
  $('quizTitle').textContent =
    `${q.lang === 'en' ? '英语' : '日语'} · ${q.idx + 1}/${q.plan.length}`;
}

function nextWord() {
  const q = S.quiz;
  if (!q) return;
  if (q.timer) { clearTimeout(q.timer); q.timer = null; }
  q.idx += 1;
  while (q.idx < q.plan.length && q.answered.has(q.plan[q.idx].w)) q.idx += 1;
  if (q.idx >= q.plan.length) {
    renderQuiz();
    // 一门语言读完就推一次，让电脑端尽快看到
    syncQuiet();
    return;
  }
  renderQuiz();
}

function exitQuiz() {
  if (S.quiz && S.quiz.timer) clearTimeout(S.quiz.timer);
  S.quiz = null;
  syncQuiet();
  renderAll();
  showView('home');
}

/* ------------------------------------------------------------------ 首页 */

function renderHome() {
  const t = C.today();
  const der = S.der;

  $('streakNum').textContent = C.streak(der.days);

  // 四个入口, 顺带累计今日总进度
  let planTotal = 0;
  let planDone = 0;
  for (const lang of ['en', 'jp']) {
    const plan = C.planFor(t, lang, words(lang), der);
    // 今天做了什么, 由两部分构成: 本机答的 + 另一台设备同步过来的计数。
    // 电脑端的作答折叠进了 base, 具体是哪些词已经无从得知, 但答了多少是知道的。
    const local = new Set(todayEvents(lang).map((e) => e.w));
    const localDone = plan.filter((p) => local.has(p.w)).length;
    const synced = ((der.done || {})[t] || {})[lang] || 0;
    const done = Math.min(plan.length, Math.max(localDone, synced));

    planTotal += plan.length;
    planDone += done;

    const el = $(lang === 'en' ? 'tileEn' : 'tileJp');
    const complete = plan.length > 0 && done >= plan.length;
    el.classList.toggle('done', complete);
    el.querySelector('[data-foot]').textContent = complete
      ? '今日已完成 ✓'
      : (done ? `${done} / ${plan.length}` : `共 ${plan.length} 个`);
  }

  const pct = planTotal ? Math.round((planDone / planTotal) * 100) : 0;
  $('todayPct').textContent = `${pct}%`;
  $('todayBar').style.width = `${pct}%`;
  $('todayHint').textContent = planTotal === 0
    ? '词表里还没有内容'
    : (planDone >= planTotal ? '今天的任务已全部完成 🎉' : `还剩 ${planTotal - planDone} 个词`);

  // 错题本入口
  for (const lang of ['en', 'jp']) {
    const open = Object.entries(der.mistakes)
      .filter(([k, m]) => k.startsWith(lang + ':') && !m.g);
    const due = open.filter(([, m]) => {
      const d = C.nextDue(m);
      return d && d <= t;
    }).length;
    const el = $(lang === 'en' ? 'tileErrEn' : 'tileErrJp');
    el.querySelector('[data-foot]').textContent = open.length
      ? (due ? `${open.length} 个 · 今日待复习 ${due}` : `${open.length} 个待复习`)
      : '暂无错词';
  }

  // 累计数据
  $('statWords').textContent = words('en').length + words('jp').length;
  $('statStudied').textContent = Object.keys(der.stats).length;
  $('statMistakes').textContent = Object.values(der.mistakes).filter((m) => !m.g).length;

  // 同步状态
  const cfgOk = gh.isConfigured();
  const pend = gh.hasPending();
  const pill = $('syncPill');
  pill.textContent = !cfgOk
    ? '未开启同步 · 在「同步」页配置'
    : (pend ? '有改动待同步 · 回到首页会自动推送' : '数据已同步');
  pill.className = 'sync-pill' + (pend ? ' pending' : '');
}

/* ------------------------------------------------------------------ 错题本 */

function renderMistakes() {
  const t = C.today();
  const lang = S.lang;
  const rows = Object.entries(S.der.mistakes)
    .filter(([k, m]) => k.startsWith(lang + ':') && !m.g)
    .map(([k, m]) => ({ word: C.splitKey(k)[1], m, due: C.nextDue(m) || '' }))
    .sort((a, b) => (a.due < b.due ? -1 : a.due > b.due ? 1 : 0));

  const box = $('mistakeList');
  if (!rows.length) {
    box.innerHTML = '<div class="empty">错题本是空的<br>答错的词会自动出现在这里</div>';
    return;
  }
  box.innerHTML = rows.map((r) => {
    const rec = wordRec(lang, r.word) || {};
    const due = r.due && r.due <= t;
    const detail = lang === 'en' ? (rec.ipa || '') : [rec.ac, rec.r].filter(Boolean).join('　');
    return `<div class="row${due ? ' due' : ''}">
      <div class="r1">
        <span class="w">${esc(r.word)}</span>
        <span class="tag${due ? ' hot' : ''}">${due ? '今日待复习' : '下次 ' + r.due}</span>
      </div>
      <div class="m">${esc(rec.m || '')}</div>
      <div class="meta">${esc(detail)}　错 ${r.m.e || 0} 次　进度 ${C.mistakeProgress(r.m)}</div>
    </div>`;
  }).join('') + `<div class="btn-row"><button id="reviewNow">把到期的并入今日复习</button></div>`;

  $('reviewNow').onclick = () => {
    // 把到期错题的 next_due 提前到今天 —— 计划是算出来的, 改数据即可
    const t2 = C.today();
    let n = 0;
    for (const [k, m] of Object.entries(S.der.mistakes)) {
      if (!k.startsWith(lang + ':') || m.g) continue;
      const d = C.nextDue(m);
      if (d && d <= t2) continue;          // 已经到期, 不用动
      if (d && d <= C.addDays(t2, 3)) { m.a = C.addDays(t2, -(C.REVIEW_OFFSETS[m.s] || 0)); n++; }
    }
    gh.saveLocalState(S.state);
    refreshDerived();
    toast(n ? `已把 ${n} 个词并入今日复习` : '没有可提前的词');
    renderMistakes();
  };
}

/* ------------------------------------------------------------------ 数据库 */

function renderDB() {
  const lang = S.lang;
  const q = ($('search').value || '').trim().toLowerCase();
  let list = words(lang);
  if (q) {
    list = list.filter((r) =>
      (r.w || '').toLowerCase().includes(q) ||
      (r.m || '').toLowerCase().includes(q) ||
      (r.r || '').toLowerCase().includes(q));
  }
  const box = $('dbList');
  $('dbCount').textContent = `${list.length} 条`;
  if (!list.length) {
    box.innerHTML = '<div class="empty">没有匹配的词条</div>';
    return;
  }
  box.innerHTML = list.slice(0, 400).map((r) => {
    const key = C.keyOf(lang, r.w);
    const m = S.der.mistakes[key];
    const detail = lang === 'en' ? (r.ipa || '') : [r.ac, r.r].filter(Boolean).join('　');
    const stat = S.der.stats[key] ? `　学于 ${S.der.stats[key]}` : '';
    const err = m && !m.g ? `　<span class="tag hot">错题 ${C.mistakeProgress(m)}</span>` : '';
    return `<div class="row">
      <div class="r1"><span class="w">${esc(r.w)}</span><span class="meta">${esc(detail)}</span></div>
      <div class="m">${esc(r.m || '（缺释义）')}</div>
      <div class="meta">${stat}${err}</div>
    </div>`;
  }).join('');
}

/* ------------------------------------------------------------------ 设置 */

function renderSettings() {
  const c = gh.loadConfig();
  $('token').value = c.token || '';
  $('owner').value = c.owner || '';
  $('repo').value = c.repo || '';
  const n = S.state.events.length;
  const d = S.der;
  $('stats').innerHTML =
    `词条 ${words('en').length + words('jp').length} 个　` +
    `错题 ${Object.values(d.mistakes).filter((m) => !m.g).length} 个　` +
    `打卡 ${d.days.size} 天　事件 ${n} 条`;
}

/* ------------------------------------------------------------------ 同步 */

function syncQuiet() {
  if (!gh.isConfigured()) return;
  gh.syncNow()
    .then((r) => {
      S.state = r.state;
      refreshDerived();
      renderHome();
      toast(r.changed ? '已同步' : '已是最新');
    })
    .catch((e) => {
      gh.markPending(true);
      toast(`同步失败：${e.message || e}`);
    });
}

async function doSync(manual) {
  if (!gh.isConfigured()) {
    if (manual) toast('请先填写访问令牌和仓库名');
    return;
  }
  const btn = $('syncBtn');
  if (btn) { btn.disabled = true; btn.textContent = '同步中…'; }
  try {
    const r = await gh.syncNow();
    S.state = r.state;
    refreshDerived();
    renderAll();
    toast(r.changed ? `同步完成（${r.sha}）` : '已是最新，无需同步');
  } catch (e) {
    gh.markPending(true);
    toast(`同步失败：${e.message || e}`);
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = '立即同步'; }
  }
}

/* ------------------------------------------------------------------ 视图切换 */

function showView(name) {
  document.querySelectorAll('.view').forEach((v) => v.classList.remove('active'));
  const el = $(name);
  if (el) el.classList.add('active');
  $('tabs').style.display = name === 'quiz' ? 'none' : 'flex';
  document.querySelectorAll('#tabs button').forEach((b) =>
    b.classList.toggle('on', b.dataset.view === name));
  window.scrollTo(0, 0);
}

function renderAll() {
  refreshDerived();
  renderHome();
  renderMistakes();
  renderDB();
  renderSettings();
}

let toastTimer = null;
function toast(msg) {
  const el = $('toast');
  el.textContent = msg;
  el.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove('show'), 2200);
}

/* ------------------------------------------------------------------ 启动 */

function bind() {
  $('tileEn').onclick = () => startQuiz('en');
  $('tileJp').onclick = () => startQuiz('jp');
  $('tileErrEn').onclick = () => { S.lang = 'en'; renderMistakes(); showView('mistakes'); };
  $('tileErrJp').onclick = () => { S.lang = 'jp'; renderMistakes(); showView('mistakes'); };

  document.querySelectorAll('#tabs button').forEach((b) => {
    b.onclick = () => { showView(b.dataset.view); renderAll(); };
  });

  $('backBtn').onclick = exitQuiz;
  $('doneBack').onclick = exitQuiz;
  $('answer').addEventListener('keydown', (e) => {
    if (e.key === 'Enter') { e.preventDefault(); submitAnswer(); }
  });
  $('submitBtn').onclick = submitAnswer;
  $('nextBtn').onclick = nextWord;

  document.querySelectorAll('.seg').forEach((seg) => {
    seg.querySelectorAll('button').forEach((b) => {
      b.onclick = () => {
        S.lang = b.dataset.lang;
        seg.querySelectorAll('button').forEach((x) => x.classList.toggle('on', x === b));
        renderMistakes();
        renderDB();
      };
    });
  });

  $('search').addEventListener('input', renderDB);
  $('saveCfg').onclick = () => {
    gh.saveConfig({
      token: $('token').value.trim(),
      owner: $('owner').value.trim(),
      repo: $('repo').value.trim() || 'Trilingo-data',
      path: 'state.json',
      branch: 'main',
    });
    renderHome();
    toast('已保存');
  };
  $('testBtn').onclick = async () => {
    $('syncMsg').textContent = '正在测试…';
    const r = await gh.testConnection();
    $('syncMsg').textContent = r.msg;
    $('syncMsg').className = r.ok ? 'sub ok-text' : 'sub bad-text';
  };
  $('syncBtn').onclick = () => doSync(true);

  $('clearBtn').onclick = () => {
    if (!confirm('将清空本机保存的学习数据，然后从云端重新拉取。\n\n'
               + '本机上还没同步出去的答题记录会丢失。\n\n确定继续吗？')) return;
    gh.clearLocal();
    S.state = gh.loadLocalState();
    refreshDerived();
    renderAll();
    toast('已清空，正在从云端重新拉取…');
    doSync(true);
  };

  // 回到前台且有待同步内容时自动推一次
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden && gh.hasPending()) syncQuiet();
  });
}

async function init() {
  bind();
  refreshDerived();
  renderAll();
  showView('home');
  // 启动时后台拉一次, 让手机上立刻能看到电脑端的进度。
  // 用 pullOnly 而不是完整同步: 只拉不推, 避免本机残留的旧数据被反推回云端。
  if (gh.isConfigured()) {
    gh.pullOnly()
      .then((st) => { if (st) { S.state = st; renderAll(); } })
      .catch(() => {});
  }
}

init();

if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('./sw.js').catch(() => {});
  });
}
