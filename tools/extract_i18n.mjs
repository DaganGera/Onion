// Collect every t('key', 'English') call into apps/web/src/locales/en.json (the reference for translators).
// Also reports keys missing from each translation file.
import fs from 'node:fs';
import path from 'node:path';

const dir = 'apps/web/src';
const out = {};
const re = /\bt\(\s*['"`]([\w.]+)['"`]\s*,\s*'((?:[^'\\]|\\.)*)'/g;
const walk = (d) => fs.readdirSync(d, { withFileTypes: true }).forEach((e) => {
  const p = path.join(d, e.name);
  if (e.isDirectory()) return walk(p);
  if (!/\.tsx?$/.test(e.name)) return;
  const s = fs.readFileSync(p, 'utf8');
  for (const m of s.matchAll(re)) out[m[1]] = m[2].replace(/\\'/g, "'");
});
walk(dir);
delete out.key; // the example in lib/i18n.ts docs
Object.assign(out, { 'layer.top': 'top', 'layer.middle': 'middle', 'layer.bottom': 'bottom' });
const sorted = Object.fromEntries(Object.keys(out).sort().map((k) => [k, out[k]]));
const loc = path.join(dir, 'locales');
fs.writeFileSync(path.join(loc, 'en.json'), JSON.stringify(sorted, null, 1) + '\n');
console.log(Object.keys(sorted).length, 'keys');
for (const f of fs.readdirSync(loc)) {
  if (f === 'en.json' || !f.endsWith('.json')) continue;
  const tr = JSON.parse(fs.readFileSync(path.join(loc, f), 'utf8'));
  const missing = Object.keys(sorted).filter((k) => !(k in tr));
  console.log(f, 'missing', missing.length, missing.slice(0, 8).join(' '));
}
