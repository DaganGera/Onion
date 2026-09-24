/// <reference lib="webworker" />
// Tier-1 learned cross-check, run in the vision worker when models/tier1.json says it ships.
import { applyTier1, bulbCrop, downscale, TIER0, type BulbResult, type RGBA } from '@parakh/vision';

interface Meta { ship: boolean; file: string; size: number; mean: number[]; std: number[]; thr_high: number; sha256: string }
let meta: Meta | null | undefined;
let session: unknown = null;

async function load(baseHref: string): Promise<Meta | null> {
  if (meta !== undefined) return meta;
  try {
    const base = new URL(baseHref);
    const r = await fetch(new URL('models/tier1.json', base));
    meta = r.ok ? ((await r.json()) as Meta) : null;
    if (!meta?.ship) return (meta = null);
    const ort = await import('onnxruntime-web/wasm');
    ort.env.wasm.wasmPaths = new URL('ort/', base).href;
    ort.env.wasm.numThreads = 1;
    const bytes = new Uint8Array(await (await fetch(new URL(`models/${meta.file}`, base))).arrayBuffer());
    session = await ort.InferenceSession.create(bytes, { executionProviders: ['wasm'] });
    return meta;
  } catch (e) {
    console.warn('Tier-1 unavailable, Tier-0 only:', e);
    return (meta = null);
  }
}

export async function runTier1(img: RGBA, bulbs: BulbResult[], baseHref: string): Promise<{ ms: number } | null> {
  const m = await load(baseHref);
  if (!m || !session) return null;
  const t0 = performance.now();
  const { img: work } = downscale(img, TIER0.workSide);
  const use = bulbs.filter((b) => !b.excluded);
  if (!use.length) return { ms: 0 };
  const S = m.size, n = use.length, data = new Float32Array(n * 3 * S * S);
  use.forEach((b, k) => {
    const c = bulbCrop(work, b, S);
    for (let i = 0; i < S * S; i++) for (let ch = 0; ch < 3; ch++) data[k * 3 * S * S + ch * S * S + i] = (c[i * 4 + ch] / 255 - m.mean[ch]) / m.std[ch];
  });
  const ort = await import('onnxruntime-web/wasm');
  const out = await (session as { run: (f: Record<string, unknown>) => Promise<Record<string, { data: Float32Array }>> }).run({ x: new ort.Tensor('float32', data, [n, 3, S, S]) });
  const logits = out.logits.data;
  use.forEach((b, k) => {
    const a = logits[2 * k], z = logits[2 * k + 1];
    applyTier1(b, 1 / (1 + Math.exp(a - z)), m.thr_high);
  });
  return { ms: performance.now() - t0 };
}
