// Tier-0 image-level evaluation on the public Zenodo onion dataset (real photos).
// node --import tsx tools/eval_zenodo.ts <zenodo "2. Bulb" dir> [perCell=40]
//
// Question answered: does the Tier-0 defect score separate photos the dataset
// authors labelled "unhealthy" from "healthy"? This is NOT procurement-grade
// accuracy (labels are image-level, no size truth, no grader). It is the only
// real-photo number available before field data exists.
//
// Split: images are grouped in blocks of 25 consecutive ids (bursts of one
// scene). block % 5 == 0 is TUNE (thresholds), block % 5 == 4 is HOLDOUT
// (reported), blocks 1-3 are reserved for training the Tier-1 model.
// The decision threshold is chosen on TUNE only; images viewed while writing
// the thresholds are excluded from both.
import fs from 'node:fs';
import path from 'node:path';
import { analyze, TIER0 } from '@parakh/vision';
import { hashCanonical, wilson } from '@parakh/core';
import { readImage } from './imgio.mjs';

const root = process.argv[2];
const perCell = parseInt(process.argv[3] ?? '40');
const VIEWED = new Set([13276, 7341, 15296, 7046, 7049, 13277, 7101, 13291, 11156, 7047, 7048, 7100, 13278, 13279, 13290, 12266, 12561, 12961, 11451, 11851, 4046, 4341, 4741, 13571, 13971, 15591, 15991, 7741]);
const cells = [
  ['healthy', 'red', 'multiple', '1. Healthy/1. Red Onion/2. Multiple'],
  ['healthy', 'red', 'single', '1. Healthy/1. Red Onion/1. Single'],
  ['healthy', 'white', 'multiple', '1. Healthy/2. White Onion/2. Multiple'],
  ['healthy', 'white', 'single', '1. Healthy/2. White Onion/1. Single'],
  ['unhealthy', 'red', 'multiple', '2. Unhealthy/1. Red Onion/2. Multiple'],
  ['unhealthy', 'red', 'single', '2. Unhealthy/1. Red Onion/1. Single'],
  ['unhealthy', 'white', 'multiple', '2. Unhealthy/2. White Onion/2. Multiple'],
  ['unhealthy', 'white', 'single', '2. Unhealthy/2. White Onion/1. Single'],
] as const;

type Row = { id: number; label: 0 | 1; variety: string; qty: string; split: 'tune' | 'holdout'; score: number; bulbs: number; ms: number };
const rows: Row[] = [];
for (const [health, variety, qty, dir] of cells) {
  const files = fs.readdirSync(path.join(root, dir)).filter((f) => /\.jpe?g$/i.test(f)).sort();
  const ids = files.map((f) => parseInt(f.replace(/\D/g, ''))).filter((id) => !VIEWED.has(id));
  for (const split of ['tune', 'holdout'] as const) {
    const pool = ids.filter((id) => Math.floor(id / 25) % 5 === (split === 'tune' ? 0 : 4));
    // Deterministic spread across the pool.
    const n = Math.min(split === 'tune' ? Math.ceil(perCell / 2) : perCell, pool.length);
    for (let k = 0; k < n; k++) {
      const id = pool[Math.floor((k * pool.length) / n)];
      const f = path.join(root, dir, `Onion${String(id).padStart(5, '0')}.jpg`);
      const t0 = Date.now();
      const a = analyze(readImage(f));
      const ms = Date.now() - t0;
      const used = a.bulbs.filter((b) => !b.excluded);
      // Image score: worst bulb's rot + blackening surface share.
      const score = used.reduce((m, b) => Math.max(m, (b.frac.rot ?? 0) + (b.frac.blackening ?? 0)), 0);
      rows.push({ id, label: health === 'unhealthy' ? 1 : 0, variety, qty, split, score, bulbs: used.length, ms });
    }
    process.stdout.write(`${health}/${variety}/${qty}/${split} done\n`);
  }
}

