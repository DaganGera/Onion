/** Minimal image containers. RGBA bytes, row-major, like ImageData. */
export interface RGBA { width: number; height: number; data: Uint8ClampedArray | Uint8Array }
export interface Gray { width: number; height: number; data: Float32Array }
export interface Mask { width: number; height: number; data: Uint8Array }

export const mask = (w: number, h: number): Mask => ({ width: w, height: h, data: new Uint8Array(w * h) });

/** Area-average downscale so the long side is at most `maxSide`. Returns the scale factor used. */
export function downscale(img: RGBA, maxSide: number): { img: RGBA; s: number } {
  const long = Math.max(img.width, img.height);
  if (long <= maxSide) return { img, s: 1 };
  const s = maxSide / long;
  const w = Math.max(1, Math.round(img.width * s)), h = Math.max(1, Math.round(img.height * s));
  const out = new Uint8ClampedArray(w * h * 4);
  const fx = img.width / w, fy = img.height / h;
  for (let y = 0; y < h; y++) {
    const y0 = Math.floor(y * fy), y1 = Math.max(y0 + 1, Math.floor((y + 1) * fy));
    for (let x = 0; x < w; x++) {
      const x0 = Math.floor(x * fx), x1 = Math.max(x0 + 1, Math.floor((x + 1) * fx));
      let r = 0, g = 0, b = 0, n = 0;
      for (let yy = y0; yy < y1; yy++) {
        let i = (yy * img.width + x0) * 4;
        for (let xx = x0; xx < x1; xx++, i += 4) { r += img.data[i]; g += img.data[i + 1]; b += img.data[i + 2]; n++; }
      }
      const o = (y * w + x) * 4;
      out[o] = r / n; out[o + 1] = g / n; out[o + 2] = b / n; out[o + 3] = 255;
    }
  }
  return { img: { width: w, height: h, data: out }, s: w / img.width };
}

export function toGray(img: RGBA): Gray {
  const n = img.width * img.height, out = new Float32Array(n);
  for (let i = 0, j = 0; i < n; i++, j += 4) out[i] = 0.299 * img.data[j] + 0.587 * img.data[j + 1] + 0.114 * img.data[j + 2];
  return { width: img.width, height: img.height, data: out };
}

// ---- CIE Lab (D65) with a lookup table for the sRGB decode ----
const LIN = new Float32Array(256);
for (let i = 0; i < 256; i++) { const c = i / 255; LIN[i] = c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4); }
const f = (t: number) => (t > 0.008856 ? Math.cbrt(t) : 7.787 * t + 16 / 116);

export interface Lab { L: Float32Array; a: Float32Array; b: Float32Array; width: number; height: number }

export function toLab(img: RGBA): Lab {
  const n = img.width * img.height;
  const L = new Float32Array(n), A = new Float32Array(n), B = new Float32Array(n);
  for (let i = 0, j = 0; i < n; i++, j += 4) {
    const r = LIN[img.data[j]], g = LIN[img.data[j + 1]], b = LIN[img.data[j + 2]];
    const x = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047;
    const y = 0.2126 * r + 0.7152 * g + 0.0722 * b;
    const z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883;
    const fx = f(x), fy = f(y), fz = f(z);
    L[i] = 116 * fy - 16; A[i] = 500 * (fx - fy); B[i] = 200 * (fy - fz);
  }
  return { L, a: A, b: B, width: img.width, height: img.height };
}

export function median(xs: ArrayLike<number>): number {
  const a = Float32Array.from(xs).sort();
  if (!a.length) return 0;
  const m = a.length >> 1;
  return a.length % 2 ? a[m] : (a[m - 1] + a[m]) / 2;
}

export function quantile(sorted: Float32Array, q: number): number {
  if (!sorted.length) return 0;
  return sorted[Math.min(sorted.length - 1, Math.max(0, Math.floor(q * (sorted.length - 1))))];
}
