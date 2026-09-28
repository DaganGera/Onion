// Screenshot the built landing page and run the in-browser demo once.
// Usage: npm -w @parakh/landing run build && node tools/landing_shots.mjs
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { chromium } from 'playwright';

const root = path.resolve(import.meta.dirname, '..');
const out = path.join(root, 'reports', 'landing');
fs.mkdirSync(out, { recursive: true });
const srv = spawn('npx', ['vite', 'preview', '--port', '4180', '--strictPort'], { cwd: path.join(root, 'apps/landing'), shell: true });
await new Promise((r) => setTimeout(r, 2500));
const url = 'http://localhost:4180/';
const browser = await chromium.launch({ args: ['--use-gl=angle', '--enable-unsafe-swiftshader'] });
const errors = [];
let ok = true;
try {
  for (const [name, vp] of [['desktop', { width: 1440, height: 900 }], ['mobile', { width: 390, height: 844 }], ['small', { width: 360, height: 740 }]]) {
    const page = await browser.newPage({ viewport: vp });
    page.on('pageerror', (e) => errors.push(`${name}: ${e.message}`));
    page.on('console', (m) => { if (m.type() === 'error') errors.push(`${name}: ${m.text()}`); });
    await page.goto(url, { waitUntil: 'networkidle' });
    await page.waitForSelector('[data-ready]', { timeout: 30000 }).catch(() => errors.push(name + ': 3D model did not load'));
    await page.waitForTimeout(2600);
    await page.screenshot({ path: path.join(out, `${name}-hero.png`) });
    for (const id of ['how', 'demo', 'who', 'get']) {
      await page.locator(`#${id}`).scrollIntoViewIfNeeded();
      await page.waitForTimeout(900);
      if (id === 'demo' && name === 'desktop') {
        await page.locator('#demo button').first().click();
        await page.getByText('onions found').waitFor({ timeout: 90000 });
        const n = await page.locator('#demo [aria-live] .font-heading').first().textContent();
        console.log('demo count:', n);
        await page.locator('#demo').scrollIntoViewIfNeeded();
      }
      await page.screenshot({ path: path.join(out, `${name}-${id}.png`) });
    }
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - innerWidth);
    if (overflow > 0) { ok = false; console.log(`${name}: horizontal overflow ${overflow}px`); }
    await page.close();
  }
} finally {
  await browser.close();
  srv.kill();
  spawn('taskkill', ['/pid', String(srv.pid), '/f', '/t'], { shell: true });
}
if (errors.length) { ok = false; console.log(errors.join('\n')); }
console.log(ok ? 'landing OK' : 'landing FAIL');
process.exit(ok ? 0 : 1);
