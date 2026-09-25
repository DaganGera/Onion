import { DEFECTS, heightCorrect, predictWeight, sizeSigmaMm, type BulbMeasurement, type Defect, type WeightModel, DEFAULT_WEIGHT_MODEL } from '@parakh/core';
import { calibFromCoin, calibFromIntrinsics, calibFromMarkers, detectA4, detectAruco, toPlane, type Calibration } from './calib';
import { TIER0 } from './config';
import { applyH, convexHull, feret, inv3, polygonArea, type Pt } from './geom';
import { downscale, mask, median, normalise, toLab, type Lab, type Mask, type RGBA } from './img';
import { close, components, distanceTransform, erode, open } from './morph';
import { watershedSplit } from './watershed';

/** Per-pixel defect codes in label crops. */
export const CODE = { bg: 0, healthy: 1, blackening: 2, rot: 3, sunburn: 4, spots: 5, sprouting: 6, peeled: 7, ignored: 8 } as const;
const CODE_OF: Record<Exclude<Defect, 'cut'>, number> = { blackening: 2, rot: 3, sunburn: 4, spots: 5, sprouting: 6, peeled: 7 };

export interface BulbResult {
  idx: number;
  hull: Pt[];                   // working px
  bbox: [number, number, number, number];
  centroid: Pt;
  excluded: null | 'edge' | 'shape' | 'small';
  areaPx: number;
  solidity: number;
  minMm: number; maxMm: number; sdMm: number;
  frac: Record<Defect, number | null>;  // 0..1
  fsd: number;                  // 0..1
  shape: { double: boolean; bottleneck: boolean; split: boolean };
  conf: number;                 // 0..1
  weightG: number; weightSdG: number;
  labels: { x0: number; y0: number; w: number; h: number; data: Uint8Array };
  /** Tier-1 learned cross-check: probability the bulb is unhealthy (absent when no model ran). */
  p1?: number;
  /** True when Tier 1 is confident the bulb is unhealthy but Tier 0 measured it clean: sent to a human. */
  disagree?: boolean;
}

export interface Analysis {
  width: number; height: number; scale: number;
  calib: Calibration;
  bulbs: BulbResult[];
  timings: Record<string, number>;
}

export interface AnalyzeOptions {
  coin?: { x: number; y: number; mm: number };  // tap in ORIGINAL image px
  camHmm?: number;                               // used by the intrinsics tier
  weightModel?: WeightModel;
}

const now = () => (typeof performance !== 'undefined' ? performance.now() : Date.now());

export function analyze(original: RGBA, opts: AnalyzeOptions = {}): Analysis {
  const t: Record<string, number> = {};
  let t0 = now();
  const { img: raw, s } = downscale(original, TIER0.workSide);
  const { width: w, height: h } = raw;
  const img = TIER0.normalise ? normalise(raw) : raw;
  const lab = toLab(img);
  t.prep = now() - t0; t0 = now();

  // ---- L2a calibration: best available tier ----
  const markers = detectAruco(img);
  let calib = calibFromMarkers(markers, w, h);
  const a4 = detectA4(lab);
  if (!calib && a4) calib = a4;
  if (!calib && opts.coin) calib = calibFromCoin(lab, { x: opts.coin.x * s, y: opts.coin.y * s }, opts.coin.mm);
  if (!calib) calib = calibFromIntrinsics(w, h, opts.camHmm);
  t.calib = now() - t0; t0 = now();

  // ---- L2b foreground: colour distance from background model(s) ----
  const fg = segment(lab, calib, a4);
  t.segment = now() - t0; t0 = now();

  // ---- split touching bulbs ----
  const { labels: compLabels } = components(fg);
  const dist = distanceTransform(fg);
  const ws = watershedSplit(fg, dist, compLabels, { minPeak: TIER0.seg.wsMinPeakFrac * Math.max(w, h), nms: TIER0.seg.wsNms });
  t.watershed = now() - t0; t0 = now();

  if (TIER0.seg.merge) mergeFragments(ws, w, h, calib);
  const filled = assignEnclosedHoles(ws, fg);
  const bulbs = measureBulbs(ws, filled, lab, calib, opts.weightModel ?? DEFAULT_WEIGHT_MODEL);
  t.defects = now() - t0;
  return { width: w, height: h, scale: s, calib, bulbs, timings: t };
}

