/// <reference lib="webworker" />
// Tier-2 learned onion segmentation in the vision worker (ONNX Runtime Web, WASM).
import { downscale, resizeLabels, segInput, segInstances, workSize, type RGBA, type SegMeta } from '@parakh/vision';

let meta: SegMeta | null | undefined;
let session: unknown = null;

async function load(baseHref: string): Promise<SegMeta | null> {
  if (meta !== undefined) return meta;
  try {
    const base = new URL(baseHref);
    const r = await fetch(new URL('models/seg.json', base));
    meta = r.ok ? ((await r.json()) as SegMeta) : null;
    if (!meta) return null;
    const ort = await import('onnxruntime-web/wasm');
    ort.env.wasm.wasmPaths = new URL('ort/', base).href;
    ort.env.wasm.numThreads = 1;
    const bytes = new Uint8Array(await (await fetch(new URL(`models/${meta.file}`, base))).arrayBuffer());
    session = await ort.InferenceSession.create(bytes, { executionProviders: ['wasm'] });
    return meta;
  } catch (e) {
    console.warn('Tier-2 segmentation unavailable, colour detector only:', e);
    return (meta = null);
  }
}

/** Onion instance labels at analyze()'s working resolution, or null when no model ships. */
export async function runSeg(img: RGBA, baseHref: string): Promise<{ labels: Int32Array; ms: number } | null> {
  const m = await load(baseHref);
  if (!m || !session) return null;
  const t0 = performance.now();
  const { w: W, h: H } = workSize(img.width, img.height);
  const work = downscale(img, Math.max(W, H)).img;
  const x = segInput(work, m);
  const ort = await import('onnxruntime-web/wasm');
  const out = await (session as { run: (f: Record<string, unknown>) => Promise<Record<string, { data: Float32Array }>> }).run({ x: new ort.Tensor('float32', x.data, [1, 3, x.h, x.w]) });
  const lab = segInstances(out.logits.data, x.w, x.h);
  return { labels: resizeLabels(lab, x.w, x.h, W, H), ms: performance.now() - t0 };
}
