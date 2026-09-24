// Data engine (W7): officer corrections -> labelled Tier-1 training crops.
// node --import tsx tools/corrections_to_crops.ts <corrections.json> <evidence dir> <crops dir>
// Then: python scripts/train_tier1.py --crops <crops dir>
// Label rule: corrected to REJECT -> unhealthy (1); corrected to GRADE_A or URS -> healthy (0); contests are skipped.
import fs from 'node:fs';
import path from 'node:path';
import jpeg from 'jpeg-js';
import { analyze, bulbCrop, downscale, TIER0 } from '@parakh/vision';
import { writeJpeg } from './imgio.mjs';

const [, , corrFile, evDir, out] = process.argv;
const corr = JSON.parse(fs.readFileSync(corrFile, 'utf8')).rows as { captureId: string; bulbIdx: number; to: string; reason: string }[];
const caps = new Map<string, string>();
for (const f of fs.readdirSync(evDir).filter((x) => x.endsWith('.parakh.json'))) {
  for (const c of JSON.parse(fs.readFileSync(path.join(evDir, f), 'utf8')).captures) caps.set(c.id, c.jpegBase64);
}
fs.mkdirSync(path.join(out, 'img'), { recursive: true });
const rows = ['file,image_id,label,variety,qty,split,bulb'];
let n = 0;
for (const c of corr) {
  const label = c.to === 'REJECT' ? 1 : c.to === 'GRADE_A' || c.to === 'URS' ? 0 : -1;
  const b64 = caps.get(c.captureId);
  if (label < 0 || !b64) continue;
  const j = jpeg.decode(Buffer.from(b64, 'base64'), { useTArray: true });
  const img = { width: j.width, height: j.height, data: j.data };
  const bulb = analyze(img).bulbs.find((b) => b.idx === c.bulbIdx);
  if (!bulb) continue;
  const name = `corr_${n}.jpg`;
  writeJpeg(path.join(out, 'img', name), { width: 128, height: 128, data: bulbCrop(downscale(img, TIER0.workSide).img, bulb, 128) }, 90);
  rows.push(`${name},${9000000 + n},${label},field,single,train,${c.bulbIdx}`);
  n++;
}
fs.writeFileSync(path.join(out, 'crops_corrections.csv'), rows.join('\n'));
console.log(`${n} corrected bulbs added as training crops`);
