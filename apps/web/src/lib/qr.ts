import qrcode from 'qrcode-generator';

/** QR matrix for a Parakh code. Base45 fits the alphanumeric mode (~5.5 bits/char). */
export function qrMatrix(text: string): boolean[][] {
  const alnum = /^[0-9A-Z $%*+\-./:]*$/.test(text);
  for (const ecc of ['L', 'M'] as const) { // smallest symbol first: dense codes scan better from phone screens
    try {
      const q = qrcode(0, ecc);
      q.addData(text, alnum ? 'Alphanumeric' : 'Byte');
      q.make();
      const n = q.getModuleCount();
      return Array.from({ length: n }, (_, r) => Array.from({ length: n }, (_, c) => q.isDark(r, c)));
    } catch { /* too long at this level, try the next */ }
  }
  throw new Error('Too much data for one QR code');
}

export function qrPath(m: boolean[][]): string {
  let d = '';
  m.forEach((row, y) => row.forEach((on, x) => { if (on) d += `M${x + 4} ${y + 4}h1v1h-1z`; }));
  return d;
}

/** Scan a QR from a video frame: BarcodeDetector when present, jsQR otherwise. */
let detector: { detect: (s: CanvasImageSource) => Promise<{ rawValue: string }[]> } | null | undefined;
export async function scanFrame(v: HTMLVideoElement): Promise<string | null> {
  if (detector === undefined) {
    const BD = (window as unknown as { BarcodeDetector?: new (o: object) => typeof detector }).BarcodeDetector;
    try { detector = BD ? new BD({ formats: ['qr_code'] }) : null; } catch { detector = null; }
  }
  if (detector) {
    try { const r = await detector.detect(v); if (r[0]?.rawValue) return r[0].rawValue; } catch { /* fall back */ }
  }
  const w = v.videoWidth, h = v.videoHeight;
  if (!w) return null;
  const s = Math.min(1, 1000 / Math.max(w, h));
  const c = new OffscreenCanvas(Math.round(w * s), Math.round(h * s));
  const g = c.getContext('2d', { willReadFrequently: true })!;
  g.drawImage(v, 0, 0, c.width, c.height);
  const { default: jsQR } = await import('jsqr');
  const r = jsQR(g.getImageData(0, 0, c.width, c.height).data, c.width, c.height, { inversionAttempts: 'dontInvert' });
  return r?.data ?? null;
}
