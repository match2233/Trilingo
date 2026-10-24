/* 生活记录 (PWA 版): 记账 + 记鹿. 只存本机 localStorage, 不参与同步. */

const LKEY = 'trilingo.ledger.v1';
const DKEY = 'trilingo.deer.v1';

const CURRENCIES = ['CNY', 'JPY', 'USD'];
const CUR_NAME = { CNY: '人民币', JPY: '日元', USD: '美元' };
const CUR_SIGN = { CNY: '¥', JPY: '¥', USD: '$' };
const DEER_COLOR = { 0: '#FFFFFF', 1: '#F5D547', 2: '#F0902B', 3: '#D64545' };
const DEER_TEXT = { 0: '#7A8194', 1: '#7A6A12', 2: '#7A4712', 3: '#FFFFFF' };
const DEER_LABEL = { 0: '白', 1: '黄', 2: '橙', 3: '红' };

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s == null ? '' : s).replace(/[&<>"]/g, (c) =>
  ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

let toast = () => {};
let currency = 'CNY';

export function initLife(hooks) {
  toast = hooks.toast || toast;
  bind();
}

/* ------------------------------------------------------------------ 通用 */

export function todayStr(d) {
  const t = d || new Date();
  return `${t.getFullYear()}-${String(t.getMonth() + 1).padStart(2, '0')}-${String(t.getDate()).padStart(2, '0')}`;
}

function money(cents) {
  return (cents / 100).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function parseMoney(text) {
  const s = String(text || '').trim().replace(/,/g, '');
  if (!s) return null;
  if (!/^\d+(\.\d{1,2})?$/.test(s)) return null;
  return Math.round(parseFloat(s) * 100);
}

function loadLedger() {
  try { return JSON.parse(localStorage.getItem(LKEY) || '[]'); } catch { return []; }
}

function saveLedger(list) {
  try { localStorage.setItem(LKEY, JSON.stringify(list)); } catch { /* ignore */ }
}

function loadDeer() {
  try { return JSON.parse(localStorage.getItem(DKEY) || '{}'); } catch { return {}; }
}

function saveDeer(obj) {
  try { localStorage.setItem(DKEY, JSON.stringify(obj)); } catch { /* ignore */ }
}

/* ------------------------------------------------------------------ 记账 */

export function renderLedger() {
  const all = loadLedger();
  const sign = CUR_SIGN[currency];
  const mine = all.filter((e) => e.currency === currency)
    .sort((a, b) => (a.at < b.at ? 1 : -1));

  const inc = mine.filter((e) => e.kind === 'income').reduce((s, e) => s + e.cents, 0);
  const exp = mine.filter((e) => e.kind === 'expense').reduce((s, e) => s + e.cents, 0);
  const bal = inc - exp;

  $('lgBalance').textContent = `${sign}${money(bal)}`;
  $('lgBalance').style.color = bal >= 0 ? '' : '#d64545';
  $('lgTotal').textContent = `${sign}${money(bal)}`;
  $('lgIncome').textContent = `${sign}${money(inc)}`;

  $('lgList').innerHTML = mine.length ? mine.map((e) => `
    <div class="lg-item">
      <span>${esc(String(e.at).replace('T', ' ').slice(0, 16))}</span>
      <span>${esc(e.source || '未填写')}</span>
      <span class="amt ${e.kind === 'income' ? 'income' : 'expense'}">
        ${e.kind === 'income' ? '+' : '−'}${sign}${money(e.cents)}
      </span>
    </div>`).join('') : '<div class="empty">还没有记录</div>';
}

function submit(kind) {
  const srcEl = $(kind === 'income' ? 'incSrc' : 'expSrc');
  const amtEl = $(kind === 'income' ? 'incAmt' : 'expAmt');
  const cents = parseMoney(amtEl.value);
  if (cents === null) { toast('金额最多两位小数，例如 22.70'); amtEl.focus(); return; }
  if (cents <= 0) { toast('金额要大于 0'); amtEl.focus(); return; }
  const all = loadLedger();
  const now = new Date();
  all.push({
    id: Date.now() + Math.random(),
    day: todayStr(now),
    at: `${todayStr(now)}T${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}:${String(now.getSeconds()).padStart(2, '0')}`,
    kind,
    source: (srcEl.value || '').trim() || '未填写',
    currency,
    cents,
  });
  saveLedger(all);
  amtEl.value = '';
  srcEl.value = '';
  renderLedger();
  toast(`已记一笔${kind === 'income' ? '收入' : '支出'} ${CUR_SIGN[currency]}${money(cents)}`);
}

/* ------------------------------------------------------------------ 记鹿 */

export function targetDay() {
  const d = new Date();
  d.setDate(d.getDate() - 1);       // 今天填的是昨天
  return todayStr(d);
}

export function renderDeer() {
  const day = targetDay();
  const all = loadDeer();
  const cur = all[day];

  $('deerDay').textContent = `填写 ${day}（昨天）的数据` +
    (cur === undefined ? '：还没有记录' : `：已记为 ${cur}（${DEER_LABEL[cur]}），再按就是改掉这个值`);

  $('deerRow').innerHTML = [0, 1, 2, 3].map((lv) => `
    <button class="deer-btn ${cur === lv ? 'on' : ''}" data-lv="${lv}"
      style="background:${DEER_COLOR[lv]};color:${DEER_TEXT[lv]}">${lv}</button>`).join('');
  $('deerRow').querySelectorAll('.deer-btn').forEach((b) => {
    b.onclick = () => {
      const lv = Number(b.dataset.lv);
      const data = loadDeer();
      data[day] = lv;
      saveDeer(data);
      renderDeer();
      toast(`已记 ${day} 为 ${lv}`);
    };
  });

  // 当月日历
  const now = new Date();
  const y = now.getFullYear();
  const m = now.getMonth();
  const first = new Date(y, m, 1);
  const days = new Date(y, m + 1, 0).getDate();
  const lead = (first.getDay() + 6) % 7;      // 周一起
  const prefix = `${y}-${String(m + 1).padStart(2, '0')}`;
  let total = 0;
  for (let d = 1; d <= days; d += 1) {
    const v = all[`${prefix}-${String(d).padStart(2, '0')}`];
    if (v !== undefined) total += v;
  }
  let cells = '';
  for (let i = 0; i < lead; i += 1) cells += '<div></div>';
  for (let d = 1; d <= days; d += 1) {
    const v = all[`${prefix}-${String(d).padStart(2, '0')}`];
    const bg = v === undefined ? '' : DEER_COLOR[v];
    const fg = v === undefined ? '' : DEER_TEXT[v];
    cells += `<div class="deer-day" style="background:${bg || 'transparent'};color:${fg || 'var(--muted)'}">
      ${v === undefined ? d : `<span>${d}</span><b style="font-size:10px">${v}</b>`}</div>`;
  }
  $('deerCal').innerHTML = cells;
  $('deerStat').textContent = `${y} 年 ${m + 1} 月　鹿次数 ${total}`;
}

/* ------------------------------------------------------------------ 绑定 */

function bind() {
  // 注意: 入口按钮与返回按钮的跳转由 app.js 统一绑定,
  // 这里再绑一次会把那边的 showView 覆盖掉 (只渲染不跳页)。
  $('incSubmit').onclick = () => submit('income');
  $('expSubmit').onclick = () => submit('expense');
  $('incAmt').addEventListener('keydown', (e) => { if (e.key === 'Enter') submit('income'); });
  $('expAmt').addEventListener('keydown', (e) => { if (e.key === 'Enter') submit('expense'); });
  document.querySelectorAll('#curSeg button').forEach((b) => {
    b.onclick = () => {
      currency = b.dataset.cur;
      document.querySelectorAll('#curSeg button').forEach((x) =>
        x.classList.toggle('on', x === b));
      renderLedger();
    };
  });
}

export function ledgerFooter() {
  const all = loadLedger();
  for (const cur of CURRENCIES) {
    const mine = all.filter((e) => e.currency === cur);
    if (!mine.length) continue;
    const inc = mine.filter((e) => e.kind === 'income').reduce((s, e) => s + e.cents, 0);
    const exp = mine.filter((e) => e.kind === 'expense').reduce((s, e) => s + e.cents, 0);
    return `${CUR_SIGN[cur]}${money(inc - exp)}`;
  }
  return '';
}

export function deerFooter() {
  const all = loadDeer();
  const now = new Date();
  const prefix = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
  let total = 0;
  Object.entries(all).forEach(([d, v]) => { if (d.startsWith(prefix)) total += v; });
  return total ? `本月 ${total} 次` : '';
}
