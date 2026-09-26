import { drawSample, sha256Hex } from '@parakh/core';
import { db, type CaptureRow, type LotRow } from './db';
import { loadSettings } from './device';
import { newLotId } from './lots';
import { analyzeBitmap, toEvidenceJpeg } from './vision';

/**
 * Real photos from the public Zenodo dataset 10.5281/zenodo.20254934
 * (CC-BY 4.0, Pune markets, Motorola Edge 50 Ultra). Used for the replay demo
 * only; never for a reported accuracy number. See docs/SOURCES.md D1.
 */
export const SAMPLES = [
  { file: 'Onion13276.jpg', note: 'unhealthy red, white cloth' },
  { file: 'Onion07046.jpg', note: 'healthy red, beige cloth' },
  { file: 'Onion07049.jpg', note: 'healthy red, lilac cloth' },
  { file: 'Onion15296.jpg', note: 'unhealthy white, grey cloth' },
  { file: 'Onion13291.jpg', note: 'unhealthy red, grey cloth' },
  { file: 'Onion11156.jpg', note: 'healthy white, red cloth' },
  { file: 'Onion07101.jpg', note: 'healthy red, tiles' },
  { file: 'Onion13277.jpg', note: 'unhealthy red, wooden table (hard)' },
];

/**
 * The stored photos carry no calibration sheet, so their scale comes from the
 * camera-intrinsics tier with this ASSUMED camera height (A-REPLAY-1). The tier,
 * its ±25 % scale uncertainty and this height are printed on every receipt.
 */
export const REPLAY_CAM_H = 260;

async function loadImage(src: string): Promise<HTMLImageElement> {
  const img = new Image();
  img.src = src;
  await img.decode();
  return img;
}

async function addCapture(lotId: string, file: string, tray: number, look: number, at: Date) {
  const img = await loadImage(`./samples/${file}`);
  const ev = await toEvidenceJpeg(img, img.naturalWidth, img.naturalHeight);
  const a = await analyzeBitmap(ev.bitmap, { camHmm: REPLAY_CAM_H });
  const row: CaptureRow = {
    id: `${lotId}-t${tray}-l${look}`, lotId, tray, look, at: at.toISOString(), mode: 'replay', image: ev.blob,
    imageHash: await sha256Hex(new Uint8Array(await ev.blob.arrayBuffer())), width: a.width, height: a.height,
    calib: { tier: a.calib.tier, mmPerPx: a.calib.mmPerPx, camHmm: a.calib.camHmm, scaleSd: a.calib.scaleSd, note: a.calib.note },
    bulbs: a.bulbs, timings: a.timings, loc: null,
  };
  await db.captures.put(row);
}

/** One demo lot: four real market photos as four trays, replayed through the same pipeline. */
export async function seedDemoLot(opts: { files?: string[]; centre?: string; farmer?: string } = {}): Promise<string> {
  const s = await loadSettings();
  const centre = opts.centre ?? s.centre;
  const id = newLotId(centre);
  const files = opts.files ?? ['Onion13276.jpg', 'Onion07046.jpg', 'Onion07049.jpg', 'Onion15296.jpg'];
  const d = await drawSample({ lotId: id, farmerCode: '4821', officerCode: '1177', date: new Date().toISOString().slice(0, 10), nSacks: 24, k: 5 });
  const lot: LotRow = {
    id, createdAt: new Date().toISOString(), centre, officer: s.officer, farmerRef: opts.farmer ?? 'Demo seller (replay)', variety: 'mixed',
    sacks: 24, declaredKg: 1200, packId: s.packId, mode: 'replay', overrides: [], certHashes: [], demo: true,
    sampling: { farmerCode: '4821', officerCode: '1177', seed: d.seed, draws: d.draws },
  };
  await db.lots.put(lot);
  const t0 = Date.now();
  for (let i = 0; i < files.length; i++) await addCapture(id, files[i], i + 1, 1, new Date(t0 + i * 45000));
  return id;
}
