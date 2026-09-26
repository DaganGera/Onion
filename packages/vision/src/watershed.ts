import type { Mask } from './img';

/**
 * Split touching bulbs: markers are distance-transform peaks kept by
 * non-maximum suppression (a peak survives only if no stronger peak lies
 * within `nms * its radius`), then a priority flood over -distance assigns
 * every foreground pixel to one marker.
 */
export function watershedSplit(m: Mask, dist: Float32Array, compLabels: Int32Array, opts: { minPeak: number; nms: number }): Int32Array {
  const { width: w, height: h } = m;
  const peaks: { i: number; d: number; comp: number }[] = [];
  for (let y = 1; y < h - 1; y++) {
    for (let x = 1; x < w - 1; x++) {
      const i = y * w + x, d = dist[i];
      if (d < opts.minPeak) continue;
      let isMax = true;
      for (let dy = -1; dy <= 1 && isMax; dy++) for (let dx = -1; dx <= 1; dx++) {
        if ((dx || dy) && dist[i + dy * w + dx] > d) { isMax = false; break; }
      }
      if (isMax) peaks.push({ i, d, comp: compLabels[i] });
    }
  }
  peaks.sort((a, b) => b.d - a.d);
  const kept: typeof peaks = [];
  for (const p of peaks) {
    const px = p.i % w, py = (p.i - px) / w;
    let ok = true;
    for (const q of kept) {
      if (q.comp !== p.comp) continue;
      const qx = q.i % w, qy = (q.i - qx) / w;
      if (Math.hypot(px - qx, py - qy) < opts.nms * Math.max(p.d, q.d)) { ok = false; break; }
    }
    if (ok) kept.push(p);
  }
  // Components with no surviving peak (tiny) still get a marker at their max.
  const labels = new Int32Array(w * h);
  kept.forEach((p, k) => { labels[p.i] = k + 1; });

  // Binary heap keyed by -dist (flood from the peaks downhill).
  const heapI: number[] = [], heapK: number[] = [];
  const push = (i: number, k: number) => {
    heapI.push(i); heapK.push(k);
    let c = heapI.length - 1;
    while (c > 0) {
      const p = (c - 1) >> 1;
      if (heapK[p] <= heapK[c]) break;
      [heapI[p], heapI[c]] = [heapI[c], heapI[p]]; [heapK[p], heapK[c]] = [heapK[c], heapK[p]]; c = p;
    }
  };
  const pop = () => {
    const i = heapI[0];
    const li = heapI.pop()!, lk = heapK.pop()!;
    if (heapI.length) {
      heapI[0] = li; heapK[0] = lk;
      let c = 0;
      for (;;) {
        const l = 2 * c + 1, r = l + 1;
        let s = c;
        if (l < heapI.length && heapK[l] < heapK[s]) s = l;
        if (r < heapI.length && heapK[r] < heapK[s]) s = r;
        if (s === c) break;
        [heapI[s], heapI[c]] = [heapI[c], heapI[s]]; [heapK[s], heapK[c]] = [heapK[c], heapK[s]]; c = s;
      }
    }
    return i;
  };
  for (const p of kept) push(p.i, -p.d);
  while (heapI.length) {
    const i = pop(), x = i % w, y = (i - x) / w, lab = labels[i];
    const nb = [x > 0 ? i - 1 : -1, x < w - 1 ? i + 1 : -1, y > 0 ? i - w : -1, y < h - 1 ? i + w : -1];
    for (const j of nb) {
      if (j < 0 || !m.data[j] || labels[j]) continue;
      labels[j] = lab;
      push(j, -dist[j]);
    }
  }
  return labels;
}
