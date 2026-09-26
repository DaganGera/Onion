import { useRef, useState } from 'react';
import { segInput, segInstances, resizeLabels, type SegMeta } from '@parakh/vision';

const SAMPLES = [
  { src: './demo/Onion07046.jpg', label: 'Healthy red, cloth' },
  { src: './demo/Onion13276.jpg', label: 'Rotting red, pile' },
  { src: './demo/Onion15296.jpg', label: 'White, damaged' },
  { src: './demo/Onion11156.jpg', label: 'White, on red cloth' },
];
const PALETTE = [[230, 174, 69], [247, 238, 225], [214, 90, 140], [120, 200, 150], [120, 170, 240], [240, 130, 90]];

type Ort = typeof import('onnxruntime-web/wasm');
let session: Promise<{ ort: Ort; s: unknown; meta: SegMeta }> | null = null;
function loadModel(onProgress: (s: string) => void) {
  if (!session) session = (async () => {
    onProgress('Loading the on-device runtime…');
    const ort = await import('onnxruntime-web/wasm');
    ort.env.wasm.wasmPaths = new URL('./ort/', location.href).href;
    ort.env.wasm.numThreads = 1;
    const meta: SegMeta = await (await fetch('./models/seg.json')).json();
    onProgress('Downloading the onion model (16 MB, once)…');
    const bytes = new Uint8Array(await (await fetch(`./models/${meta.file}`)).arrayBuffer());
    const s = await ort.InferenceSession.create(bytes, { executionProviders: ['wasm'] });
    return { ort, s, meta };
  })();
  return session;
}

export function LiveDemo() {
  const canvas = useRef<HTMLCanvasElement>(null);
  const [status, setStatus] = useState('Pick a real market photo, or use your own. Nothing is uploaded.');
  const [result, setResult] = useState<{ n: number; ms: number } | null>(null);
  const [busy, setBusy] = useState(false);
  const [active, setActive] = useState<string | null>(null);

  async function run(src: string) {
    setBusy(true); setResult(null); setActive(src);
    try {
      const img = new Image(); img.crossOrigin = 'anonymous'; img.src = src; await img.decode();
      const c = canvas.current!;
      const scale = Math.min(1, 1024 / Math.max(img.naturalWidth, img.naturalHeight));
      c.width = Math.round(img.naturalWidth * scale); c.height = Math.round(img.naturalHeight * scale);
      const g = c.getContext('2d', { willReadFrequently: true })!;
      g.drawImage(img, 0, 0, c.width, c.height);
      const { ort, s, meta } = await loadModel(setStatus);
      setStatus('Finding onions on your device…');
      const px = g.getImageData(0, 0, c.width, c.height);
      const t0 = performance.now();
      const x = segInput(px, meta);
      const out = await (s as { run: (f: Record<string, unknown>) => Promise<Record<string, { data: Float32Array }>> }).run({ x: new ort.Tensor('float32', x.data, [1, 3, x.h, x.w]) });
      const lab = resizeLabels(segInstances(out.logits.data, x.w, x.h), x.w, x.h, c.width, c.height);
      const ms = performance.now() - t0;
      // Paint each onion: tint + outline.
      const W = c.width, H = c.height, d = px.data;
      const ids = new Set<number>();
      for (let i = 0; i < W * H; i++) {
        const k = lab[i];
        if (!k) continue;
        ids.add(k);
        const col = PALETTE[k % PALETTE.length];
        const x0 = i % W, y0 = (i - x0) / W;
        const edge = x0 === 0 || y0 === 0 || x0 === W - 1 || y0 === H - 1 || x0 < 2 || x0 > W - 3 || y0 < 2 || y0 > H - 3 || lab[i - 2] !== k || lab[i + 2] !== k || lab[i - 2 * W] !== k || lab[i + 2 * W] !== k;
        const a = edge ? 0.95 : 0.22;
        d[i * 4] = d[i * 4] * (1 - a) + col[0] * a; d[i * 4 + 1] = d[i * 4 + 1] * (1 - a) + col[1] * a; d[i * 4 + 2] = d[i * 4 + 2] * (1 - a) + col[2] * a;
      }
      g.putImageData(px, 0, 0);
      setResult({ n: ids.size, ms });
      setStatus('Done. This ran entirely in your browser.');
    } catch (e) {
      setStatus('This browser could not run the model: ' + String(e).slice(0, 120));
    } finally { setBusy(false); }
  }

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)] items-start">
      <div className="liquid-glass rounded-[1.25rem] p-3">
        <div className="relative aspect-[4/3] w-full overflow-hidden rounded-[0.9rem] bg-black/40">
          <canvas ref={canvas} className="h-full w-full object-contain" aria-label="Photo with detected onions outlined" />
          {!active && <div className="absolute inset-0 grid place-items-center text-white/60 text-sm font-body px-6 text-center">Choose a photo to see every onion found and outlined.</div>}
          {busy && <div className="absolute inset-x-0 bottom-0 h-1 overflow-hidden bg-white/10"><div className="h-full w-1/3 bg-[var(--color-gold)] animate-[slide_1.1s_ease-in-out_infinite]" /></div>}
        </div>
      </div>
      <div className="flex flex-col gap-4">
        <div className="grid grid-cols-2 gap-3">
          {SAMPLES.map((s) => (
            <button key={s.src} disabled={busy} onClick={() => run(s.src)}
              className={`liquid-glass rounded-[0.9rem] p-1.5 text-left btn-hover disabled:opacity-60 ${active === s.src ? 'ring-2 ring-[var(--color-gold)]' : ''}`}>
              <img src={s.src} alt="" className="aspect-[4/3] w-full rounded-[0.6rem] object-cover" />
              <span className="block px-1.5 pt-1.5 pb-0.5 text-xs text-white/85 font-body">{s.label}</span>
            </button>
          ))}
        </div>
        <label className="liquid-glass rounded-full px-5 py-3 text-sm text-white text-center cursor-pointer btn-hover">
          Use my own onion photo
          <input type="file" accept="image/*" className="sr-only" onChange={(e) => { const f = e.target.files?.[0]; if (f) run(URL.createObjectURL(f)); }} />
        </label>
        <div className="liquid-glass rounded-[1.25rem] p-5" aria-live="polite">
          {result ? (
            <div className="flex items-end gap-6">
              <div><div className="font-heading italic text-5xl leading-none tracking-[-1px]">{result.n}</div><div className="mt-2 text-xs text-white/80">onions found</div></div>
              <div><div className="font-heading italic text-5xl leading-none tracking-[-1px]">{(result.ms / 1000).toFixed(1)}s</div><div className="mt-2 text-xs text-white/80">on this device</div></div>
            </div>
          ) : null}
          <p className={`text-sm text-white/85 font-light ${result ? 'mt-4' : ''}`}>{status}</p>
          <p className="mt-2 text-xs text-white/55">Demo photos: Zenodo 10.5281/zenodo.20254934, CC-BY 4.0. The full app also sizes each onion in millimetres, checks defects and grades by rule pack.</p>
        </div>
      </div>
    </div>
  );
}
