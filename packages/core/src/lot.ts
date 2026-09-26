import { adjudicate, applyOverrides } from './adjudicate';
import { clusterBootstrap, designEffect, jeffreys, sprt, wilson, type SprtDecision } from './stats';
import { BUCKETS, type Bucket, type BulbMeasurement, type Override, type RulePack } from './types';

export interface ShareEstimate {
  est: number;               // point estimate, percent
  ci: [number, number];      // 95 % interval, percent
  method: 'cluster-bootstrap' | 'wilson-deff';
  bayes: [number, number];   // Jeffreys credible interval on effective n, percent
}

export interface LotResult {
  packId: string;
  n_bulb_observations: number;
  n_trays: number;
  n_looks: number;
  counts: Record<Bucket, number>;       // over the looks used for estimation
  byCount: Record<Bucket, ShareEstimate>;
  byWeight: Record<Bucket, ShareEstimate>;
  procured: { byWeight: ShareEstimate; byCount: ShareEstimate };
  deff: number;
  perLookNonA: number[][];              // per tray, per look: % not Grade A (occlusion evidence)
  sprt: { decision: SprtDecision; traysMore: number; llr: number; A: number; B: number };
  referShare: number;
  overridden: number;
  contested: number;
}

const r2 = (x: number) => Math.round(x * 100) / 100;
const pct = (x: number) => r2(100 * x);

/**
 * Bulbs -> lot. A pure function of (measurements, pack, overrides, seed).
 *
 * Trays are clusters. Looks re-observe the same bulbs, so for each tray we
 * keep ONE look for estimation (the one showing the most non-Grade-A share by
 * default: the least occluded view; see docs/DECISIONS.md) and never pool
 * looks as if they were new onions.
 */
