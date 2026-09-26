// Tier-0 speed on this machine (Node, single thread). node --import tsx tools/bench.ts <dir with jpgs> [n]
// Run on an idle machine; a phone number must come from the app itself (E6).
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { analyze } from '@parakh/vision';
import { readImage } from './imgio.mjs';
const [, , dir, nArg] = process.argv;
const files = fs.readdirSync(dir).filter((f) => /\.jpe?g$/i.test(f)).slice(0, parseInt(nArg ?? '20'));
analyze(readImage(path.join(dir, files[0]))); // warm-up (JIT)
const ms: number[] = [];
for (const f of files) { const img = readImage(path.join(dir, f)); const t = performance.now(); analyze(img); ms.push(performance.now() - t); }
ms.sort((a, b) => a - b);
const q = (p: number) => Math.round(ms[Math.min(ms.length - 1, Math.floor(p * ms.length))]);
const r = { generatedBy: 'tools/bench.ts', at: new Date().toISOString(), note: 'Node.js, single thread, 1024 px working resolution, idle machine.', machine: `${os.cpus()[0].model}, Node ${process.version}`, n: ms.length, tier0_ms: { p50: q(0.5), p95: q(0.95) } };
fs.writeFileSync('reports/bench.json', JSON.stringify(r, null, 2));
console.log(r.tier0_ms);
