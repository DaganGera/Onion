// Smoke test a deployed build: node tools/smoke_live.mjs https://dagangera.github.io/Onion/
import { chromium } from 'playwright';
const url = process.argv[2];
const b = await chromium.launch();
const p = await (await b.newContext({ viewport: { width: 390, height: 844 } })).newPage();
const errs = [];
p.on('pageerror', (e) => errs.push(String(e)));
await p.goto(url);
await p.getByRole('button', { name: /Load the demo lot/ }).click();
await p.locator('.verdict').waitFor({ timeout: 120000 });
const t1 = await p.evaluate(() => new Promise((res) => { const rq = indexedDB.open('parakh'); rq.onsuccess = () => { const g = rq.result.transaction('captures').objectStore('captures').getAll(); g.onsuccess = () => res(g.result.flatMap((c) => c.bulbs).filter((x) => typeof x.p1 === 'number').length); }; }));
console.log(JSON.stringify({ url, verdict: await p.locator('.verdict h2').innerText(), bulbsWithTier1: t1, errors: errs }));
await b.close();
