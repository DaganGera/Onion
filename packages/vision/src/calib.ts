import { AR } from '../vendor/aruco/index.js';
import { TIER_SCALE_SD, type CalibrationTier } from '@parakh/core';
import { TIER0 } from './config';
import { applyH, convexHull, feret, homography, localScale, polygonArea, type H3, type Pt } from './geom';
import { components } from './morph';
import { mask, type Lab, type RGBA } from './img';

/** Legacy printed mat (legacy/app/mat_layout.py): A4 landscape, 8 x 40 mm DICT_4X4_50 markers, IDs 0-7. */
const M = 40, L = 12, R = 297 - 12 - 40, CX = (297 - 40) / 2, T = 12, B = 210 - 12 - 40, CY = (210 - 40) / 2;
export const MAT_ORIGINS: Record<number, [number, number]> = {
  0: [L, T], 1: [CX, T], 2: [R, T], 3: [L, CY], 4: [R, CY], 5: [L, B], 6: [CX, B], 7: [R, B],
};

export interface Calibration {
  tier: CalibrationTier;
  H: H3 | null;           // image px (working res) -> plane mm
  mmPerPx: number;        // at image centre
  camHmm: number;
  camHsdMm: number;
  scaleSd: number;        // relative
  markers: { id: number; corners: Pt[] }[];
  sheet: Pt[] | null;     // A4 corners in working px
  exclude: Pt[][];        // polygons to ignore during segmentation (markers, coin)
  note: string;
}

const fPx = (w: number) => w / (2 * Math.tan((TIER0.intrinsics.hfovDeg * Math.PI) / 360));

function finish(tier: CalibrationTier, H: H3 | null, mmPerPx: number, w: number, h: number, extra: Partial<Calibration>): Calibration {
  // Camera height from focal length (FOV prior, ASSUMED A-FOV-1) and plane scale at the image centre.
  const s = H ? localScale(H, { x: w / 2, y: h / 2 }) : mmPerPx;
  const camH = tier === 'intrinsics' ? TIER0.intrinsics.defaultCamHmm : fPx(w) * s;
  return {
    tier, H, mmPerPx: s, camHmm: camH, camHsdMm: camH * TIER0.intrinsics.camHsdFrac,
    scaleSd: TIER_SCALE_SD[tier], markers: [], sheet: null, exclude: [], note: '', ...extra,
  };
}

export function detectAruco(img: RGBA): { id: number; corners: Pt[] }[] {
  const det = new AR.Detector({ dictionaryName: 'ARUCO_4X4_1000', maxHammingDistance: 1 });
  return det.detect(img).filter((m) => m.id in MAT_ORIGINS).map((m) => ({ id: m.id, corners: m.corners.map((c) => ({ x: c.x, y: c.y })) }));
}

export function calibFromMarkers(markers: { id: number; corners: Pt[] }[], w: number, h: number): Calibration | null {
  if (!markers.length) return null;
  const src: Pt[] = [], dst: Pt[] = [];
  for (const m of markers) {
    const [ox, oy] = MAT_ORIGINS[m.id];
    const plane = [{ x: ox, y: oy }, { x: ox + M, y: oy }, { x: ox + M, y: oy + M }, { x: ox, y: oy + M }];
    m.corners.forEach((c, i) => { src.push(c); dst.push(plane[i]); });
  }
  const H = homography(src, dst);
  // One marker = 4 points: homography is exact but fragile; widen the uncertainty.
  const cal = finish('aruco', H, 0, w, h, { markers, exclude: markers.map((m) => m.corners), note: `${markers.length} marker(s)` });
  if (markers.length < 2) cal.scaleSd *= 2;
  return cal;
}

