/**
 * Tier-2 onion instance segmentation, post-processing half (the network runs in
 * the app worker or in Node for evaluation). The student predicts per pixel:
 * 0 background, 1 onion interior, 2 onion edge. Interior blobs are seeds; every
 * onion pixel (interior or edge) joins its nearest seed. Touching onions stay
 * apart because the edge band between them is never a seed.
 * Must match scripts/train_seg.py `instances()`.
 */
export interface SegMeta { file: string; side: number; mean: number[]; std: number[]; sha256: string; version: string }

/** Resize RGBA to the network input (long side = meta.side, both sides multiples of 32) as a CHW float tensor. */
export function segInput(img: { width: number; height: number; data: Uint8ClampedArray | Uint8Array }, meta: SegMeta) {
  const s = meta.side / Math.max(img.width, img.height);
  const w = Math.max(32, Math.round((img.width * s) / 32) * 32), h = Math.max(32, Math.round((img.height * s) / 32) * 32);
  const out = new Float32Array(3 * w * h);
  const fx = img.width / w, fy = img.height / h;
  for (let y = 0; y < h; y++) {
    const sy = Math.min(img.height - 1, (y + 0.5) * fy - 0.5), y0 = Math.max(0, Math.floor(sy)), y1 = Math.min(img.height - 1, y0 + 1), wy = sy - y0;
    for (let x = 0; x < w; x++) {
      const sx = Math.min(img.width - 1, (x + 0.5) * fx - 0.5), x0 = Math.max(0, Math.floor(sx)), x1 = Math.min(img.width - 1, x0 + 1), wx = sx - x0;
      for (let c = 0; c < 3; c++) {
        const v00 = img.data[(y0 * img.width + x0) * 4 + c], v01 = img.data[(y0 * img.width + x1) * 4 + c];
        const v10 = img.data[(y1 * img.width + x0) * 4 + c], v11 = img.data[(y1 * img.width + x1) * 4 + c];
        const v = (v00 * (1 - wx) + v01 * wx) * (1 - wy) + (v10 * (1 - wx) + v11 * wx) * wy;
        out[c * w * h + y * w + x] = (v / 255 - meta.mean[c]) / meta.std[c];
      }
    }
  }
  return { data: out, w, h };
}

/** Logits (3, h, w) -> instance labels (h, w), 0 = background. */
export function segInstances(logits: Float32Array, w: number, h: number, minSeedPx = 60): Int32Array {
  const n = w * h;
  const seed = new Uint8Array(n), fg = new Uint8Array(n);
  for (let i = 0; i < n; i++) {
    const a = logits[i], b = logits[n + i], c = logits[2 * n + i];
    const m = Math.max(a, b, c), ea = Math.exp(a - m), eb = Math.exp(b - m), ec = Math.exp(c - m), z = ea + eb + ec;
    if (eb / z > 0.5) seed[i] = 1;
    if ((eb + ec) / z > 0.5) fg[i] = 1;
  }
  // Label seed components (4-connected); drop tiny ones.
  const lab = new Int32Array(n);
  let next = 0;
  const stack: number[] = [];
  const sizes: number[] = [0];
  for (let s = 0; s < n; s++) {
    if (!seed[s] || lab[s]) continue;
    next++; let size = 0;
    lab[s] = next; stack.push(s);
    while (stack.length) {
      const i = stack.pop()!, x = i % w, y = (i - x) / w; size++;
      if (x > 0 && seed[i - 1] && !lab[i - 1]) { lab[i - 1] = next; stack.push(i - 1); }
      if (x < w - 1 && seed[i + 1] && !lab[i + 1]) { lab[i + 1] = next; stack.push(i + 1); }
      if (y > 0 && seed[i - w] && !lab[i - w]) { lab[i - w] = next; stack.push(i - w); }
      if (y < h - 1 && seed[i + w] && !lab[i + w]) { lab[i + w] = next; stack.push(i + w); }
    }
    sizes.push(size);
  }
  const remap = new Int32Array(next + 1);
  let k = 0;
  for (let j = 1; j <= next; j++) remap[j] = sizes[j] >= minSeedPx ? ++k : 0;
  for (let i = 0; i < n; i++) lab[i] = remap[lab[i]];
  // Multi-source BFS: each onion pixel joins the nearest seed (through onion pixels).
  const q = new Int32Array(n);
  let qh = 0, qt = 0;
  for (let i = 0; i < n; i++) if (lab[i]) q[qt++] = i;
  while (qh < qt) {
    const i = q[qh++], x = i % w, y = (i - x) / w, l = lab[i];
    const nb = [x > 0 ? i - 1 : -1, x < w - 1 ? i + 1 : -1, y > 0 ? i - w : -1, y < h - 1 ? i + w : -1];
    for (const j of nb) if (j >= 0 && fg[j] && !lab[j]) { lab[j] = l; q[qt++] = j; }
  }
  return lab;
}

/** Nearest-neighbour resize of a label map. */
export function resizeLabels(lab: Int32Array, w: number, h: number, W: number, H: number): Int32Array {
  const out = new Int32Array(W * H);
  for (let y = 0; y < H; y++) {
    const sy = Math.min(h - 1, Math.floor(((y + 0.5) * h) / H));
    for (let x = 0; x < W; x++) out[y * W + x] = lab[sy * w + Math.min(w - 1, Math.floor(((x + 0.5) * w) / W))];
  }
  return out;
}
