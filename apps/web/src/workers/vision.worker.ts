/// <reference lib="webworker" />
import { analyze, frameStats, quickScan, type AnalyzeOptions } from '@parakh/vision';
import { runTier1 } from './tier1';
import { runSeg } from './seg';

type Req =
  | { id: number; kind: 'analyze'; bitmap: ImageBitmap; opts: AnalyzeOptions; base: string }
  | { id: number; kind: 'scan'; bitmap: ImageBitmap };

function pixels(bitmap: ImageBitmap) {
  const c = new OffscreenCanvas(bitmap.width, bitmap.height);
  const g = c.getContext('2d', { willReadFrequently: true })!;
  g.drawImage(bitmap, 0, 0);
  bitmap.close();
  return g.getImageData(0, 0, c.width, c.height);
}

self.onmessage = async (e: MessageEvent<Req>) => {
  const m = e.data;
  try {
    const img = pixels(m.bitmap);
    if (m.kind === 'scan') {
      const s = quickScan(img);
      const f = frameStats(img);
      (self as unknown as Worker).postMessage({ id: m.id, ok: true, value: { ...s, ...f } });
    } else {
      const t0 = performance.now();
      const seg = await runSeg(img, m.base).catch(() => null);
      const a = analyze(img, seg ? { ...m.opts, instances: seg.labels } : m.opts);
      a.timings.seg = seg ? seg.ms : -1;
      const t1 = await runTier1(img, a.bulbs, m.base);
      if (t1) a.timings.tier1 = t1.ms;
      a.timings.total = performance.now() - t0;
      (self as unknown as Worker).postMessage({ id: m.id, ok: true, value: a });
    }
  } catch (err) {
    (self as unknown as Worker).postMessage({ id: m.id, ok: false, error: String(err) });
  }
};
