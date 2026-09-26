import { describe, expect, it } from 'vitest';
import fc from 'fast-check';
import { adjudicateBulb, applyOverrides, packById, PACKS, type Bucket } from '../src';
import { bulb } from './fixtures';

const jun = packById('in-psf-2026-06-relaxed-a')!;
const RANK: Record<Bucket, number> = { GRADE_A: 0, URS: 1, REFER: 1.5, REJECT: 2 };

describe('adjudication', () => {
  it('clean medium bulb is Grade A', () => {
    expect(adjudicateBulb(bulb(0), jun).bucket).toBe('GRADE_A');
  });
  it('34.2% blackening is beyond the relaxed 30% limit: REJECT with explicit codes', () => {
    const v = adjudicateBulb(bulb(0, { f: { blackening: 342 } }), jun);
    expect(v.bucket).toBe('REJECT');
    expect(v.codes).toContain('BLACKENING_34.2PCT_GT_30PCT');
    expect(v.codes).toContain('BLACKENING_34.2PCT_GT_5PCT');
  });
  it('20% blackening falls to URS with a reason why not A', () => {
    const v = adjudicateBulb(bulb(0, { f: { blackening: 200 } }), jun);
    expect(v.bucket).toBe('URS');
    expect(v.codes).toEqual(['BLACKENING_20PCT_GT_5PCT']);
  });
  it('size straddling 45 mm within its uncertainty goes to REFER, not a coin flip', () => {
    const v = adjudicateBulb(bulb(0, { size: { min: 448, max: 470, sd: 10 } }), jun);
    expect(v.bucket).toBe('REFER');
    expect(v.codes.some((c) => c.startsWith('BORDERLINE_SIZE_44.8MM'))).toBe(true);
  });
  it('undersized for URS too: REJECT with SIZE code', () => {
    const v = adjudicateBulb(bulb(0, { size: { min: 300, max: 330, sd: 5 } }), jun);
    expect(v.bucket).toBe('REJECT');
    expect(v.codes).toContain('SIZE_30MM_LT_35MM');
  });
  it('rot is a hard reject', () => {
    expect(adjudicateBulb(bulb(0, { f: { rot: 120 } }), jun)).toMatchObject({ bucket: 'REJECT', codes: ['ROT_12PCT_GT_1PCT'] });
  });
  it('low perception confidence goes to REFER', () => {
    expect(adjudicateBulb(bulb(0, { conf: 300 }), jun).bucket).toBe('REFER');
  });
  it('not-assessed cut is noted, not silently passed', () => {
    expect(adjudicateBulb(bulb(0), jun).notes).toContain('NOT_ASSESSED_CUT');
  });
  it('more defect never gives a better bucket (monotonicity, all packs, property)', () => {
    fc.assert(fc.property(fc.integer({ min: 0, max: 1000 }), fc.integer({ min: 0, max: 1000 }),
      fc.constantFrom('blackening', 'spots', 'sunburn', 'rot', 'sprouting', 'peeled'), fc.integer({ min: 0, max: PACKS.length - 1 }),
      (a, b, d, pi) => {
        const [lo, hi] = a < b ? [a, b] : [b, a];
        const p = PACKS[pi];
        const x = adjudicateBulb(bulb(0, { f: { [d]: lo } }), p).bucket;
        const y = adjudicateBulb(bulb(0, { f: { [d]: hi } }), p).bucket;
        expect(RANK[y]).toBeGreaterThanOrEqual(RANK[x] === 1.5 ? 1 : RANK[x]);
      }));
  });
  it('overrides sit beside the AI verdict; contest sends to REFER; latest wins', () => {
    const ai = [adjudicateBulb(bulb(0), jun), adjudicateBulb(bulb(1, { f: { rot: 200 } }), jun)];
    const f = applyOverrides(ai, [
      { bulb: 'b1', by: 'farmer', kind: 'contest', reason: 'DEFECT_IS_SOIL_OR_SHADOW', at: 't1' },
      { bulb: 'b0', by: 'officer', kind: 'override', to: 'URS', reason: 'VISUAL_REINSPECTION', at: 't2' },
    ]);
    expect(f[0]).toMatchObject({ ai: 'GRADE_A', final: 'URS' });
    expect(f[1]).toMatchObject({ ai: 'REJECT', final: 'REFER' });
    const g = applyOverrides(ai, [
      { bulb: 'b1', by: 'farmer', kind: 'contest', reason: 'DEFECT_IS_SOIL_OR_SHADOW', at: 't1' },
      { bulb: 'b1', by: 'officer', kind: 'override', to: 'URS', reason: 'DEFECT_IS_SOIL_OR_SHADOW', at: 't3' },
    ]);
    expect(g[1]).toMatchObject({ ai: 'REJECT', final: 'URS' });
  });
});