/** k-means in Lab over a pixel sample: several background colours (wood grain, cloth folds). */
function kmeansLab(lab: Lab, idx: number[], k: number, minShare = 0): [number, number, number][] {
  const step = Math.max(1, Math.floor(idx.length / 4000));
  const pts: [number, number, number][] = [];
  for (let j = 0; j < idx.length; j += step) { const i = idx[j]; pts.push([lab.L[i], lab.a[i], lab.b[i]]); }
  if (!pts.length) return [];
  const c: [number, number, number][] = Array.from({ length: Math.min(k, pts.length) }, (_, q) => [...pts[Math.floor(((q + 0.5) * pts.length) / k)]] as [number, number, number]);
  for (let it = 0; it < 10; it++) {
    const acc = c.map(() => [0, 0, 0, 0]);
    for (const p of pts) {
      let bi = 0, bd = Infinity;
      c.forEach((q, qi) => { const d = (p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2 + (p[2] - q[2]) ** 2; if (d < bd) { bd = d; bi = qi; } });
      acc[bi][0] += p[0]; acc[bi][1] += p[1]; acc[bi][2] += p[2]; acc[bi][3]++;
    }
    acc.forEach((a, qi) => { if (a[3]) c[qi] = [a[0] / a[3], a[1] / a[3], a[2] / a[3]]; });
  }
  // Drop minor clusters: an onion touching the border must not become "background".
  const share = c.map(() => 0);
  for (const p of pts) { let bi = 0, bd = Infinity; c.forEach((q, qi) => { const d = (p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2 + (p[2] - q[2]) ** 2; if (d < bd) { bd = d; bi = qi; } }); share[bi]++; }
  const kept = c.filter((_, qi) => share[qi] >= minShare * pts.length);
  return kept.length ? kept : [c[share.indexOf(Math.max(...share))]];
}

/** Calibration sheet outline in image px (printed mat from its homography, or the detected A4 quad). */
export function sheetQuad(calib: Calibration, a4: Calibration | null): Pt[] | null {
  if (calib.tier === 'aruco' && calib.H) {
    const Hi = inv3(calib.H);
    return [{ x: 0, y: 0 }, { x: 297, y: 0 }, { x: 297, y: 210 }, { x: 0, y: 210 }].map((p) => applyH(Hi, p));
  }
  return a4?.sheet ?? null;
}

function segment(lab: Lab, calib: Calibration, a4: Calibration | null): Mask {
  const { width: w, height: h } = lab;
  const n = w * h;
  const S = TIER0.seg;
  // Background colours sampled from the image border (several clusters: wood grain, cloth, tiles).
  const ring: number[] = [];
  const bw = Math.max(2, Math.round(S.borderFrac * Math.min(w, h)));
  for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) if (x < bw || y < bw || x >= w - bw || y >= h - bw) ring.push(y * w + x);
  const bgModels = kmeansLab(lab, ring, S.bgClusters, S.bgMinShare);
  // The calibration sheet: its paper colour is background too, and so is everything printed on it.
  const quad = sheetQuad(calib, a4);
  const onSheet = mask(w, h);
  if (quad) {
    fillPoly(onSheet, grow(quad, 1.02), 1);
    const paper: number[] = [];
    for (let i = 0; i < n; i++) if (onSheet.data[i] && lab.L[i] > 60 && Math.hypot(lab.a[i], lab.b[i]) < 14) paper.push(i);
    if (paper.length > 50) bgModels.push(...kmeansLab(lab, paper, 1));
  }
  // Distance with lightness down-weighted, so soft shadows stay background.
  const kL = 0.45;
  const d = new Float32Array(n);
  for (let i = 0; i < n; i++) {
    let best = Infinity;
    for (const [L, a, b] of bgModels) best = Math.min(best, Math.hypot(kL * (lab.L[i] - L), lab.a[i] - a, lab.b[i] - b));
    d[i] = best;
  }
  let thr: number = S.minDeltaE;
  { // Otsu on the distance histogram, but never below the floor.
    const hist = new Float64Array(100);
    for (let i = 0; i < n; i++) hist[Math.min(99, Math.floor(d[i]))]++;
    let sum = 0; for (let i = 0; i < 100; i++) sum += i * hist[i];
    let sB = 0, wB = 0, best = 0, o = 0;
    for (let i = 0; i < 100; i++) { wB += hist[i]; if (!wB) continue; const wF = n - wB; if (!wF) break; sB += i * hist[i]; const m = (sB / wB - (sum - sB) / wF); const bt = wB * wF * m * m; if (bt > best) { best = bt; o = i; } }
    thr = Math.max(thr, Math.min(o, 40));
  }
  let m = mask(w, h);
  const bgL = Math.max(...bgModels.map((b) => b[0]));
  for (let i = 0; i < n; i++) {
    const C = Math.hypot(lab.a[i], lab.b[i]);
    const L = lab.L[i];
    // Grey, white and black (paper, printing, cables, shadows) are never onion skin.
    // Onion rot/mould inside a bulb is recovered later by the enclosed-hole fill.
    const a = lab.a[i], b = lab.b[i];
    // Grey/white only counts as background on the sheet (paper, print); pale onions elsewhere stay.
    // Black print/markers are on the sheet; off the sheet, dark patches may be mould on a bulb and must stay.
    const neutral = onSheet.data[i] && (C < S.sheetNeutralMaxC || (L < 35 && C < S.darkNeutralMaxC));
    // Onion skin is red, purple, pink, golden, brown or cream, never blue or cyan (paper tint, cables, bags).
    const cool = a < S.coolMaxA && b < S.coolMaxB;
    const shadow = C < S.shadowMaxC && L < bgL - 12 && L < S.shadowMaxL && L > Math.max(S.shadowMinL, 0.38 * bgL);
    m.data[i] = d[i] > thr && !neutral && !cool && !shadow ? 1 : 0;
  }
  for (const poly of calib.exclude) fillPoly(m, grow(poly, 1.35), 0);
  m = open(close(m, S.closeR), S.openR);
  m = fillSmallHoles(m, S.smallHoleFrac * n);
  // Keep only onion-sized, onion-coloured blobs.
  const { labels, comps } = components(m);
  const minA = S.minAreaFrac * n;
  const sumC = new Float64Array(comps.length + 1);
  for (let i = 0; i < n; i++) if (labels[i]) sumC[labels[i]] += Math.hypot(lab.a[i], lab.b[i]);
  const keep = new Uint8Array(comps.length + 1);
  for (const c of comps) keep[c.id] = c.area >= minA && sumC[c.id] / c.area >= S.minMeanC ? 1 : 0;
  for (let i = 0; i < n; i++) if (labels[i] && !keep[labels[i]]) m.data[i] = 0;
  return m;
}

/**
 * Rejoin pieces of one onion. Shadows, highlights or a crease can make the
 * watershed cut a bulb in two. Two touching regions are merged when their
 * union is still convex (one round bulb, not two touching bulbs, whose union
 * has a waist) and not larger than an onion. Greedy, longest shared border first.
 */
function mergeFragments(ws: Int32Array, w: number, h: number, calib: Calibration) {
  const n = ws.reduce((m, v) => Math.max(m, v), 0);
  if (n < 2) return;
  const GAP = Math.max(2, Math.round(Math.max(w, h) / 200));
  const area = new Float64Array(n + 1);
  const pts: Pt[][] = Array.from({ length: n + 1 }, () => []);
  const border = new Map<number, number>();
  for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
    const i = y * w + x, a = ws[i];
    if (!a) continue;
    area[a]++;
    const r = x < w - 1 ? ws[i + 1] : 0, d = y < h - 1 ? ws[i + w] : 0;
    const l = x > 0 ? ws[i - 1] : 0, u = y > 0 ? ws[i - w] : 0;
    if (r !== a || d !== a || l !== a || u !== a) pts[a].push({ x, y });
    // Neighbours within a small gap count as touching (a crease or glare line can leave a thin gap).
    for (let g = 1; g <= GAP; g++) {
      const bs = [x + g < w ? ws[i + g] : 0, y + g < h ? ws[i + g * w] : 0];
      for (const b of bs) if (b && b !== a) { const k = a < b ? a * 65536 + b : b * 65536 + a; border.set(k, (border.get(k) ?? 0) + 1); }
    }
  }
  const parent = Array.from({ length: n + 1 }, (_, i) => i);
  const find = (i: number): number => (parent[i] === i ? i : (parent[i] = find(parent[i])));
  const hulls = new Map<number, Pt[]>();
  const hullOf = (r: number) => { if (!hulls.has(r)) hulls.set(r, convexHull(pts[r])); return hulls.get(r)!; };
  const mmPerPx = calib.tier !== 'intrinsics' ? calib.mmPerPx : 0;
  const pairs = [...border.entries()].sort((p, q) => q[1] - p[1]);
  for (const [k, len] of pairs) {
    const a = find(Math.floor(k / 65536)), b = find(k % 65536);
    if (a === b || len < 4) continue;
    const hull = convexHull([...hullOf(a), ...hullOf(b)]);
    const union = area[a] + area[b];
    const solidity = union / Math.max(1, polygonArea(hull));
    const f = feret(hull);
    const tooBig = mmPerPx ? f.max * mmPerPx > TIER0.seg.maxDiamMm : false;
    const elongated = f.min > 0 && f.max / f.min > 1.6;
    // A bulb cut in two shares a long seam (a chord); two touching bulbs meet at a short neck.
    const contact = len / GAP;
    const smaller = feret(area[a] < area[b] ? hullOf(a) : hullOf(b)).min;
    const longSeam = contact >= TIER0.seg.mergeMinSeam * smaller;
    if (solidity < TIER0.seg.mergeMinSolidity || !longSeam || tooBig || elongated) continue;
    parent[b] = a;
    area[a] = union;
    pts[a] = hull;
    hulls.set(a, hull);
  }
  for (let i = 0; i < ws.length; i++) if (ws[i]) ws[i] = find(ws[i]);
}