function auc(rs: Row[]) {
  const pos = rs.filter((r) => r.label === 1).map((r) => r.score), neg = rs.filter((r) => r.label === 0).map((r) => r.score);
  let s = 0;
  for (const p of pos) for (const q of neg) s += p > q ? 1 : p === q ? 0.5 : 0;
  return pos.length && neg.length ? s / (pos.length * neg.length) : NaN;
}
function at(rs: Row[], thr: number) {
  const tp = rs.filter((r) => r.label === 1 && r.score >= thr).length, P = rs.filter((r) => r.label === 1).length;
  const tn = rs.filter((r) => r.label === 0 && r.score < thr).length, N = rs.filter((r) => r.label === 0).length;
  const r3 = (x: number) => Math.round(x * 1000) / 1000;
  const [sl, sh] = wilson(tp, P), [pl, ph] = wilson(tn, N);
  return { n_unhealthy: P, n_healthy: N, sensitivity: r3(tp / P), sensitivity_ci95: [r3(sl), r3(sh)], specificity: r3(tn / N), specificity_ci95: [r3(pl), r3(ph)], accuracy: r3((tp + tn) / (P + N)) };
}
const tune = rows.filter((r) => r.split === 'tune'), hold = rows.filter((r) => r.split === 'holdout');
// Threshold: maximise Youden's J on TUNE only.
const cands = [...new Set(tune.map((r) => r.score))].sort((a, b) => a - b);
let best = { thr: 0.05, j: -1 };
for (const c of cands) { const m = at(tune, c); const j = m.sensitivity + m.specificity - 1; if (j > best.j) best = { thr: c, j }; }

const sub = (f: (r: Row) => boolean) => ({ auc: Math.round(auc(hold.filter(f)) * 1000) / 1000, ...at(hold.filter(f), best.thr) });
const ms = hold.map((r) => r.ms).sort((a, b) => a - b);
const report = {
  generatedBy: 'tools/eval_zenodo.ts',
  at: new Date().toISOString(),
  dataset: 'Zenodo 10.5281/zenodo.20254934 (CC-BY 4.0), bulb images, real photos from Pune markets',
  model: `${TIER0.id}@${TIER0.version}`,
  modelHash: await hashCanonical(TIER0),
  question: 'Image-level: does max(rot+blackening share) over detected bulbs separate authors\' "unhealthy" from "healthy" photos?',
  caveats: [
    'Labels are per image, from the dataset authors; "unhealthy" is not the same as a procurement Reject.',
    'No size truth and no grader labels: this says nothing about Grade A / URS accuracy.',
    'Single-camera dataset (Motorola Edge 50 Ultra), one city; field photos will differ.',
  ],
  threshold_from_tune: Math.round(best.thr * 1000) / 1000,
  n_tune: tune.length, n_holdout: hold.length,
  holdout: {
    all: sub(() => true),
    red: sub((r) => r.variety === 'red'),
    white: sub((r) => r.variety === 'white'),
    single: sub((r) => r.qty === 'single'),
    multiple: sub((r) => r.qty === 'multiple'),
  },
  holdout_ids: hold.map((r) => ({ id: r.id, label: r.label, variety: r.variety, qty: r.qty, score: Math.round(r.score * 1e4) / 1e4 })),
  tune_ids: tune.map((r) => ({ id: r.id, label: r.label, variety: r.variety, qty: r.qty, score: Math.round(r.score * 1e4) / 1e4 })),
  node_latency_ms: { p50: ms[Math.floor(ms.length * 0.5)], p95: ms[Math.floor(ms.length * 0.95)], note: 'desktop Node, not a phone' },
};
fs.mkdirSync('reports', { recursive: true });
fs.writeFileSync('reports/zenodo_tier0.json', JSON.stringify(report, null, 2));
console.log(JSON.stringify(report.holdout.all), 'thr', report.threshold_from_tune);
