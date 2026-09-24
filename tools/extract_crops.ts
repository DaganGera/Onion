// Bulb crops for Tier-1 training/eval, cut by the Tier-0 segmentation.
// node --import tsx tools/extract_crops.ts <zenodo "2. Bulb" dir> <outDir> [maxPerCell]
// Singles: the largest usable bulb, labelled from the folder (exact per-bulb label).
// Multiples: every usable bulb, labelled with the image label (noisy; eval only).
import fs from 'node:fs';
import path from 'node:path';
import { analyze, downscale } from '@parakh/vision';
import { readImage, writeJpeg } from './imgio.mjs';

const [, , root, out, maxArg, shardArg] = process.argv;
const maxPer = parseInt(maxArg ?? '100000');
const [shard, nShards] = (shardArg ?? '0/1').split('/').map(Number);
fs.mkdirSync(path.join(out, 'img'), { recursive: true });
const rows: string[] = ['file,image_id,label,variety,qty,split,bulb'];
const cells = [['1. Healthy', 0], ['2. Unhealthy', 1]] as const;
// Resume: crops already on disk are reused instead of re-running perception.
const done = new Map<number, string[]>();
for (const f of fs.readdirSync(path.join(out, 'img'))) { const id = parseInt(f); done.set(id, [...(done.get(id) ?? []), f]); }
const SIZE = 128;
for (const [hdir, label] of cells) for (const [vdir, variety] of [['1. Red Onion', 'red'], ['2. White Onion', 'white']]) for (const [qdir, qty] of [['1. Single', 'single'], ['2. Multiple', 'multiple']]) {
  const dir = path.join(root, hdir, vdir, qdir);
  let files = fs.readdirSync(dir).filter((f) => /\.jpe?g$/i.test(f)).sort();
  if (files.length > maxPer) files = files.filter((_, i) => i % Math.ceil(files.length / maxPer) === 0);
  for (const f of files) {
    const id = parseInt(f.replace(/\D/g, ''));
    if (id % nShards !== shard) continue;
    const b = Math.floor(id / 25) % 5;
    const split = b === 0 ? 'tune' : b === 4 ? 'holdout' : 'train';
    if (qty === 'multiple' && split === 'train') continue; // noisy labels: never train on them
    if (done.has(id)) { for (const name of done.get(id)!) rows.push(`${name},${id},${label},${variety},${qty},${split},${parseInt(name.split('_')[1])}`); continue; }
    const img = readImage(path.join(dir, f));
    const a = analyze(img);
    const { img: work } = downscale(img, 1024);
    let bulbs = a.bulbs.filter((x) => !x.excluded && x.areaPx > 900);
    if (qty === 'single') bulbs = bulbs.sort((p, q) => q.areaPx - p.areaPx).slice(0, 1);
    for (const bu of bulbs) {
      const [x0, y0, x1, y1] = bu.bbox;
      const side = Math.round(Math.max(x1 - x0, y1 - y0) * 1.1);
      const cx = (x0 + x1) / 2, cy = (y0 + y1) / 2;
      const crop = new Uint8ClampedArray(SIZE * SIZE * 4);
      for (let y = 0; y < SIZE; y++) for (let x = 0; x < SIZE; x++) {
        const sx = Math.round(cx - side / 2 + (x + 0.5) * side / SIZE), sy = Math.round(cy - side / 2 + (y + 0.5) * side / SIZE);
        const o = (y * SIZE + x) * 4;
        if (sx >= 0 && sy >= 0 && sx < work.width && sy < work.height) { const i = (sy * work.width + sx) * 4; crop[o] = work.data[i]; crop[o + 1] = work.data[i + 1]; crop[o + 2] = work.data[i + 2]; }
        crop[o + 3] = 255;
      }
      const name = `${id}_${bu.idx}.jpg`;
      writeJpeg(path.join(out, 'img', name), { width: SIZE, height: SIZE, data: crop }, 90);
      rows.push(`${name},${id},${label},${variety},${qty},${split},${bu.idx}`);
    }
  }
  console.log(hdir, vdir, qdir, 'done', rows.length);
}
fs.writeFileSync(path.join(out, 'crops.csv'), rows.join('\n'));