export function gradeLot(bulbs: BulbMeasurement[], pack: RulePack, overrides: Override[] = [], seedHex = '0'.repeat(32)): LotResult {
  const ai = adjudicate(bulbs, pack);
  const fin = applyOverrides(ai, overrides);
  const finalOf = new Map(fin.map((f) => [f.id, f.final]));

  const trays = new Map<number, Map<number, BulbMeasurement[]>>();
  for (const b of bulbs) {
    if (!trays.has(b.tray)) trays.set(b.tray, new Map());
    const looks = trays.get(b.tray)!;
    if (!looks.has(b.look)) looks.set(b.look, []);
    looks.get(b.look)!.push(b);
  }
  const trayIds = [...trays.keys()].sort((a, b) => a - b);

  type Agg = { n: number; w: number; c: Record<Bucket, number>; cw: Record<Bucket, number> };
  const zero = (): Record<Bucket, number> => ({ GRADE_A: 0, URS: 0, REJECT: 0, REFER: 0 });
  const agg = (bs: BulbMeasurement[]): Agg => {
    const a: Agg = { n: 0, w: 0, c: zero(), cw: zero() };
    for (const b of bs) {
      const k = finalOf.get(b.id)!;
      a.n++; a.w += b.w; a.c[k]++; a.cw[k] += b.w;
    }
    return a;
  };

  const chosen: Agg[] = [];
  const perLookNonA: number[][] = [];
  let maxLooks = 0;
  for (const t of trayIds) {
    const looks = [...trays.get(t)!.entries()].sort((a, b) => a[0] - b[0]).map(([, bs]) => agg(bs));
    maxLooks = Math.max(maxLooks, looks.length);
    const nonA = looks.map((l) => (l.n ? 1 - l.c.GRADE_A / l.n : 0));
    perLookNonA.push(nonA.map(pct));
    if (pack.lot.look_merge === 'mean' && looks.length > 1) {
      const m: Agg = { n: 0, w: 0, c: zero(), cw: zero() };
      for (const l of looks) { m.n += l.n / looks.length; m.w += l.w / looks.length; for (const k of BUCKETS) { m.c[k] += l.c[k] / looks.length; m.cw[k] += l.cw[k] / looks.length; } }
      chosen.push(m);
    } else {
      let best = 0;
      nonA.forEach((v, i) => { if (v > nonA[best]) best = i; });
      chosen.push(looks[best]);
    }
  }

  const N = chosen.reduce((s, a) => s + a.n, 0);
  const counts = zero();
  for (const a of chosen) for (const k of BUCKETS) counts[k] += a.c[k];

  const estimate = (sel: (a: Agg) => number, tot: (a: Agg) => number, salt: string): ShareEstimate & { deff: number } => {
    const clusters = chosen.map((a) => ({ x: sel(a), n: tot(a) }));
    const X = clusters.reduce((s, c) => s + c.x, 0), T = clusters.reduce((s, c) => s + c.n, 0);
    const p = T > 0 ? X / T : 0;
    const deff = designEffect(clusters);
    // Effective counts in bulb units, so weight shares get a sensible n.
    const kB = p * N;
    const jb = jeffreys(Math.round(kB), Math.round(N), deff);
    let ci: [number, number], method: ShareEstimate['method'];
    if (clusters.length >= 3) {
      ci = clusterBootstrap(clusters, seedHex.slice(0, 24) + salt, pack.lot.bootstrap_b);
      method = 'cluster-bootstrap';
    } else {
      // Too few trays to resample. Wilson on the design-effect-deflated n.
      const nE = Math.max(1, Math.round(N / deff));
      ci = wilson(Math.round(p * nE), nE);
      method = 'wilson-deff';
    }
    return { est: pct(p), ci: [pct(ci[0]), pct(ci[1])], method, bayes: [pct(jb.lo), pct(jb.hi)], deff };
  };

  const salt = (s: string) => Array.from(s).reduce((h, ch) => ((h * 31 + ch.charCodeAt(0)) >>> 0), 7).toString(16).padStart(8, '0');
  const byCount = {} as Record<Bucket, ShareEstimate>;
  const byWeight = {} as Record<Bucket, ShareEstimate>;
  let deffA = 1;
  for (const k of BUCKETS) {
    const c = estimate((a) => a.c[k], (a) => a.n, salt('c' + k));
    const w = estimate((a) => a.cw[k], (a) => a.w, salt('w' + k));
    if (k === 'GRADE_A') deffA = c.deff;
    byCount[k] = strip(c); byWeight[k] = strip(w);
  }
  const proc = pack.procured;
  const pc = estimate((a) => proc.reduce((s, k) => s + a.c[k], 0), (a) => a.n, salt('pc'));
  const pw = estimate((a) => proc.reduce((s, k) => s + a.cw[k], 0), (a) => a.w, salt('pw'));

  const bad = pack.lot.sprt.bucket_set;
  const s = sprt(chosen.map((a) => ({ bad: Math.round(bad.reduce((x, k) => x + a.c[k], 0)), n: Math.round(a.n) })),
    pack.lot.sprt.p0, pack.lot.sprt.p1, pack.lot.sprt.alpha, pack.lot.sprt.beta, deffA);
  const referShare = N ? counts.REFER / N : 0;
  let decision: SprtDecision = s.decision;
  if (referShare > pack.lot.refer_share_max) decision = 'REFER_TO_HUMAN';
  else if (decision === 'SAMPLE_MORE' && trayIds.length >= pack.lot.max_trays) decision = 'REFER_TO_HUMAN';

  return {
    packId: pack.id,
    n_bulb_observations: bulbs.length,
    n_trays: trayIds.length,
    n_looks: maxLooks,
    counts: mapVals(counts, r2),
    byCount, byWeight,
    procured: { byWeight: strip(pw), byCount: strip(pc) },
    deff: r2(deffA),
    perLookNonA,
    sprt: { decision, traysMore: Number.isFinite(s.traysMore) ? s.traysMore : -1, llr: r2(s.llr), A: r2(s.A), B: r2(s.B) },
    referShare: pct(referShare),
    overridden: overrides.filter((o) => o.kind === 'override').length,
    contested: overrides.filter((o) => o.kind === 'contest').length,
  };
}

function strip(e: ShareEstimate & { deff?: number }): ShareEstimate {
  return { est: e.est, ci: e.ci, method: e.method, bayes: e.bayes };
}
function mapVals<T extends string>(o: Record<T, number>, f: (x: number) => number): Record<T, number> {
  const out = {} as Record<T, number>;
  for (const k of Object.keys(o) as T[]) out[k] = f(o[k]);
  return out;
}

/** Indicative value range from the weight-based procured share. Never official. */
export function indicativeValue(lotKg: number, ratePerQuintal: number, procuredByWeight: ShareEstimate) {
  const q = lotKg / 100;
  return {
    low: Math.round(q * ratePerQuintal * procuredByWeight.ci[0] / 100),
    mid: Math.round(q * ratePerQuintal * procuredByWeight.est / 100),
    high: Math.round(q * ratePerQuintal * procuredByWeight.ci[1] / 100),
  };
}
