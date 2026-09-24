// Field studies E1-E4 on the team's own data (docs/HUMAN_TASKS.md T4-T7).
// node --import tsx tools/eval_field.ts [fieldDir=field]
// Each study writes reports/eN_*.json. With no data it writes status "awaiting field data" and no numbers.
import fs from 'node:fs';
import path from 'node:path';
import jpeg from 'jpeg-js';
import { blandAltman, cohenKappa, fitWeightModel, fleissKappa, gradeLot, icc1, majority, packById, PACKS, adjudicate, resultSeed, type SignedCert } from '@parakh/core';
import { analyze, toMeasurement, type BulbResult } from '@parakh/vision';

const field = process.argv[2] ?? 'field';
fs.mkdirSync('reports', { recursive: true });
const write = (name: string, obj: object) => fs.writeFileSync(path.join('reports', name), JSON.stringify({ generatedBy: 'tools/eval_field.ts', at: new Date().toISOString(), ...obj }, null, 2));
const csv = (f: string): Record<string, string>[] => {
  if (!fs.existsSync(f)) return [];
  const [head, ...lines] = fs.readFileSync(f, 'utf8').trim().split(/\r?\n/);
  const h = head.split(',').map((s) => s.trim());
  return lines.filter((l) => l.trim()).map((l) => Object.fromEntries(l.split(',').map((v, i) => [h[i], v.trim()])));
};
type Bundle = { cert: SignedCert; captures: { id: string; tray: number; look: number; jpegBase64: string; calib: { tier: string }; guard?: { scans: number; failed: number; refused: number } | null }[] };
const bundles: Bundle[] = [];
const walk = (d: string) => { if (!fs.existsSync(d)) return; for (const e of fs.readdirSync(d, { withFileTypes: true })) { const p = path.join(d, e.name); if (e.isDirectory()) walk(p); else if (e.name.endsWith('.parakh.json')) bundles.push(JSON.parse(fs.readFileSync(p, 'utf8'))); } };
walk(field);
const latest = new Map<string, Bundle>();
for (const b of bundles) { const k = b.cert.core.lot.id; if (!latest.has(k) || latest.get(k)!.cert.core.rev < b.cert.core.rev) latest.set(k, b); }

/** Re-run perception on a stored capture; bulbs in reading order (rows top to bottom, then left to right). */
function orderedBulbs(c: Bundle['captures'][number]): BulbResult[] {
  const j = jpeg.decode(Buffer.from(c.jpegBase64, 'base64'), { useTArray: true });
  const bs = analyze({ width: j.width, height: j.height, data: j.data }).bulbs.filter((b) => !b.excluded);
  const hMed = bs.map((b) => b.bbox[3] - b.bbox[1]).sort((a, b) => a - b)[bs.length >> 1] ?? 1;
  return bs.sort((a, b) => (Math.abs(a.centroid.y - b.centroid.y) > 0.6 * hMed ? a.centroid.y - b.centroid.y : a.centroid.x - b.centroid.x));
}
const r3 = (x: number) => Math.round(x * 1000) / 1000;

