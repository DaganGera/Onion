import { DEFECTS, heightCorrect, predictWeight, sizeSigmaMm, type BulbMeasurement, type Defect, type WeightModel, DEFAULT_WEIGHT_MODEL } from '@parakh/core';
import { calibFromCoin, calibFromIntrinsics, calibFromMarkers, detectA4, detectAruco, toPlane, type Calibration } from './calib';
import { TIER0 } from './config';
import { convexHull, feret, polygonArea, type Pt } from './geom';
import { downscale, mask, median, toLab, type Lab, type Mask, type RGBA } from './img';
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
  const { img, s } = downscale(original, TIER0.workSide);
  const { width: w, height: h } = img;
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

  const filled = assignEnclosedHoles(ws, fg);
  const bulbs = measureBulbs(ws, filled, lab, calib, opts.weightModel ?? DEFAULT_WEIGHT_MODEL);
  t.defects = now() - t0;
  return { width: w, height: h, scale: s, calib, bulbs, timings: t };
}

function segment(lab: Lab, calib: Calibration, a4: Calibration | null): Mask {
  const { width: w, height: h } = lab;
  const n = w * h;
  const bgModels: [number, number, number][] = [];
  // Border ring model.
  const ring: number[] = [];
  const bw = Math.max(2, Math.round(TIER0.seg.borderFrac * Math.min(w, h)));
  for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) if (x < bw || y < bw || x >= w - bw || y >= h - bw) ring.push(y * w + x);
  const med = (idx: number[], arr: Float32Array) => { const v = Float32Array.from(idx, (i) => arr[i]).sort(); return v[v.length >> 1] ?? 0; };
  bgModels.push([med(ring, lab.L), med(ring, lab.a), med(ring, lab.b)]);
  // Sheet (A4 or printed mat) is usually the background right under the onions.
  if (a4?.sheet) {
    const q = a4.sheet;
    const cx = q.reduce((s, p) => s + p.x, 0) / 4, cy = q.reduce((s, p) => s + p.y, 0) / 4;
    const idx: number[] = [];
    for (let y = Math.round(cy - h * 0.05); y < cy + h * 0.05; y++) for (let x = Math.round(cx - w * 0.05); x < cx + w * 0.05; x++) {
      const i = y * w + x;
      if (i >= 0 && i < n && lab.L[i] > 68 && Math.hypot(lab.a[i], lab.b[i]) < 18) idx.push(i);
    }
    if (idx.length > 20) bgModels.push([med(idx, lab.L), med(idx, lab.a), med(idx, lab.b)]);
  }
  // Distance with lightness down-weighted, so soft shadows on the sheet stay background.
  const kL = 0.45;
  const d = new Float32Array(n);
  for (let i = 0; i < n; i++) {
    let best = Infinity;
    for (const [L, a, b] of bgModels) best = Math.min(best, Math.hypot(kL * (lab.L[i] - L), lab.a[i] - a, lab.b[i] - b));
    d[i] = best;
  }
  let thr: number = TIER0.seg.minDeltaE;
  { // Otsu on the distance histogram, but never below the floor.
    const hist = new Float64Array(100);
    for (let i = 0; i < n; i++) hist[Math.min(99, Math.floor(d[i]))]++;
    let sum = 0; for (let i = 0; i < 100; i++) sum += i * hist[i];
    let sB = 0, wB = 0, best = 0, o = 0;
    for (let i = 0; i < 100; i++) { wB += hist[i]; if (!wB) continue; const wF = n - wB; if (!wF) break; sB += i * hist[i]; const m = (sB / wB - (sum - sB) / wF); const bt = wB * wF * m * m; if (bt > best) { best = bt; o = i; } }
    thr = Math.max(thr, Math.min(o, 40));
  }
  let m = mask(w, h);
  // Cast shadows and crevices between touching bulbs: dark, near-neutral, darker than the background.
  const bgL = Math.max(...bgModels.map((b) => b[0]));
  for (let i = 0; i < n; i++) {
    const C = Math.hypot(lab.a[i], lab.b[i]);
    // Near-black is mould on a bulb, not a cast shadow on a light background.
    const shadow = C < TIER0.seg.shadowMaxC && lab.L[i] < bgL - 12 && lab.L[i] < TIER0.seg.shadowMaxL && lab.L[i] > Math.max(TIER0.seg.shadowMinL, 0.38 * bgL);
    m.data[i] = d[i] > thr && !shadow ? 1 : 0;
  }
  // Remove calibration targets from the foreground.
  for (const poly of calib.exclude) fillPoly(m, grow(poly, 1.35), 0);
  m = open(close(m, TIER0.seg.closeR), TIER0.seg.openR);
  m = fillSmallHoles(m, TIER0.seg.smallHoleFrac * n);
  // Drop tiny specks.
  const { labels, comps } = components(m);
  const minA = TIER0.seg.minAreaFrac * n;
  const keep = new Uint8Array(comps.length + 1);
  for (const c of comps) keep[c.id] = c.area >= minA ? 1 : 0;
  for (let i = 0; i < n; i++) if (labels[i] && !keep[labels[i]]) m.data[i] = 0;
  return m;
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
      else if (dL > D.brightDL) c = C < rC * D.sunburnMaxCRatio || Math.abs(angDiff(hue, rH)) > 25 ? CODE.sunburn : CODE.peeled;
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
    const excluded = edge ? 'edge' : aspect > TIER0.seg.maxAspect || solidity < TIER0.seg.minSolidity ? 'shape' : null;
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
