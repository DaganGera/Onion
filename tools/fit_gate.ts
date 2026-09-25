// Tier-1 gate for defect measurement, fitted on REAL tune-split photos (block % 5 == 0) and then
// checked once on holdout photos (block % 5 == 4).
// node --import tsx tools/fit_gate.ts <zenodo "2. Bulb" dir> [perCell=15]
// A bulb the learned classifier calls healthy with p(unhealthy) < gate has its colour defect
// fractions cleared (noted on the bulb); other bulbs keep the colour measurements.
import fs from 'node:fs';
import path from 'node:path';
import * as ort from 'onnxruntime-node';
import { analyze, bulbCrop, downscale, resizeLabels, segInput, segInstances, TIER0, workSize, type BulbResult, type RGBA } from '@parakh/vision';
import { readImage } from './imgio.mjs';

const root = process.argv[2];
const per = parseInt(process.argv[3] ?? '15');
const segMeta = JSON.parse(fs.readFileSync('apps/web/public/models/seg.json', 'utf8'));
const t1Meta = JSON.parse(fs.readFileSync('apps/web/public/models/tier1.json', 'utf8'));
const seg = await ort.InferenceSession.create('apps/web/public/models/' + segMeta.file);
const t1 = await ort.InferenceSession.create('apps/web/public/models/' + t1Meta.file);
const cells: [number, string][] = [
  [0, '1. Healthy/1. Red Onion/2. Multiple'], [0, '1. Healthy/2. White Onion/2. Multiple'], [0, '1. Healthy/1. Red Onion/1. Single'], [0, '1. Healthy/2. White Onion/1. Single'],
  [1, '2. Unhealthy/1. Red Onion/2. Multiple'], [1, '2. Unhealthy/2. White Onion/2. Multiple'], [1, '2. Unhealthy/1. Red Onion/1. Single'], [1, '2. Unhealthy/2. White Onion/1. Single'],
];
type Photo = { label: number; bulbs: (BulbResult & { p: number })[] };
async function collect(block: number): Promise<Photo[]> {
  const out: Photo[] = [];
  for (const [label, dir] of cells) {
    const ids = fs.readdirSync(path.join(root, dir)).filter((f) => /\.jpe?g$/i.test(f)).filter((f) => Math.floor(parseInt(f.replace(/\D/g, '')) / 25) % 5 === block);
    for (let k = 0; k < Math.min(per, ids.length); k++) {
      const img: RGBA = readImage(path.join(root, dir, ids[Math.floor((k * ids.length) / per)]));
      const { w: W, h: H } = workSize(img.width, img.height);
      const work = downscale(img, Math.max(W, H)).img;
      const x = segInput(work, segMeta);
      const so = await seg.run({ x: new ort.Tensor('float32', x.data, [1, 3, x.h, x.w]) });
      const inst = resizeLabels(segInstances(so.logits.data as Float32Array, x.w, x.h), x.w, x.h, W, H);
      const bulbs = analyze(img, { instances: inst }).bulbs.filter((b) => !b.excluded);
      const S = t1Meta.size, n = bulbs.length;
      const ps: number[] = [];
      if (n) {
        const data = new Float32Array(n * 3 * S * S);
        bulbs.forEach((b, j) => { const c = bulbCrop(work, b, S); for (let i = 0; i < S * S; i++) for (let ch = 0; ch < 3; ch++) data[j * 3 * S * S + ch * S * S + i] = (c[i * 4 + ch] / 255 - t1Meta.mean[ch]) / t1Meta.std[ch]; });
        const lo = (await t1.run({ x: new ort.Tensor('float32', data, [n, 3, S, S]) })).logits.data as Float32Array;
        for (let j = 0; j < n; j++) ps.push(1 / (1 + Math.exp(lo[2 * j] - lo[2 * j + 1])));
      }
      out.push({ label, bulbs: bulbs.map((b, j) => Object.assign(b, { p: ps[j] })) });
    }
  }
  return out;
}
function score(data: Photo[], gate: number) {
  let hb = 0, hFail = 0, uImg = 0, uHit = 0, hImg = 0, hHit = 0;
  for (const d of data) {
    const eff = d.bulbs.map((b) => (b.p < gate ? { rot: 0, bl: 0, fail: false } : {
      rot: b.frac.rot ?? 0, bl: b.frac.blackening ?? 0,
      fail: (b.frac.blackening ?? 0) > 0.05 || (b.frac.spots ?? 0) > 0.1 || (b.frac.sunburn ?? 0) > 0.02 || (b.frac.peeled ?? 0) > 0.1 || (b.frac.rot ?? 0) > 0.01 || (b.frac.sprouting ?? 0) > 0.01,
    }));
    const hit = eff.some((e) => e.rot + e.bl > 0.03);
    if (d.label) { uImg++; if (hit) uHit++; } else { hImg++; if (hit) hHit++; for (const e of eff) { hb++; if (e.fail) hFail++; } }
  }
  const r3 = (x: number) => Math.round(x * 1000) / 1000;
  return { gate, tpr: r3(uHit / uImg), fpr: r3(hHit / hImg), healthyBulbFail: r3(hFail / hb), obj: r3(uHit / uImg - hHit / hImg - hFail / hb) };
}
const tune = await collect(0);
const gates = [0, 0.05, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7];
const tuneRes = gates.map((g) => score(tune, g));
tuneRes.forEach((r) => console.log('tune', JSON.stringify(r)));
const best = tuneRes.reduce((a, b) => (b.obj > a.obj ? b : a));
const hold = await collect(4);
const holdRes = { chosen: score(hold, best.gate), noGate: score(hold, 0) };
console.log('holdout', JSON.stringify(holdRes));
fs.writeFileSync('reports/fit_gate.json', JSON.stringify({ generatedBy: 'tools/fit_gate.ts', at: new Date().toISOString(), config: { defects: TIER0.defects }, tune: tuneRes, chosenGate: best.gate, holdout: holdRes }, null, 2));