/** Fill background holes smaller than maxArea (specks inside a bulb). */
function fillSmallHoles(m: Mask, maxArea: number): Mask {
  const inv = mask(m.width, m.height);
  for (let i = 0; i < inv.data.length; i++) inv.data[i] = m.data[i] ? 0 : 1;
  const { labels, comps } = components(inv);
  const fill = new Uint8Array(comps.length + 1);
  for (const c of comps) fill[c.id] = !c.touchesBorder && c.area <= maxArea ? 1 : 0;
  const out = mask(m.width, m.height);
  for (let i = 0; i < out.data.length; i++) out.data[i] = m.data[i] || fill[labels[i]] ? 1 : 0;
  return out;
}

/**
 * A hole (e.g. a dark rot patch removed as "shadow") that is enclosed by ONE
 * bulb belongs to that bulb. A hole bordered by several bulbs is a crevice
 * between them and stays background. Mutates ws; returns the new foreground.
 */
function assignEnclosedHoles(ws: Int32Array, fg: Mask): Mask {
  const { width: w, height: h } = fg;
  const inv = mask(w, h);
  for (let i = 0; i < w * h; i++) inv.data[i] = fg.data[i] ? 0 : 1;
  const { labels, comps } = components(inv);
  const owner = new Int32Array(comps.length + 1).fill(-1); // -1 unknown, 0 multi/border
  for (const c of comps) if (c.touchesBorder) owner[c.id] = 0;
  for (let i = 0; i < w * h; i++) {
    const hl = labels[i];
    if (!hl || owner[hl] === 0) continue;
    const x = i % w, y = (i - x) / w;
    for (const j of [x > 0 ? i - 1 : -1, x < w - 1 ? i + 1 : -1, y > 0 ? i - w : -1, y < h - 1 ? i + w : -1]) {
      if (j < 0 || !fg.data[j]) continue;
      const r = ws[j];
      if (!r) continue;
      if (owner[hl] === -1) owner[hl] = r; else if (owner[hl] !== r) owner[hl] = 0;
    }
  }
  const out = mask(w, h);
  for (let i = 0; i < w * h; i++) {
    const hl = labels[i];
    if (fg.data[i]) out.data[i] = 1;
    else if (hl && owner[hl] > 0) { out.data[i] = 1; ws[i] = owner[hl]; }
  }
  return out;
}

