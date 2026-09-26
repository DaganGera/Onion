// E5 robustness sweep: perturb REAL held-out photos and measure how much Tier-0 output moves.
// node --import tsx tools/eval_robustness.ts <zenodo "2. Bulb" dir> [nPerCell=10]
// This is a stability test, not an accuracy claim: the perturbed photos are never used for any accuracy number.
import fs from 'node:fs';
import path from 'node:path';
import { analyze, TIER0, type RGBA } from '@parakh/vision';
import { hashCanonical } from '@parakh/core';
import { readImage } from './imgio.mjs';

const root = process.argv[2];
const per = parseInt(process.argv[3] ?? '10');
const dirs = ['1. Healthy/1. Red Onion/2. Multiple', '2. Unhealthy/1. Red Onion/2. Multiple', '1. Healthy/2. White Onion/2. Multiple', '2. Unhealthy/2. White Onion/2. Multiple'];

const clone = (im: RGBA): RGBA => ({ width: im.width, height: im.height, data: new Uint8ClampedArray(im.data) });
const perturb: Record<string, (im: RGBA) => RGBA> = {
  dark_x0_6: (im) => { const o = clone(im); for (let i = 0; i < o.data.length; i += 4) for (let c = 0; c < 3; c++) o.data[i + c] = im.data[i + c] * 0.6; return o; },
  bright_x1_4: (im) => { const o = clone(im); for (let i = 0; i < o.data.length; i += 4) for (let c = 0; c < 3; c++) o.data[i + c] = Math.min(255, im.data[i + c] * 1.4); return o; },
  warm_light: (im) => { const o = clone(im); for (let i = 0; i < o.data.length; i += 4) { o.data[i] = Math.min(255, im.data[i] * 1.12); o.data[i + 2] = im.data[i + 2] * 0.85; } return o; },
  blur_r3: (im) => { // separable box blur, radius 3 at full resolution
    const { width: w, height: h } = im, t = new Float32Array(w * h * 4), o = clone(im), r = 3;
    for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) for (let c = 0; c < 3; c++) { let s = 0, n = 0; for (let k = -r; k <= r; k++) { const xx = x + k; if (xx >= 0 && xx < w) { s += im.data[(y * w + xx) * 4 + c]; n++; } } t[(y * w + x) * 4 + c] = s / n; }
    for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) for (let c = 0; c < 3; c++) { let s = 0, n = 0; for (let k = -r; k <= r; k++) { const yy = y + k; if (yy >= 0 && yy < h) { s += t[(yy * w + x) * 4 + c]; n++; } } o.data[(y * w + x) * 4 + c] = s / n; }
    return o;
  },
  tilt_skew_10pct: (im) => { // horizontal keystone: top row squeezed 10 %, a stand-in for a tilted phone
    const { width: w, height: h } = im, o = clone(im);
    for (let y = 0; y < h; y++) { const s = 1 - 0.1 * (1 - y / h); for (let x = 0; x < w; x++) { const sx = Math.round(w / 2 + (x - w / 2) / s); const i = (y * w + x) * 4; if (sx < 0 || sx >= w) { o.data[i] = o.data[i + 1] = o.data[i + 2] = 128; } else { const j = (y * w + sx) * 4; o.data[i] = im.data[j]; o.data[i + 1] = im.data[j + 1]; o.data[i + 2] = im.data[j + 2]; } } }
    return o;
  },
  occlusion_band: (im) => { const o = clone(im); const y0 = Math.round(im.height * 0.45), y1 = Math.round(im.height * 0.55); for (let y = y0; y < y1; y++) for (let x = 0; x < im.width; x++) { const i = (y * im.width + x) * 4; o.data[i] = 60; o.data[i + 1] = 55; o.data[i + 2] = 50; } return o; },
  jpeg_noise: (im) => { const o = clone(im); let s = 12345; for (let i = 0; i < o.data.length; i += 4) for (let c = 0; c < 3; c++) { s = (s * 1103515245 + 12345) >>> 0; o.data[i + c] = Math.max(0, Math.min(255, im.data[i + c] + ((s >>> 16) % 17) - 8)); } return o; },
};

const score = (im: RGBA) => {
  const bs = analyze(im).bulbs.filter((b) => !b.excluded);
  return { n: bs.length, s: bs.reduce((m, b) => Math.max(m, (b.frac.rot ?? 0) + (b.frac.blackening ?? 0)), 0) };
};

const base: { id: number; label: number; n: number; s: number; img: RGBA }[] = [];
for (const d of dirs) {
  const label = d.startsWith('2.') ? 1 : 0;
  const ids = fs.readdirSync(path.join(root, d)).map((f) => parseInt(f.replace(/\D/g, ''))).filter((id) => Math.floor(id / 25) % 5 === 4).sort((a, b) => a - b);
  for (let k = 0; k < Math.min(per, ids.length); k++) {
    const id = ids[Math.floor((k * ids.length) / per)];
    const img = readImage(path.join(root, d, `Onion${String(id).padStart(5, '0')}.jpg`));
    base.push({ id, label, img, ...score(img) });
  }
}
const THR = JSON.parse(fs.readFileSync('reports/zenodo_tier0.json', 'utf8')).threshold_from_tune;
const r3 = (x: number) => Math.round(x * 1000) / 1000;
const results: Record<string, object> = {};
for (const [name, f] of Object.entries(perturb)) {
  let dCount = 0, dScore = 0, flips = 0;
  for (const b of base) {
    const p = score(f(b.img));
    dCount += Math.abs(p.n - b.n) / Math.max(1, b.n);
    dScore += Math.abs(p.s - b.s);
    if ((p.s >= THR) !== (b.s >= THR)) flips++;
  }
  results[name] = { mean_rel_change_bulb_count: r3(dCount / base.length), mean_abs_change_defect_score: r3(dScore / base.length), image_decision_flips: r3(flips / base.length) };
  console.log(name, results[name]);
}
fs.writeFileSync('reports/e5_robustness.json', JSON.stringify({
  generatedBy: 'tools/eval_robustness.ts', at: new Date().toISOString(), model: `${TIER0.id}@${TIER0.version}`, modelHash: await hashCanonical(TIER0),
  question: 'How much does Tier-0 output move when a real held-out photo is darkened, brightened, colour-shifted, blurred, skewed, partly covered or noised?',
  photos: base.length, source: 'Zenodo 10.5281/zenodo.20254934 multi-bulb photos, holdout blocks only (block % 5 == 4)',
  note: 'Perturbed copies of real photos, used only to measure stability. Not an accuracy result. The Capture Guard would refuse some of these (dark, blur).',
  threshold: THR, perturbations: results,
}, null, 2));
