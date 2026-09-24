import { useEffect, useState } from 'preact/hooks';
import { Database } from 'lucide-preact';
import { db, type CertRow } from '../lib/db';
import { t } from '../lib/i18n';
import { issueCertificate } from '../lib/lots';
import { seedDemoLot } from '../lib/demo';
import { TopBar, toast } from '../components/ui';

interface CentreRow { centre: string; lots: number; bulbs: number; gradeA: number[]; refer: number[]; actions: number; overridesAgainstAi: number; sizes: number[]; tiers: Record<string, number>; demo: boolean }

function spark(values: number[]) {
  if (values.length < 2) return null;
  const lo = Math.min(...values), hi = Math.max(...values), span = hi - lo || 1;
  const d = values.map((v, i) => `${i ? 'L' : 'M'}${(i / (values.length - 1)) * 100} ${36 - ((v - lo) / span) * 32}`).join(' ');
  return <svg class="spark" viewBox="0 0 100 40" preserveAspectRatio="none" aria-hidden="true"><path d={d} /></svg>;
}

export function Fleet() {
  const [rows, setRows] = useState<CentreRow[] | null>(null);
  const [busy, setBusy] = useState(false);
  const load = async () => {
    const certs = await db.certs.toArray();
    const latest = new Map<string, CertRow>();
    for (const c of certs) { const cur = latest.get(c.lotId); if (!cur || c.rev > cur.rev) latest.set(c.lotId, c); }
    const lots = new Map((await db.lots.toArray()).map((l) => [l.id, l]));
    const by = new Map<string, CentreRow>();
    for (const c of [...latest.values()].sort((a, b) => a.issuedAt.localeCompare(b.issuedAt))) {
      const k = c.signed.core;
      const r = by.get(c.centre) ?? { centre: c.centre, lots: 0, bulbs: 0, gradeA: [], refer: [], actions: 0, overridesAgainstAi: 0, sizes: [], tiers: {}, demo: false };
      r.lots++; r.bulbs += k.bulbs.length; r.gradeA.push(k.headline.gradeA); r.refer.push(k.headline.refer);
      r.actions += k.overrides.length; r.overridesAgainstAi += k.overrides.filter((o) => o.kind === 'override').length;
      const sz = k.bulbs.map((b) => b.size.min).sort((a, b) => a - b);
      if (sz.length) r.sizes.push(sz[sz.length >> 1] / 10);
      r.tiers[k.calib.tier] = (r.tiers[k.calib.tier] ?? 0) + 1;
      r.demo ||= !!lots.get(c.lotId)?.demo;
      by.set(c.centre, r);
    }
    setRows([...by.values()]);
  };
  useEffect(() => { load(); }, []);

  const seedFleet = async () => {
    setBusy(true);
    try {
      const plan: [string, string, string[]][] = [
        ['NSK-02 (demo)', 'Demo seller A', ['Onion07046.jpg', 'Onion07049.jpg']],
        ['NSK-02 (demo)', 'Demo seller B', ['Onion13276.jpg', 'Onion07101.jpg']],
        ['KRN-05 (demo)', 'Demo seller C', ['Onion15296.jpg', 'Onion11156.jpg']],
        ['KRN-05 (demo)', 'Demo seller D', ['Onion13291.jpg', 'Onion13277.jpg']],
      ];
      for (const [centre, farmer, files] of plan) {
        const id = await seedDemoLot({ centre, farmer, files });
        // One officer action per demo lot, so the disagreement column is not empty.
        await db.lots.update(id, { overrides: [{ bulb: 'b0', by: 'officer', kind: 'override', to: 'URS', reason: 'VISUAL_REINSPECTION', at: new Date().toISOString() }] });
        await issueCertificate(id);
      }
      await load();
      toast(t('fl.seeded', 'Demo centres added (replayed real photos).'));
    } finally { setBusy(false); }
  };

  return (
    <>
      <TopBar title={t('fl.title', 'Fleet dashboard')} />
      <main class="page">
        <p class="small muted">{t('fl.intro', 'Built from signed receipts only. Watch for a centre whose results drift, whose human overrides disagree with the model often, or that falls back to weak size calibration.')}</p>
        {rows && rows.length === 0 && <p class="small">{t('fl.empty', 'No signed receipts on this phone yet.')}</p>}
        {rows?.map((r) => {
          const mean = (xs: number[]) => (xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : 0);
          return (
            <section key={r.centre} class="card section">
              <div class="section-head"><h2 style={{ fontSize: 'var(--text-lg)' }}>{r.centre}</h2>{r.demo && <span class="chip assumed">demo data</span>}</div>
              <dl class="kv">
                <dt>{t('fl.lots', 'Lots · bulb-observations')}</dt><dd>{r.lots} · {r.bulbs}</dd>
                <dt>{t('fl.a', 'Mean Grade A by weight')}</dt><dd>{mean(r.gradeA).toFixed(1)}%</dd>
                <dt>{t('fl.refer', 'Mean “needs human check”')}</dt><dd>{mean(r.refer).toFixed(1)}%</dd>
                <dt>{t('fl.dis', 'Officer overrides per 100 bulbs')}</dt><dd>{r.bulbs ? ((100 * r.overridesAgainstAi) / r.bulbs).toFixed(2) : '—'}</dd>
                <dt>{t('fl.tiers', 'Size calibration used')}</dt><dd>{Object.entries(r.tiers).map(([k, v]) => `${k} ${v}`).join(', ')}</dd>
              </dl>
              <div>
                <p class="xs muted">{t('fl.drift', 'Median bulb size per lot, mm (a steady slide can mean calibration drift)')}</p>
                {spark(r.sizes) ?? <p class="xs muted">{t('fl.need2', 'Needs two or more lots.')}</p>}
                <p class="mono xs muted">{r.sizes.map((x) => x.toFixed(1)).join(' · ')}</p>
              </div>
            </section>
          );
        })}
        <button class="btn quiet block" disabled={busy} data-state={busy ? 'loading' : undefined} onClick={seedFleet}>
          <Database size={18} aria-hidden="true" />{busy ? t('fl.busy', 'Measuring demo photos…') : t('fl.seed', 'Add demo centres')}
        </button>
        <p class="note">{t('fl.server', 'With a sync server, every centre’s receipts and signed log heads land here. This build keeps everything on the phone.')}</p>
      </main>
    </>
  );
}
