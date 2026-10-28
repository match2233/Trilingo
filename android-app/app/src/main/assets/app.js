/* 身体锻炼 — 独立 Android 版
 * 数据只保存在本机（Android SharedPreferences / 浏览器 localStorage）。
 * 不包含任何同步逻辑；只有用户主动点击 AI 报告按钮时才会发起网络请求。
 */
(function () {
  'use strict';

  // ------------------------------------------------------------- 基础数据
  const APP_VERSION = '1.0.0';
  const STORE_KEY = 'body_exercise_v1';
  const APP_CONFIG = Object.assign({
    apiKey: '',
    baseUrl: 'https://api.deepseek.com',
    model: 'deepseek-flash'
  }, window.APP_CONFIG || {});

  const DAYS = [
    { n: 1, key: 'push', name: '推日', sub: '胸 / 肩 / 三头', color: '#b9552a' },
    { n: 2, key: 'pull', name: '拉日', sub: '背 / 二头', color: '#3d5bb5' },
    { n: 3, key: 'legs', name: '腿日', sub: '腿 / 臀 / 腹', color: '#247a4c' }
  ];

  const MOVES = [
    { slug: 'incline-press', cn: '哑铃上斜卧推', day: 1, reps: 12 },
    { slug: 'bench-press', cn: '哑铃卧推', day: 1, reps: 12 },
    { slug: 'shoulder-press', cn: '哑铃肩推', day: 1, reps: 12 },
    { slug: 'lateral-raise', cn: '哑铃侧平举', day: 1, reps: 12 },
    { slug: 'triceps-ext', cn: '哑铃颈后臂屈伸', day: 1, reps: 12 },
    { slug: 'rdl', cn: '哑铃罗马尼亚硬拉', day: 2, reps: 12 },
    { slug: 'bent-row', cn: '哑铃俯身划船', day: 2, reps: 12 },
    { slug: 'single-row', cn: '单臂哑铃划船', day: 2, reps: 12 },
    { slug: 'reverse-fly', cn: '哑铃反向飞鸟', day: 2, reps: 12 },
    { slug: 'face-pull', cn: '哑铃面拉', day: 2, reps: 12 },
    { slug: 'bicep-curl', cn: '哑铃二头弯举', day: 2, reps: 12 },
    { slug: 'goblet-squat', cn: '哑铃高脚杯深蹲', day: 3, reps: 12 },
    { slug: 'crunch', cn: '哑铃卷腹', day: 3, reps: 12 },
    { slug: 'hip-thrust', cn: '哑铃臀桥', day: 3, reps: 12 }
  ];
  const MOVE_BY_SLUG = {};
  MOVES.forEach(function (m) { MOVE_BY_SLUG[m.slug] = m; });
  const DEFAULT_REPS = {};
  MOVES.forEach(function (m) { DEFAULT_REPS[m.slug] = m.reps; });

  const TABS = [
    { id: 'home', label: '首页', icon: 'home' },
    { id: 'weight', label: '体重', icon: 'scale' },
    { id: 'strength', label: '训练', icon: 'dumbbell' },
    { id: 'cardio', label: '有氧', icon: 'run' },
    { id: 'ai', label: '建议', icon: 'sparkles' }
  ];

  // ------------------------------------------------------------- 图标
  const ICONS = {
    home: '<path d="M3 10.5 12 3l9 7.5"/><path d="M5.5 9.5V21h5v-6h3v6h5V9.5"/>',
    scale: '<rect x="3.5" y="4" width="17" height="17" rx="4"/><path d="M8 9a4 4 0 0 1 8 0"/><path d="M12 9v3"/>',
    dumbbell: '<path d="M6.5 6.5v11M3.5 8.5v7M17.5 6.5v11M20.5 8.5v7M6.5 12h11"/>',
    run: '<circle cx="15" cy="5" r="2"/><path d="m9 20 2.5-5.5L9 12l-3 2"/><path d="m12.5 9 3 3 3-1"/><path d="m11 14.5 4 2 1 3.5"/>',
    bike: '<circle cx="6" cy="17" r="3.5"/><circle cx="18" cy="17" r="3.5"/><path d="M6 17 10.5 8h4l3.5 9M10.5 8h6M14.5 8l1.5 9"/>',
    sparkles: '<path d="m12 3 1.4 4.6L18 9l-4.6 1.4L12 15l-1.4-4.6L6 9l4.6-1.4L12 3Z"/><path d="m19 15 .8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8L19 15Z"/><path d="m5 14 .6 1.9L7.5 16.5l-1.9.6L5 19l-.6-1.9-1.9-.6 1.9-.6L5 14Z"/>',
    user: '<circle cx="12" cy="8" r="3.5"/><path d="M4.5 20a7.5 7.5 0 0 1 15 0"/>',
    plus: '<path d="M12 5v14M5 12h14"/>',
    history: '<path d="M3.5 12a8.5 8.5 0 1 0 2.5-6"/><path d="M3.5 4v4.5H8"/><path d="M12 7.5V12l3 2"/>',
    trash: '<path d="M4 7h16M9 7V4.5h6V7M6.5 7l.8 12.5h9.4L17.5 7M10 10.5v6M14 10.5v6"/>',
    close: '<path d="m6 6 12 12M18 6 6 18"/>',
    check: '<path d="m5 12 4.5 4.5L19 6.5"/>',
    info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8h.01"/>',
    shield: '<path d="M12 3 5 6v5.5c0 4.5 2.8 7.6 7 9.5 4.2-1.9 7-5 7-9.5V6l-7-3Z"/><path d="m9 12 2 2 4-4"/>',
    clock: '<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/>',
    flame: '<path d="M12.5 3.5s.9 3.1-1.6 5.4C8.2 11.4 7 13.2 7 15a5 5 0 0 0 10 0c0-2.2-1.2-4-2.7-5.4-.4 1-.9 1.7-1.7 2.3.2-2.8-.1-6-.1-8.4Z"/>',
    heart: '<path d="M20.5 8.5c0 4.5-8.5 10-8.5 10s-8.5-5.5-8.5-10A4.5 4.5 0 0 1 12 6a4.5 4.5 0 0 1 8.5 2.5Z"/>',
    settings: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1-2.8 2.8-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.5V21h-4v-.1a1.7 1.7 0 0 0-1-1.5 1.7 1.7 0 0 0-1.9.3l-.1.1L4.2 17l.1-.1a1.7 1.7 0 0 0 .3-1.9 1.7 1.7 0 0 0-1.5-1H3v-4h.1a1.7 1.7 0 0 0 1.5-1 1.7 1.7 0 0 0-.3-1.9L4.2 7 7 4.2l.1.1a1.7 1.7 0 0 0 1.9.3 1.7 1.7 0 0 0 1-1.5V3h4v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.9-.3l.1-.1L19.8 7l-.1.1a1.7 1.7 0 0 0-.3 1.9 1.7 1.7 0 0 0 1.5 1h.1v4h-.1a1.7 1.7 0 0 0-1.5 1Z"/>',
    key: '<circle cx="8" cy="15" r="4"/><path d="m11 12 8-8M16 7l3 3M14 9l2 2"/>',
    list: '<path d="M8 6h12M8 12h12M8 18h12M4 6h.01M4 12h.01M4 18h.01"/>',
    edit: '<path d="M4 20h4L19 9l-4-4L4 16v4Z"/><path d="m13.5 6.5 4 4"/>',
    arrow: '<path d="m9 5 7 7-7 7"/>',
    undo: '<path d="M4 9h9a5 5 0 0 1 0 10H8"/><path d="m8 5-4 4 4 4"/>',
    calendar: '<rect x="3.5" y="5" width="17" height="16" rx="3"/><path d="M7.5 3v4M16.5 3v4M3.5 10h17"/>',
    trend: '<path d="m3 17 6-6 4 4 8-8"/><path d="M15 7h6v6"/>',
    water: '<path d="M12 3s6 6.5 6 11a6 6 0 0 1-12 0c0-4.5 6-11 6-11Z"/>',
    moon: '<path d="M20 15.5A8.5 8.5 0 0 1 8.5 4 8.5 8.5 0 1 0 20 15.5Z"/>'
  };

  function icon(name, cls) {
    return '<svg class="' + (cls || '') + '" viewBox="0 0 24 24" fill="none" ' +
      'stroke="currentColor" stroke-width="1.8" stroke-linecap="round" ' +
      'stroke-linejoin="round" aria-hidden="true">' + (ICONS[name] || '') + '</svg>';
  }

  // ------------------------------------------------------------- 工具
  function $(sel, root) { return (root || document).querySelector(sel); }
  function $$(sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }
  function pad(n) { return n < 10 ? '0' + n : '' + n; }
  function uid() { return Date.now().toString(36) + Math.random().toString(36).slice(2, 8); }
  function num(v) { const n = parseFloat(v); return isFinite(n) ? n : null; }
  function round1(v) { return Math.round(Number(v) * 10) / 10; }
  function fmtNum(v) {
    const n = Number(v);
    if (!isFinite(n)) return '—';
    return String(Math.round(n * 10) / 10).replace(/\.0$/, '');
  }
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c];
    });
  }
  function isoNow(d) {
    d = d || new Date();
    return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate()) +
      'T' + pad(d.getHours()) + ':' + pad(d.getMinutes()) + ':' + pad(d.getSeconds());
  }
  function toLocalDate(value) {
    if (value instanceof Date) return value;
    const text = String(value == null ? '' : value).slice(0, 10);
    if (/^\d{4}-\d{2}-\d{2}$/.test(text)) return parseKey(text);
    return new Date(value);
  }
  function dateKey(d) {
    d = toLocalDate(d || new Date());
    if (!d || isNaN(d.getTime())) return '';
    return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate());
  }
  function parseKey(k) {
    const p = String(k).slice(0, 10).split('-');
    return new Date(Number(p[0]), Number(p[1]) - 1, Number(p[2]));
  }
  function addDays(d, n) {
    const x = new Date(d.getTime());
    x.setDate(x.getDate() + n);
    return x;
  }
  function dayDiff(a, b) {
    const from = toLocalDate(a);
    const to = toLocalDate(b);
    if (!from || !to || isNaN(from.getTime()) || isNaN(to.getTime())) return 0;
    const fromDay = new Date(from.getFullYear(), from.getMonth(), from.getDate());
    const toDay = new Date(to.getFullYear(), to.getMonth(), to.getDate());
    return Math.round((toDay.getTime() - fromDay.getTime()) / 86400000);
  }
  function atDate(at) { return parseKey(String(at).slice(0, 10)); }
  function stampAt(at) {
    const s = String(at || '');
    return s.length >= 19 ? s.slice(0, 10) + ' ' + s.slice(11, 19) : s.replace('T', ' ');
  }
  function shortStamp(at) {
    const s = String(at || '');
    return s.length >= 16 ? s.slice(5, 10).replace('-', '/') + ' ' + s.slice(11, 16) : s;
  }
  function timeOnly(at) {
    const s = String(at || '');
    return s.length >= 16 ? s.slice(11, 16) : '';
  }
  function moveName(slug) { return (MOVE_BY_SLUG[slug] && MOVE_BY_SLUG[slug].cn) || slug; }
  function dayMeta(n) { return DAYS.find(function (d) { return d.n === n; }) || DAYS[0]; }
  function daysAgoKey(n) { return dateKey(addDays(new Date(), -n)); }

  let toastTimer = null;
  function toast(msg) {
    const el = $('#toast');
    if (!el) return;
    el.textContent = msg;
    el.classList.add('show');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { el.classList.remove('show'); }, 2100);
  }

  function vibrate() {
    try {
      if (window.Android && Android.vibrate) Android.vibrate(12);
    } catch (e) { /* ignore */ }
  }

  // ------------------------------------------------------------- 数据
  function defaultState() {
    return {
      version: 1,
      profile: { sex: '男', age: null, height: null },
      settings: { dumbbell: '5', reps: {} },
      api: {
        apiKey: APP_CONFIG.apiKey || '',
        baseUrl: APP_CONFIG.baseUrl || 'https://api.deepseek.com',
        model: APP_CONFIG.model || 'deepseek-flash'
      },
      weights: [],
      logs: [],
      cardio: [],
      reports: [],
      updatedAt: ''
    };
  }

  function normalizeState(raw) {
    const base = defaultState();
    if (!raw || typeof raw !== 'object') return base;
    const out = Object.assign(base, raw);
    out.profile = Object.assign({ sex: '男', age: null, height: null }, raw.profile || {});
    out.settings = Object.assign({ dumbbell: '5', reps: {} }, raw.settings || {});
    out.api = Object.assign({}, base.api, raw.api || {});
    out.weights = Array.isArray(raw.weights) ? raw.weights : [];
    out.logs = Array.isArray(raw.logs) ? raw.logs : [];
    out.cardio = Array.isArray(raw.cardio) ? raw.cardio : [];
    out.reports = Array.isArray(raw.reports) ? raw.reports : [];
    return out;
  }

  function loadState() {
    let text = '';
    try {
      if (window.Android && Android.loadData) text = Android.loadData() || '';
    } catch (e) { text = ''; }
    if (!text) {
      try { text = localStorage.getItem(STORE_KEY) || ''; } catch (e) { text = ''; }
    }
    if (!text) return defaultState();
    try { return normalizeState(JSON.parse(text)); }
    catch (e) { return defaultState(); }
  }

  function persist() {
    state.updatedAt = isoNow();
    const text = JSON.stringify(state);
    try {
      if (window.Android && Android.saveData) {
        Android.saveData(text);
        return;
      }
    } catch (e) { /* fallback */ }
    try { localStorage.setItem(STORE_KEY, text); } catch (e) { /* ignore */ }
  }

  let state = loadState();
  let currentTab = 'home';
  let strengthDay = 1;
  let cardioKind = 'run';
  let cardioDraft = { km: '', minutes: '', hr: '' };  // minutes 存用户输入原文(分:秒)
  let currentReportId = null;
  let generating = false;
  let aiStatusText = '';
  let aiStatusClass = '';

  // ------------------------------------------------------------- 计算
  function sortedWeights() {
    return state.weights.slice().sort(function (a, b) { return a.at < b.at ? -1 : 1; });
  }
  function latestWeight() {
    const ws = sortedWeights();
    return ws.length ? ws[ws.length - 1] : null;
  }
  function dailyMean(records) {
    const map = {};
    records.forEach(function (r) {
      const k = String(r.at).slice(0, 10);
      if (!map[k]) map[k] = [];
      map[k].push(Number(r.kg));
    });
    return Object.keys(map).sort().map(function (k) {
      const vals = map[k];
      return {
        key: k,
        date: parseKey(k),
        kg: Math.round((vals.reduce(function (a, b) { return a + b; }, 0) / vals.length) * 100) / 100
      };
    });
  }
  function movingAverage(points, windowSize) {
    const out = [];
    const w = windowSize || 7;
    for (let i = 0; i < points.length; i++) {
      const lo = Math.max(0, i - w + 1);
      let sum = 0;
      for (let j = lo; j <= i; j++) sum += points[j].kg;
      out.push({ key: points[i].key, date: points[i].date, kg: Math.round((sum / (i - lo + 1)) * 100) / 100 });
    }
    return out;
  }
  function trendSlope(points) {
    if (!points || points.length < 2) return 0;
    const xs = points.map(function (p) { return dayDiff(points[0].key, p.key); });
    const ys = points.map(function (p) { return p.kg; });
    const n = xs.length;
    const mx = xs.reduce(function (a, b) { return a + b; }, 0) / n;
    const my = ys.reduce(function (a, b) { return a + b; }, 0) / n;
    let den = 0, nom = 0;
    for (let i = 0; i < n; i++) {
      den += (xs[i] - mx) * (xs[i] - mx);
      nom += (xs[i] - mx) * (ys[i] - my);
    }
    return den ? Math.round((nom / den * 7) * 100) / 100 : 0;
  }
  function bmi(kg) {
    const h = Number(state.profile.height);
    if (!h || !kg) return null;
    const m = h / 100;
    return Math.round((kg / (m * m)) * 10) / 10;
  }
  // 时长：内部仍以「分钟(小数)」存，输入输出都按 分:秒 处理
  function parseDuration(text) {
    var t = String(text == null ? '' : text).trim().replace(/：/g, ':');
    if (!t) return null;
    t = t.replace(/分/g, ':').replace(/秒/g, '').replace(/['’]/g, ':')
         .replace(/["″]/g, '');
    if (t.indexOf(':') >= 0) {
      var parts = t.split(':').filter(function (x) { return x !== ''; });
      if (parts.length === 2) {
        var m = Number(parts[0]); var sec = Number(parts[1]);
        if (!isFinite(m) || !isFinite(sec) || m < 0 || sec < 0) return null;
        return Math.round(m * 60 + sec);
      }
      if (parts.length !== 1) return null;
      t = parts[0];
    }
    var v = Number(t);
    if (!isFinite(v) || v <= 0) return null;
    return Math.round(v * 60);
  }

  function fmtDuration(minutes) {
    var total = Math.round(Number(minutes || 0) * 60);
    if (!(total > 0)) return '—';
    return Math.floor(total / 60) + "'" + pad(total % 60) + '"';
  }

  function paceText(km, minutes) {
    if (!(km > 0) || !(minutes > 0)) return '—';
    const sec = minutes * 60 / km;
    return Math.floor(sec / 60) + "'" + pad(Math.floor(sec % 60)) + '"/km';
  }
  function speedText(km, minutes) {
    if (!(km > 0) || !(minutes > 0)) return '—';
    return (km / (minutes / 60)).toFixed(1) + ' km/h';
  }
  function repsOf(log) {
    const s = String(log.reps == null ? '' : log.reps).trim();
    if (s) return s;
    return String((state.settings.reps && state.settings.reps[log.move]) || DEFAULT_REPS[log.move] || 12);
  }
  function weightOf(log) {
    const s = String(log.dumbbell == null ? '' : log.dumbbell).trim();
    return s || String(state.settings.dumbbell || '');
  }
  function profileText() {
    const p = state.profile;
    const parts = [];
    if (p.sex) parts.push(String(p.sex));
    if (p.height) parts.push(p.height + 'cm');
    if (p.age) parts.push(p.age + ' 岁');
    return parts.length ? parts.join('、') : '未填性别/年龄/身高';
  }
  function weekKeys(n) {
    const out = [];
    for (let i = n - 1; i >= 0; i--) out.push(daysAgoKey(i));
    return out;
  }
  function inKeys(at, keys) { return keys.indexOf(String(at).slice(0, 10)) >= 0; }

  // ------------------------------------------------------------- 顶栏/底栏
  function renderTopbar() {
    const el = $('#topbar');
    if (currentTab === 'home') {
      el.innerHTML =
        '<div class="top-row">' +
          '<div class="brand-mark">' + icon('dumbbell') + '</div>' +
          '<div class="brand-copy"><h1>身体锻炼</h1><p>' +
            '每天比昨天更强一点 · 数据只存本机</p></div>' +
          '<button type="button" class="avatar-btn" data-action="profile" aria-label="个人资料">' +
            icon('user') + '</button>' +
        '</div>';
    } else {
      const titles = {
        weight: ['体重记录', '看清长期趋势，不被一天的波动吓到'],
        strength: ['力量训练', '点一下动作卡片 = 记录一组'],
        cardio: ['有氧运动', '跑步、骑行都记在这里'],
        ai: ['AI 建议', '点了才会发送数据，不点不发请求']
      };
      const t = titles[currentTab] || ['身体锻炼', ''];
      el.innerHTML =
        '<div class="top-row">' +
          '<div class="top-title"><h1>' + t[0] + '</h1><p>' + t[1] + '</p></div>' +
          '<button type="button" class="avatar-btn" data-action="profile" aria-label="个人资料">' +
            icon('user') + '</button>' +
        '</div>';
    }
  }

  function renderTabbar() {
    const el = $('#tabbar');
    el.innerHTML = TABS.map(function (t) {
      return '<button type="button" class="tab' + (currentTab === t.id ? ' active' : '') +
        '" data-tab="' + t.id + '" aria-label="' + t.label + '">' + icon(t.icon) +
        '<span>' + t.label + '</span></button>';
    }).join('');
  }

  // ------------------------------------------------------------- 首页
  function activityItems() {
    const items = [];
    state.weights.forEach(function (w) {
      items.push({
        at: w.at, icon: 'scale', color: '#3d6ce7', soft: '#ecf1ff',
        title: '体重 ' + fmtNum(w.kg) + ' kg',
        sub: '体重记录'
      });
    });
    state.logs.forEach(function (l) {
      items.push({
        at: l.at, icon: 'dumbbell', color: '#b9552a', soft: '#fff0e8',
        title: moveName(l.move),
        sub: weightOf(l) + ' kg · ' + repsOf(l) + ' 次'
      });
    });
    state.cardio.forEach(function (c) {
      items.push({
        at: c.at, icon: c.kind === 'run' ? 'run' : 'bike',
        color: c.kind === 'run' ? '#2f9e63' : '#3d6ce7',
        soft: c.kind === 'run' ? '#eaf7f0' : '#ecf1ff',
        title: (c.kind === 'run' ? '跑步' : '骑行') + ' ' + Number(c.km).toFixed(1) + ' km',
        sub: c.minutes + ' 分钟'
      });
    });
    return items.sort(function (a, b) { return a.at < b.at ? 1 : -1; }).slice(0, 6);
  }

  function renderHome() {
    const ws = sortedWeights();
    const latest = ws.length ? ws[ws.length - 1] : null;
    const keys7 = weekKeys(7);
    const recent30 = ws.filter(function (w) { return dayDiff(w.at, new Date()) <= 29; });
    const daily = dailyMean(recent30);
    const first = daily.length ? daily[0].kg : (ws.length ? ws[0].kg : null);
    const slope = daily.length > 1 ? trendSlope(daily) : 0;
    const b = latest ? bmi(latest.kg) : null;

    const logs7 = state.logs.filter(function (l) { return inKeys(l.at, keys7); });
    const days7 = {};
    logs7.forEach(function (l) { days7[String(l.at).slice(0, 10)] = 1; });
    const today = dateKey(new Date());
    const todayLogs = state.logs.filter(function (l) { return String(l.at).slice(0, 10) === today; });
    const cardio7 = state.cardio.filter(function (c) { return inKeys(c.at, keys7); });
    const cardioKm = cardio7.reduce(function (a, c) { return a + Number(c.km || 0); }, 0);

    const lastLog = state.logs.slice().sort(function (a, b) { return a.at < b.at ? 1 : -1; })[0];
    let recommend = 1;
    if (lastLog) {
      const lastDay = new Date(lastLog.at.slice(0, 10) + 'T00:00:00');
      recommend = (MOVE_BY_SLUG[lastLog.move] ? MOVE_BY_SLUG[lastLog.move].day % 3 : 0) + 1;
      if (lastLog.at.slice(0, 10) !== today && dayDiff(lastLog.at, new Date()) >= 2) recommend = 1;
      if (lastDay && isNaN(lastDay.getTime())) recommend = 1;
    }
    const weekSets = {};
    DAYS.forEach(function (d) { weekSets[d.n] = 0; });
    logs7.forEach(function (l) {
      const mv = MOVE_BY_SLUG[l.move];
      if (mv) weekSets[mv.day] += 1;
    });

    const hero = latest
      ? '<section class="hero">' +
          '<div class="hero-top"><span>最新体重</span>' +
            (b ? '<span class="hero-pill">BMI ' + b + '</span>' : '<span class="hero-pill">只存本机</span>') +
          '</div>' +
          '<div class="hero-value">' + fmtNum(latest.kg) + ' <small>kg</small></div>' +
          '<div class="hero-sub">' +
            (first != null && latest.kg !== first ? '较期初 ' + (latest.kg - first >= 0 ? '+' : '') + round1(latest.kg - first) + ' kg · ' : '') +
            '趋势 ' + (slope >= 0 ? '+' : '') + slope.toFixed(2) + ' kg/周' +
          '</div>' +
          '<div class="hero-actions">' +
            '<button type="button" class="hero-btn solid" data-tab="weight">' + icon('plus') + '记录体重</button>' +
            '<button type="button" class="hero-btn" data-tab="strength">' + icon('dumbbell') + '开始训练</button>' +
          '</div>' +
        '</section>'
      : '<section class="hero">' +
          '<div class="hero-top"><span>身体锻炼</span><span class="hero-pill">数据只存本机</span></div>' +
          '<div class="hero-value" style="font-size:28px;line-height:1.25;margin-top:12px">先记录一次体重<br>再开始今天的力量训练</div>' +
          '<div class="hero-sub">所有记录都保存在这台手机，不会上传或同步</div>' +
          '<div class="hero-actions">' +
            '<button type="button" class="hero-btn solid" data-tab="weight">' + icon('plus') + '记录体重</button>' +
            '<button type="button" class="hero-btn" data-action="profile">' + icon('user') + '填写资料</button>' +
          '</div>' +
        '</section>';

    const stats =
      '<div class="stat-grid">' +
        '<div class="stat"><div class="stat-icon" style="background:#eaf7f0;color:#2f9e63">' + icon('dumbbell') + '</div>' +
          '<b>' + Object.keys(days7).length + '<small>/7</small></b><span>本周训练</span></div>' +
        '<div class="stat"><div class="stat-icon" style="background:#fff0e8;color:#f0763f">' + icon('flame') + '</div>' +
          '<b>' + todayLogs.length + '<small>组</small></b><span>今日完成</span></div>' +
        '<div class="stat"><div class="stat-icon" style="background:#ecf1ff;color:#3d6ce7">' + icon('run') + '</div>' +
          '<b>' + fmtNum(cardioKm) + '<small>km</small></b><span>本周有氧</span></div>' +
      '</div>';

    const quick =
      '<div class="quick-row">' +
        '<button type="button" class="quick" data-tab="weight">' + icon('scale') + '<span>记体重</span></button>' +
        '<button type="button" class="quick" data-tab="strength">' + icon('dumbbell') + '<span>记一组</span></button>' +
        '<button type="button" class="quick" data-tab="cardio">' + icon('run') + '<span>记有氧</span></button>' +
        '<button type="button" class="quick" data-tab="ai">' + icon('sparkles') + '<span>AI 建议</span></button>' +
      '</div>';

    const plans =
      '<section class="card plan-card">' +
        '<div class="card-title"><h3>今天练什么</h3><small>点一天查看动作</small></div>' +
        '<div class="plan-grid">' +
        DAYS.map(function (d) {
          return '<button type="button" class="plan day-' + d.n + (recommend === d.n ? ' recommended' : '') +
            '" data-plan="' + d.n + '"><div class="day">第 ' + d.n + ' 天</div>' +
            '<div class="name">' + d.name + '</div><div class="count">' + weekSets[d.n] + ' 组 · ' + d.sub + '</div></button>';
        }).join('') +
        '</div>' +
      '</section>';

    const acts = activityItems();
    const activity =
      '<section class="card">' +
        '<div class="card-title"><h3>最近记录</h3><small>' + (latest ? '更新于 ' + shortStamp(latest.at) : '还没有数据') + '</small></div>' +
        (acts.length ? '<div class="activity">' + acts.map(function (a) {
          return '<div class="act"><div class="act-ico" style="background:' + a.soft + ';color:' + a.color + '">' +
            icon(a.icon) + '</div><div class="act-main"><b>' + esc(a.title) + '</b><span>' + esc(a.sub) +
            '</span></div><div class="act-time">' + timeOnly(a.at) + '</div></div>';
        }).join('') + '</div>'
          : '<div class="empty">' + icon('list') + '还没有记录，从上面开始吧</div>') +
      '</section>';

    return '<div class="page">' + hero + stats + quick + plans + activity +
      '<div class="privacy-note">' + icon('shield') +
      '<span>所有数据只保存在这台手机，不参与任何同步。只有主动点击【AI 建议】时，才会把所选区间的记录发送到你配置的 AI 接口。</span>' +
      '</div></div>';
  }

  // ------------------------------------------------------------- 体重
  function renderWeight() {
    const ws = sortedWeights();
    const latest = ws.length ? ws[ws.length - 1] : null;
    const recent = ws.filter(function (w) { return dayDiff(w.at, new Date()) <= 29; });
    const daily = dailyMean(recent);
    const first = daily.length ? daily[0].kg : null;
    const slope = daily.length > 1 ? trendSlope(daily) : 0;
    const b = latest ? bmi(latest.kg) : null;
    const change = latest && first != null ? latest.kg - first : null;
    const list = ws.slice().reverse();

    const add =
      '<section class="card">' +
        '<div class="card-title"><h3>记录体重</h3><small>每次记录都会带时间</small></div>' +
        '<form data-form="weight">' +
          '<div class="input-row">' +
            '<div class="input-wrap"><input id="weightInput" name="kg" type="number" step="0.1" inputmode="decimal" placeholder="例如 65.4" autocomplete="off"><span class="unit">kg</span></div>' +
            '<button type="submit" class="btn">' + icon('plus') + '记录</button>' +
          '</div>' +
        '</form>' +
      '</section>';

    const chart =
      '<section class="card chart-card">' +
        '<div class="chart-top"><div><h3>体重趋势</h3><p>最近 30 天 · 灰点是日均，绿线是 7 日均线</p></div>' +
        '<div class="legend"><span><i style="background:#c9d4d9"></i>日均</span><span><i style="background:#2f9e63"></i>7 日</span></div></div>' +
        (daily.length >= 2 ? '<canvas id="weightChart" height="210"></canvas>'
          : '<div class="chart-empty">还差一天记录就能看到趋势<br>同一天多次记录会取平均</div>') +
      '</section>';

    const metrics =
      '<div class="metric-grid">' +
        '<div class="metric"><span>当前体重</span><b>' + (latest ? fmtNum(latest.kg) + '<small> kg</small>' : '—') + '</b></div>' +
        '<div class="metric"><span>30 天变化</span><b class="' + (change != null && change >= 0 ? 'up' : 'down') + '">' +
          (change == null ? '—' : (change >= 0 ? '+' : '') + round1(change) + '<small> kg</small>') + '</b></div>' +
        '<div class="metric"><span>周趋势</span><b>' + (slope >= 0 ? '+' : '') + slope.toFixed(2) + '<small> kg/周</small></b></div>' +
        '<div class="metric"><span>BMI</span><b>' + (b == null ? '—' : b) + '<small>' + (b == null ? ' 填身高后计算' : '') + '</small></b></div>' +
      '</div>';

    const rows = list.length ? list.slice(0, 12).map(function (w) {
      return '<div class="row"><div class="act-ico" style="background:#ecf1ff;color:#3d6ce7">' + icon('scale') + '</div>' +
        '<div class="row-main"><b>' + fmtNum(w.kg) + ' kg</b><span>' + stampAt(w.at) + '</span></div>' +
        '<button type="button" class="row-del" data-action="delete-weight" data-id="' + w.id + '" aria-label="删除">' +
        icon('trash') + '</button></div>';
    }).join('') : '<div class="empty">' + icon('scale') + '还没有体重记录</div>';

    const history =
      '<section class="card">' +
        '<div class="card-title"><h3>最近记录</h3>' +
          (list.length > 12 ? '<button type="button" class="link" data-action="weight-history">全部 ' + list.length + ' 条</button>' : '') +
        '</div><div class="list">' + rows + '</div>' +
      '</section>';

    return '<div class="page">' + add + chart + metrics + history +
      '<div class="privacy-note">' + icon('info') +
      '<span>同一天可以记录多次，曲线会按天取平均。突然的 0.5~1.5 kg 波动很正常，重点看 7 日均线。</span></div></div>';
  }

  function drawWeightChart() {
    const canvas = $('#weightChart');
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    if (rect.width < 50) return;
    const dpr = window.devicePixelRatio || 1;
    const W = rect.width;
    const H = 210;
    canvas.width = Math.round(W * dpr);
    canvas.height = Math.round(H * dpr);
    canvas.style.height = H + 'px';
    const ctx = canvas.getContext('2d');
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, W, H);

    const ws = sortedWeights().filter(function (w) { return dayDiff(w.at, new Date()) <= 29; });
    const daily = dailyMean(ws);
    if (daily.length < 2) return;

    const ma = movingAverage(daily, 7);
    const padL = 38, padR = 12, padT = 14, padB = 26;
    let lo = Math.min.apply(null, daily.map(function (p) { return p.kg; }).concat(ma.map(function (p) { return p.kg; })));
    let hi = Math.max.apply(null, daily.map(function (p) { return p.kg; }).concat(ma.map(function (p) { return p.kg; })));
    const extra = Math.max(0.4, (hi - lo) * 0.3);
    lo -= extra; hi += extra;
    const xMax = Math.max(1, dayDiff(daily[0].key, daily[daily.length - 1].key));
    function px(key) { return padL + (W - padL - padR) * (dayDiff(daily[0].key, key) / xMax); }
    function py(v) { return padT + (H - padT - padB) * (1 - (v - lo) / (hi - lo)); }

    ctx.font = '10px -apple-system, "Noto Sans SC", sans-serif';
    ctx.textAlign = 'right';
    ctx.textBaseline = 'middle';
    for (let i = 0; i < 4; i++) {
      const v = lo + (hi - lo) * i / 3;
      const y = py(v);
      ctx.strokeStyle = '#edf2f4';
      ctx.lineWidth = 1;
      ctx.beginPath(); ctx.moveTo(padL, y); ctx.lineTo(W - padR, y); ctx.stroke();
      ctx.fillStyle = '#9aa7ae';
      ctx.fillText(v.toFixed(1), padL - 6, y);
    }

    ctx.textAlign = 'center';
    ctx.textBaseline = 'top';
    const step = Math.max(1, Math.ceil(daily.length / 5));
    for (let i = 0; i < daily.length; i += step) {
      const p = daily[i];
      ctx.fillStyle = '#9aa7ae';
      ctx.fillText(p.key.slice(5).replace('-', '/'), px(p.key), H - padB + 7);
    }

    // 日均折线 + 点
    ctx.strokeStyle = '#c9d4d9';
    ctx.lineWidth = 1.4;
    ctx.beginPath();
    daily.forEach(function (p, i) {
      if (i === 0) ctx.moveTo(px(p.key), py(p.kg));
      else ctx.lineTo(px(p.key), py(p.kg));
    });
    ctx.stroke();
    daily.forEach(function (p) {
      ctx.beginPath();
      ctx.fillStyle = '#c9d4d9';
      ctx.arc(px(p.key), py(p.kg), 2.2, 0, Math.PI * 2);
      ctx.fill();
    });

    // 7 日均线（平滑）
    if (ma.length > 1) {
      ctx.strokeStyle = '#2f9e63';
      ctx.lineWidth = 2.6;
      ctx.lineJoin = 'round';
      ctx.lineCap = 'round';
      ctx.beginPath();
      ctx.moveTo(px(ma[0].key), py(ma[0].kg));
      for (let i = 1; i < ma.length; i++) {
        const x0 = px(ma[i - 1].key), y0 = py(ma[i - 1].kg);
        const x1 = px(ma[i].key), y1 = py(ma[i].kg);
        const mx = (x0 + x1) / 2;
        ctx.bezierCurveTo(mx, y0, mx, y1, x1, y1);
      }
      ctx.stroke();
    }

    const last = daily[daily.length - 1];
    ctx.fillStyle = '#2f9e63';
    ctx.font = 'bold 11px -apple-system, "Noto Sans SC", sans-serif';
    ctx.textAlign = 'right';
    ctx.textBaseline = 'bottom';
    ctx.fillText(last.kg.toFixed(1) + ' kg', Math.min(W - padR, px(last.key) + 8), py(last.kg) - 8);
  }

  // ------------------------------------------------------------- 力量
  function todayLogs() {
    const t = dateKey(new Date());
    return state.logs.filter(function (l) { return String(l.at).slice(0, 10) === t; });
  }
  function moveCountToday(slug) {
    return todayLogs().filter(function (l) { return l.move === slug; }).length;
  }
  function renderStrength() {
    const t = dateKey(new Date());
    const todays = todayLogs();
    const keys7 = weekKeys(7);
    const weekLogs = state.logs.filter(function (l) { return inKeys(l.at, keys7); });
    const daySets = {};
    DAYS.forEach(function (d) { daySets[d.n] = 0; });
    weekLogs.forEach(function (l) {
      const mv = MOVE_BY_SLUG[l.move];
      if (mv) daySets[mv.day] += 1;
    });
    const moves = MOVES.filter(function (m) { return m.day === strengthDay; });
    const db = state.settings.dumbbell || '5';

    const dayInfo = dayMeta(strengthDay);
    const head =
      '<div class="strength-head"><div><h2>' + dayInfo.name + '训练</h2><p>' + dayInfo.sub + ' · ' + moves.length + ' 个动作</p></div>' +
      '<div class="head-actions">' +
        '<button type="button" class="btn small ghost" data-action="strength-settings">' + icon('settings') + '参数</button>' +
        '<button type="button" class="btn small ghost" data-action="strength-history">' + icon('history') + '历史</button>' +
      '</div></div>';

    const dbBar =
      '<div class="dumbbell-bar">' +
        '<div class="db-icon">' + icon('dumbbell') + '</div>' +
        '<div class="db-copy"><span>哑铃重量（单手）</span><b>' + esc(db) + ' kg</b></div>' +
        '<input id="dumbbellInput" class="db-input" type="number" step="0.5" inputmode="decimal" value="' + esc(db) + '" aria-label="哑铃重量">' +
        '<button type="button" class="btn small soft" data-action="save-dumbbell">保存</button>' +
      '</div>';

    const todayLine =
      '<div class="today-line"><span>今天 <b>' + todays.length + ' 组</b> · ' +
      Object.keys(todays.reduce(function (m, l) { m[l.move] = 1; return m; }, {})).length + ' 个动作</span>' +
      '<button type="button" class="undo" data-action="undo-last"' + (todays.length ? '' : ' disabled') + '>' +
      icon('undo') + ' 撤销上一组</button></div>';

    const tabs = '<div class="day-tabs">' + DAYS.map(function (d) {
      return '<button type="button" class="day-tab' + (strengthDay === d.n ? ' active' : '') + '" data-day="' + d.n + '">' +
        d.name + '<small>' + d.sub + ' · ' + daySets[d.n] + ' 组</small></button>';
    }).join('') + '</div>';

    const cards = '<div class="move-grid">' + moves.map(function (m) {
      const cnt = moveCountToday(m.slug);
      const reps = (state.settings.reps && state.settings.reps[m.slug]) || m.reps;
      return '<div class="move-card day-' + m.day + '" data-action="log-move" data-move="' + m.slug + '">' +
        '<div class="move-img"><img src="' + m.slug + '.png" alt="' + esc(m.cn) + '" loading="lazy"></div>' +
        '<div class="move-name">' + esc(m.cn) + '</div>' +
        '<div class="move-meta"><span>每组 <b>' + esc(reps) + '</b> 次</span>' +
        '<span class="count' + (cnt ? '' : ' zero') + '">' + (cnt ? '今天 ' + cnt + ' 组' : '点一下记录') + '</span></div>' +
        '<div class="move-foot">' +
          '<button type="button" class="reps" data-action="edit-reps" data-move="' + m.slug + '">' + esc(reps) + ' 次</button>' +
          '<button type="button" class="undo-mini" data-action="undo-move" data-move="' + m.slug + '"' + (cnt ? '' : ' disabled') + '>撤销</button>' +
        '</div>' +
      '</div>';
    }).join('') + '</div>';

    return '<div class="page">' + head + dbBar + todayLine + tabs + cards +
      '<div class="privacy-note">' + icon('info') +
      '<span>每组都会记下当时的哑铃重量和次数快照。修改重量或每组次数后，旧的记录不会被改掉。</span></div></div>';
  }

  function saveDumbbell(silent) {
    const input = $('#dumbbellInput');
    if (!input) return true;
    const v = num(input.value);
    if (v == null || v < 0 || v > 200) {
      toast('请输入 0~200 之间的重量');
      return false;
    }
    state.settings.dumbbell = String(v);
    persist();
    if (!silent) toast('哑铃重量已保存');
    return true;
  }

  function logMove(slug) {
    const mv = MOVE_BY_SLUG[slug];
    if (!mv) return;
    const input = $('#dumbbellInput');
    if (input) {
      const v = num(input.value);
      if (v != null && v >= 0 && v <= 200) state.settings.dumbbell = String(v);
    }
    const reps = String((state.settings.reps && state.settings.reps[slug]) || mv.reps);
    state.logs.push({
      id: uid(),
      at: isoNow(),
      move: slug,
      dumbbell: String(state.settings.dumbbell || ''),
      reps: reps
    });
    persist();
    vibrate();
    toast(mv.cn + ' · ' + state.settings.dumbbell + ' kg × ' + reps + ' 次');
    render();
  }

  function undoLast(move) {
    const t = dateKey(new Date());
    const candidates = state.logs.filter(function (l) {
      return String(l.at).slice(0, 10) === t && (!move || l.move === move);
    });
    if (!candidates.length) { toast('今天还没有可撤销的记录'); return; }
    const last = candidates[candidates.length - 1];
    state.logs = state.logs.filter(function (l) { return l.id !== last.id; });
    persist();
    toast('已撤销一组' + (move ? ' · ' + moveName(move) : ''));
    render();
  }

  // ------------------------------------------------------------- 有氧
  function renderCardio() {
    const records = state.cardio.slice().sort(function (a, b) { return a.at < b.at ? 1 : -1; });
    const runs = records.filter(function (c) { return c.kind === 'run'; });
    const bikes = records.filter(function (c) { return c.kind === 'bike'; });
    const runKm = runs.reduce(function (a, c) { return a + Number(c.km || 0); }, 0);
    const bikeKm = bikes.reduce(function (a, c) { return a + Number(c.km || 0); }, 0);
    const runMin = runs.reduce(function (a, c) { return a + Number(c.minutes || 0); }, 0);

    const form =
      '<section class="card">' +
        '<div class="card-title"><h3>记录一次有氧</h3><small>' + (cardioKind === 'run' ? '跑步' : '骑行') + '</small></div>' +
        '<div class="kind-row">' +
          '<button type="button" class="kind-btn' + (cardioKind === 'run' ? ' active' : '') + '" data-cardio-kind="run">' + icon('run') + '户外跑步</button>' +
          '<button type="button" class="kind-btn' + (cardioKind === 'bike' ? ' active' : '') + '" data-cardio-kind="bike">' + icon('bike') + '户外骑行</button>' +
        '</div>' +
        '<form data-form="cardio">' +
          '<div class="form-grid">' +
            '<div class="field"><label for="cardioKm">距离</label><div class="input-wrap">' +
              '<input id="cardioKm" name="km" type="number" step="0.01" inputmode="decimal" placeholder="0.00" value="' + esc(cardioDraft.km) + '"><span class="unit">km</span></div></div>' +
            '<div class="field"><label for="cardioMin">时间（分:秒）</label><div class="input-wrap">' +
              '<input id="cardioMin" name="minutes" type="text" inputmode="numeric" placeholder="32:15" value="' + esc(cardioDraft.minutes) + '"><span class="unit">分:秒</span></div></div>' +
            '<div class="field wide"><label for="cardioHr">平均心率（可不填）</label><div class="input-wrap">' +
              '<input id="cardioHr" name="hr" type="number" step="1" inputmode="numeric" placeholder="例如 150" value="' + esc(cardioDraft.hr) + '"><span class="unit">bpm</span></div></div>' +
          '</div>' +
          '<button type="submit" class="btn block" style="margin-top:12px">' + icon('plus') + '保存这次有氧</button>' +
        '</form>' +
      '</section>';

    const stats =
      '<div class="mini-stat-grid">' +
        '<div class="mini-stat"><b>' + runKm.toFixed(1) + '</b><span>跑步 km</span></div>' +
        '<div class="mini-stat"><b>' + bikeKm.toFixed(1) + '</b><span>骑行 km</span></div>' +
        '<div class="mini-stat"><b>' + (runMin > 0 ? paceText(runKm, runMin) : '—') + '</b><span>跑步均配</span></div>' +
      '</div>';

    const list = records.length ? records.slice(0, 30).map(function (c) {
      const isRun = c.kind === 'run';
      const pace = isRun ? paceText(c.km, c.minutes) : speedText(c.km, c.minutes);
      const hr = c.hr ? ' · 心率 ' + c.hr + ' bpm' : '';
      return '<div class="row"><div class="act-ico" style="background:' + (isRun ? '#eaf7f0' : '#ecf1ff') +
        ';color:' + (isRun ? '#2f9e63' : '#3d6ce7') + '">' + icon(isRun ? 'run' : 'bike') + '</div>' +
        '<div class="row-main"><b>' + (isRun ? '跑步' : '骑行') + ' ' + Number(c.km).toFixed(2) + ' km</b>' +
        '<span>' + shortStamp(c.at) + ' · ' + fmtDuration(c.minutes) + ' · ' + pace + hr + '</span></div>' +
        '<button type="button" class="row-del" data-action="delete-cardio" data-id="' + c.id + '" aria-label="删除">' + icon('trash') + '</button></div>';
    }).join('') : '<div class="empty">' + icon('run') + '还没有有氧记录</div>';

    return '<div class="page">' + form + stats +
      '<section class="card"><div class="card-title"><h3>有氧记录</h3><small>' + records.length + ' 次</small></div>' +
      '<div class="list">' + list + '</div></section>' +
      '<div class="privacy-note">' + icon('info') +
      '<span>跑步自动计算配速，骑行自动计算均速。心率可以不填；所有记录只保存在本机。</span></div></div>';
  }

  // ------------------------------------------------------------- AI
  function renderAi() {
    const reports = state.reports.slice().sort(function (a, b) { return a.at < b.at ? 1 : -1; });
    let current = null;
    if (currentReportId) current = reports.find(function (r) { return r.id === currentReportId; });
    if (!current && reports.length) current = reports[0];

    const intro =
      '<section class="card ai-intro">' +
        '<h3>' + icon('sparkles') + '让 AI 帮你看数据</h3>' +
        '<p>点击下面的按钮才会发送数据：统计区间内的每一条体重、每一组力量训练、每一次有氧，以及性别/年龄/身高。不点不发请求。</p>' +
      '</section>';

    const buttons = '<div class="ai-actions">' + [
      { kind: 'week', title: '周报', sub: '最近 7 天 · 150 字以内', icon: 'calendar', color: '#2f9e63', soft: '#eaf7f0' },
      { kind: 'month', title: '月报', sub: '最近 30 天 · 详细分析', icon: 'trend', color: '#3d6ce7', soft: '#ecf1ff' },
      { kind: 'half', title: '半年报', sub: '最近 182 天 · 长期趋势', icon: 'history', color: '#b9552a', soft: '#fff0e8' }
    ].map(function (b) {
      return '<button type="button" class="report-btn" data-action="generate" data-kind="' + b.kind + '"' +
        (generating ? ' disabled' : '') + '>' +
        '<span class="r-ico" style="background:' + b.soft + ';color:' + b.color + '">' + icon(b.icon) + '</span>' +
        '<span class="r-main"><b>' + b.title + '</b><span>' + b.sub + '</span></span>' +
        '<span class="r-arrow">' + icon('arrow') + '</span></button>';
    }).join('') + '</div>';

    const status = '<div class="ai-status ' + aiStatusClass + '">' +
      (generating ? '<span class="spinner"></span>正在生成，请稍候…' : esc(aiStatusText || '报告会存进本机历史，随时可以回看')) +
      '</div>';

    const view = current ? '<div class="report-view"><div class="rv-head"><b>' +
      ({ week: '周报', month: '月报', half: '半年报' }[current.kind] || current.kind) +
      '</b><span>' + stampAt(current.at) + '</span></div>' + esc(current.content) + '</div>' : '';

    const history = reports.length ? '<section class="card" style="margin-top:12px">' +
      '<div class="card-title"><h3>历史报告</h3><small>' + reports.length + ' 份</small></div><div class="list">' +
      reports.slice(0, 10).map(function (r) {
        return '<div class="row report-row" data-action="view-report" data-id="' + r.id + '">' +
          '<div class="act-ico" style="background:#f3f6f7;color:#0f766e">' + icon('sparkles') + '</div>' +
          '<div class="row-main"><b>' + ({ week: '周报', month: '月报', half: '半年报' }[r.kind] || r.kind) + '</b>' +
          '<span>' + stampAt(r.at) + ' · ' + String(r.content || '').length + ' 字</span></div>' +
          '<button type="button" class="row-del" data-action="delete-report" data-id="' + r.id + '" aria-label="删除报告">' + icon('trash') + '</button>' +
        '</div>';
      }).join('') + '</div></section>' : '';

    return '<div class="page">' + intro + buttons + status + view + history +
      '<div class="privacy-note">' + icon('shield') +
      '<span>AI 报告只保存在本机。所有数据不参与同步，也不会自动上传。需要修改 API Key 时，点右上角头像进入资料设置。</span></div></div>';
  }

  // ------------------------------------------------------------- AI 数据整理
  function buildDigest(days) {
    const today = new Date();
    const start = addDays(today, -(days - 1));
    const since = dateKey(start);
    const until = dateKey(today);
    const lines = [];
    lines.push('统计区间：' + since + ' 至 ' + until + '（最近 ' + days + ' 天，含首尾）');
    lines.push('用户：' + profileText() + '，目标增重增肌、长期坚持、每天至少不比前一天轻松');
    lines.push('说明：下面是区间内全部原始记录，未抽样、未截断。');
    lines.push('');

    // 体重
    const ws = sortedWeights().filter(function (w) {
      const k = String(w.at).slice(0, 10);
      return k >= since && k <= until;
    });
    lines.push('【体重】');
    if (ws.length) {
      const daily = dailyMean(ws);
      const first = daily[0].kg;
      const last = daily[daily.length - 1].kg;
      const b = bmi(last);
      lines.push('汇总：' + ws.length + ' 次记录 / ' + daily.length + ' 个记录日；' +
        '期初（' + daily[0].key + '）' + fmtNum(first) + 'kg → 期末（' + daily[daily.length - 1].key + '）' +
        fmtNum(last) + 'kg；变化 ' + (last - first >= 0 ? '+' : '') + round1(last - first) + 'kg；' +
        '趋势 ' + (trendSlope(daily) >= 0 ? '+' : '') + trendSlope(daily).toFixed(2) + 'kg/周' +
        (b ? '；期末 BMI ' + b : ''));
      lines.push('全部体重记录（时间 · 数值）：');
      ws.forEach(function (w) { lines.push('  ' + stampAt(w.at) + ' · ' + fmtNum(w.kg) + 'kg'); });
      lines.push('按天平均：' + daily.map(function (d) { return d.key + ' ' + fmtNum(d.kg) + 'kg'; }).join('；'));
    } else {
      lines.push('  ' + days + ' 天内没有体重记录');
    }
    lines.push('');

    // 力量训练
    const logs = state.logs.filter(function (l) {
      const k = String(l.at).slice(0, 10);
      return k >= since && k <= until;
    }).sort(function (a, b) { return a.at < b.at ? -1 : 1; });
    lines.push('【力量训练】');
    if (logs.length) {
      const dbDefault = state.settings.dumbbell || '';
      function weightOfLog(l) { return String(l.dumbbell || '').trim() || dbDefault; }
      function repsOfLog(l) {
        return String(l.reps || '').trim() ||
          String((state.settings.reps && state.settings.reps[l.move]) || DEFAULT_REPS[l.move] || '12');
      }
      const perDay = {}, perMove = {};
      let totalReps = 0, totalVolume = 0;
      logs.forEach(function (l) {
        const day = String(l.at).slice(0, 10);
        (perDay[day] = perDay[day] || []).push(l);
        (perMove[l.move] = perMove[l.move] || []).push(l);
        const reps = num(repsOfLog(l)), weight = num(weightOfLog(l));
        if (reps) totalReps += reps;
        if (reps && weight) totalVolume += reps * weight;
      });
      const trainedDays = Object.keys(perDay).length;
      const lastDay = Object.keys(perDay).sort().pop();
      const gap = dayDiff(lastDay, today);
      lines.push('汇总：' + trainedDays + ' 天有打卡（' + trainedDays + '/' + days + '）；共 ' +
        logs.length + ' 组 / ' + fmtNum(totalReps) + ' 次 / 总容量 ' + fmtNum(Math.round(totalVolume * 10) / 10) +
        ' kg·次；最近一次 ' + lastDay + '（距今 ' + gap + ' 天）');
      const marks = [];
      for (let i = 0; i < days; i++) {
        marks.push(perDay[dateKey(addDays(start, i))] ? '练' : '·');
      }
      lines.push('逐日打卡：' + marks.join('') + '（左旧右新）');
      lines.push('逐组全部明细（时间 · 动作 · 哑铃重量 · 每组次数）：');
      logs.forEach(function (l) {
        lines.push('  ' + stampAt(l.at) + ' · ' + moveName(l.move) + ' · ' +
          (weightOfLog(l) || '—') + 'kg · ' + (repsOfLog(l) || '—') + '次');
      });
      lines.push('按天汇总：');
      Object.keys(perDay).sort().forEach(function (day) {
        const rs = perDay[day];
        const dReps = rs.reduce(function (a, l) { return a + (num(repsOfLog(l)) || 0); }, 0);
        const dVol = rs.reduce(function (a, l) {
          return a + (num(repsOfLog(l)) || 0) * (num(weightOfLog(l)) || 0);
        }, 0);
        const moves = [];
        rs.forEach(function (l) { if (moves.indexOf(moveName(l.move)) < 0) moves.push(moveName(l.move)); });
        lines.push('  ' + day + '：' + rs.length + ' 组 / ' + fmtNum(dReps) + ' 次 / ' +
          fmtNum(Math.round(dVol * 10) / 10) + ' kg·次；动作：' + moves.join('、'));
      });
      lines.push('按动作汇总：');
      Object.keys(perMove).sort(function (a, b) {
        return perMove[a][0].at < perMove[b][0].at ? -1 : 1;
      }).forEach(function (slug) {
        const rs = perMove[slug];
        const reps = rs.reduce(function (a, l) { return a + (num(repsOfLog(l)) || 0); }, 0);
        const vol = rs.reduce(function (a, l) {
          return a + (num(repsOfLog(l)) || 0) * (num(weightOfLog(l)) || 0);
        }, 0);
        const weights = [], repsSet = [];
        rs.forEach(function (l) {
          const w = weightOfLog(l), r = repsOfLog(l);
          if (w && weights.indexOf(w) < 0) weights.push(w);
          if (r && repsSet.indexOf(r) < 0) repsSet.push(r);
        });
        weights.sort(function (a, b) { return (num(a) || 0) - (num(b) || 0); });
        repsSet.sort(function (a, b) { return (num(a) || 0) - (num(b) || 0); });
        lines.push('  ' + moveName(slug) + '：' + rs.length + ' 组 / ' + fmtNum(reps) + ' 次 / ' +
          fmtNum(Math.round(vol * 10) / 10) + ' kg·次；' + stampAt(rs[0].at) + ' 至 ' +
          stampAt(rs[rs.length - 1].at) + '；重量 ' + (weights.join('、') || '—') + 'kg；每组次数 ' +
          (repsSet.join('、') || '—'));
      });
    } else {
      lines.push('  ' + days + ' 天内一次都没练');
    }
    lines.push('');

    // 有氧
    const cardio = state.cardio.filter(function (c) {
      const k = String(c.at).slice(0, 10);
      return k >= since && k <= until;
    }).sort(function (a, b) { return a.at < b.at ? -1 : 1; });
    lines.push('【有氧】');
    if (cardio.length) {
      const runs = cardio.filter(function (c) { return c.kind === 'run'; });
      const bikes = cardio.filter(function (c) { return c.kind === 'bike'; });
      const hrs = runs.filter(function (c) { return c.hr; }).map(function (c) { return Number(c.hr); });
      const rk = runs.reduce(function (a, c) { return a + Number(c.km || 0); }, 0);
      const bk = bikes.reduce(function (a, c) { return a + Number(c.km || 0); }, 0);
      lines.push('汇总：跑步 ' + runs.length + ' 次 ' + rk.toFixed(1) + 'km' +
        (hrs.length ? '（平均心率 ' + Math.round(hrs.reduce(function (a, b) { return a + b; }, 0) / hrs.length) + 'bpm）' : '') +
        '；骑行 ' + bikes.length + ' 次 ' + bk.toFixed(1) + 'km；共 ' + cardio.length + ' 次');
      lines.push('全部有氧记录（时间 · 项目 · 距离 · 时长 · 配速/均速 · 心率）：');
      cardio.forEach(function (c) {
        let speed;
        if (c.kind === 'run') speed = paceText(c.km, c.minutes);
        else if (Number(c.minutes) > 0) speed = (Number(c.km) / (Number(c.minutes) / 60)).toFixed(1) + 'km/h';
        else speed = '—';
        lines.push('  ' + stampAt(c.at) + ' · ' + (c.kind === 'run' ? '跑步' : '骑行') + ' · ' +
          Number(c.km).toFixed(2) + 'km · ' + Math.round(c.minutes) + '分钟 · ' + speed + ' · 心率 ' + (c.hr ? c.hr + 'bpm' : '—'));
      });
    } else {
      lines.push('  ' + days + ' 天内没有有氧记录');
    }
    return lines.join('\n');
  }

  function systemPrompt(kind, label) {
    if (kind === 'week') {
      return '你是私人健身教练，给用户写' + label + '。用户目标：增重增肌、长期坚持、每天不比前一天轻松。\n\n' +
        '只写**一段话**，**不超过 150 个字（标点也算）**，不要标题、不要分点、不要换行、不要寒暄、不要复述原始数据。\n\n' +
        '内容必须包含：\n' +
        '1. 用 1~2 个最关键的数据判断这周练得够不够、体重/饮食是否达标；\n' +
        '2. 只挑最致命的 1 个问题；\n' +
        '3. 给出下周唯一重点，必须是能立刻执行的动作 + 组数×次数×重量，或每日热量/蛋白目标。\n\n' +
        '禁止"注意休息""均衡饮食"这类空话；没有数据就直说"本周没有记录"，不要编造。';
    }
    const half = kind === 'half';
    const plan = half ? '给出未来 4 周的具体安排，并按月份对比这半年的长期变化' : '给出未来 2 周的具体安排';
    const floor = half ? 1000 : 600;
    return '你是私人健身教练，给用户写' + label + '。用户目标：增重增肌、长期坚持、每天不比前一天轻松。\n\n' +
      '这次要**尽可能详细**：篇幅不设上限，通常不少于 ' + floor + ' 字；宁可长而具体，不要短而空泛。每个判断都必须引用数据中的日期、动作、组数、次数、重量、体重或心率；数据里没有的不要编造，缺数据就写"数据不足"。\n\n' +
      '按下面结构输出（保留短标题）：\n' +
      '一、总体结论：这' + label + '练够了还是没练够、吃够了还是没吃够，用数据说明。\n' +
      '二、体重与饮食：期初→期末、变化速度、日/周波动、BMI 趋势；结合增重目标判断吃得够不够。\n' +
      '三、力量训练：**逐个动作**分析训练频率、组数、每组次数、重量变化、总容量和进步/停滞原因；明确指出哪个动作该加重量、哪个该加次数、哪个该减量或换动作。\n' +
      '四、有氧：次数、距离、时长、配速、心率，判断是否影响增肌恢复。\n' +
      '五、问题与风险：按严重程度列出，必须有数据支撑。\n' +
      '六、下一阶段计划：' + plan + '，逐动作写清组数×次数×重量；饮食给出每日热量/蛋白目标。\n\n' +
      '硬性要求：不要泛泛而谈"均衡饮食""注意休息"；不要只复述原始明细，要把明细归纳成趋势和结论，但保留关键数字。';
  }

  function limitWeek(text, limit) {
    limit = limit || 150;
    let t = String(text || '').trim().replace(/\*\*|##|`/g, '').replace(/\s+/g, ' ');
    if (t.length <= limit) return t;
    const head = t.slice(0, limit);
    let cut = -1;
    '。！？；!?;'.split('').forEach(function (ch) {
      const i = head.lastIndexOf(ch);
      if (i > cut) cut = i;
    });
    if (cut >= Math.floor(limit * 3 / 4)) return head.slice(0, cut + 1);
    return head.slice(0, limit - 1).replace(/[，,、\s]+$/, '') + '…';
  }

  function isDeepSeek(api) {
    const model = String(api.model || '').toLowerCase();
    const base = String(api.baseUrl || '').toLowerCase();
    return model.indexOf('deepseek') === 0 || base.indexOf('deepseek') >= 0;
  }

  // ------------------------------------------------------------- 网络（仅 AI 按钮调用）
  window.__apiCalls = 0;
  const pendingRequests = {};
  function nativePost(url, headers, body, timeoutSec) {
    window.__apiCalls += 1;
    return new Promise(function (resolve, reject) {
      const id = 'r' + uid();
      pendingRequests[id] = { resolve: resolve, reject: reject };
      const timer = setTimeout(function () {
        if (pendingRequests[id]) {
          delete pendingRequests[id];
          reject(new Error('请求超时，请检查网络或稍后重试'));
        }
      }, (timeoutSec + 20) * 1000);
      pendingRequests[id].timer = timer;
      try {
        if (window.Android && Android.post) {
          Android.post(url, JSON.stringify(headers || {}), body, id, timeoutSec);
          return;
        }
        // 浏览器预览用（Android App 内不会走这里）
        fetch(url, { method: 'POST', headers: headers || {}, body: body }).then(function (resp) {
          return resp.text().then(function (text) {
            if (!resp.ok) throw new Error('HTTP ' + resp.status + '：' + text.slice(0, 160));
            return text;
          });
        }).then(function (text) {
          if (!pendingRequests[id]) return;
          clearTimeout(pendingRequests[id].timer);
          delete pendingRequests[id];
          resolve(JSON.parse(text));
        }).catch(function (err) {
          if (!pendingRequests[id]) return;
          clearTimeout(pendingRequests[id].timer);
          delete pendingRequests[id];
          reject(err);
        });
      } catch (err) {
        clearTimeout(timer);
        delete pendingRequests[id];
        reject(err);
      }
    });
  }

  window.__nativeHttp = function (id, status, text) {
    const pending = pendingRequests[id];
    if (!pending) return;
    clearTimeout(pending.timer);
    delete pendingRequests[id];
    if (status >= 200 && status < 300) {
      try { pending.resolve(JSON.parse(text)); }
      catch (e) { pending.reject(new Error('AI 返回内容无法解析')); }
      return;
    }
    let detail = String(text || '').slice(0, 180);
    try {
      const obj = JSON.parse(text);
      detail = (obj.error && (obj.error.message || obj.error.code)) || detail;
    } catch (e) { /* ignore */ }
    pending.reject(new Error(status ? 'HTTP ' + status + '：' + detail : detail || '网络请求失败'));
  };

  async function generateReport(kind) {
    if (generating) return;
    if (!state.api.apiKey) {
      toast('请先在资料设置里填写 API Key');
      showProfile('api');
      return;
    }
    const labels = { week: '周报', month: '月报', half: '半年报' };
    const days = { week: 7, month: 30, half: 182 }[kind];
    const maxTokens = { week: 500, month: 4096, half: 8192 }[kind];
    const timeout = { week: 120, month: 300, half: 600 }[kind];
    generating = true;
    aiStatusText = '正在整理数据并请求 AI…';
    aiStatusClass = '';
    render();
    try {
      const digest = buildDigest(days);
      const payload = {
        model: state.api.model || 'deepseek-flash',
        messages: [
          { role: 'system', content: systemPrompt(kind, labels[kind]) },
          { role: 'user', content: digest }
        ],
        temperature: 0.4,
        stream: false,
        max_tokens: maxTokens
      };
      if (isDeepSeek(state.api)) payload.thinking = { type: 'disabled' };
      const url = String(state.api.baseUrl || 'https://api.deepseek.com').replace(/\/+$/, '') + '/chat/completions';
      const headers = {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer ' + state.api.apiKey
      };
      const data = await nativePost(url, headers, JSON.stringify(payload), timeout);
      const choice = (data.choices && data.choices[0]) || {};
      let text = String((choice.message && choice.message.content) || '').trim();
      if (!text) {
        if (choice.finish_reason === 'length') throw new Error('AI 输出被截断（max_tokens 用完），请重试');
        throw new Error('AI 没有返回内容');
      }
      if (kind === 'week') text = limitWeek(text, 150);
      const report = { id: uid(), at: isoNow(), kind: kind, content: text };
      state.reports.unshift(report);
      persist();
      currentReportId = report.id;
      aiStatusText = labels[kind] + '已生成 · ' + shortStamp(report.at);
      aiStatusClass = 'ok';
      toast(labels[kind] + '已生成');
    } catch (err) {
      aiStatusText = '生成失败：' + String(err && err.message || err).slice(0, 120);
      aiStatusClass = 'error';
      toast('生成失败');
    } finally {
      generating = false;
      render();
    }
  }

  // ------------------------------------------------------------- 弹窗
  function openSheet(title, body, actions, onMount) {
    closeSheet();
    const root = $('#modal-root');
    root.innerHTML =
      '<div class="modal-backdrop">' +
        '<div class="sheet" role="dialog" aria-modal="true" aria-label="' + esc(title) + '">' +
          '<div class="sheet-grip"></div>' +
          '<div class="sheet-head"><h2>' + esc(title) + '</h2>' +
            '<button type="button" class="close" data-close="1" aria-label="关闭">' + icon('close') + '</button>' +
          '</div>' +
          '<div class="sheet-body">' + body + '</div>' +
          (actions ? '<div class="sheet-actions">' + actions + '</div>' : '') +
        '</div>' +
      '</div>';
    const backdrop = $('.modal-backdrop', root);
    backdrop.addEventListener('click', function (e) {
      if (e.target === backdrop || e.target.closest('[data-close]')) closeSheet();
    });
    if (onMount) onMount(root);
  }
  function closeSheet() {
    const root = $('#modal-root');
    if (root) root.innerHTML = '';
  }

  function confirmDialog(title, text, okLabel, danger) {
    return new Promise(function (resolve) {
      openSheet(title,
        '<p class="confirm-text">' + esc(text) + '</p>',
        '<button type="button" class="btn ghost" data-close="1">取消</button>' +
        '<button type="button" class="btn' + (danger ? ' danger' : '') + '" id="confirmOk">' + esc(okLabel || '确定') + '</button>',
        function (root) {
          $('#confirmOk', root).addEventListener('click', function () {
            closeSheet();
            resolve(true);
          });
          const backdrop = $('.modal-backdrop', root);
          const obs = new MutationObserver(function () {
            if (!document.body.contains(backdrop)) { obs.disconnect(); resolve(false); }
          });
          obs.observe(root, { childList: true });
        });
    });
  }

  function showProfile(section) {
    const p = state.profile;
    const api = state.api;
    const body =
      '<div class="modal-card">' +
        '<h3>个人资料</h3><p>只用于计算 BMI 和生成 AI 报告，保存在本机。</p>' +
        '<div class="field"><label for="profileSex">性别</label>' +
          '<div class="input-wrap"><input id="profileSex" type="text" maxlength="4" placeholder="男 / 女" value="' + esc(p.sex || '') + '"></div>' +
          '<div class="chips"><button type="button" class="chip" data-fill-sex="男">男</button>' +
          '<button type="button" class="chip" data-fill-sex="女">女</button></div></div>' +
        '<div class="field"><label for="profileAge">年龄</label>' +
          '<div class="input-wrap"><input id="profileAge" type="number" min="1" max="120" inputmode="numeric" placeholder="例如 55" value="' + (p.age == null ? '' : esc(p.age)) + '"><span class="unit">岁</span></div></div>' +
        '<div class="field"><label for="profileHeight">身高</label>' +
          '<div class="input-wrap"><input id="profileHeight" type="number" min="80" max="250" step="0.5" inputmode="decimal" placeholder="例如 170" value="' + (p.height == null ? '' : esc(p.height)) + '"><span class="unit">cm</span></div></div>' +
        '<button type="button" class="btn block" style="margin-top:14px" data-action="save-profile">保存资料</button>' +
      '</div>' +
      '<div class="modal-card">' +
        '<h3>AI 接口</h3><p>默认已经填好当前使用的 Key。只有点 AI 报告时才会用到。</p>' +
        '<div class="field"><label for="apiKey">API Key</label>' +
          '<div class="input-wrap"><input id="apiKey" type="password" autocomplete="off" spellcheck="false" value="' + esc(api.apiKey || '') + '">' +
          '<button type="button" class="suffix-btn" data-action="toggle-key">显示</button></div></div>' +
        '<div class="field"><label for="apiBase">Base URL</label>' +
          '<div class="input-wrap"><input id="apiBase" type="text" autocomplete="off" value="' + esc(api.baseUrl || '') + '"></div></div>' +
        '<div class="field"><label for="apiModel">模型</label>' +
          '<div class="input-wrap"><input id="apiModel" type="text" autocomplete="off" value="' + esc(api.model || '') + '"></div></div>' +
        '<button type="button" class="btn block" style="margin-top:14px" data-action="save-api">保存 AI 设置</button>' +
      '</div>' +
      '<div class="modal-card"><h3>关于数据</h3><p>所有体重、训练、有氧和报告只保存在这台手机，不使用任何同步。清除应用数据会一并删除。版本 ' + APP_VERSION + '。</p></div>';
    openSheet('资料与设置', body, '', function (root) {
      if (section === 'api') {
        setTimeout(function () { const el = $('#apiKey', root); if (el) el.focus(); }, 180);
      }
    });
  }

  function showWeightHistory() {
    const list = sortedWeights().slice().reverse();
    const body = list.length ? '<div class="modal-card" style="padding:4px 14px"><div class="list">' +
      list.map(function (w) {
        return '<div class="row"><div class="row-main"><b>' + fmtNum(w.kg) + ' kg</b><span>' + stampAt(w.at) + '</span></div>' +
          '<button type="button" class="row-del" data-action="delete-weight" data-id="' + w.id + '">' + icon('trash') + '</button></div>';
      }).join('') + '</div></div>' : '<div class="modal-card"><p>还没有体重记录。</p></div>';
    openSheet('全部体重记录', body);
  }

  function showStrengthHistory() {
    const logs = state.logs.slice().sort(function (a, b) { return a.at < b.at ? 1 : -1; });
    if (!logs.length) {
      openSheet('力量训练历史', '<div class="modal-card"><p>还没有力量训练记录。</p></div>');
      return;
    }
    const groups = {};
    logs.forEach(function (l) {
      const day = String(l.at).slice(0, 10);
      (groups[day] = groups[day] || []).push(l);
    });
    const body = Object.keys(groups).sort().reverse().map(function (day) {
      const rs = groups[day];
      const byMove = {};
      rs.forEach(function (l) { (byMove[l.move] = byMove[l.move] || []).push(l); });
      return '<div class="modal-card history-group"><div class="history-date">' + day +
        '<span>' + rs.length + ' 组</span></div>' +
        Object.keys(byMove).map(function (slug) {
          const sets = byMove[slug];
          const last = sets[sets.length - 1];
          return '<div class="history-item"><div class="hi-main"><b>' + moveName(slug) + '</b>' +
            '<span>' + weightOf(last) + ' kg · ' + repsOf(last) + ' 次/组</span></div>' +
            '<div class="hi-side">' + sets.length + ' 组</div></div>';
        }).join('') + '</div>';
    }).join('');
    openSheet('力量训练历史', body);
  }

  function showStrengthSettings() {
    const reps = state.settings.reps || {};
    const rows = MOVES.map(function (m) {
      return '<div class="reps-row"><span>' + m.cn + '</span>' +
        '<input class="reps-input" data-move="' + m.slug + '" type="number" min="1" max="100" inputmode="numeric" value="' +
        esc(reps[m.slug] || m.reps) + '"><span style="flex:none;color:#7d8b97;font-size:12px">次</span></div>';
    }).join('');
    const body = '<div class="modal-card"><h3>默认哑铃重量</h3><p>单手重量，单位 kg。点动作卡片时使用。</p>' +
      '<div class="field"><div class="input-wrap"><input id="setDumbbell" type="number" step="0.5" inputmode="decimal" value="' +
      esc(state.settings.dumbbell || '5') + '"><span class="unit">kg / 手</span></div></div></div>' +
      '<div class="modal-card"><h3>每个动作的每组次数</h3><p>只影响之后新记录的组，旧记录保留当时的快照。</p>' +
      '<div class="reps-list">' + rows + '</div></div>';
    openSheet('训练参数', body,
      '<button type="button" class="btn ghost" data-close="1">取消</button>' +
      '<button type="button" class="btn" data-action="save-strength-settings">保存</button>');
  }

  function showEditReps(slug) {
    const m = MOVE_BY_SLUG[slug];
    if (!m) return;
    const cur = (state.settings.reps && state.settings.reps[slug]) || m.reps;
    const body = '<div class="modal-card"><h3>' + m.cn + '</h3><p>设置每组次数。之后点卡片会按这个次数记录。</p>' +
      '<div class="field"><div class="input-wrap"><input id="oneReps" type="number" min="1" max="100" inputmode="numeric" value="' +
      esc(cur) + '"><span class="unit">次 / 组</span></div></div></div>';
    openSheet('每组次数', body,
      '<button type="button" class="btn ghost" data-close="1">取消</button>' +
      '<button type="button" class="btn" data-action="save-move-reps" data-move="' + slug + '">保存</button>');
  }

  // ------------------------------------------------------------- 交互
  function saveProfile() {
    const sex = String(($('#profileSex') || {}).value || '').trim();
    const ageRaw = String(($('#profileAge') || {}).value || '').trim();
    const heightRaw = String(($('#profileHeight') || {}).value || '').trim();
    const age = num(ageRaw);
    const height = num(heightRaw);
    if (ageRaw && (age == null || age < 1 || age > 120)) { toast('年龄请填 1~120'); return; }
    if (heightRaw && (height == null || height < 80 || height > 250)) { toast('身高请填 80~250 cm'); return; }
    state.profile.sex = sex;
    state.profile.age = ageRaw ? Math.round(age) : null;
    state.profile.height = heightRaw ? Math.round(height * 10) / 10 : null;
    persist();
    closeSheet();
    toast('资料已保存');
    render();
  }

  function saveApi() {
    const key = String(($('#apiKey') || {}).value || '').trim();
    const base = String(($('#apiBase') || {}).value || '').trim() || 'https://api.deepseek.com';
    const model = String(($('#apiModel') || {}).value || '').trim() || 'deepseek-flash';
    state.api.apiKey = key;
    state.api.baseUrl = base;
    state.api.model = model;
    persist();
    closeSheet();
    toast('AI 设置已保存');
    render();
  }

  function saveStrengthSettings() {
    const db = num(($('#setDumbbell') || {}).value);
    if (db == null || db < 0 || db > 200) { toast('哑铃重量请填 0~200'); return; }
    state.settings.dumbbell = String(db);
    state.settings.reps = state.settings.reps || {};
    $$('.reps-input').forEach(function (el) {
      const v = num(el.value);
      const m = MOVE_BY_SLUG[el.getAttribute('data-move')];
      if (m) state.settings.reps[m.slug] = v != null && v >= 1 && v <= 100 ? String(Math.round(v)) : String(m.reps);
    });
    persist();
    closeSheet();
    toast('训练参数已保存');
    render();
  }

  function saveMoveReps(slug) {
    const v = num(($('#oneReps') || {}).value);
    if (v == null || v < 1 || v > 100) { toast('每组次数请填 1~100'); return; }
    state.settings.reps = state.settings.reps || {};
    state.settings.reps[slug] = String(Math.round(v));
    persist();
    closeSheet();
    toast('每组次数已保存');
    render();
  }

  function handleForm(form) {
    const type = form.getAttribute('data-form');
    if (type === 'weight') {
      const kg = num(form.kg.value);
      if (kg == null || kg < 25 || kg > 200) { toast('体重请填 25~200 kg'); return; }
      state.weights.push({ id: uid(), at: isoNow(), kg: Math.round(kg * 10) / 10 });
      persist();
      toast('已记录 ' + fmtNum(kg) + ' kg');
      render();
      setTimeout(function () {
        const el = $('#weightInput'); if (el) el.focus();
      }, 30);
      return;
    }
    if (type === 'cardio') {
      const km = num(form.km.value);
      const sec = parseDuration(form.minutes.value);
      const hr = num(form.hr.value);
      if (km == null || km <= 0 || km > 500) { toast('距离请填 0.01~500 km'); return; }
      if (sec == null || sec <= 0 || sec > 86400) { toast('时间请按 分:秒 填，例如 32:15'); return; }
      if (form.hr.value && (hr == null || hr < 40 || hr > 250)) { toast('心率请填 40~250，或留空'); return; }
      state.cardio.push({
        id: uid(), at: isoNow(), kind: cardioKind,
        km: Math.round(km * 100) / 100,
        minutes: Math.round(sec / 60 * 1000) / 1000,   // 保留到秒
        hr: hr ? Math.round(hr) : 0
      });
      cardioDraft = { km: '', minutes: '', hr: '' };
      persist();
      toast((cardioKind === 'run' ? '跑步' : '骑行') + '已记录');
      render();
    }
  }

  function handleAction(action, el) {
    const id = el.getAttribute('data-id');
    if (action === 'profile') { showProfile(); return; }
    if (action === 'weight-history') { showWeightHistory(); return; }
    if (action === 'strength-history') { showStrengthHistory(); return; }
    if (action === 'strength-settings') { showStrengthSettings(); return; }
    if (action === 'save-dumbbell') { saveDumbbell(false); return; }
    if (action === 'log-move') { logMove(el.getAttribute('data-move')); return; }
    if (action === 'undo-last') { undoLast(); return; }
    if (action === 'undo-move') { undoLast(el.getAttribute('data-move')); return; }
    if (action === 'edit-reps') { showEditReps(el.getAttribute('data-move')); return; }
    if (action === 'save-strength-settings') { saveStrengthSettings(); return; }
    if (action === 'save-move-reps') { saveMoveReps(el.getAttribute('data-move')); return; }
    if (action === 'save-profile') { saveProfile(); return; }
    if (action === 'save-api') { saveApi(); return; }
    if (action === 'toggle-key') {
      const input = $('#apiKey');
      if (input) {
        input.type = input.type === 'password' ? 'text' : 'password';
        el.textContent = input.type === 'password' ? '显示' : '隐藏';
      }
      return;
    }
    if (action === 'delete-weight') {
      const w = state.weights.find(function (x) { return x.id === id; });
      if (!w) return;
      confirmDialog('删除体重记录', '确定删除 ' + fmtNum(w.kg) + ' kg（' + stampAt(w.at) + '）吗？', '删除', true).then(function (ok) {
        if (!ok) return;
        state.weights = state.weights.filter(function (x) { return x.id !== id; });
        persist(); closeSheet(); toast('已删除'); render();
      });
      return;
    }
    if (action === 'delete-cardio') {
      const c = state.cardio.find(function (x) { return x.id === id; });
      if (!c) return;
      confirmDialog('删除有氧记录', '确定删除这条 ' + (c.kind === 'run' ? '跑步' : '骑行') + '记录吗？', '删除', true).then(function (ok) {
        if (!ok) return;
        state.cardio = state.cardio.filter(function (x) { return x.id !== id; });
        persist(); toast('已删除'); render();
      });
      return;
    }
    if (action === 'generate') { generateReport(el.getAttribute('data-kind')); return; }
    if (action === 'view-report') {
      currentReportId = id;
      aiStatusText = '';
      aiStatusClass = '';
      render();
      return;
    }
    if (action === 'delete-report') {
      const r = state.reports.find(function (x) { return x.id === id; });
      if (!r) return;
      confirmDialog('删除 AI 报告', '确定删除这份 ' + ({ week: '周报', month: '月报', half: '半年报' }[r.kind] || r.kind) + '（' + stampAt(r.at) + '）吗？', '删除', true).then(function (ok) {
        if (!ok) return;
        state.reports = state.reports.filter(function (x) { return x.id !== id; });
        if (currentReportId === id) currentReportId = null;
        persist(); closeSheet(); toast('已删除'); render();
      });
      return;
    }
    if (action === 'exit-selftest') { location.href = 'index.html'; return; }
  }

  // ------------------------------------------------------------- 自检
  function runSelfTest() {
    const backup = JSON.stringify(state);
    const today = new Date();
    const d0 = dateKey(today);
    const d1 = dateKey(addDays(today, -1));
    const d3 = dateKey(addDays(today, -3));
    state = normalizeState({
      profile: { sex: '男', age: 55, height: 174 },
      settings: { dumbbell: '5', reps: { 'bench-press': 12 } },
      weights: [
        { id: 'w1', at: d3 + 'T08:00:00', kg: 58.7 },
        { id: 'w2', at: d1 + 'T09:00:00', kg: 59.15 },
        { id: 'w3', at: d0 + 'T17:15:31', kg: 58.95 }
      ],
      logs: [
        { id: 'l1', at: d1 + 'T10:00:00', move: 'bench-press', dumbbell: '5', reps: '12' },
        { id: 'l2', at: d0 + 'T10:05:00', move: 'bench-press', dumbbell: '7.5', reps: '10' },
        { id: 'l3', at: d0 + 'T10:08:00', move: 'goblet-squat', dumbbell: '5', reps: '12' }
      ],
      cardio: [
        { id: 'c1', at: d0 + 'T18:00:00', kind: 'run', km: 5, minutes: 30, hr: 150 }
      ],
      reports: []
    });
    window.__apiCalls = 0;
    const tests = [];
    function test(name, fn) {
      try { fn(); tests.push({ ok: true, name: name }); }
      catch (e) { tests.push({ ok: false, name: name, msg: String(e && e.message || e) }); }
    }
    const digest = buildDigest(7);
    test('周报数据包含逐组明细', function () {
      if (digest.indexOf('哑铃卧推') < 0) throw new Error('缺少动作名');
      if (digest.indexOf('7.5kg') < 0) throw new Error('缺少重量');
      if (digest.indexOf('10次') < 0) throw new Error('缺少次数');
      if (digest.indexOf('5.00km') < 0) throw new Error('缺少有氧距离');
      if (digest.indexOf('150bpm') < 0) throw new Error('缺少心率');
    });
    test('统计区间含首尾', function () {
      if (digest.indexOf(dateKey(addDays(today, -6)) + ' 至 ' + d0) < 0) throw new Error('区间不对');
    });
    test('周报提示词限制 150 字', function () {
      if (systemPrompt('week', '周报').indexOf('150') < 0) throw new Error('提示词缺少 150');
    });
    test('月报提示词逐个动作', function () {
      if (systemPrompt('month', '月报').indexOf('逐个动作') < 0) throw new Error('缺少逐个动作');
    });
    test('半年报提示词按月份', function () {
      if (systemPrompt('half', '半年报').indexOf('按月份') < 0) throw new Error('缺少按月份');
    });
    test('周报超长会截断到 150 字内', function () {
      const s = limitWeek('练得很好。'.repeat(80), 150);
      if (s.length > 150) throw new Error('长度 ' + s.length);
    });
    test('配速计算', function () {
      if (paceText(5, 30) !== '6\'00"/km') throw new Error(paceText(5, 30));
    });
    test('BMI 计算', function () {
      if (bmi(60) !== 19.8) throw new Error(String(bmi(60)));
    });
    test('日期计算兼容字符串和 Date', function () {
      if (dateKey(d0) !== d0) throw new Error('dateKey 字符串失败');
      if (dayDiff(d3, d0) !== 3) throw new Error('字符串天数差 ' + dayDiff(d3, d0));
      if (dayDiff(d1, today) !== 1) throw new Error('混合天数差 ' + dayDiff(d1, today));
    });
    test('DeepSeek 参数识别', function () {
      if (!isDeepSeek({ model: 'deepseek-flash', baseUrl: 'https://api.deepseek.com' })) throw new Error('官方未识别');
      if (isDeepSeek({ model: 'gpt-4o', baseUrl: 'https://api.openai.com' })) throw new Error('误判其它模型');
    });
    test('空数据提示', function () {
      const keep = state;
      state = normalizeState({ profile: { sex: '男' } });
      const empty = buildDigest(7);
      state = keep;
      if (empty.indexOf('没有体重记录') < 0) throw new Error('缺少空数据提示');
    });
    test('首页可渲染', function () {
      const html = renderHome();
      if (html.indexOf('今天练什么') < 0) throw new Error('缺少训练计划');
      if (html.indexOf('本周训练') < 0) throw new Error('缺少本周统计');
    });
    test('体重页可渲染', function () {
      const html = renderWeight();
      if (html.indexOf('体重趋势') < 0) throw new Error('缺少体重趋势');
      if (html.indexOf('data-form="weight"') < 0) throw new Error('缺少体重输入');
    });
    test('力量页可渲染', function () {
      const html = renderStrength();
      if (html.indexOf('哑铃卧推') < 0) throw new Error('缺少推日动作');
      if (html.indexOf('data-action="log-move"') < 0) throw new Error('缺少记录动作');
    });
    test('有氧页可渲染', function () {
      const html = renderCardio();
      if (html.indexOf('记录一次有氧') < 0) throw new Error('缺少有氧表单');
      if (html.indexOf('data-cardio-kind="run"') < 0) throw new Error('缺少跑步切换');
    });
    test('有氧表单不横向溢出', function () {
      const keepHtml = document.getElementById('main').innerHTML;
      document.getElementById('main').innerHTML = renderCardio();
      const grid = $('.form-grid');
      const card = grid ? grid.closest('.card') : null;
      if (!grid || !card) { document.getElementById('main').innerHTML = keepHtml; throw new Error('缺少表单'); }
      const g = grid.getBoundingClientRect();
      const c = card.getBoundingClientRect();
      document.getElementById('main').innerHTML = keepHtml;
      if (g.right > c.right + 1 || g.left < c.left - 1) throw new Error('表单宽度溢出');
    });
    test('趋势图绘制不报错', function () {
      const keepHtml = document.getElementById('main').innerHTML;
      document.getElementById('main').innerHTML = renderWeight();
      drawWeightChart();
      document.getElementById('main').innerHTML = keepHtml;
    });
    test('AI 页可渲染历史报告', function () {
      const keepReports = state.reports;
      const keepId = currentReportId;
      state.reports = [{ id: 'selftest-report', at: d0 + 'T20:00:00', kind: 'week', content: '测试报告内容' }];
      currentReportId = 'selftest-report';
      const html = renderAi();
      state.reports = keepReports;
      currentReportId = keepId;
      if (html.indexOf('测试报告内容') < 0) throw new Error('缺少报告正文');
      if (html.indexOf('data-action="generate"') < 0) throw new Error('缺少三个报告按钮');
    });
    test('资料页有性别年龄身高输入', function () {
      showProfile();
      const sex = $('#profileSex');
      const age = $('#profileAge');
      const height = $('#profileHeight');
      const ageValue = age ? age.value : '';
      const heightValue = height ? height.value : '';
      closeSheet();
      if (!sex || !age || !height) throw new Error('缺少资料输入框');
      if (ageValue !== '55' || heightValue !== '174') throw new Error('资料回填不正确');
    });
    test('测试期间没有调用 API', function () {
      if (window.__apiCalls !== 0) throw new Error('API 调用次数 ' + window.__apiCalls);
    });
    state = normalizeState(JSON.parse(backup));

    const passed = tests.filter(function (t) { return t.ok; }).length;
    const failed = tests.length - passed;
    document.getElementById('topbar').style.display = 'none';
    document.getElementById('tabbar').style.display = 'none';
    document.getElementById('main').innerHTML =
      '<div class="selftest"><h1>本地功能自检</h1>' +
      '<p class="sub">不联网、不调用 API · ' + new Date().toLocaleString('zh-CN') + '</p>' +
      '<div class="test-block">' + tests.map(function (t) {
        return '<div class="test-line"><span class="mark ' + (t.ok ? 'ok' : 'bad') + '">' +
          (t.ok ? '✓' : '✕') + '</span><div>' + esc(t.name) +
          (t.msg ? '<code>' + esc(t.msg) + '</code>' : '') + '</div></div>';
      }).join('') + '</div>' +
      '<div class="test-summary ' + (failed ? 'bad' : '') + '">' +
      (failed ? failed + ' 项失败，请检查' : '全部 ' + passed + ' 项通过') +
      ' · API 调用 ' + window.__apiCalls + ' 次</div>' +
      '<button type="button" class="btn block" style="margin-top:14px" data-action="exit-selftest">返回应用</button>' +
      '</div>';
  }

  // ------------------------------------------------------------- 导航
  function setTab(tab) {
    if (!TABS.some(function (t) { return t.id === tab; })) return;
    currentTab = tab;
    closeSheet();
    render();
    window.scrollTo(0, 0);
    if (tab === 'weight') requestAnimationFrame(drawWeightChart);
  }

  function render() {
    renderTopbar();
    renderTabbar();
    const main = $('#main');
    if (currentTab === 'home') main.innerHTML = renderHome();
    else if (currentTab === 'weight') main.innerHTML = renderWeight();
    else if (currentTab === 'strength') main.innerHTML = renderStrength();
    else if (currentTab === 'cardio') main.innerHTML = renderCardio();
    else if (currentTab === 'ai') main.innerHTML = renderAi();
    if (currentTab === 'weight') requestAnimationFrame(drawWeightChart);
  }

  // ------------------------------------------------------------- 事件
  document.addEventListener('click', function (e) {
    const tab = e.target.closest('[data-tab]');
    if (tab) { setTab(tab.getAttribute('data-tab')); return; }
    const plan = e.target.closest('[data-plan]');
    if (plan) {
      strengthDay = Number(plan.getAttribute('data-plan')) || 1;
      setTab('strength');
      return;
    }
    const day = e.target.closest('[data-day]');
    if (day) {
      strengthDay = Number(day.getAttribute('data-day')) || 1;
      render();
      return;
    }
    const kind = e.target.closest('[data-cardio-kind]');
    if (kind) {
      const form = $('[data-form="cardio"]');
      if (form) {
        cardioDraft = { km: form.km.value, minutes: form.minutes.value, hr: form.hr.value };
      }
      cardioKind = kind.getAttribute('data-cardio-kind');
      render();
      return;
    }
    const fillSex = e.target.closest('[data-fill-sex]');
    if (fillSex) {
      const input = $('#profileSex');
      if (input) input.value = fillSex.getAttribute('data-fill-sex');
      return;
    }
    const el = e.target.closest('[data-action]');
    if (el) {
      e.preventDefault();
      handleAction(el.getAttribute('data-action'), el);
    }
  });

  document.addEventListener('submit', function (e) {
    const form = e.target.closest('[data-form]');
    if (form) { e.preventDefault(); handleForm(form); }
  });

  document.addEventListener('keydown', function (e) {
    if (e.key !== 'Enter') return;
    if (e.target.id === 'weightInput') {
      e.preventDefault();
      const form = e.target.closest('form');
      if (form) handleForm(form);
    } else if (e.target.id === 'dumbbellInput') {
      e.preventDefault();
      saveDumbbell(false);
    }
  });

  window.addEventListener('resize', function () {
    if (currentTab === 'weight') requestAnimationFrame(drawWeightChart);
  });

  window.__androidBack = function () {
    if ($('.modal-backdrop')) { closeSheet(); return true; }
    if (currentTab !== 'home') { setTab('home'); return true; }
    return false;
  };

  window.addEventListener('error', function (e) {
    const msg = '页面脚本错误：' + (e.message || e.error || '未知错误');
    document.body.insertAdjacentHTML('afterbegin',
      '<div style="position:fixed;left:12px;right:12px;top:12px;z-index:999;padding:12px;' +
      'border-radius:12px;background:#d95b5b;color:#fff;font:13px/1.5 sans-serif">' +
      esc(msg) + '</div>');
  });
  window.addEventListener('unhandledrejection', function (e) {
    const msg = '未处理错误：' + (e.reason && e.reason.message || e.reason || '未知');
    document.body.insertAdjacentHTML('afterbegin',
      '<div style="position:fixed;left:12px;right:12px;top:12px;z-index:999;padding:12px;' +
      'border-radius:12px;background:#d95b5b;color:#fff;font:13px/1.5 sans-serif">' +
      esc(msg) + '</div>');
  });

  // ------------------------------------------------------------- 启动
  const params = new URLSearchParams(location.search);
  if (params.get('selftest') === '1') {
    runSelfTest();
  } else {
    render();
    if (currentTab === 'weight') requestAnimationFrame(drawWeightChart);
  }
})();
