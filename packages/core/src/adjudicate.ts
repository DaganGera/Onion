import type { BulbMeasurement, BulbVerdict, Bucket, Override, Rule, RulePack } from './types';

type Outcome = 'pass' | 'fail' | 'borderline' | 'na';

/** Size measure selected by the pack, in 0.1 mm, with its sigma. */
export function sizeOf(b: BulbMeasurement, pack: RulePack): { v: number; sd: number } {
  const { min, max, sd } = b.size;
  const v = pack.size_metric === 'min_feret' ? min : pack.size_metric === 'max_feret' ? max : Math.round((min + max) / 2);
  return { v, sd };
}

function valueOf(b: BulbMeasurement, r: Rule, pack: RulePack): { v: number | null; sd: number } {
  if (r.m === 'size') return sizeOf(b, pack);
  if (r.m === 'double' || r.m === 'bottleneck' || r.m === 'split') return { v: b.shape[r.m] ? 1 : 0, sd: 0 };
  const v = b.frac[r.m];
  // Boundary uncertainty scales with lesion extent: an empty mask is not
  // "0 +/- fsd". sd = fsd * 2*sqrt(p(1-p)), i.e. fsd at p=0.5, ~0 at p=0.
  const p = v === null ? 0 : Math.min(1, Math.max(0, v / 1000));
  return { v, sd: b.fsd * 2 * Math.sqrt(p * (1 - p)) };
}

function test(v: number, op: Rule['op'], lim: number): boolean {
  switch (op) {
    case '<=': return v <= lim;
    case '<': return v < lim;
    case '>=': return v >= lim;
    case '>': return v > lim;
    case '==': return v === lim;
  }
}

/**
 * A rule passes definitively only if it passes at both ends of the
 * measurement's k-sigma interval, and fails definitively only if it fails at
 * both ends. Anything in between is borderline -> the bulb goes to a human.
 * Integer arithmetic only (margin is rounded), so every engine agrees.
 */
export function evalRule(b: BulbMeasurement, r: Rule, pack: RulePack): Outcome {
  const { v, sd } = valueOf(b, r, pack);
  if (v === null) return 'na';
  const margin = r.op === '==' ? 0 : Math.round(sd * pack.k_sigma);
  const lo = v - margin, hi = v + margin;
  const a = test(lo, r.op, r.v), z = test(hi, r.op, r.v);
  if (a && z) return 'pass';
  if (!a && !z) return 'fail';
  return 'borderline';
}

const OP_WORD: Record<Rule['op'], string> = { '<=': 'GT', '<': 'GE', '>=': 'LT', '>': 'LE', '==': 'NE' };

function fmt(m: Rule['m'], x: number): string {
  if (m === 'size') return `${trimNum(x / 10)}MM`;
  if (m === 'double' || m === 'bottleneck' || m === 'split') return x ? 'YES' : 'NO';
  return `${trimNum(x / 10)}PCT`;
}
const trimNum = (x: number) => (Number.isInteger(x) ? String(x) : x.toFixed(1));

/** e.g. BLACKENING_34.2PCT_GT_30PCT, SIZE_41.3MM_LT_45MM, DOUBLE_YES_NE_NO */
export function reasonCode(b: BulbMeasurement, r: Rule, pack: RulePack, outcome: Outcome): string {
  const { v } = valueOf(b, r, pack);
  const name = r.m.toUpperCase();
  if (outcome === 'na') return `NOT_ASSESSED_${name}`;
  const pre = outcome === 'borderline' ? 'BORDERLINE_' : '';
  return `${pre}${name}_${fmt(r.m, v ?? 0)}_${OP_WORD[r.op]}_${fmt(r.m, r.v)}`;
}

export function adjudicateBulb(b: BulbMeasurement, pack: RulePack): BulbVerdict {
  const notes = new Set<string>();
  const run = (rules: Rule[]) => {
    const fails: string[] = [], borders: string[] = [];
    for (const r of rules) {
      const o = evalRule(b, r, pack);
      if (o === 'fail') fails.push(reasonCode(b, r, pack, o));
      else if (o === 'borderline') borders.push(reasonCode(b, r, pack, o));
      else if (o === 'na') {
        notes.add(reasonCode(b, r, pack, o));
        if (r.na === 'refer') borders.push(reasonCode(b, r, pack, o));
      }
    }
    return { fails, borders };
  };

  if (b.conf < pack.refer.min_conf) {
    return { id: b.id, bucket: 'REFER', codes: [`LOW_CONFIDENCE_${b.conf}_LT_${pack.refer.min_conf}`], notes: [...notes] };
  }
  const rej = run(pack.reject_rules);
  if (rej.fails.length) return { id: b.id, bucket: 'REJECT', codes: rej.fails, notes: [...notes] };
  if (rej.borders.length) return { id: b.id, bucket: 'REFER', codes: rej.borders, notes: [...notes] };

  const why: string[] = [];
  for (const bucket of pack.buckets) {
    const r = run(bucket.rules);
    if (r.fails.length) { why.push(...r.fails); continue; }
    if (r.borders.length) return { id: b.id, bucket: 'REFER', codes: [...why, ...r.borders], notes: [...notes] };
    return { id: b.id, bucket: bucket.id, codes: why, notes: [...notes] };
  }
  return { id: b.id, bucket: 'REJECT', codes: dedupe(why), notes: [...notes] };
}

const dedupe = (xs: string[]) => [...new Set(xs)];

export function adjudicate(bulbs: BulbMeasurement[], pack: RulePack): BulbVerdict[] {
  return bulbs.map((b) => adjudicateBulb(b, pack));
}

/**
 * Apply human actions on top of the AI verdicts. The AI verdict is never
 * altered: the returned `final` sits beside it. The latest override wins;
 * an open contest (no later override) sends the bulb to REFER.
 */
export function applyOverrides(ai: BulbVerdict[], overrides: Override[]): { id: string; ai: Bucket; final: Bucket; by?: string }[] {
  const last = new Map<string, Override>();
  for (const o of overrides) last.set(o.bulb, o);
  return ai.map((v) => {
    const o = last.get(v.id);
    if (!o) return { id: v.id, ai: v.bucket, final: v.bucket };
    if (o.kind === 'contest') return { id: v.id, ai: v.bucket, final: 'REFER', by: `${o.by}:contest:${o.reason}` };
    return { id: v.id, ai: v.bucket, final: o.to ?? v.bucket, by: `${o.by}:override:${o.reason}` };
  });
}
