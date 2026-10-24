/* Node 侧验证 PWA 的"私有题库回退"逻辑 (不需要真浏览器, 不碰真 token).
 * 跑法: node tools/test_minna_fallback.mjs
 */
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';

const store = new Map();
globalThis.localStorage = {
  getItem: (k) => (store.has(k) ? store.get(k) : null),
  setItem: (k, v) => store.set(k, String(v)),
  removeItem: (k) => store.delete(k),
};

const bank = JSON.parse(fs.readFileSync(
  path.join(process.cwd(), 'data', 'minna_tests.json'), 'utf-8'));
const small = { version: 1, lessons: bank.lessons.slice(0, 2) };
const b64 = Buffer.from(JSON.stringify(small), 'utf-8').toString('base64');

localStorage.setItem('trilingo.sync.cfg', JSON.stringify({
  token: 'test-token', owner: 'match2233', repo: 'Trilingo-data',
}));

let asked = [];
globalThis.fetch = async (url) => {
  asked.push(url);
  if (url === 'minna_tests.json') return { ok: false, status: 404 };
  if (url.includes('/contents/minna_tests.json')) {
    return { ok: true, status: 200, json: async () => ({ content: b64 }) };
  }
  return { ok: false, status: 404 };
};

const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'minna-'));
const src = fs.readFileSync('docs/minna.js', 'utf-8')
  .replace(/^export /gm, '') + '\nexport { loadBank };\n';
fs.writeFileSync(path.join(dir, 'm.mjs'), src, 'utf-8');

const mod = await import('file://' + path.join(dir, 'm.mjs').replace(/\\/g, '/'));
const got = await mod.loadBank();

const fail = [];
const ok = (c, m, extra) => { console.log((c ? 'OK   ' : 'FAIL ') + m + (extra ? '   [' + extra + ']' : '')); if (!c) fail.push(m); };

ok(asked[0] === 'minna_tests.json', '先尝试本地部署的题库', asked[0]);
ok(asked.some((u) => u.includes('/contents/minna_tests.json')), '本地缺失时回退到私有数据仓库');
ok((got.lessons || []).length === 2, '从私有仓库解出题库', String((got.lessons || []).length));
ok(got.lessons[0].sections.length > 0, '解析出大题结构');
ok(localStorage.getItem('trilingo.minna.bank') !== null, '结果写入本地缓存');

// 第二次: 断网也应能从缓存读到
globalThis.fetch = async () => { throw new Error('offline'); };
mod.M && (mod.M.bank = null);
const again = await mod.loadBank();
ok((again.lessons || []).length === 2, '断网时用本地缓存');

console.log('');
console.log(fail.length ? `失败 ${fail.length} 项` : '全部通过');
process.exit(fail.length ? 1 : 0);
