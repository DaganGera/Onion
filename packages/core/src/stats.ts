import { prngFromHex, randInt } from './prng';

/** Wilson score interval. Ported from legacy app/grading.py (golden-vector tested). */
export function wilson(k: number, n: number, z = 1.96): [number, number] {
  if (n <= 0) return [0, 1];
  const p = k / n;
  const denom = 1 + (z * z) / n;
  const centre = p + (z * z) / (2 * n);
  const margin = z * Math.sqrt((p * (1 - p)) / n + (z * z) / (4 * n * n));
  return [Math.max(0, (centre - margin) / denom), Math.min(1, (centre + margin) / denom)];
}

// ---- Beta distribution (for the Jeffreys / Bayesian small-sample view) ----

function lgamma(x: number): number {
  // Lanczos approximation, g=7, n=9.
  const c = [0.99999999999980993, 676.5203681218851, -1259.1392167224028, 771.32342877765313,
    -176.61502916214059, 12.507343278686905, -0.13857109526572012, 9.9843695780195716e-6, 1.5056327351493116e-7];
  if (x < 0.5) return Math.log(Math.PI / Math.sin(Math.PI * x)) - lgamma(1 - x);
  x -= 1;
  let a = c[0];
  const t = x + 7.5;
  for (let i = 1; i < 9; i++) a += c[i] / (x + i);
  return 0.5 * Math.log(2 * Math.PI) + (x + 0.5) * Math.log(t) - t + Math.log(a);
}

function betacf(a: number, b: number, x: number): number {
  const EPS = 1e-14, FPMIN = 1e-300;
  let c = 1, d = 1 - ((a + b) * x) / (a + 1);
  if (Math.abs(d) < FPMIN) d = FPMIN;
  d = 1 / d;
  let h = d;
  for (let m = 1; m <= 300; m++) {
    const m2 = 2 * m;
    let aa = (m * (b - m) * x) / ((a - 1 + m2) * (a + m2));
    d = 1 + aa * d; if (Math.abs(d) < FPMIN) d = FPMIN;
    c = 1 + aa / c; if (Math.abs(c) < FPMIN) c = FPMIN;
    d = 1 / d; h *= d * c;
    aa = (-(a + m) * (a + b + m) * x) / ((a + m2) * (a + 1 + m2));
    d = 1 + aa * d; if (Math.abs(d) < FPMIN) d = FPMIN;
    c = 1 + aa / c; if (Math.abs(c) < FPMIN) c = FPMIN;
    d = 1 / d;
    const del = d * c;
    h *= del;
    if (Math.abs(del - 1) < EPS) break;
  }
  return h;
}

/** Regularized incomplete beta I_x(a, b). */
export function betaCdf(x: number, a: number, b: number): number {
  if (x <= 0) return 0;
  if (x >= 1) return 1;
  const bt = Math.exp(lgamma(a + b) - lgamma(a) - lgamma(b) + a * Math.log(x) + b * Math.log(1 - x));
  return x < (a + 1) / (a + b + 2) ? (bt * betacf(a, b, x)) / a : 1 - (bt * betacf(b, a, 1 - x)) / b;
}

export function betaQuantile(q: number, a: number, b: number): number {
  let lo = 0, hi = 1;
  for (let i = 0; i < 80; i++) {
    const mid = (lo + hi) / 2;
    if (betaCdf(mid, a, b) < q) lo = mid; else hi = mid;
  }
  return (lo + hi) / 2;
}

/**
 * Jeffreys interval on an effective sample size. k and n are scaled down by
 * the design effect first, so clustering (bulbs in a tray are not
 * independent) widens the interval instead of being ignored.
 */
export function jeffreys(k: number, n: number, deff = 1, level = 0.95): { lo: number; hi: number; mean: number; nEff: number } {
  const s = Math.max(1, deff);
  const kE = k / s, nE = n / s;
  const a = kE + 0.5, b = nE - kE + 0.5;
  const t = (1 - level) / 2;
  return {
    lo: k === 0 ? 0 : betaQuantile(t, a, b),
    hi: k === n ? 1 : betaQuantile(1 - t, a, b),
    mean: a / (a + b),
    nEff: nE,
  };
}

