import { TIER0 } from './config';
import { downscale, toGray, type RGBA } from './img';

export type GateId = 'level' | 'sharp' | 'exposure' | 'glare' | 'target' | 'bulbs';
export interface Gate { id: GateId; ok: boolean; value: number; msg: string }

export interface FrameStats { sharp: number; meanL: number; clipped: number }

/** Cheap per-frame statistics for the live Capture Guard (runs on a ~480 px preview). */
export function frameStats(img: RGBA): FrameStats {
  const { img: small } = downscale(img, 480);
  const g = toGray(small);
  const { width: w, height: h, data } = g;
  let sum = 0, sum2 = 0, n = 0, clipped = 0, lsum = 0;
  for (let y = 1; y < h - 1; y++) {
    for (let x = 1; x < w - 1; x++) {
      const i = y * w + x;
      const lap = data[i - 1] + data[i + 1] + data[i - w] + data[i + w] - 4 * data[i];
      sum += lap; sum2 += lap * lap; n++;
    }
  }
  for (let i = 0; i < w * h; i++) { lsum += data[i]; if (data[i] > 250) clipped++; }
  const mean = sum / n;
  return { sharp: sum2 / n - mean * mean, meanL: (lsum / (w * h)) * (100 / 255), clipped: clipped / (w * h) };
}

/**
 * Each gate returns one plain sentence. The Capture Guard shows the first
 * failing one; the shutter fires only when all pass.
 */
export function evaluateGates(s: FrameStats, o: { tiltDeg: number | null; targetFound: boolean; bulbs: number }): Gate[] {
  const g = TIER0.guard;
  return [
    { id: 'level', ok: o.tiltDeg === null || o.tiltDeg <= g.maxTiltDeg, value: o.tiltDeg ?? 0, msg: 'Hold the phone flat, parallel to the table.' },
    { id: 'sharp', ok: s.sharp >= g.minSharp, value: s.sharp, msg: 'Too blurry. Hold still or move a little further away.' },
    { id: 'exposure', ok: s.meanL >= g.minMeanL && s.meanL <= g.maxMeanL, value: s.meanL, msg: s.meanL < g.minMeanL ? 'Too dark. Move to better light.' : 'Too bright. Avoid direct sun on the tray.' },
    { id: 'glare', ok: s.clipped <= g.maxClipped, value: s.clipped, msg: 'Glare on the onions. Tilt away from the light or shade the tray.' },
    { id: 'target', ok: o.targetFound, value: o.targetFound ? 1 : 0, msg: 'Keep the calibration sheet fully in view.' },
    { id: 'bulbs', ok: o.bulbs >= g.minBulbs, value: o.bulbs, msg: 'No onions found. Point the camera at the tray.' },
  ];
}

/** Tilt from a DeviceOrientation reading (phone flat, screen up = 0 deg). */
export function tiltFromOrientation(beta: number | null, gamma: number | null): number | null {
  if (beta === null || gamma === null) return null;
  const b = (beta * Math.PI) / 180, c = (gamma * Math.PI) / 180;
  return (Math.acos(Math.max(-1, Math.min(1, Math.cos(b) * Math.cos(c)))) * 180) / Math.PI;
}
