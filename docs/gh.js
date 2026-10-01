/* GitHub 私有仓库同步 —— 与 app/ghsync.py 用同一套协议。
 *
 * 读:  GET  /repos/{owner}/{repo}/contents/{path}   拿到 base64 内容与 sha
 * 写:  PUT  /repos/{owner}/{repo}/contents/{path}   必须带 sha
 * sha 是乐观锁: 期间被电脑端改过会返回 409, 此时重新拉取合并再提交。
 * 因为合并满足交换律, 重试一定会收敛。
 */

import { merge, emptyState } from './core.js';

const API = 'https://api.github.com';
const CFG_KEY = 'trilingo.sync.cfg';
const STATE_KEY = 'trilingo.state';
const PENDING_KEY = 'trilingo.pending';

/* ------------------------------------------------------------------ 本地存储 */

export function loadConfig() {
  try {
    const raw = localStorage.getItem(CFG_KEY);
    return raw ? JSON.parse(raw) : { token: '', owner: '', repo: 'Trilingo-data', path: 'state.json', branch: 'main' };
  } catch {
    return { token: '', owner: '', repo: 'Trilingo-data', path: 'state.json', branch: 'main' };
  }
}

export function saveConfig(cfg) {
  localStorage.setItem(CFG_KEY, JSON.stringify(cfg));
}

export const isConfigured = () => {
  const c = loadConfig();
  return !!(c.token && c.owner && c.repo);
};

export function loadLocalState() {
  try {
    const raw = localStorage.getItem(STATE_KEY);
    return raw ? JSON.parse(raw) : emptyState();
  } catch {
    return emptyState();
  }
}

export function saveLocalState(state) {
  localStorage.setItem(STATE_KEY, JSON.stringify(state));
}

/** 清空本机数据. 合并是求并集的, 不先清掉, 本机旧进度会在下次同步时流回云端. */
export function clearLocal() {
  localStorage.removeItem(STATE_KEY);
  localStorage.removeItem(PENDING_KEY);
}

/** 有未推送的改动时置位, 界面上提示"待同步" */
export const markPending = (on) => {
  if (on) localStorage.setItem(PENDING_KEY, '1');
  else localStorage.removeItem(PENDING_KEY);
};
export const hasPending = () => localStorage.getItem(PENDING_KEY) === '1';

/* ------------------------------------------------------------------ HTTP */

async function call(method, url, cfg, body) {
  const resp = await fetch(url, {
    method,
    headers: {
      Authorization: `Bearer ${cfg.token}`,
      Accept: 'application/vnd.github+json',
      'X-GitHub-Api-Version': '2022-11-28',
      ...(body ? { 'Content-Type': 'application/json' } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  });

  if (!resp.ok) {
    let msg = `${resp.status}`;
    try {
      const j = await resp.json();
      if (j && j.message) msg = j.message;
    } catch { /* 忽略 */ }
    const err = new Error(msg);
    err.status = resp.status;
    throw err;
  }
  const text = await resp.text();
  return text ? JSON.parse(text) : {};
}

/* ------------------------------------------------------------------ 读写远端 */

export async function pull(cfg) {
  const c = cfg || loadConfig();
  const url = `${API}/repos/${c.owner}/${c.repo}/contents/${c.path}?ref=${c.branch}`;
  try {
    const data = await call('GET', url, c);
    const sha = data.sha || '';
    if (!data.content) throw new Error('远端文件过大，超出 Contents API 上限');
    // GitHub 返回的 base64 带换行, 且内容是 UTF-8, 需先转字节再解码
    const bin = atob(data.content.replace(/\s/g, ''));
    const bytes = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    return { state: JSON.parse(new TextDecoder().decode(bytes)), sha };
  } catch (e) {
    if (e.status === 404) return { state: emptyState(), sha: '' };  // 首次同步
    throw e;
  }
}

export async function push(state, sha, cfg, message) {
  const c = cfg || loadConfig();
  const json = JSON.stringify(state);
  const bytes = new TextEncoder().encode(json);
  let bin = '';
  for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
  const content = btoa(bin);

  const body = {
    message: message || 'sync from iphone',
    content,
    branch: c.branch,
  };
  if (sha) body.sha = sha;

  const url = `${API}/repos/${c.owner}/${c.repo}/contents/${c.path}`;
  const data = await call('PUT', url, c, body);
  return (data.content && data.content.sha) || '';
}

/* ------------------------------------------------------------------ 主流程 */

/** 拉取 -> 合并 -> 保存本地 -> 回传。返回合并后的状态。 */
export async function syncNow() {
  if (!isConfigured()) throw new Error('尚未配置同步');
  const cfg = loadConfig();
  const local = loadLocalState();

  const { state: remote, sha } = await pull(cfg);
  let merged = merge(local, remote);
  merged.updated = new Date().toISOString().slice(0, 19);

  const changed = JSON.stringify({ ...local, updated: '' }) !== JSON.stringify({ ...merged, updated: '' });

  let newSha = sha;
  if (changed || !sha) {
    try {
      newSha = await push(merged, sha, cfg);
    } catch (e) {
      if (e.status !== 409) throw e;
      // 期间被另一端改过: 重拉、重合并、再提交一次
      const again = await pull(cfg);
      merged = merge(merged, again.state);
      newSha = await push(merged, again.sha, cfg, 'sync from iphone (retry)');
    }
  }

  saveLocalState(merged);
  markPending(false);
  return { state: merged, changed, sha: (newSha || '').slice(0, 8) };
}

/** 只拉取并合并到本地, **不上传**.

 * 启动时用它: 既能让本机立刻看到另一台设备的进度, 又不会把本机尚存的
 * 旧数据反推回云端 —— 重置进度时这一点很关键, 否则一端刚重置完, 另一端
 * 一打开就把它推回来了。
 */
export async function pullOnly() {
  if (!isConfigured()) return null;
  const cfg = loadConfig();
  const local = loadLocalState();
  const { state: remote } = await pull(cfg);
  const merged = merge(local, remote);
  saveLocalState(merged);
  return merged;
}

export async function testConnection(cfg) {
  const c = cfg || loadConfig();
  if (!c.token) return { ok: false, msg: '还没有填写访问令牌。' };
  if (!c.owner || !c.repo) return { ok: false, msg: '还没有填写用户名或仓库名。' };
  try {
    const me = await call('GET', `${API}/user`, c);
    const repo = await call('GET', `${API}/repos/${c.owner}/${c.repo}`, c);
    return {
      ok: true,
      msg: `连接成功：以 ${me.login} 身份访问到${repo.private ? '私有' : '公开'}仓库 ${c.repo}`,
    };
  } catch (e) {
    return { ok: false, msg: e.message || String(e) };
  }
}