// ---- E1: size vs caliper, per calibration tier; weight model fit ----
{
  const truth = csv(path.join(field, 'size_truth.csv')).filter((r) => r.photo_file && r.min_equatorial_mm);
  if (!truth.length) write('e1_size.json', { status: 'awaiting field data', needs: 'field/size_truth.csv + evidence files (HUMAN_TASKS T4)' });
  else {
    // Photo files named in the CSV are capture ids; bulbs in a photo are laid out in bulb-number order.
    const byPhoto = new Map<string, Record<string, string>[]>();
    for (const r of truth) byPhoto.set(r.photo_file, [...(byPhoto.get(r.photo_file) ?? []), r]);
    const pairs: { tier: string; appMin: number; appMax: number; calMin: number; calMax: number }[] = [];
    for (const b of latest.values()) for (const c of b.captures) {
      const rows = byPhoto.get(c.id);
      if (!rows) continue;
      const bs = orderedBulbs(c);
      rows.sort((x, y) => +x.bulb_no - +y.bulb_no).forEach((r, i) => { if (bs[i]) pairs.push({ tier: c.calib.tier, appMin: bs[i].minMm, appMax: bs[i].maxMm, calMin: +r.min_equatorial_mm, calMax: +r.max_equatorial_mm }); });
    }
    const tiers = [...new Set(pairs.map((p) => p.tier))];
    const per = Object.fromEntries(tiers.map((t) => {
      const ps = pairs.filter((p) => p.tier === t);
      const mn = blandAltman(ps.map((p) => p.appMin), ps.map((p) => p.calMin)), mx = blandAltman(ps.map((p) => p.appMax), ps.map((p) => p.calMax));
      return [t, { n: ps.length, minFeret: { bias_mm: r3(mn.bias), mae_mm: r3(mn.mae), loa_mm: mn.loa.map(r3) }, maxFeret: { bias_mm: r3(mx.bias), mae_mm: r3(mx.mae), loa_mm: mx.loa.map(r3) } }];
    }));
    const wpairs = truth.filter((r) => r.weight_g).map((r) => ({ dMm: (+r.min_equatorial_mm + +r.max_equatorial_mm) / 2, g: +r.weight_g }));
    const wm = wpairs.length >= 5 ? fitWeightModel(wpairs) : null;
    write('e1_size.json', { status: 'ok', n_pairs: pairs.length, per_tier: per, weight_model: wm && { a: wm.a, b: r3(wm.b), residual_sd_log: r3(wm.residualSd), n: wm.n } });
  }
}

// ---- E2: repeatability (Gauge R&R style) ----
{
  const runs = [...latest.values()].filter((b) => /^E2\s/i.test(b.cert.core.lot.farmerRef));
  if (runs.length < 6) write('e2_repeatability.json', { status: 'awaiting field data', needs: 'at least 6 lots named "E2 <phone> <light> <n>" (HUMAN_TASKS T7)', found: runs.length });
  else {
    const val = (b: Bundle) => b.cert.core.headline.gradeA;
    const key = (b: Bundle, i: number) => b.cert.core.lot.farmerRef.split(/\s+/)[i] ?? '?';
    const groupBy = (i: number) => { const m = new Map<string, number[]>(); for (const b of runs) m.set(key(b, i), [...(m.get(key(b, i)) ?? []), val(b)]); return m; };
    const all = runs.map(val);
    const mean = all.reduce((a, b) => a + b, 0) / all.length;
    const sd = Math.sqrt(all.reduce((s, x) => s + (x - mean) ** 2, 0) / (all.length - 1));
    const cond = new Map<string, number[]>();
    for (const b of runs) { const k = `${key(b, 1)}|${key(b, 2)}`; cond.set(k, [...(cond.get(k) ?? []), val(b)]); }
    const phones = groupBy(1), lights = groupBy(2);
    const m = (xs: number[]) => r3(xs.reduce((a, b) => a + b, 0) / xs.length);
    write('e2_repeatability.json', {
      status: 'ok', n_captures: runs.length, gradeA_pct_mean: r3(mean), gradeA_pct_sd: r3(sd),
      by_phone: Object.fromEntries([...phones].map(([k, v]) => [k, { n: v.length, mean: m(v) }])),
      by_light: Object.fromEntries([...lights].map(([k, v]) => [k, { n: v.length, mean: m(v) }])),
      icc_conditions: [...cond.values()].filter((g) => g.length > 1).length > 1 ? r3(icc1([...cond.values()].filter((g) => g.length > 1))) : null,
      ...(() => { const gs = runs.flatMap((b) => b.captures.map((c) => c.guard)).filter((g): g is NonNullable<typeof g> => !!g); const sc = gs.reduce((s, g) => s + g.scans, 0); return { capture_guard_failing_scan_share: sc ? r3(gs.reduce((s, g) => s + g.failed, 0) / sc) : null, capture_guard_refused_presses: gs.reduce((s, g) => s + g.refused, 0), capture_guard_note: 'Share of live-preview scans in which at least one gate failed, over all E2 captures.' }; })(),
    });
  }
}

