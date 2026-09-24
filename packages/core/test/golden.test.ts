import { describe, expect, it } from 'vitest';
import golden from './golden/legacy_grading.json';
import { wilson } from '../src';
import { legacyMergeLooks } from '../src/legacy';

describe('parity with legacy Python grading (golden vectors)', () => {
  it('wilson_interval matches to 1e-12', () => {
    for (const g of golden.wilson) {
      const [lo, hi] = wilson(g.k, g.n);
      expect(lo).toBeCloseTo(g.lo, 12);
      expect(hi).toBeCloseTo(g.hi, 12);
    }
  });
  it('merge_looks matches on 40 random cases', () => {
    const corr = { one: golden.constants.occlusion_correction_1look, two: golden.constants.occlusion_correction_2look };
    for (const c of golden.merge_looks) {
      const ts = legacyMergeLooks(c.looks as Record<string, unknown>[][], corr) as Record<string, unknown>;
      const py = c.result as Record<string, unknown>;
      for (const [k, v] of Object.entries(py)) {
        const t = ts[k];
        if (typeof v === 'number') expect(Math.abs((t as number) - v), k).toBeLessThanOrEqual(0.0100001);
        else if (Array.isArray(v)) (v as number[]).forEach((x, i) => expect(Math.abs((t as number[])[i] - x)).toBeLessThanOrEqual(0.0100001));
        else for (const [kk, vv] of Object.entries(v as Record<string, number>)) expect(Math.abs((t as Record<string, number>)[kk] - vv), `${k}.${kk}`).toBeLessThanOrEqual(0.0100001);
      }
    }
  });
});
