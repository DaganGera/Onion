// Debug overlay: node --import tsx tools/viz.ts <image> <out.png>
import { analyze, downscale, CODE } from '@parakh/vision';
import { readImage, writePng } from './imgio.mjs';

const [, , inp, out] = process.argv;
const img = readImage(inp);
const t = Date.now();
const a = analyze(img);
console.log(`${inp}: ${img.width}x${img.height} -> ${a.width}x${a.height}, ${Date.now() - t} ms`, a.timings);
console.log(`calib ${a.calib.tier} ${a.calib.note} mm/px=${a.calib.mmPerPx.toFixed(3)} camH=${a.calib.camHmm.toFixed(0)}`);
const { img: v } = downscale(img, 1024);
const col: Record<number, [number, number, number]> = { 2: [0, 0, 0], 3: [150, 60, 0], 4: [255, 230, 0], 5: [0, 160, 255], 6: [0, 220, 0], 7: [255, 0, 255] };
for (const b of a.bulbs) {
  const L = b.labels;
  for (let y = 0; y < L.h; y++) for (let x = 0; x < L.w; x++) {
    const c = L.data[y * L.w + x];
    const o = ((y + L.y0) * v.width + (x + L.x0)) * 4;
    if (col[c]) { v.data[o] = col[c][0]; v.data[o + 1] = col[c][1]; v.data[o + 2] = col[c][2]; }
  }
  for (let i = 0; i < b.hull.length; i++) {
    const p = b.hull[i], q = b.hull[(i + 1) % b.hull.length];
    const n = Math.ceil(Math.hypot(q.x - p.x, q.y - p.y));
    for (let s = 0; s <= n; s++) {
      const x = Math.round(p.x + ((q.x - p.x) * s) / Math.max(1, n)), y = Math.round(p.y + ((q.y - p.y) * s) / Math.max(1, n));
      const o = (y * v.width + x) * 4;
      if (o >= 0 && o < v.data.length) { v.data[o] = b.excluded ? 128 : 255; v.data[o + 1] = b.excluded ? 128 : 40; v.data[o + 2] = b.excluded ? 128 : 40; }
    }
  }
  const f = Object.entries(b.frac).filter(([, x]) => x && x > 0.005).map(([k, x]) => `${k}=${((x as number) * 100).toFixed(1)}%`).join(' ');
  console.log(`#${b.idx} ${b.excluded ?? 'ok'} d=${b.minMm.toFixed(1)}-${b.maxMm.toFixed(1)}mm±${b.sdMm.toFixed(1)} sol=${b.solidity.toFixed(2)} conf=${b.conf.toFixed(2)} ${f}`);
}
if (out) writePng(out, v);
void CODE;
