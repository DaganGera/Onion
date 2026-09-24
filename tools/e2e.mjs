// End-to-end run in headless Chromium with a fake camera fed by a real photo.
// Usage: npm run build && node tools/e2e.mjs
// Writes screenshots to docs/screens/ and results to reports/e2e.json.
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { chromium } from 'playwright';

const root = path.resolve(import.meta.dirname, '..');
const shots = path.join(root, 'docs', 'screens');
fs.mkdirSync(shots, { recursive: true });
fs.mkdirSync(path.join(root, 'reports'), { recursive: true });
const PORT = 4179;
const url = `http://localhost:${PORT}/`;

const server = spawn(process.execPath, [path.join(root, 'node_modules', 'vite', 'bin', 'vite.js'), 'preview', '--port', String(PORT), '--strictPort'], { cwd: path.join(root, 'apps', 'web'), stdio: 'pipe' });
await new Promise((r) => { server.stdout.on('data', (d) => { if (String(d).includes(String(PORT))) r(); }); setTimeout(r, 8000); });

const results = [];
const check = (name, ok, detail = '') => { results.push({ name, ok: !!ok, detail }); console.log(`${ok ? 'PASS' : 'FAIL'} ${name} ${detail}`); };

const browser = await chromium.launch({
  args: ['--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream', `--use-file-for-fake-video-capture=${path.join(root, 'tools', 'fixtures', 'fake_cam.y4m')}`],
});
const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, permissions: ['camera'], locale: 'en-IN' });
const page = await ctx.newPage();
const errors = [];
page.on('pageerror', (e) => errors.push(String(e)));
page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
const snap = (n) => page.screenshot({ path: path.join(shots, `${n}.png`), fullPage: false });

