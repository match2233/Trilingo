/* 验证收藏夹在同步里的合并: 电脑端 state.fav 与手机端 state.fav 求并集 */
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';

const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'fav-'));
const src = fs.readFileSync('docs/core.js', 'utf-8')
  .replace(/^export /gm, '') + '\nexport { merge, emptyState };\n';
fs.writeFileSync(path.join(dir, 'core.mjs'), src, 'utf-8');
const core = await import('file://' + path.join(dir, 'core.mjs').replace(/\\/g, '/'));

const fail = [];
const ok = (c, m, x) => {
  console.log((c ? 'OK   ' : 'FAIL ') + m + (x !== undefined ? '   [' + x + ']' : ''));
  if (!c) fail.push(m);
};

// 电脑端: 收藏了 L01-S1-1(有笔记) 和 L02-S3-4(无笔记)
const desktop = core.emptyState();
desktop.fav = {
  'L01-S1-1': { note: '电脑写的笔记', at: '2026-10-24T09:00:00' },
  'L02-S3-4': { note: '', at: '2026-10-24T09:05:00' },
};

// 手机端: 收藏了 L03-S2-2, 并且给 L01-S1-1 写了更新的笔记
const phone = core.emptyState();
phone.fav = {
  'L03-S2-2': { note: '手机上收藏的', at: '2026-10-24T10:00:00' },
  'L01-S1-1': { note: '手机新写的笔记', at: '2026-10-24T10:10:00' },
};

const m = core.merge(phone, desktop, 'remote');
ok(Object.keys(m.fav).length === 3, '合并后共 3 条收藏', Object.keys(m.fav).length);
ok(m.fav['L03-S2-2'] && m.fav['L03-S2-2'].note === '手机上收藏的', '手机端的收藏保留');
ok(m.fav['L02-S3-4'] !== undefined, '电脑端的收藏保留');
ok(m.fav['L01-S1-1'].note === '手机新写的笔记', '同一条取较新的笔记',
  m.fav['L01-S1-1'].note);

// 二次合并应当幂等 (两端再同步一次不会变)
const m2 = core.merge(m, m, 'remote');
ok(JSON.stringify(m2.fav) === JSON.stringify(m.fav), '合并幂等');

// 手机端本地合并 (prefer=local) 也要保住 fav
const m3 = core.merge(phone, desktop, 'local');
ok(Object.keys(m3.fav).length === 3, 'prefer=local 时也合并 fav', Object.keys(m3.fav).length);

console.log('');
console.log(fail.length ? `失败 ${fail.length} 项` : '全部通过');
process.exit(fail.length ? 1 : 0);
