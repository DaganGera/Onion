// Node-side image IO for scripts and tests (pngjs MIT, jpeg-js BSD-3).
import fs from 'node:fs';
import { PNG } from 'pngjs';
import jpeg from 'jpeg-js';

export function readImage(path) {
  const buf = fs.readFileSync(path);
  if (buf[0] === 0x89) { const p = PNG.sync.read(buf); return { width: p.width, height: p.height, data: p.data }; }
  const j = jpeg.decode(buf, { useTArray: true, maxMemoryUsageInMB: 1024 });
  return { width: j.width, height: j.height, data: j.data };
}

export function writePng(path, img) {
  const p = new PNG({ width: img.width, height: img.height });
  p.data = Buffer.from(img.data.buffer, img.data.byteOffset, img.data.byteLength);
  fs.writeFileSync(path, PNG.sync.write(p));
}

export function writeJpeg(path, img, quality = 85) {
  fs.writeFileSync(path, jpeg.encode({ width: img.width, height: img.height, data: img.data }, quality).data);
}
