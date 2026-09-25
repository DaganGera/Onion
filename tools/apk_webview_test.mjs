// Drive the installed APK's WebView over the raw DevTools protocol.
// Setup: adb forward tcp:9333 localabstract:webview_devtools_remote_<pid>; then node tools/apk_webview_test.mjs
import fs from 'node:fs';

const targets = await (await fetch('http://localhost:9333/json/list')).json();
const target = targets.find((t) => t.type === 'page');
const ws = new WebSocket(target.webSocketDebuggerUrl);
await new Promise((r) => ws.addEventListener('open', r));
let id = 0;
const pending = new Map();
const errors = [];
ws.addEventListener('message', (e) => {
  const m = JSON.parse(e.data);
  if (m.id && pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id); }
  if (m.method === 'Runtime.exceptionThrown') errors.push(m.params.exceptionDetails.exception?.description?.slice(0, 200));
});
const send = (method, params = {}) => new Promise((res) => { const i = ++id; pending.set(i, res); ws.send(JSON.stringify({ id: i, method, params })); });
const run = async (expr) => {
  const r = await send('Runtime.evaluate', { expression: `(async () => { ${expr} })()`, awaitPromise: true, returnByValue: true });
  if (r.result?.exceptionDetails) throw new Error(r.result.exceptionDetails.exception?.description ?? 'eval error');
  return r.result?.result?.value;
};
await send('Runtime.enable');
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const waitFor = async (sel, ms = 240000) => { const t = Date.now(); while (Date.now() - t < ms) { if (await run(`return !!document.querySelector(${JSON.stringify(sel)})`)) return; await sleep(1000); } throw new Error('timeout ' + sel); };
const click = (text) => run(`const b = [...document.querySelectorAll('button,a')].find((x) => x.textContent.includes(${JSON.stringify(text)})); if (!b) throw new Error('no button ${text}'); b.click(); return true;`);
const idb = (store, key) => run(`return await new Promise((res) => { const rq = indexedDB.open('parakh'); rq.onsuccess = () => { const s = rq.result.transaction('${store}').objectStore('${store}'); const g = ${key ? `s.get(${key})` : 's.getAll()'}; g.onsuccess = () => res(g.result); }; });`);

const out = {};
// Fresh start: drop the app database, then reload.
await run(`await new Promise((r) => { const d = indexedDB.deleteDatabase('parakh'); d.onsuccess = d.onerror = d.onblocked = () => r(); }); location.hash = '#/'; location.reload(); return true;`).catch(() => {});
await sleep(6000);
await waitFor('.hero-card', 30000);
await click('Load the demo lot');
const t0 = Date.now();
await waitFor('.verdict');
out.demo_ms = Date.now() - t0;
out.verdict = await run(`return document.querySelector('.verdict h2').textContent`);
const caps = await idb('captures');
out.captures = caps.map((c) => ({ total_ms: Math.round(c.timings.total), tier1_ms: Math.round(c.timings.tier1 ?? -1), bulbs_with_tier1: c.bulbs.filter((x) => typeof x.p1 === 'number').length, bulbs: c.bulbs.filter((x) => !x.excluded).length }));
const t1 = Date.now();
await click('Sign and issue receipt');
await waitFor('.receipt', 300000);
out.sign_ms = Date.now() - t1;
out.stamp = await run(`return document.querySelector('.stamp').innerText`);
const hash = await run(`return location.hash.split('/').pop()`);
const cert = await idb('certs', JSON.stringify(hash));
out.qr_chars = cert.qr.length;
await run(`location.hash = '#/verify'; return true;`);
await waitFor('textarea', 20000);
await run(`const t = document.querySelector('textarea'); const set = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set; set.call(t, ${JSON.stringify(cert.qr)}); t.dispatchEvent(new Event('input', { bubbles: true })); return true;`);
await sleep(300);
const t2 = Date.now();
await click('Check');
await waitFor('.checks', 300000);
out.verify_ms = Date.now() - t2;
out.verify = await run(`return document.querySelector('.verdict h2').textContent`);
out.errors = errors;
fs.writeFileSync('reports/apk_webview.json', JSON.stringify({ generatedBy: 'tools/apk_webview_test.mjs', at: new Date().toISOString(), device: 'Android 15 emulator (x86_64, WHPX, swiftshader GPU), system WebView', ua: target.description ?? '', ...out }, null, 2));
console.log(JSON.stringify(out));
ws.close();
