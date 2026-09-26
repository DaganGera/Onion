export type Pt = { x: number; y: number };
export type H3 = number[]; // 3x3 row-major homography

/** Andrew's monotone chain convex hull. */
export function convexHull(pts: Pt[]): Pt[] {
  const p = [...pts].sort((a, b) => a.x - b.x || a.y - b.y);
  if (p.length < 3) return p;
  const cross = (o: Pt, a: Pt, b: Pt) => (a.x - o.x) * (b.y - o.y) - (a.y - o.y) * (b.x - o.x);
  const lo: Pt[] = [], up: Pt[] = [];
  for (const q of p) { while (lo.length >= 2 && cross(lo[lo.length - 2], lo[lo.length - 1], q) <= 0) lo.pop(); lo.push(q); }
  for (let i = p.length - 1; i >= 0; i--) { const q = p[i]; while (up.length >= 2 && cross(up[up.length - 2], up[up.length - 1], q) <= 0) up.pop(); up.push(q); }
  return lo.slice(0, -1).concat(up.slice(0, -1));
}

export function polygonArea(poly: Pt[]): number {
  let s = 0;
  for (let i = 0; i < poly.length; i++) { const a = poly[i], b = poly[(i + 1) % poly.length]; s += a.x * b.y - b.x * a.y; }
  return Math.abs(s) / 2;
}

/**
 * Min and max Feret (caliper) diameters of a convex polygon. Min Feret is
 * the smallest width over all edge directions; max is the diameter.
 */
export function feret(hull: Pt[]): { min: number; max: number; minAngle: number } {
  const n = hull.length;
  if (n < 2) return { min: 0, max: 0, minAngle: 0 };
  let max = 0;
  for (let i = 0; i < n; i++) for (let j = i + 1; j < n; j++) max = Math.max(max, Math.hypot(hull[i].x - hull[j].x, hull[i].y - hull[j].y));
  let min = Infinity, minAngle = 0;
  for (let i = 0; i < n; i++) {
    const a = hull[i], b = hull[(i + 1) % n];
    const len = Math.hypot(b.x - a.x, b.y - a.y);
    if (len < 1e-9) continue;
    const nx = -(b.y - a.y) / len, ny = (b.x - a.x) / len;
    let lo = Infinity, hi = -Infinity;
    for (const p of hull) { const d = (p.x - a.x) * nx + (p.y - a.y) * ny; if (d < lo) lo = d; if (d > hi) hi = d; }
    if (hi - lo < min) { min = hi - lo; minAngle = Math.atan2(ny, nx); }
  }
  return { min: Number.isFinite(min) ? min : 0, max, minAngle };
}

export function applyH(H: H3, p: Pt): Pt {
  const w = H[6] * p.x + H[7] * p.y + H[8];
  return { x: (H[0] * p.x + H[1] * p.y + H[2]) / w, y: (H[3] * p.x + H[4] * p.y + H[5]) / w };
}

/** Normalised DLT homography from >= 4 correspondences (src -> dst). */
export function homography(src: Pt[], dst: Pt[]): H3 {
  const norm = (ps: Pt[]) => {
    const cx = ps.reduce((s, p) => s + p.x, 0) / ps.length, cy = ps.reduce((s, p) => s + p.y, 0) / ps.length;
    const md = ps.reduce((s, p) => s + Math.hypot(p.x - cx, p.y - cy), 0) / ps.length || 1;
    const k = Math.SQRT2 / md;
    return { T: [k, 0, -k * cx, 0, k, -k * cy, 0, 0, 1], pts: ps.map((p) => ({ x: k * (p.x - cx), y: k * (p.y - cy) })) };
  };
  const a = norm(src), b = norm(dst);
  // Solve A h = 0 with h9 = 1 via least squares normal equations (8 unknowns).
  const M: number[][] = [], r: number[] = [];
  for (let i = 0; i < src.length; i++) {
    const { x, y } = a.pts[i], { x: u, y: v } = b.pts[i];
    M.push([x, y, 1, 0, 0, 0, -u * x, -u * y]); r.push(u);
    M.push([0, 0, 0, x, y, 1, -v * x, -v * y]); r.push(v);
  }
  const AtA = Array.from({ length: 8 }, () => new Array(8).fill(0)), Atb = new Array(8).fill(0);
  for (let k = 0; k < M.length; k++) for (let i = 0; i < 8; i++) { Atb[i] += M[k][i] * r[k]; for (let j = 0; j < 8; j++) AtA[i][j] += M[k][i] * M[k][j]; }
  const h = solve(AtA, Atb);
  const Hn = [...h, 1];
  // H = Tb^-1 * Hn * Ta
  const TbInv = inv3(b.T);
  return mul3(mul3(TbInv, Hn), a.T);
}

function solve(A: number[][], b: number[]): number[] {
  const n = b.length, M = A.map((row, i) => [...row, b[i]]);
  for (let c = 0; c < n; c++) {
    let p = c;
    for (let r = c + 1; r < n; r++) if (Math.abs(M[r][c]) > Math.abs(M[p][c])) p = r;
    [M[c], M[p]] = [M[p], M[c]];
    const d = M[c][c] || 1e-12;
    for (let r = 0; r < n; r++) {
      if (r === c) continue;
      const f = M[r][c] / d;
      for (let k = c; k <= n; k++) M[r][k] -= f * M[c][k];
    }
  }
  return M.map((row, i) => row[n] / (row[i] || 1e-12));
}

export function mul3(A: H3, B: H3): H3 {
  const C = new Array(9).fill(0);
  for (let i = 0; i < 3; i++) for (let j = 0; j < 3; j++) for (let k = 0; k < 3; k++) C[3 * i + j] += A[3 * i + k] * B[3 * k + j];
  return C;
}

export function inv3(m: H3): H3 {
  const [a, b, c, d, e, f, g, h, i] = m;
  const A = e * i - f * h, B = -(d * i - f * g), C = d * h - e * g;
  const det = a * A + b * B + c * C;
  return [A / det, -(b * i - c * h) / det, (b * f - c * e) / det, B / det, (a * i - c * g) / det, -(a * f - c * d) / det, C / det, -(a * h - b * g) / det, (a * e - b * d) / det];
}

/** Local plane scale (mm per image pixel) at an image point, from the homography Jacobian. */
export function localScale(H: H3, p: Pt): number {
  const e = 0.5;
  const a = applyH(H, { x: p.x - e, y: p.y }), b = applyH(H, { x: p.x + e, y: p.y });
  const c = applyH(H, { x: p.x, y: p.y - e }), d = applyH(H, { x: p.x, y: p.y + e });
  const jx = { x: b.x - a.x, y: b.y - a.y }, jy = { x: d.x - c.x, y: d.y - c.y };
  return Math.sqrt(Math.abs(jx.x * jy.y - jx.y * jy.x));
}