// ---- E3: human baseline vs AI on the same 60 bulbs ----
{
  const raters = fs.existsSync(field) ? fs.readdirSync(field).filter((f) => /^e3_rater\d+\.csv$/.test(f)) : [];
  const e3 = [...latest.values()].find((b) => /^E3\b/i.test(b.cert.core.lot.farmerRef));
  if (raters.length < 3 || !e3) write('e3_human_baseline.json', { status: 'awaiting field data', needs: 'field/e3_rater1..3.csv and a lot named "E3" (HUMAN_TASKS T6)', raters: raters.length, lot: !!e3 });
  else {
    const norm = (g: string) => ({ A: 'GRADE_A', URS: 'URS', U: 'URS', R: 'REJECT', '?': 'REFER' } as Record<string, string>)[g.toUpperCase()] ?? 'REFER';
    const grades = raters.map((f) => new Map(csv(path.join(field, f)).map((r) => [+r.bulb_no, norm(r['grade(A/URS/R/?)'] ?? r.grade ?? '?')])));
    const pack = PACKS.find((p) => e3.cert.core.pack.id === p.id) ?? packById('in-psf-2026-07-30-a-only')!;
    // AI verdicts per photo in reading order; bulbs were photographed in number order.
    let no = 1;
    const ai = new Map<number, string>();
    for (const c of e3.captures.sort((a, b) => a.id.localeCompare(b.id))) {
      const ms = orderedBulbs(c).map((b, i) => toMeasurement(b, `b${i}`, c.tray, c.look));
      for (const v of adjudicate(ms, pack)) ai.set(no++, v.bucket);
    }
    const ids = [...grades[0].keys()].filter((k) => grades.every((g) => g.has(k)) && ai.has(k));
    const cats = ['GRADE_A', 'URS', 'REJECT', 'REFER'];
    const kappa = fleissKappa(ids.map((k) => cats.map((c) => grades.filter((g) => g.get(k) === c).length)));
    const maj = ids.map((k) => majority(grades.map((g) => g.get(k)!)));
    const aiVsMaj = cohenKappa(ids.map((k) => ai.get(k)!), maj);
    const humansVsOthers = grades.map((g, i) => cohenKappa(ids.map((k) => g.get(k)!), ids.map((k) => majority(grades.filter((_, j) => j !== i).map((o) => o.get(k)!)))));
    const avgHuman = humansVsOthers.reduce((s, x) => s + x.agreement, 0) / humansVsOthers.length;
    write('e3_human_baseline.json', {
      status: 'ok', n_bulbs: ids.length, n_raters: grades.length, fleiss_kappa_humans: r3(kappa),
      ai_vs_majority: { agreement: r3(aiVsMaj.agreement), kappa: r3(aiVsMaj.kappa) },
      human_vs_majority_of_others: humansVsOthers.map((x) => ({ agreement: r3(x.agreement), kappa: r3(x.kappa) })),
      ai_at_least_as_good_as_average_human: aiVsMaj.agreement >= avgHuman,
    });
  }
}

// ---- E4: lot-level truth and interval coverage ----
{
  const truth = csv(path.join(field, 'lot_truth.csv'));
  const rows = truth.map((t) => ({ t, b: latest.get(t.app_lot_id) })).filter((x) => x.b);
  if (!rows.length) write('e4_lot_truth.json', { status: 'awaiting field data', needs: 'field/lot_truth.csv + evidence files (HUMAN_TASKS T5)' });
  else {
    const out = [];
    for (const { t, b } of rows) {
      const k = b!.cert.core;
      const pack = PACKS.find((p) => p.id === k.pack.id)!;
      const r = gradeLot(k.bulbs, pack, [], await resultSeed(k)); // AI only, no human overrides
      const kg = +t.gradeA_kg + +t.urs_kg + +t.reject_kg;
      const truthA = (100 * +t.gradeA_kg) / kg;
      out.push({ lot: t.lot_id, truth_gradeA_pct: r3(truthA), app_gradeA_pct: r.byWeight.GRADE_A.est, ci: r.byWeight.GRADE_A.ci, covered: truthA >= r.byWeight.GRADE_A.ci[0] && truthA <= r.byWeight.GRADE_A.ci[1], refer_pct: r.byWeight.REFER.est });
    }
    const errs = out.map((o) => Math.abs(o.app_gradeA_pct - o.truth_gradeA_pct));
    write('e4_lot_truth.json', { status: 'ok', n_lots: out.length, mae_gradeA_pp: r3(errs.reduce((a, b) => a + b, 0) / errs.length), coverage_95: r3(out.filter((o) => o.covered).length / out.length), lots: out });
  }
}
console.log('field evaluation written to reports/ (bundles found:', bundles.length, ')');
