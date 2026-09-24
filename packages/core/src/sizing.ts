/**
 * Size and weight math. Pure functions, no image handling.
 */

export type CalibrationTier = 'aruco' | 'a4' | 'coin' | 'intrinsics';

/**
 * Relative 1-sigma scale uncertainty per tier. ASSUMED starting values
 * (docs/SOURCES.md A-SCALE-*); E1 replaces them with fitted numbers.
 */
export const TIER_SCALE_SD: Record<CalibrationTier, number> = {
  aruco: 0.006,
  a4: 0.015,
  coin: 0.03,
  intrinsics: 0.12,
};

/**
 * A bulb's widest horizontal section (its equator) sits about one radius
 * above the calibration plane, closer to the camera, so it images larger.
 * With camera height H above the plane and measured plane-scale diameter
 * dm, the true diameter d satisfies d = dm * (H - d/2) / H, giving
 *   d = dm / (1 + dm / (2H)).
 */
export function heightCorrect(dPlaneMm: number, camHeightMm: number): number {
  if (!(camHeightMm > 0)) return dPlaneMm;
  return dPlaneMm / (1 + dPlaneMm / (2 * camHeightMm));
}

/** Size sigma in mm from scale uncertainty, segmentation jitter and camera-height uncertainty. */
export function sizeSigmaMm(dMm: number, tier: CalibrationTier, mmPerPx: number, camHeightMm: number, camHeightSdMm: number): number {
  const scale = dMm * TIER_SCALE_SD[tier];
  const seg = 1.5 * mmPerPx; // ~1.5 px boundary jitter, ASSUMED (A-SEG-1)
  // d(d)/dH from heightCorrect, times sigma_H.
  const dh = camHeightMm > 0 ? (dMm * dMm) / (2 * camHeightMm * camHeightMm) * camHeightSdMm : 0;
  return Math.sqrt(scale * scale + seg * seg + dh * dh);
}

export interface WeightModel {
  a: number;          // grams per mm^b
  b: number;
  residualSd: number; // relative (log-scale) residual sigma
  source: 'assumed' | 'fitted';
  n?: number;
}

/**
 * ASSUMED default until the user's kitchen-scale fit exists: sphere of
 * density 0.95 g/cm^3 on the mean Feret diameter (A-WEIGHT-1).
 */
export const DEFAULT_WEIGHT_MODEL: WeightModel = {
  a: (0.95 * Math.PI) / 6 / 1000,
  b: 3,
  residualSd: 0.18,
  source: 'assumed',
};

export function predictWeight(dMm: number, m: WeightModel = DEFAULT_WEIGHT_MODEL): { g: number; sdG: number } {
  const g = m.a * Math.pow(dMm, m.b);
  return { g, sdG: g * m.residualSd };
}

/** Least-squares fit of log w = log a + b log d. Used by scripts/fit_weight. */
export function fitWeightModel(pairs: { dMm: number; g: number }[]): WeightModel {
  const xs = pairs.map((p) => Math.log(p.dMm)), ys = pairs.map((p) => Math.log(p.g));
  const n = xs.length;
  const mx = xs.reduce((s, x) => s + x, 0) / n, my = ys.reduce((s, y) => s + y, 0) / n;
  let sxy = 0, sxx = 0;
  for (let i = 0; i < n; i++) { sxy += (xs[i] - mx) * (ys[i] - my); sxx += (xs[i] - mx) ** 2; }
  const b = sxy / sxx, la = my - b * mx;
  let ss = 0;
  for (let i = 0; i < n; i++) ss += (ys[i] - la - b * xs[i]) ** 2;
  return { a: Math.exp(la), b, residualSd: Math.sqrt(ss / Math.max(1, n - 2)), source: 'fitted', n };
}
