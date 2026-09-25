// Onion counting accuracy: Tier-0 colour detector vs Tier-2 learned segmentation.
// node --import tsx tools/eval_count.ts <zenodo root (contains "2. Bulb")> [field photo ...]
// Truth: tools/fixtures/count_truth.csv (onions counted by eye in held-out photos; ambiguous piles flagged
// and reported separately). Runs the same post-processing code the phone uses.
import fs from 'node:fs';
import path from 'node:path';
import * as ort from 'onnxruntime-node';
import { analyze, resizeLabels, segInput, segInstances, workSize, downscale, type RGBA, type SegMeta } from '@parakh/vision';
import { readImage } from './imgio.mjs';

const [, , zroot, ...fieldPhotos] = process.argv;
const metaPath = 'apps/web/public/models/seg.json';
const meta: SegMeta | null = fs.existsSync(metaPath) ? JSON.parse(fs.readFileSync(metaPath, 'utf8')) : null;
const session = meta ? await ort.InferenceSession.create(path.join('apps/web/public/models', meta.file)) : null;

async function tier2Labels(img: RGBA): Promise<Int32Array | undefined> {
  if (!session || !meta) return undefined;
  const { w: W, h: H } = workSize(img.width, img.height);
  const work = downscale(img, Math.max(W, H)).img;
  const x = segInput(work, meta);
  const out = await session.run({ x: new ort.Tensor('float32', x.data, [1, 3, x.h, x.w]) });
  const lab = segInstances(out.logits.data as Float32Array, x.w, x.h);
  return resizeLabels(lab, x.w, x.h, W, H);
}
const counted = (bulbs: { excluded: string | null }[]) => bulbs.filter((b) => b.excluded !== 'small' && b.excluded !== 'shape').length;

const rows = fs.readFileSync('tools/fixtures/count_truth.csv', 'utf8').trim().split(/\r?\n/).slice(1).map((l) => { const [id, rel, n, amb] = l.split(','); return { id, rel: rel.replace(/\\/g, '/'), n: n === '' ? null : +n, amb: amb === '1' }; });
const res: { id: string; truth: number | null; amb: boolean; t0: number; t2: number | null }[] = [];
for (const r of rows) {
  const img = readImage(path.join(zroot, r.rel));
  const t0 = counted(analyze(img).bulbs);
  const lab = await tier2Labels(img);
  const t2 = lab ? counted(analyze(img, { instances: lab }).bulbs) : null;
  res.push({ id: r.id, truth: r.n, amb: r.amb, t0, t2 });
  console.log(r.id, 'truth', r.n, r.amb ? '(amb)' : '', 'tier0', t0, 'tier2', t2);
}
const stat = (sel: typeof res, key: 't0' | 't2') => {
  const v = sel.filter((r) => r.truth !== null && r[key] !== null);
  if (!v.length) return null;
  const err = v.map((r) => (r[key] as number) - (r.truth as number));
  const r3 = (x: number) => Math.round(x * 100) / 100;
  return { n_photos: v.length, mae: r3(err.reduce((s, e) => s + Math.abs(e), 0) / v.length), exact: r3(err.filter((e) => e === 0).length / v.length), within1: r3(err.filter((e) => Math.abs(e) <= 1).length / v.length), mean_error: r3(err.reduce((s, e) => s + e, 0) / v.length) };
};
const clear = res.filter((r) => !r.amb), amb = res.filter((r) => r.amb);
const field: Record<string, unknown>[] = [];
for (const f of fieldPhotos) {
  const img = readImage(f);
  const lab = await tier2Labels(img);
  field.push({ photo: path.basename(f), tier0: counted(analyze(img).bulbs), tier2: lab ? counted(analyze(img, { instances: lab }).bulbs) : null });
}
const report = {
  generatedBy: 'tools/eval_count.ts', at: new Date().toISOString(),
  question: 'How many onions does the detector find, compared with a count by eye?',
  truth: 'tools/fixtures/count_truth.csv: onions visible (including ones cut by the frame edge), counted by eye by the build assistant on held-out Zenodo photos (block % 5 == 4). Not a grader study.',
  model: meta ? { tier2: meta.file, sha256: meta.sha256, version: meta.version } : null,
  clear_photos: { tier0: stat(clear, 't0'), tier2: stat(clear, 't2') },
  ambiguous_piles: { tier0: stat(amb, 't0'), tier2: stat(amb, 't2') },
  field_photos: field,
  per_photo: res,
};
fs.writeFileSync('reports/count_eval.json', JSON.stringify(report, null, 2));
console.log(JSON.stringify({ clear: report.clear_photos, amb: report.ambiguous_piles, field }, null, 1));
