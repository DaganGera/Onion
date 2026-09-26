/**
 * Straight port of legacy app/grading.py merge_looks, kept only to prove the
 * TS math matches the Python it replaces (golden vectors in test/golden).
 * The product uses lot.ts, which supersedes this.
 */
import { wilson } from './stats';

const CLASS_NAMES = ['sound', 'rotten', 'sprouted', 'black_smut', 'damaged_skin', 'doubles'];
const round2 = (x: number) => Math.round(x * 100) / 100;

export function legacyMergeLooks(looks: Record<string, unknown>[][], corr: { one: number; two: number }) {
  const bulbs = looks.flat();
  const n = bulbs.length, nLooks = looks.length;
  const trayIds = new Set(bulbs.map((b) => b.tray_id).filter((t) => t !== undefined && t !== null));
  const nTrays = trayIds.size ? trayIds.size : n ? 1 : 0;
  const cls = (b: Record<string, unknown>) => {
    const r = b.cls;
    if (typeof r === 'string') return r;
    if (typeof r === 'number' && r >= 0 && Math.trunc(r) < CLASS_NAMES.length) return CLASS_NAMES[Math.trunc(r)];
    return 'sound';
  };
  const classCounts: Record<string, number> = Object.fromEntries(CLASS_NAMES.map((c) => [c, 0]));
  const gradeCounts: Record<string, number> = { A: 0, B: 0, C: 0, UNDERSIZED: 0, UNKNOWN: 0 };
  let nRef = 0;
  for (const b of bulbs) {
    classCounts[cls(b)]++;
    const g = (b.size_grade as string) ?? 'UNKNOWN';
    gradeCounts[g in gradeCounts ? g : 'UNKNOWN']++;
    if (b.decision === 'REFER') nRef++;
  }
  const pct = (c: number) => (n ? round2((100 * c) / n) : 0);
  const [lo, hi] = wilson(gradeCounts.A, n);
  const rates = looks.filter((l) => l.length).map((l) => l.filter((b) => cls(b) !== 'sound').length / l.length);
  const raw = rates.length ? Math.max(...rates) : 0;
  const factor = (nLooks >= 2 ? corr.two : corr.one) || 1;
  return {
    n_bulb_observations: n, n_looks: nLooks, n_trays: nTrays,
    class_counts: classCounts,
    class_pcts: Object.fromEntries(Object.entries(classCounts).map(([k, v]) => [k, pct(v)])),
    grade_counts: gradeCounts,
    grade_pcts: Object.fromEntries(Object.entries(gradeCounts).map(([k, v]) => [k, pct(v)])),
    grade_a_pct: pct(gradeCounts.A),
    grade_a_ci_low: round2(100 * lo), grade_a_ci_high: round2(100 * hi),
    defect_rate_raw: round2(100 * raw),
    defect_rate_corrected: round2(100 * Math.min(1, raw / factor)),
    defect_rate_per_look: rates.map((r) => round2(100 * r)),
    occlusion_factor_applied: factor,
    n_referred: nRef,
  };
}