/**
 * Design effect from between-cluster variation of a ratio (Kish).
 * Clusters: {x: bucket amount, n: total amount}. Returns >= 1.
 */
export function designEffect(clusters: { x: number; n: number }[]): number {
  const m = clusters.length;
  const N = clusters.reduce((s, c) => s + c.n, 0);
  if (m < 2 || N <= 0) return 1;
  const p = clusters.reduce((s, c) => s + c.x, 0) / N;
  if (p <= 0 || p >= 1) return 1;
  const nbar = N / m;
  // Variance of the ratio estimator under clustering vs under SRS.
  let ss = 0;
  for (const c of clusters) ss += (c.x - p * c.n) ** 2;
  const varClust = (m / (m - 1)) * ss / (N * N);
  const varSrs = (p * (1 - p)) / N;
  const d = varClust / varSrs;
  return Number.isFinite(d) ? Math.max(1, Math.min(d, nbar)) : 1;
}

/**
 * Cluster (tray-level) percentile bootstrap of a ratio sum(x)/sum(n).
 * Resamples whole trays, never individual bulbs. Seeded, so reproducible.
 */
export function clusterBootstrap(clusters: { x: number; n: number }[], seedHex: string, B = 2000, level = 0.95): [number, number] {
  const m = clusters.length;
  if (m === 0) return [0, 1];
  const next = prngFromHex(seedHex);
  const est: number[] = [];
  for (let i = 0; i < B; i++) {
    let sx = 0, sn = 0;
    for (let j = 0; j < m; j++) { const c = clusters[randInt(next, m)]; sx += c.x; sn += c.n; }
    est.push(sn > 0 ? sx / sn : 0);
  }
  est.sort((a, b) => a - b);
  const t = (1 - level) / 2;
  const at = (q: number) => est[Math.min(B - 1, Math.max(0, Math.floor(q * B)))];
  return [at(t), at(1 - t)];
}

export type SprtDecision = 'ACCEPT_LOT' | 'REJECT_LOT' | 'SAMPLE_MORE' | 'REFER_TO_HUMAN';

/**
 * Wald SPRT on the share of bulbs in a "bad" bucket set, with each tray's
 * contribution deflated by the design effect. H0: p = p0 (acceptable lot),
 * H1: p = p1 (rejectable lot).
 */
export function sprt(trays: { bad: number; n: number }[], p0: number, p1: number, alpha: number, beta: number, deff = 1) {
  const A = Math.log((1 - beta) / alpha);
  const B = Math.log(beta / (1 - alpha));
  const lr1 = Math.log(p1 / p0), lr0 = Math.log((1 - p1) / (1 - p0));
  let llr = 0, bad = 0, n = 0;
  for (const t of trays) { llr += (t.bad * lr1 + (t.n - t.bad) * lr0) / Math.max(1, deff); bad += t.bad; n += t.n; }
  let decision = "SAMPLE_MORE" as SprtDecision;
  if (llr >= A) decision = 'REJECT_LOT';
  else if (llr <= B) decision = 'ACCEPT_LOT';
  // Expected LLR gain from one more tray like the average one, at the observed rate.
  let traysMore = 0;
  if (decision === 'SAMPLE_MORE' && trays.length) {
    const phat = Math.min(0.999, Math.max(0.001, bad / Math.max(1, n)));
    const nPer = n / trays.length;
    const drift = (nPer * (phat * lr1 + (1 - phat) * lr0)) / Math.max(1, deff);
    if (Math.abs(drift) > 1e-9) {
      const target = drift > 0 ? A : B;
      traysMore = Math.max(1, Math.ceil((target - llr) / drift));
    } else traysMore = Infinity;
  } else if (decision === 'SAMPLE_MORE') traysMore = 1;
  return { llr, A, B, decision, traysMore };
}