function grow(poly: Pt[], k: number): Pt[] {
  const cx = poly.reduce((s, p) => s + p.x, 0) / poly.length, cy = poly.reduce((s, p) => s + p.y, 0) / poly.length;
  return poly.map((p) => ({ x: cx + (p.x - cx) * k, y: cy + (p.y - cy) * k }));
}

function fillPoly(m: Mask, poly: Pt[], v: number) {
  const ys = poly.map((p) => p.y);
  const y0 = Math.max(0, Math.floor(Math.min(...ys))), y1 = Math.min(m.height - 1, Math.ceil(Math.max(...ys)));
  for (let y = y0; y <= y1; y++) {
    const xs: number[] = [];
    for (let i = 0; i < poly.length; i++) {
      const a = poly[i], b = poly[(i + 1) % poly.length];
      if ((a.y <= y && b.y > y) || (b.y <= y && a.y > y)) xs.push(a.x + ((y - a.y) / (b.y - a.y)) * (b.x - a.x));
    }
    xs.sort((p, q) => p - q);
    for (let k = 0; k + 1 < xs.length; k += 2) for (let x = Math.max(0, Math.ceil(xs[k])); x <= Math.min(m.width - 1, Math.floor(xs[k + 1])); x++) m.data[y * m.width + x] = v;
  }
}

