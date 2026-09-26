import { useEffect, useState } from 'preact/hooks';
import { Search, Play, Inbox } from 'lucide-preact';
import { t } from '../lib/i18n';
import { go } from '../lib/router';
import { seedDemoLot } from '../lib/demo';
import { TopBar } from '../components/ui';
import { LotRow, loadLots, type LotWithCert } from '../components/LotRow';

type Filter = 'all' | 'signed' | 'draft' | 'refer';

export function Lots() {
  const [lots, setLots] = useState<LotWithCert[] | null>(null);
  const [q, setQ] = useState('');
  const [f, setF] = useState<Filter>('all');
  const [busy, setBusy] = useState(false);
  useEffect(() => { loadLots().then(setLots); }, []);
  const shown = (lots ?? []).filter((l) => {
    const s = q.trim().toLowerCase();
    if (s && !`${l.farmerRef} ${l.id} ${l.variety} ${l.centre}`.toLowerCase().includes(s)) return false;
    if (f === 'signed') return !!l.cert;
    if (f === 'draft') return !l.cert;
    if (f === 'refer') return l.cert?.signed.core.headline.decision === 'REFER_TO_HUMAN';
    return true;
  });
  const chip = (id: Filter, label: string) => <button class="fchip" aria-pressed={f === id} onClick={() => setF(id)}>{label}</button>;

  return (
    <>
      <TopBar title={t('lots.title', 'Lots')} subtitle={lots ? (lots.length === 1 ? t('lots.sub1', '1 lot on this phone') : t('lots.sub', '{n} lots on this phone', { n: lots.length })) : undefined} />
      <main class="page with-tabs">
        <label class="searchbox">
          <Search size={18} aria-hidden="true" />
          <input value={q} onInput={(e) => setQ((e.target as HTMLInputElement).value)} placeholder={t('lots.search', 'Search farmer, lot ID or variety')} aria-label={t('lots.search', 'Search farmer, lot ID or variety')} />
        </label>
        <div class="fchips" role="group">
          {chip('all', t('lots.f.all', 'All'))}{chip('signed', t('lots.f.signed', 'Signed'))}{chip('draft', t('lots.f.draft', 'Not signed'))}{chip('refer', t('lots.f.refer', 'Needs check'))}
        </div>
        {lots && shown.length > 0 && <nav class="lotlist">{shown.map((l) => <LotRow key={l.id} l={l} />)}</nav>}
        {lots && shown.length === 0 && (
          <div class="empty">
            <Inbox size={28} aria-hidden="true" />
            <p>{lots.length ? t('lots.none', 'No lots match.') : t('lots.empty', 'No lots yet. Tap the scan button to grade one, or load the demo lot.')}</p>
            {!lots.length && (
              <button class="btn quiet" disabled={busy} data-state={busy ? 'loading' : undefined} onClick={async () => { setBusy(true); try { go(`lot/${await seedDemoLot()}`); } finally { setBusy(false); } }}>
                <Play size={18} aria-hidden="true" />{busy ? t('home.demo.busy', 'Measuring demo photos…') : t('home.demo', 'Load the demo lot')}
              </button>
            )}
          </div>
        )}
      </main>
    </>
  );
}
