import { mask, type Mask } from './img';

/** Separable square erosion/dilation with radius r (window 2r+1). */
function boxMorph(m: Mask, r: number, dilate: boolean): Mask {
  if (r <= 0) return m;
  const { width: w, height: h } = m;
  const tmp = new Uint8Array(w * h), out = mask(w, h);
  const want = dilate ? 1 : 0;
  // Horizontal pass with a running count.
  for (let y = 0; y < h; y++) {
    let cnt = 0;
    const row = y * w;
    for (let x = -r; x < w; x++) {
      const xin = x + r, xout = x - r - 1;
      if (xin < w && m.data[row + xin] === want) cnt++;
      if (xout >= 0 && m.data[row + xout] === want) cnt--;
      if (x >= 0) tmp[row + x] = dilate ? (cnt > 0 ? 1 : 0) : cnt > 0 ? 0 : 1;
    }
  }
  for (let x = 0; x < w; x++) {
    let cnt = 0;
    for (let y = -r; y < h; y++) {
      const yin = y + r, yout = y - r - 1;
      if (yin < h && tmp[yin * w + x] === want) cnt++;
      if (yout >= 0 && tmp[yout * w + x] === want) cnt--;
      if (y >= 0) out.data[y * w + x] = dilate ? (cnt > 0 ? 1 : 0) : cnt > 0 ? 0 : 1;
    }
  }
  return out;
}
export const dilate = (m: Mask, r: number) => boxMorph(m, r, true);
export const erode = (m: Mask, r: number) => boxMorph(m, r, false);
export const open = (m: Mask, r: number) => dilate(erode(m, r), r);
export const close = (m: Mask, r: number) => erode(dilate(m, r), r);

/** Fill holes: background not connected to the border becomes foreground. */
export function fillHoles(m: Mask): Mask {
  const { width: w, height: h } = m;
  const seen = new Uint8Array(w * h);
  const stack: number[] = [];
  const push = (i: number) => { if (!seen[i] && !m.data[i]) { seen[i] = 1; stack.push(i); } };
  for (let x = 0; x < w; x++) { push(x); push((h - 1) * w + x); }
  for (let y = 0; y < h; y++) { push(y * w); push(y * w + w - 1); }
  while (stack.length) {
    const i = stack.pop()!, x = i % w, y = (i - x) / w;
    if (x > 0) push(i - 1); if (x < w - 1) push(i + 1); if (y > 0) push(i - w); if (y < h - 1) push(i + w);
  }
  const out = mask(w, h);
  for (let i = 0; i < w * h; i++) out.data[i] = m.data[i] || !seen[i] ? 1 : 0;
  return out;
}

export interface Component { id: number; area: number; x0: number; y0: number; x1: number; y1: number; touchesBorder: boolean; cx: number; cy: number }

/** 4-connected component labelling. Labels start at 1. */
export function components(m: Mask): { labels: Int32Array; comps: Component[] } {
  const { width: w, height: h } = m;
  const labels = new Int32Array(w * h);
  const comps: Component[] = [];
  const stack: number[] = [];
  for (let s = 0; s < w * h; s++) {
    if (!m.data[s] || labels[s]) continue;
    const id = comps.length + 1;
    const c: Component = { id, area: 0, x0: w, y0: h, x1: 0, y1: 0, touchesBorder: false, cx: 0, cy: 0 };
    labels[s] = id; stack.push(s);
    while (stack.length) {
      const i = stack.pop()!, x = i % w, y = (i - x) / w;
      c.area++; c.cx += x; c.cy += y;
      if (x < c.x0) c.x0 = x; if (x > c.x1) c.x1 = x; if (y < c.y0) c.y0 = y; if (y > c.y1) c.y1 = y;
      if (x === 0 || y === 0 || x === w - 1 || y === h - 1) c.touchesBorder = true;
      const nb = [x > 0 ? i - 1 : -1, x < w - 1 ? i + 1 : -1, y > 0 ? i - w : -1, y < h - 1 ? i + w : -1];
      for (const j of nb) if (j >= 0 && m.data[j] && !labels[j]) { labels[j] = id; stack.push(j); }
    }
    c.cx /= c.area; c.cy /= c.area;
    comps.push(c);
  }
  return { labels, comps };
}

/** Exact Euclidean distance transform (Felzenszwalb-Huttenlocher), distance to nearest background pixel. */
export function distanceTransform(m: Mask): Float32Array {
  const { width: w, height: h } = m;
  const INF = 1e20;
  const d = new Float64Array(w * h);
  for (let i = 0; i < w * h; i++) d[i] = m.data[i] ? INF : 0;
  const n = Math.max(w, h);
  const f = new Float64Array(n), z = new Float64Array(n + 1), v = new Int32Array(n), out = new Float64Array(n);
  const pass = (len: number) => {
    let k = 0; v[0] = 0; z[0] = -INF; z[1] = INF;
    for (let q = 1; q < len; q++) {
      let s = (f[q] + q * q - (f[v[k]] + v[k] * v[k])) / (2 * q - 2 * v[k]);
      while (s <= z[k]) { k--; s = (f[q] + q * q - (f[v[k]] + v[k] * v[k])) / (2 * q - 2 * v[k]); }
      k++; v[k] = q; z[k] = s; z[k + 1] = INF;
    }
    k = 0;
    for (let q = 0; q < len; q++) { while (z[k + 1] < q) k++; out[q] = (q - v[k]) ** 2 + f[v[k]]; }
  };
  for (let x = 0; x < w; x++) { for (let y = 0; y < h; y++) f[y] = d[y * w + x]; pass(h); for (let y = 0; y < h; y++) d[y * w + x] = out[y]; }
  for (let y = 0; y < h; y++) { for (let x = 0; x < w; x++) f[x] = d[y * w + x]; pass(w); for (let x = 0; x < w; x++) d[y * w + x] = out[x]; }
  const r = new Float32Array(w * h);
  for (let i = 0; i < w * h; i++) r[i] = Math.sqrt(d[i]);
  return r;
}

/** Otsu threshold on values in [0, maxV]. */
export function otsu(values: ArrayLike<number>, maxV: number, bins = 128): number {
  const hist = new Float64Array(bins);
  let n = 0;
  for (let i = 0; i < values.length; i++) { const b = Math.min(bins - 1, Math.max(0, Math.floor((values[i] / maxV) * bins))); hist[b]++; n++; }
  let sum = 0;
  for (let i = 0; i < bins; i++) sum += i * hist[i];
  let sumB = 0, wB = 0, best = 0, thr = 0;
  for (let i = 0; i < bins; i++) {
    wB += hist[i]; if (!wB) continue;
    const wF = n - wB; if (!wF) break;
    sumB += i * hist[i];
    const mB = sumB / wB, mF = (sum - sumB) / wF;
    const between = wB * wF * (mB - mF) ** 2;
    if (between > best) { best = between; thr = i; }
  }
  return ((thr + 1) / bins) * maxV;
}