function measureBulbs(ws: Int32Array, fg: Mask, lab: Lab, calib: Calibration, wm: WeightModel): BulbResult[] {
  const { width: w, height: h } = lab;
  const D = TIER0.defects;
  const inner = erode(fg, D.erode);
  const nLab = ws.reduce((m, v) => Math.max(m, v), 0);
  const px: number[][] = Array.from({ length: nLab + 1 }, () => []);
  for (let i = 0; i < w * h; i++) if (ws[i]) px[ws[i]].push(i);
  const out: BulbResult[] = [];

  for (let k = 1; k <= nLab; k++) {
    const P = px[k];
    if (P.length < 30) continue;
    let x0 = w, y0 = h, x1 = 0, y1 = 0, cx = 0, cy = 0, edge = false;
    const boundary: Pt[] = [];
    for (const i of P) {
      const x = i % w, y = (i - x) / w;
      cx += x; cy += y;
      if (x < x0) x0 = x; if (x > x1) x1 = x; if (y < y0) y0 = y; if (y > y1) y1 = y;
      if (x === 0 || y === 0 || x === w - 1 || y === h - 1) edge = true;
      if (x === 0 || x === w - 1 || y === 0 || y === h - 1 || ws[i - 1] !== k || ws[i + 1] !== k || ws[i - w] !== k || ws[i + w] !== k) boundary.push({ x, y });
    }
    cx /= P.length; cy /= P.length;
    const hull = convexHull(boundary);
    const hullArea = Math.max(1, polygonArea(hull));
    const solidity = Math.min(1, P.length / hullArea);
    const fpx = feret(hull);
    const aspect = fpx.min > 0 ? fpx.max / fpx.min : 99;

    // Size in plane mm via the calibration, then the equator-height correction.
    const hullMm = convexHull(hull.map((p) => toPlane(calib, p)));
    const fm = feret(hullMm);
    const minMm = heightCorrect(fm.min, calib.camHmm), maxMm = heightCorrect(fm.max, calib.camHmm);
    const meanMm = (minMm + maxMm) / 2;
    const sdMm = sizeSigmaMm(meanMm, calib.tier, calib.mmPerPx, calib.camHmm, calib.camHsdMm);

    // ---- per-bulb colour model: reference = mid/upper-lightness pixels ----
    const Pin = P.filter((i) => inner.data[i]);
    const use = Pin.length > 40 ? Pin : P;
    const Ls = Float32Array.from(use, (i) => lab.L[i]).sort();
    const lo = Ls[Math.floor(D.refLo * (Ls.length - 1))], hi = Ls[Math.floor(D.refHi * (Ls.length - 1))];
    const refIdx = use.filter((i) => lab.L[i] >= lo && lab.L[i] <= hi);
    const mid = (arr: Float32Array) => { const v = Float32Array.from(refIdx, (i) => arr[i]).sort(); return v[v.length >> 1] ?? 0; };
    const rL = mid(lab.L), ra = mid(lab.a), rb = mid(lab.b);
    const rC = Math.hypot(ra, rb), rH = (Math.atan2(rb, ra) * 180) / Math.PI;
    // Shading model: light usually comes from one side, and a sphere darkens
    // toward its rim. Fit L = a + b*x + c*y on the healthy-looking pixels, then
    // take per-ring medians of the residual. Defects are deviations from THIS
    // bulb's own lit skin, not from a fixed colour.
    const R0 = Math.sqrt(P.length / Math.PI);
    let sxx = 0, sxy = 0, syy = 0, sxl = 0, syl = 0, sl = 0, nn = 0;
    for (const i of refIdx) {
      const x = (i % w) - cx, y = Math.floor(i / w) - cy, L = lab.L[i];
      sxx += x * x; sxy += x * y; syy += y * y; sxl += x * L; syl += y * L; sl += L; nn++;
    }
    const det = sxx * syy - sxy * sxy;
    const gx = nn > 20 && Math.abs(det) > 1e-6 ? (sxl * syy - syl * sxy) / det : 0;
    const gy = nn > 20 && Math.abs(det) > 1e-6 ? (syl * sxx - sxl * sxy) / det : 0;
    const plane = (x: number, y: number) => rL + gx * (x - cx) + gy * (y - cy);
    const RINGS = [0.35, 0.55, 0.72, 0.86, 2];
    const ringOf = (x: number, y: number) => { const r = Math.hypot(x - cx, y - cy) / R0; let k = 0; while (k < RINGS.length - 1 && r > RINGS[k]) k++; return k; };
    const ringVals: number[][] = RINGS.map(() => []);
    for (const i of refIdx) { const x = i % w, y = (i - x) / w; ringVals[ringOf(x, y)].push(lab.L[i] - plane(x, y)); }
    const ringOff = ringVals.map((v) => (v.length > 30 ? Math.min(4, median(v)) : 0));
    const expectL = (x: number, y: number) => plane(x, y) + ringOff[ringOf(x, y)];
    const saturatedSkin = rC > D.specMinRefC;
    const bw = x1 - x0 + 1, bh = y1 - y0 + 1;
    const codes = new Uint8Array(bw * bh);
    for (const i of P) {
      const x = i % w, y = (i - x) / w, o = (y - y0) * bw + (x - x0);
      const rho = Math.hypot(x - cx, y - cy) / R0;
      if (!inner.data[i] || rho > D.rimRho) { codes[o] = CODE.ignored; continue; }
      const L = lab.L[i], a = lab.a[i], b = lab.b[i];
      const C = Math.hypot(a, b), hue = (Math.atan2(b, a) * 180) / Math.PI, dL = L - expectL(x, y);
      let c: number = CODE.healthy;
      if (L > 96 || (saturatedSkin && C < D.specMaxC && dL > D.specDL)) c = CODE.ignored; // specular highlight on glossy skin
      else if (hue >= D.sproutMinHue && hue <= D.sproutMaxHue && C >= D.sproutMinC && a < -4) c = CODE.sprouting;
      else if ((C < D.blackAbsC && L < D.blackAbsL) || (C < D.blackMaxC && dL < -D.blackDL && L < D.blackMaxL)) c = CODE.blackening;
      else if (dL < -D.rotDL && C >= D.rotMinC && hue >= D.rotMinHue && hue <= D.rotMaxHue) c = CODE.rot; // brown, not shaded purple
      else if (dL > D.brightDL) {
        // Pale patch: bleached and yellow-shifted = sunburn; much paler than the skin with the same hue = peeled
        // (flesh under a lost tunic). Natural paler streaks on red skin stay healthy.
        if (C < rC * D.sunburnMaxCRatio || Math.abs(angDiff(hue, rH)) > 25) c = CODE.sunburn;
        else if (dL > D.peelDL && C < rC * D.peelMaxCRatio) c = CODE.peeled;
      }
      else if (Math.hypot(dL, a - ra, b - rb) > D.spotDE) c = CODE.spots;
      codes[o] = c;
    }
    despeckle(codes, bw, bh, Math.max(D.minBlob, Math.round(D.minBlobFrac * P.length)));

    // Sphere-model area weighting: projected pixels near the rim cover more surface.
    const R = Math.sqrt(P.length / Math.PI);
    const acc = new Float64Array(9);
    for (const i of P) {
      const x = i % w, y = (i - x) / w;
      const c = codes[(y - y0) * bw + (x - x0)];
      if (c === CODE.ignored || c === CODE.bg) continue;
      const rho = Math.min(D.rhoCap, Math.hypot(x - cx, y - cy) / R);
      acc[c] += 1 / Math.sqrt(1 - rho * rho);
    }
    const tot = acc[1] + acc[2] + acc[3] + acc[4] + acc[5] + acc[6] + acc[7];
    const frac = {} as Record<Defect, number | null>;
    for (const d of DEFECTS) frac[d] = d === 'cut' ? null : tot > 0 ? acc[CODE_OF[d as Exclude<Defect, 'cut'>]] / tot : 0;

    let conf = 0.95;
    if (P.length < TIER0.conf.minPx) conf -= 0.35;
    if (solidity < 0.8) conf -= 0.25;
    if (refIdx.length < 50) conf -= 0.2;
    if (calib.tier === 'intrinsics') conf -= 0.05;
    // With a real scale (mat, sheet or coin), a blob outside the onion size window is not an onion.
    const realScale = calib.tier !== 'intrinsics';
    const sizeOut = realScale && (maxMm < TIER0.seg.minDiamMm || minMm > TIER0.seg.maxDiamMm);
    const greenBlob = (frac.sprouting ?? 0) > 0.6; // mostly green: a leaf, sprout or bag, not a bulb
    const excluded = edge ? 'edge' : sizeOut ? 'small' : greenBlob ? 'shape' : aspect > TIER0.seg.maxAspect || solidity < TIER0.seg.minSolidity ? 'shape' : null;
    const { g, sdG } = predictWeight(meanMm, wm);
    out.push({
      idx: out.length, hull, bbox: [x0, y0, x1, y1], centroid: { x: cx, y: cy }, excluded, areaPx: P.length, solidity,
      minMm, maxMm, sdMm, frac, fsd: D.fsdBase / 1000,
      shape: { double: solidity < TIER0.shape.doubleSolidity, split: solidity < TIER0.shape.splitSolidity, bottleneck: aspect > TIER0.shape.bottleneckAspect },
      conf: Math.max(0.05, conf), weightG: g, weightSdG: sdG,
      labels: { x0, y0, w: bw, h: bh, data: codes },
    });
  }
  return out;
}

