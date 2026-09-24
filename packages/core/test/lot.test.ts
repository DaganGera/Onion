import { describe, expect, it } from 'vitest';
import { betaCdf, clusterBootstrap, gradeLot, jeffreys, packById, packHash, sprt, indicativeValue } from '../src';
import { randomLot, resetRnd } from './fixtures';

const jun = packById('in-psf-2026-06-relaxed-a')!;
const jul = packById('in-psf-2026-07-30-a-only')!;
const pre = packById('in-psf-2026-pre-a')!;
const SEED = 'cd'.repeat(16);

describe('statistics', () => {
  it('beta cdf known values', () => {
    expect(betaCdf(0.5, 2, 2)).toBeCloseTo(0.5, 10);
    expect(betaCdf(0.3, 1, 1)).toBeCloseTo(0.3, 10);
    expect(betaCdf(0.2, 2, 5)).toBeCloseTo(0.34464, 5);
  });
  it('jeffreys widens with design effect', () => {
    const a = jeffreys(10, 100), b = jeffreys(10, 100, 3);
    expect(b.hi - b.lo).toBeGreaterThan(a.hi - a.lo);
  });
  it('bootstrap is reproducible from its seed and brackets the estimate', () => {
    const c = [{ x: 3, n: 40 }, { x: 8, n: 45 }, { x: 5, n: 38 }, { x: 1, n: 41 }];
    expect(clusterBootstrap(c, 'ab'.repeat(16))).toEqual(clusterBootstrap(c, 'ab'.repeat(16)));
    const [lo, hi] = clusterBootstrap(c, 'ab'.repeat(16));
    expect(lo).toBeLessThanOrEqual(17 / 164);
    expect(hi).toBeGreaterThanOrEqual(17 / 164);
  });
  it('sprt accepts clean, rejects bad, asks for more when unclear', () => {
    expect(sprt([{ bad: 0, n: 40 }, { bad: 1, n: 40 }], 0.1, 0.25, 0.05, 0.1).decision).toBe('ACCEPT_LOT');
    expect(sprt([{ bad: 20, n: 40 }, { bad: 18, n: 40 }], 0.1, 0.25, 0.05, 0.1).decision).toBe('REJECT_LOT');
    const m = sprt([{ bad: 7, n: 40 }], 0.1, 0.25, 0.05, 0.1);
    expect(m.decision).toBe('SAMPLE_MORE');
    expect(m.traysMore).toBeGreaterThan(0);
  });
});

describe('lot grading', () => {
  resetRnd(7);
  const bulbs = randomLot(120, 4, 2);
  it('is a pure function (same input, identical output)', () => {
    expect(gradeLot(bulbs, jun, [], SEED)).toEqual(gradeLot(bulbs, jun, [], SEED));
  });
  it('shares sum to ~100 and intervals contain the estimate', () => {
    const r = gradeLot(bulbs, jun, [], SEED);
    for (const view of [r.byCount, r.byWeight]) {
      const s = Object.values(view).reduce((a, e) => a + e.est, 0);
      expect(Math.abs(s - 100)).toBeLessThan(0.05);
      for (const e of Object.values(view)) {
        expect(e.ci[0]).toBeLessThanOrEqual(e.est + 1e-9);
        expect(e.ci[1]).toBeGreaterThanOrEqual(e.est - 1e-9);
      }
    }
    expect(r.n_bulb_observations).toBe(120);
    expect(r.n_trays).toBe(4);
    expect(r.n_looks).toBe(2);
  });
  it('W1 time travel: same bulbs, different pack hash, different procured share', async () => {
    expect(await packHash(jun)).not.toBe(await packHash(jul));
    const a = gradeLot(bulbs, jun, [], SEED), b = gradeLot(bulbs, jul, [], SEED), c = gradeLot(bulbs, pre, [], SEED);
    expect(a.byWeight.URS.est).toBeGreaterThan(0);
    expect(b.procured.byWeight.est).toBeLessThan(a.procured.byWeight.est);
    expect(c.byWeight.URS.est).toBe(0);
  });
  it('indicative value is ordered low <= mid <= high', () => {
    const r = gradeLot(bulbs, jun, [], SEED);
    const v = indicativeValue(1000, 2125, r.procured.byWeight);
    expect(v.low).toBeLessThanOrEqual(v.mid);
    expect(v.mid).toBeLessThanOrEqual(v.high);
  });
});
