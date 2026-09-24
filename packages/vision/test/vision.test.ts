import { describe, expect, it } from 'vitest';
import fs from 'node:fs';
import { PNG } from 'pngjs';
import { heightCorrect } from '@parakh/core';
import { applyH, calibFromCoin, calibFromMarkers, toLab, components, convexHull, detectAruco, distanceTransform, feret, mask, watershedSplit } from '../src';

describe('calibration', () => {
  it('finds all 8 markers of the legacy printed mat and recovers its scale (11.81 px/mm at 300 dpi)', () => {
    const png = PNG.sync.read(fs.readFileSync('legacy/calibration_mat.png'));
    const m = detectAruco({ width: png.width, height: png.height, data: png.data });
    expect(m.map((x) => x.id).sort()).toEqual([0, 1, 2, 3, 4, 5, 6, 7]);
    const cal = calibFromMarkers(m, png.width, png.height)!;
    expect(1 / cal.mmPerPx).toBeCloseTo(3508 / 297, 1);
    // A known point: marker 0 top-left corner is at (12, 12) mm.
    const p = applyH(cal.H!, m.find((x) => x.id === 0)!.corners[0]);
    expect(p.x).toBeCloseTo(12, 0);
    expect(p.y).toBeCloseTo(12, 0);
  });
});

describe('coin tier', () => {
  it('a tapped 27 mm disc of 90 px gives 0.3 mm/px; tapping a non-disc is refused', () => {
    const w = 800, h = 600, d = new Uint8ClampedArray(w * h * 4);
    for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
      const i = (y * w + x) * 4, inDisc = Math.hypot(x - 200, y - 150) < 45, inBar = x > 20 && x < 120 && y > 20 && y < 40;
      const v = inDisc ? [190, 170, 90] : inBar ? [40, 120, 40] : [235, 235, 230];
      d[i] = v[0]; d[i + 1] = v[1]; d[i + 2] = v[2]; d[i + 3] = 255;
    }
    const lab = toLab({ width: w, height: h, data: d });
    const cal = calibFromCoin(lab, { x: 200, y: 150 }, 27)!;
    expect(cal.tier).toBe('coin');
    expect(cal.mmPerPx).toBeCloseTo(27 / 90, 2);
    expect(calibFromCoin(lab, { x: 70, y: 30 }, 27)).toBeNull();
  });
});

describe('geometry', () => {
  it('Feret of a 10x4 rectangle is min 4, max ~10.77', () => {
    const f = feret(convexHull([{ x: 0, y: 0 }, { x: 10, y: 0 }, { x: 10, y: 4 }, { x: 0, y: 4 }, { x: 5, y: 2 }]));
    expect(f.min).toBeCloseTo(4, 6);
    expect(f.max).toBeCloseTo(Math.hypot(10, 4), 6);
  });
  it('height correction shrinks a 60 mm plane reading by d/(2H)', () => {
    expect(heightCorrect(60, 400)).toBeCloseTo(60 / 1.075, 6);
    expect(heightCorrect(60, 0)).toBe(60);
  });
  it('watershed splits two touching disks into two regions', () => {
    const w = 120, h = 70, m = mask(w, h);
    for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) if (Math.hypot(x - 38, y - 35) < 28 || Math.hypot(x - 84, y - 35) < 26) m.data[y * w + x] = 1;
    const { labels } = components(m);
    const ws = watershedSplit(m, distanceTransform(m), labels, { minPeak: 5, nms: 1.35 });
    expect(new Set(Array.from(ws).filter((v) => v > 0)).size).toBe(2);
  });
});