const angDiff = (a: number, b: number) => ((a - b + 540) % 360) - 180;

/** Defect blobs smaller than minBlob px revert to healthy. */
function despeckle(codes: Uint8Array, w: number, h: number, minBlob: number) {
  const seen = new Uint8Array(w * h);
  for (let s = 0; s < w * h; s++) {
    const c = codes[s];
    if (seen[s] || c < 2 || c > 7) continue;
    const blob = [s], stack = [s];
    seen[s] = 1;
    while (stack.length) {
      const i = stack.pop()!, x = i % w, y = (i - x) / w;
      for (const j of [x > 0 ? i - 1 : -1, x < w - 1 ? i + 1 : -1, y > 0 ? i - w : -1, y < h - 1 ? i + w : -1]) {
        if (j >= 0 && !seen[j] && codes[j] === c) { seen[j] = 1; stack.push(j); blob.push(j); }
      }
    }
    if (blob.length < minBlob) for (const i of blob) codes[i] = CODE.healthy;
  }
}

/** Quantise a vision result into the integer record the grading core adjudicates. */
export function toMeasurement(b: BulbResult, id: string, tray: number, look: number): BulbMeasurement {
  const pm = (x: number | null) => (x === null ? null : Math.round(x * 1000));
  const frac = {} as BulbMeasurement['frac'];
  for (const d of DEFECTS) frac[d] = pm(b.frac[d]);
  return {
    id, tray, look,
    size: { min: Math.round(b.minMm * 10), max: Math.round(b.maxMm * 10), sd: Math.max(1, Math.round(b.sdMm * 10)) },
    frac, fsd: Math.round(b.fsd * 1000), shape: { ...b.shape }, conf: Math.round(b.conf * 1000),
    w: Math.min(65535, Math.round(b.weightG * 10)), wsd: Math.min(65535, Math.round(b.weightSdG * 10)),
  };
}

