// Fit Tier-0 defect thresholds on REAL tune-split photos (block % 5 == 0; holdout untouched).
// node --import tsx tools/fit_defects.ts <zenodo "2. Bulb" dir> [perCell=15]
// Objective: catch unhealthy photos (any bulb with rot+blackening above 3 %) while keeping
// healthy bulbs from failing the default pack's Grade A defect limits. Coordinate descent,
// one threshold at a time. Writes reports/fit_defects.json; the chosen values are copied into
// packages/vision/src/config.ts by hand and the holdout evaluation is re-run afterwards.
import fs from 'node:fs';
import path from 'node:path';
import * as ort from 'onnxruntime-node';
import { analyze, downscale, resizeLabels, segInput, segInstances, TIER0, workSize, type RGBA } from '@parakh/vision';
import { readImage } from './imgio.mjs';

const root = process.argv[2];
const per = parseInt(process.argv[3] ?? '15');
const meta = JSON.parse(fs.readFileSync('apps/web/public/models/seg.json', 'utf8'));
const sess = await ort.InferenceSession.create('apps/web/public/models/' + meta.file);
const cells: [number, string][] = [
  [0, '1. Healthy/1. Red Onion/2. Multiple'], [0, '1. Healthy/2. White Onion/2. Multiple'], [0, '1. Healthy/1. Red Onion/1. Single'], [0, '1. Healthy/2. White Onion/1. Single'],
  [1, '2. Unhealthy/1. Red Onion/2. Multiple'], [1, '2. Unhealthy/2. White Onion/2. Multiple'], [1, '2. Unhealthy/1. Red Onion/1. Single'], [1, '2. Unhealthy/2. White Onion/1. Single'],
];
const data: { label: number; img: RGBA; inst: Int32Array }[] = [];
for (const [label, dir] of cells) {
  const ids = fs.readdirSync(path.join(root, dir)).filter((f) => /\.jpe?g$/i.test(f)).filter((f) => Math.floor(parseInt(f.replace(/\D/g, '')) / 25) % 5 === 0);
  for (let k = 0; k < Math.min(per, ids.length); k++) {
    const img = readImage(path.join(root, dir, ids[Math.floor((k * ids.length) / per)]));
    const { w: W, h: H } = workSize(img.width, img.height);
    const x = segInput(downscale(img, Math.max(W, H)).img, meta);
    const out = await sess.run({ x: new ort.Tensor('float32', x.data, [1, 3, x.h, x.w]) });
    data.push({ label, img, inst: resizeLabels(segInstances(out.logits.data as Float32Array, x.w, x.h), x.w, x.h, W, H) });
  }
}
console.log('photos', data.length);

const D = TIER0.defects as unknown as Record<string, number>;
function score() {
  let hb = 0, hFail = 0, uImg = 0, uHit = 0, hImg = 0, hImgHit = 0;
  for (const d of data) {
    const bs = analyze(d.img, { instances: d.inst }).bulbs.filter((b) => !b.excluded);
    const rb = bs.map((b) => (b.frac.rot ?? 0) + (b.frac.blackening ?? 0));
    const hit = rb.some((v) => v > 0.03);
    if (d.label) { uImg++; if (hit) uHit++; }
    else {
      hImg++; if (hit) hImgHit++;
      for (const b of bs) {
        hb++;
        const f = b.frac;
        if ((f.blackening ?? 0) > 0.05 || (f.spots ?? 0) > 0.1 || (f.sunburn ?? 0) > 0.02 || (f.peeled ?? 0) > 0.1 || (f.rot ?? 0) > 0.01 || (f.sprouting ?? 0) > 0.01) hFail++;
      }
    }
  }
  const tpr = uHit / uImg, fpr = hImgHit / hImg, bulbFail = hFail / hb;
  return { tpr, fpr, bulbFail, obj: tpr - fpr - bulbFail };
}
const grid: Record<string, number[]> = {
  spotDE: [18, 22, 26, 30, 36],
  brightDL: [18, 22, 26, 32],
  sunburnMaxCRatio: [0.55, 0.45, 0.35, 0.25],
  rotDL: [16, 20, 24, 28],
  rotMinC: [8, 12, 16],
  blackDL: [16, 22, 28],
  sproutMinC: [14, 20, 26],
  rimRho: [0.92, 0.86, 0.8],
};
let best = score();
console.log('start', best);
const history: unknown[] = [{ start: { ...best } }];
for (let pass = 0; pass < 2; pass++) {
  for (const [k, vals] of Object.entries(grid)) {
    let bestV = D[k];
    for (const v of vals) {
      const old = D[k]; D[k] = v;
      const s = score();
      if (s.obj > best.obj + 1e-9) { best = s; bestV = v; }
      D[k] = old;
    }
    D[k] = bestV;
    history.push({ pass, param: k, value: bestV, ...best });
    console.log(pass, k, bestV, JSON.stringify(best));
  }
}
const chosen = Object.fromEntries(Object.keys(grid).map((k) => [k, D[k]]));
fs.writeFileSync('reports/fit_defects.json', JSON.stringify({ generatedBy: 'tools/fit_defects.ts', at: new Date().toISOString(), photos: data.length, split: 'tune (block % 5 == 0)', objective: 'TPR(unhealthy photo has a bulb with rot+blackening > 3%) - FPR(same on healthy photos) - share of healthy bulbs failing Grade A defect limits', chosen, final: best, history }, null, 2));
console.log('chosen', chosen);
