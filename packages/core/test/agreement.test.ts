import { describe, expect, it } from 'vitest';
import { blandAltman, cohenKappa, fleissKappa, icc1, majority } from '../src/agreement';

describe('agreement statistics', () => {
  it('Fleiss kappa matches the worked example (10 subjects, 14 raters, 5 categories) = 0.210', () => {
    const t = [
      [0, 0, 0, 0, 14], [0, 2, 6, 4, 2], [0, 0, 3, 5, 6], [0, 3, 9, 2, 0], [2, 2, 8, 1, 1],
      [7, 7, 0, 0, 0], [3, 2, 6, 3, 0], [2, 5, 3, 2, 2], [6, 5, 2, 1, 0], [0, 2, 2, 3, 7],
    ];
    expect(fleissKappa(t)).toBeCloseTo(0.21, 2);
  });
  it('Cohen kappa: perfect, and a textbook 2x2 (agreement 0.70, kappa 0.40)', () => {
    expect(cohenKappa(['A', 'B', 'A'], ['A', 'B', 'A']).kappa).toBe(1);
    const a = [...Array(20).fill('Y'), ...Array(5).fill('Y'), ...Array(10).fill('N'), ...Array(15).fill('N')];
    const b = [...Array(20).fill('Y'), ...Array(5).fill('N'), ...Array(10).fill('Y'), ...Array(15).fill('N')];
    const r = cohenKappa(a, b);
    expect(r.agreement).toBeCloseTo(0.7, 10);
    expect(r.kappa).toBeCloseTo(0.4, 10);
  });
  it('Bland-Altman bias and limits', () => {
    const r = blandAltman([11, 12, 13, 14], [10, 10, 10, 10]);
    expect(r.bias).toBe(2.5);
    expect(r.loa[0]).toBeLessThan(r.bias);
    expect(r.mae).toBe(2.5);
  });
  it('ICC is ~1 when repeats agree and lots differ, ~0 when repeats are noise', () => {
    expect(icc1([[10, 10.1, 9.9], [50, 50.2, 49.8], [80, 80, 80.1]])).toBeGreaterThan(0.99);
    expect(icc1([[1, 9, 5], [2, 8, 5], [9, 1, 5]])).toBeLessThan(0.1);
  });
  it('majority with ties', () => {
    expect(majority(['A', 'A', 'R'])).toBe('A');
    expect(majority(['A', 'R', 'U'])).toBe('?');
  });
});