/** Square bulb crop (Tier-1 input), nearest-neighbour, same geometry as tools/extract_crops.ts. */
export function bulbCrop(work: RGBA, b: BulbResult, size: number): Uint8ClampedArray {
  const [x0, y0, x1, y1] = b.bbox;
  const side = Math.round(Math.max(x1 - x0, y1 - y0) * 1.1);
  const cx = (x0 + x1) / 2, cy = (y0 + y1) / 2;
  const out = new Uint8ClampedArray(size * size * 4);
  for (let y = 0; y < size; y++) for (let x = 0; x < size; x++) {
    const sx = Math.round(cx - side / 2 + ((x + 0.5) * side) / size), sy = Math.round(cy - side / 2 + ((y + 0.5) * side) / size);
    const o = (y * size + x) * 4;
    if (sx >= 0 && sy >= 0 && sx < work.width && sy < work.height) { const i = (sy * work.width + sx) * 4; out[o] = work.data[i]; out[o + 1] = work.data[i + 1]; out[o + 2] = work.data[i + 2]; }
    out[o + 3] = 255;
  }
  return out;
}

/**
 * Fold a Tier-1 probability into a bulb. Only one direction changes anything:
 * the learned model is confident the bulb is unhealthy while the colour model
 * found neither rot nor blackening. Then the bulb goes to a human (low
 * confidence -> REFER); the colour model's measurements stay as they are.
 */
export function applyTier1(b: BulbResult, p: number, thrHigh: number) {
  b.p1 = p;
  const t0 = (b.frac.rot ?? 0) + (b.frac.blackening ?? 0);
  if (p >= thrHigh && t0 < 0.01) { b.disagree = true; b.conf = Math.min(b.conf, 0.45); }
}

/**
 * Cheap scan for the live Capture Guard (~360 px): is a calibration target
 * visible, and roughly how many bulbs are in frame. No defect analysis.
 */
export function quickScan(original: RGBA): { target: 'aruco' | 'a4' | null; bulbs: number } {
  const { img } = downscale(original, 360);
  const lab = toLab(img);
  const markers = detectAruco(img);
  const a4 = markers.length ? null : detectA4(lab);
  const calib = markers.length ? calibFromMarkers(markers, img.width, img.height)! : a4 ?? calibFromIntrinsics(img.width, img.height);
  const fg = segment(lab, calib, a4);
  const { comps } = components(fg);
  const bulbs = comps.filter((c) => !c.touchesBorder && c.area > 0.004 * img.width * img.height).length;
  return { target: markers.length ? 'aruco' : a4 ? 'a4' : null, bulbs };
}
