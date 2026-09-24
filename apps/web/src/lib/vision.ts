import type { Analysis, AnalyzeOptions } from '@parakh/vision';

let worker: Worker | null = null;
let seq = 0;
const pending = new Map<number, { res: (v: any) => void; rej: (e: Error) => void }>();

function w(): Worker {
  if (worker) return worker;
  worker = new Worker(new URL('../workers/vision.worker.ts', import.meta.url), { type: 'module' });
  worker.onmessage = (e) => {
    const p = pending.get(e.data.id);
    if (!p) return;
    pending.delete(e.data.id);
    e.data.ok ? p.res(e.data.value) : p.rej(new Error(e.data.error));
  };
  return worker;
}

function call<T>(msg: Record<string, unknown>, bitmap: ImageBitmap): Promise<T> {
  const id = ++seq;
  return new Promise<T>((res, rej) => {
    pending.set(id, { res, rej });
    w().postMessage({ ...msg, id, bitmap }, [bitmap]);
  });
}

export const analyzeBitmap = (bitmap: ImageBitmap, opts: AnalyzeOptions = {}) => call<Analysis>({ kind: 'analyze', opts }, bitmap);
export const scanBitmap = (bitmap: ImageBitmap) =>
  call<{ target: 'aruco' | 'a4' | null; bulbs: number; sharp: number; meanL: number; clipped: number }>({ kind: 'scan' }, bitmap);

/** Downscale a source to at most maxSide and JPEG-encode it (the stored evidence image). */
export async function toEvidenceJpeg(src: CanvasImageSource, w0: number, h0: number, maxSide = 1024): Promise<{ blob: Blob; bitmap: ImageBitmap; w: number; h: number }> {
  const s = Math.min(1, maxSide / Math.max(w0, h0));
  const w = Math.round(w0 * s), h = Math.round(h0 * s);
  const c = new OffscreenCanvas(w, h);
  const g = c.getContext('2d')!;
  g.drawImage(src, 0, 0, w, h);
  const blob = await c.convertToBlob({ type: 'image/jpeg', quality: 0.9 });
  // Analyse the decoded JPEG, so what is stored is exactly what was measured.
  const bitmap = await createImageBitmap(blob);
  return { blob, bitmap, w, h };
}