/** Plain A4 sheet: largest bright, low-chroma region whose hull is a convincing quadrilateral. */
export function detectA4(lab: Lab): Calibration | null {
  const { width: w, height: h } = lab;
  const m = mask(w, h);
  for (let i = 0; i < w * h; i++) m.data[i] = lab.L[i] > 68 && Math.hypot(lab.a[i], lab.b[i]) < 18 ? 1 : 0;
  const { labels, comps } = components(m);
  const big = comps.filter((c) => c.area > 0.04 * w * h && !(c.x0 === 0 && c.y0 === 0 && c.x1 === w - 1 && c.y1 === h - 1)).sort((a, b) => b.area - a.area)[0];
  if (!big) return null;
  const pts: Pt[] = [];
  for (let y = big.y0; y <= big.y1; y++) {
    let first = -1, last = -1;
    for (let x = big.x0; x <= big.x1; x++) if (labels[y * w + x] === big.id) { if (first < 0) first = x; last = x; }
    if (first >= 0) { pts.push({ x: first, y }); pts.push({ x: last, y }); }
  }
  const hull = convexHull(pts);
  const quad = bestQuad(hull);
  if (!quad) return null;
  const qa = polygonArea(quad), ha = polygonArea(hull);
  if (qa / ha < 0.93) return null; // hull is not quadrilateral enough
  const e = quad.map((p, i) => Math.hypot(quad[(i + 1) % 4].x - p.x, quad[(i + 1) % 4].y - p.y));
  const long = (e[0] + e[2]) / 2, short = (e[1] + e[3]) / 2;
  const ratio = Math.max(long, short) / Math.min(long, short);
  if (ratio < 1.15 || ratio > 1.9) return null; // A4 is 1.414; allow perspective
  const plane = long >= short
    ? [{ x: 0, y: 0 }, { x: 297, y: 0 }, { x: 297, y: 210 }, { x: 0, y: 210 }]
    : [{ x: 0, y: 0 }, { x: 210, y: 0 }, { x: 210, y: 297 }, { x: 0, y: 297 }];
  const H = homography(quad, plane);
  return finish('a4', H, 0, w, h, { sheet: quad, note: `A4 ratio ${ratio.toFixed(2)}` });
}

/** Quadrilateral from hull: the 4 hull points extreme along the diagonals, ordered TL, TR, BR, BL. */
function bestQuad(hull: Pt[]): Pt[] | null {
  if (hull.length < 4) return null;
  const pick = (f: (p: Pt) => number) => hull.reduce((a, b) => (f(b) > f(a) ? b : a));
  const tl = pick((p) => -p.x - p.y), tr = pick((p) => p.x - p.y), br = pick((p) => p.x + p.y), bl = pick((p) => -p.x + p.y);
  const q = [tl, tr, br, bl];
  if (new Set(q).size < 4) return null;
  return q;
}

/** Coin tier: the user taps the coin; region-grow from the tap in Lab and use the equivalent-circle diameter. */
export function calibFromCoin(lab: Lab, tap: Pt, coinMm: number): Calibration | null {
  const { width: w, height: h } = lab;
  const x0 = Math.round(tap.x), y0 = Math.round(tap.y);
  if (x0 < 0 || y0 < 0 || x0 >= w || y0 >= h) return null;
  const i0 = y0 * w + x0;
  const ref = { L: lab.L[i0], a: lab.a[i0], b: lab.b[i0] };
  const seen = new Uint8Array(w * h), stack = [i0];
  seen[i0] = 1;
  let area = 0;
  const pts: Pt[] = [];
  while (stack.length && area < 0.05 * w * h) {
    const i = stack.pop()!, x = i % w, y = (i - x) / w;
    area++; pts.push({ x, y });
    for (const j of [x > 0 ? i - 1 : -1, x < w - 1 ? i + 1 : -1, y > 0 ? i - w : -1, y < h - 1 ? i + w : -1]) {
      if (j < 0 || seen[j]) continue;
      const dE = Math.hypot(lab.L[j] - ref.L, lab.a[j] - ref.a, lab.b[j] - ref.b);
      if (dE < 16) { seen[j] = 1; stack.push(j); }
    }
  }
  if (area < 50 || area > 0.03 * w * h) return null;
  const hull = convexHull(pts);
  const hullA = polygonArea(hull);
  const f = feret(hull);
  // A coin seen from above is a near-perfect disc: reject blobs that are not.
  if (f.max <= 0 || f.min / f.max < 0.85 || (4 * hullA) / (Math.PI * f.max * f.max) < 0.8) return null;
  const dPx = 2 * Math.sqrt(hullA / Math.PI);
  const cal = finish('coin', null, coinMm / dPx, w, h, { exclude: [hull], note: `coin ${coinMm} mm = ${dPx.toFixed(1)} px` });
  return cal;
}

export function calibFromIntrinsics(w: number, h: number, camHmm: number = TIER0.intrinsics.defaultCamHmm): Calibration {
  const mmPerPx = camHmm / fPx(w);
  const c = finish('intrinsics', null, mmPerPx, w, h, { note: `assumed camera height ${camHmm} mm, HFOV ${TIER0.intrinsics.hfovDeg} deg` });
  c.camHmm = camHmm;
  c.camHsdMm = camHmm * 0.25;
  return c;
}

/** Map image px to plane mm for a calibration (homography when present, else uniform scale). */
export function toPlane(cal: Calibration, p: Pt): Pt {
  return cal.H ? applyH(cal.H, p) : { x: p.x * cal.mmPerPx, y: p.y * cal.mmPerPx };
}
