/* 验证 PWA 的对话型题干换行 */
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';

const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'pp-'));
let src = fs.readFileSync('docs/minna.js', 'utf-8')
  .replace(/^export /gm, '')
  .replace(/^import .*$/gm, '');
// minna.js 里的 esc 来自 import, 单独补一个同样的实现
if (!/function esc\b|const esc\b/.test(src)) {
  src = `const esc = (s) => String(s == null ? '' : s)
  .replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));\n`
    + src;
}
src += '\nexport { prettyPrompt };\n';
fs.writeFileSync(path.join(dir, 'm.mjs'), src, 'utf-8');
const mod = await import('file://' + path.join(dir, 'm.mjs').replace(/\\/g, '/'));

const fail = [];
const ok = (c, m, x) => {
  console.log((c ? 'OK   ' : 'FAIL ') + m + (x !== undefined ? '   [' + x + ']' : ''));
  if (!c) fail.push(m);
};

const cases = [
  ['A: キムさんは 会社員では ありませんか。 B: はい、会社員＿＿。', 2],
  ['A: それは 何ですか。B: これは 本です。A: そうですか。', 3],
  ['わたしは＿＿です。', 1],
  ['森さんは 課長ですか。', 1],
  ['この 問題に 対して みんなが＿＿意見が あります。', 1],
];
for (const [text, lines] of cases) {
  const out = mod.prettyPrompt(text);
  const n = out.split('<br>').length;
  ok(n === lines, `换行 ${lines} 行`, `${n} 行: ${out.slice(0, 34)}`);
}
ok(mod.prettyPrompt('A: <b>x</b> B: y').includes('&lt;b&gt;'), '会转义 HTML');

console.log('');
console.log(fail.length ? `失败 ${fail.length} 项` : '全部通过');
process.exit(fail.length ? 1 : 0);
