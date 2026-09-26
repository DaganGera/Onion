// Reason-code census with the full pipeline (Tier-2 seg + Tier-1 gate).
// node --import tsx tools/why2.ts <pack> <images...>
import fs from 'node:fs';
import * as ort from 'onnxruntime-node';
import { adjudicate, packById } from '@parakh/core';
import { analyze, applyTier1, bulbCrop, downscale, resizeLabels, segInput, segInstances, toMeasurement, workSize } from '@parakh/vision';
import { readImage } from './imgio.mjs';
const [, , packId, ...files] = process.argv;
const pack = packById(packId)!;
const sm = JSON.parse(fs.readFileSync('apps/web/public/models/seg.json', 'utf8')), tm = JSON.parse(fs.readFileSync('apps/web/public/models/tier1.json', 'utf8'));
const seg = await ort.InferenceSession.create('apps/web/public/models/' + sm.file), t1 = await ort.InferenceSession.create('apps/web/public/models/' + tm.file);
const codes: Record<string, number> = {}, buckets: Record<string, number> = {};
for (const f of files) {
  const img = readImage(f);
  const { w: W, h: H } = workSize(img.width, img.height);
  const work = downscale(img, Math.max(W, H)).img;
  const x = segInput(work, sm);
  const o = await seg.run({ x: new ort.Tensor('float32', x.data, [1, 3, x.h, x.w]) });
  const a = analyze(img, { instances: resizeLabels(segInstances(o.logits.data as Float32Array, x.w, x.h), x.w, x.h, W, H) });
  const bs = a.bulbs.filter((b) => !b.excluded);
  const S = tm.size, d = new Float32Array(bs.length * 3 * S * S);
  bs.forEach((b, j) => { const c = bulbCrop(work, b, S); for (let i = 0; i < S * S; i++) for (let ch = 0; ch < 3; ch++) d[j * 3 * S * S + ch * S * S + i] = (c[i * 4 + ch] / 255 - tm.mean[ch]) / tm.std[ch]; });
  if (bs.length) { const lo = (await t1.run({ x: new ort.Tensor('float32', d, [bs.length, 3, S, S]) })).logits.data as Float32Array; bs.forEach((b, j) => applyTier1(b, 1 / (1 + Math.exp(lo[2 * j] - lo[2 * j + 1])), tm.thr_high, tm.gate)); }
  const ms = bs.map((b, i) => toMeasurement(b, `b${i}`, 1, 1));
  for (const v of adjudicate(ms, pack)) { buckets[v.bucket] = (buckets[v.bucket] ?? 0) + 1; for (const c of v.codes) { const k = c.replace(/_[\d.]+(PCT|MM)_/, '_x_').replace(/\d+_LT_\d+/, 'x'); codes[k] = (codes[k] ?? 0) + 1; } }
  if (process.env.V) bs.forEach((b, i) => console.log(f.slice(-16), i, b.minMm.toFixed(0), b.maxMm.toFixed(0), 'sol', b.solidity.toFixed(2), JSON.stringify(b.shape), 'p', b.p1?.toFixed(2), a.calib.tier));
}
console.log(buckets);
console.log(Object.entries(codes).sort((a, b) => b[1] - a[1]).slice(0, 14));
