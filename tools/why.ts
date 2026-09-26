// Reason-code census for sample photos: node --import tsx tools/why.ts <pack> <images...>
import { adjudicate, packById } from '@parakh/core';
import { analyze, toMeasurement } from '@parakh/vision';
import { readImage } from './imgio.mjs';
const [, , packId, ...files] = process.argv;
const pack = packById(packId)!;
const codes: Record<string, number> = {}, buckets: Record<string, number> = {};
for (const f of files) {
  const a = analyze(readImage(f));
  const ms = a.bulbs.filter((b) => !b.excluded).map((b, i) => toMeasurement(b, `b${i}`, 1, 1));
  for (const v of adjudicate(ms, pack)) {
    buckets[v.bucket] = (buckets[v.bucket] ?? 0) + 1;
    for (const c of v.codes) { const k = c.replace(/_[\d.]+(PCT|MM)_/, '_x_'); codes[k] = (codes[k] ?? 0) + 1; }
  }
}
console.log(buckets);
console.log(Object.entries(codes).sort((a, b) => b[1] - a[1]).slice(0, 14));
