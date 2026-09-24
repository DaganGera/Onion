// Copy the ONNX Runtime Web WASM runtime into apps/web/public/ort so it is served and precached for offline use.
import fs from 'node:fs';
import path from 'node:path';
const src = path.resolve(import.meta.dirname, '../node_modules/onnxruntime-web/dist');
const dst = path.resolve(import.meta.dirname, '../apps/web/public/ort');
fs.mkdirSync(dst, { recursive: true });
for (const f of ['ort-wasm-simd-threaded.wasm', 'ort-wasm-simd-threaded.mjs']) fs.copyFileSync(path.join(src, f), path.join(dst, f));
console.log('ort runtime copied');
