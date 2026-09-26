import { DEFECTS, type BulbMeasurement } from '../src';

let seed = 1;
const rnd = () => ((seed = (seed * 1103515245 + 12345) >>> 0) / 2 ** 32);
export function resetRnd(s = 1) { seed = s; }

/** Hand-built measurement records for engine tests (not images, not accuracy data). */
export function bulb(i: number, over: Partial<BulbMeasurement> & { f?: Partial<Record<(typeof DEFECTS)[number], number | null>> } = {}): BulbMeasurement {
  const frac = Object.fromEntries(DEFECTS.map((d) => [d, d === 'cut' ? null : 0])) as BulbMeasurement['frac'];
  Object.assign(frac, over.f ?? {});
  const { f, ...rest } = over;
  return {
    id: `b${i}`, tray: 1, look: 1, size: { min: 550, max: 600, sd: 10 }, frac, fsd: 10,
    shape: { double: false, bottleneck: false, split: false }, conf: 900, w: 900, wsd: 150, ...rest,
  };
}

export function randomLot(n: number, trays: number, looks = 2): BulbMeasurement[] {
  const out: BulbMeasurement[] = [];
  for (let i = 0; i < n; i++) {
    const d = 350 + Math.floor(rnd() * 400);
    out.push(bulb(i, {
      tray: 1 + (i % trays), look: 1 + (Math.floor(i / trays) % looks),
      size: { min: d, max: d + Math.floor(rnd() * 80), sd: 5 + Math.floor(rnd() * 25) },
      f: { blackening: rnd() < 0.3 ? Math.floor(rnd() * 500) : 0, spots: Math.floor(rnd() * 300), sunburn: rnd() < 0.2 ? Math.floor(rnd() * 200) : 0,
        rot: rnd() < 0.08 ? 50 + Math.floor(rnd() * 400) : 0, sprouting: rnd() < 0.05 ? 40 : 0, peeled: Math.floor(rnd() * 150) },
      conf: 500 + Math.floor(rnd() * 500), w: Math.floor(d * d * d * 0.0005 / 100), wsd: 100,
    }));
  }
  return out;
}