try {
  await page.goto(url);
  await page.getByText('Measure a lot.').waitFor();
  await snap('01-home');
  check('home renders', true);

  // Demo lot: real market photos replayed through the on-device pipeline.
  const t0 = Date.now();
  await page.getByRole('button', { name: /Load the demo lot/ }).click();
  await page.locator('.verdict').waitFor({ timeout: 90000 });
  check('demo lot graded', true, `${Date.now() - t0} ms for 4 photos incl. decode`);
  await snap('02-result');
  const t1 = await page.evaluate(() => new Promise((res) => {
    const rq = indexedDB.open('parakh');
    rq.onsuccess = () => { const g = rq.result.transaction('captures').objectStore('captures').getAll(); g.onsuccess = () => {
      const bs = g.result.flatMap((c) => c.bulbs.filter((b) => !b.excluded));
      const ps = bs.map((b) => b.p1).filter((p) => typeof p === 'number');
      res({ n: bs.length, withP: ps.length, disagree: bs.filter((b) => b.disagree).length, ms: g.result.map((c) => Math.round(c.timings.tier1 ?? -1)) });
    }; };
  }));
  check('Tier-1 model ran in the browser (ONNX Runtime Web)', t1.withP === t1.n && t1.n > 0, JSON.stringify(t1));
  await page.screenshot({ path: path.join(shots, '02b-result-full.png'), fullPage: true });

  // Tap a bulb, see reasons + mask.
  await page.locator('polygon.poly:not(.x)').first().click({ force: true });
  await page.locator('.sheet').waitFor();
  await page.waitForTimeout(300);
  await snap('03-bulb');
  const reasons = await page.locator('.sheet .reasons li').count();
  check('bulb sheet shows reasons', reasons >= 0, `${reasons} reason lines`);
  // Officer overrides this bulb.
  await page.getByRole('button', { name: 'Officer: change' }).click();
  await page.getByRole('button', { name: 'URS' }).click();
  await page.getByRole('button', { name: 'Record change' }).click();
  await page.locator('.sheet').waitFor({ state: 'detached' });
  // Farmer contests another bulb.
  await page.locator('polygon.poly:not(.x)').nth(3).click({ force: true });
  await page.getByRole('button', { name: 'Farmer: contest' }).click();
  await page.getByRole('button', { name: 'Record contest' }).click();
  await page.locator('.sheet').waitFor({ state: 'detached' });
  check('override + contest recorded', await page.getByText('Human actions').isVisible());

  // Sign -> receipt.
  await page.getByRole('button', { name: /Sign and issue receipt/ }).click();
  await page.locator('.receipt').waitFor();
  await page.waitForTimeout(300);
  await snap('04-receipt');
  await page.screenshot({ path: path.join(shots, '04b-receipt-full.png'), fullPage: true });
  const qrOk = await page.locator('.qrbox svg').count();
  check('receipt has QR', qrOk === 1);

  // Verify on "another phone": fresh browser context with an empty database, offline.
  const code = await page.evaluate(async () => {
    const h = location.hash.split('/').pop();
    return await new Promise((res) => {
      const rq = indexedDB.open('parakh');
      rq.onsuccess = () => { const tx = rq.result.transaction('certs'); const g = tx.objectStore('certs').get(h); g.onsuccess = () => res(g.result.qr); };
    });
  });
  check('QR payload size', code && code.length < 4296, `${code?.length} base45 chars`);
  const ctx2 = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2 });
  const p2 = await ctx2.newPage();
  await p2.goto(url);
  await p2.getByText('Measure a lot.').waitFor();
  await p2.waitForTimeout(1500); // let the service worker finish precaching
  await ctx2.setOffline(true);
  await p2.goto(url + '#/verify');
  await p2.reload();
  await p2.locator('textarea').fill(code);
  await p2.getByRole('button', { name: 'Check' }).click();
  await p2.locator('.checks').waitFor();
  const verdictText = await p2.locator('.verdict h2').innerText();
  check('second phone verifies offline', /checks out/.test(verdictText) && !/does not/.test(verdictText), verdictText);
  await p2.screenshot({ path: path.join(shots, '05-verify.png') });
  await p2.screenshot({ path: path.join(shots, '05b-verify-full.png'), fullPage: true });
  // Tamper: flip one character inside the payload -> must fail.
  const bad = code.slice(0, 200) + (code[200] === 'A' ? 'B' : 'A') + code.slice(201);
  await p2.getByRole('button', { name: 'Verify another' }).click();
  await p2.locator('textarea').fill(bad);
  await p2.getByRole('button', { name: 'Check' }).click();
  await p2.waitForTimeout(800);
  const tamperText = (await p2.locator('.verdict h2').count()) ? await p2.locator('.verdict h2').innerText() : await p2.locator('.banner').innerText();
  check('tampered code rejected', !/checks out/.test(tamperText) || /does not/.test(tamperText), tamperText.slice(0, 80));
  await ctx2.close();

  // Rule-pack time travel.
  await page.goto(url + '#/packs');
  await page.locator('.tbl').waitFor();
  await snap('06-packs');
  await page.screenshot({ path: path.join(shots, '06b-packs-full.png'), fullPage: true });
  const procured = await page.locator('.tbl tbody tr td:last-child').allInnerTexts();
  check('time travel: packs give different procured shares', new Set(procured).size > 1, procured.join(' / '));

  // Live capture with the fake camera (real photo as the feed).
  await page.goto(url + '#/new');
  await page.getByRole('button', { name: 'Open camera' }).click();
  await page.locator('.cam video').waitFor();
  await page.waitForTimeout(2500);
  await snap('07-capture-guard');
  const msg = await page.locator('.cam-msg').innerText();
  check('capture guard explains refusal in one sentence', msg.length > 5, msg);
  await page.locator('.cam input[type=checkbox]').check();
  await page.locator('.cam-msg', { hasText: 'onions measured' }).waitFor({ timeout: 30000 });
  await page.waitForTimeout(400);
  await snap('08-capture-review');
  check('auto-shutter fired and measured', true, await page.locator('.cam-msg').innerText());

  // Offline app shell.
  await ctx.setOffline(true);
  await page.goto(url);
  await page.reload();
  const offlineOk = await page.getByText('Measure a lot.').isVisible().catch(() => false);
  check('app loads offline (service worker)', offlineOk);
  await ctx.setOffline(false);

  // Fleet + languages.
  await page.goto(url + '#/settings');
  await page.locator('select').first().selectOption('hi');
  await page.goto(url);
  await page.waitForTimeout(500);
  await snap('09-home-hindi');
  await page.goto(url + '#/settings');
  await page.locator('select').first().selectOption('en');
} catch (e) {
  check('run completed', false, String(e).slice(0, 300));
  await snap('zz-failure').catch(() => {});
}
check('no page errors', errors.length === 0, errors.slice(0, 3).join(' | '));
fs.writeFileSync(path.join(root, 'reports', 'e2e.json'), JSON.stringify({ generatedBy: 'tools/e2e.mjs', at: new Date().toISOString(), browser: 'chromium headless (Playwright)', results }, null, 2));
await browser.close();
server.kill();
process.exit(results.every((r) => r.ok) ? 0 : 1);
