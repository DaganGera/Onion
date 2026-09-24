import { useEffect, useState } from 'preact/hooks';
import { Camera, QrCode, History, Play } from 'lucide-preact';
import { packById, type SprtDecision } from '@parakh/core';
import { db, type CertRow, type LotRow } from '../lib/db';
import { loadSettings, type Settings } from '../lib/device';
import { t } from '../lib/i18n';
import { go } from '../lib/router';
import { decisionTitle, TopBar } from '../components/ui';
import { seedDemoLot } from '../lib/demo';

export function Home() {
  const [lots, setLots] = useState<(LotRow & { cert?: CertRow })[] | null>(null);
  const [s, setS] = useState<Settings | null>(null);
  const [busy, setBusy] = useState(false);
  const [offlineReady, setOfflineReady] = useState(false);
  useEffect(() => {
    navigator.serviceWorker?.ready.then(() => setOfflineReady(!!navigator.serviceWorker.controller)).catch(() => {});
  }, []);
  useEffect(() => {
    loadSettings().then(setS);
    (async () => {
      const ls = await db.lots.orderBy('createdAt').reverse().limit(25).toArray();
      const withCert = await Promise.all(ls.map(async (l) => ({ ...l, cert: l.certHashes.length ? await db.certs.get(l.certHashes[l.certHashes.length - 1]) : undefined })));
      setLots(withCert);
    })();
  }, []);
  const pack = s ? packById(s.packId) : null;
  const today = new Date().toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' });

  return (
    <>
      <TopBar />
      <main class="page">
        <section class="hero-action">
          <p class="mono xs muted">{s?.centre} · {today}</p>
          <h1>{t('home.h', 'Measure a lot. Issue a receipt anyone can check.')}</h1>
          <button class="btn primary block" onClick={() => go('new')}><Camera size={20} aria-hidden="true" />{t('home.start', 'Start a new lot')}</button>
          {pack && (
            <p class="small muted">
              {t('home.pack', 'Rule pack')}: <a href="#/packs">{pack.short}</a> <span class="chip press">{pack.status}</span>
            </p>
          )}
        </section>

        <div class="tiles">
          <a class="tile" href="#/verify"><QrCode size={22} aria-hidden="true" /><b>{t('home.verify', 'Verify a receipt')}</b><span>{t('home.verify.s', 'Scan a certificate QR. Works offline.')}</span></a>
          <a class="tile" href="#/packs"><History size={22} aria-hidden="true" /><b>{t('home.packs', 'Rule packs')}</b><span>{t('home.packs.s', 'Re-grade any lot under another norm.')}</span></a>
        </div>

        <section class="section">
          <div class="section-head">
            <h2>{t('home.recent', 'Recent lots')}</h2>
            {lots && lots.length > 0 && <span class="mono xs muted">{lots.length}</span>}
          </div>
          {lots && lots.length === 0 && (
            <div class="card tint section">
              <p class="small">{t('home.empty', 'No lots yet. Grade one with the camera, or load the demo lot: real market photos from Pune, replayed through the same pipeline.')}</p>
              <button class="btn quiet" data-state={busy ? 'loading' : undefined} disabled={busy}
                onClick={async () => { setBusy(true); try { const id = await seedDemoLot(); go(`lot/${id}`); } finally { setBusy(false); } }}>
                <Play size={18} aria-hidden="true" />{busy ? t('home.demo.busy', 'Measuring demo photos…') : t('home.demo', 'Load the demo lot')}
              </button>
            </div>
          )}
          {lots && lots.length > 0 && (
            <nav class="ledger" aria-label={t('home.recent', 'Recent lots')}>
              {lots.map((l) => {
                const h = l.cert?.signed.core.headline;
                return (
                  <a key={l.id} href={l.cert ? `#/cert/${l.cert.hash}` : `#/lot/${l.id}`}>
                    <span class="t">{l.farmerRef || l.id}</span>
                    <span class="s">{l.id} · {new Date(l.createdAt).toLocaleString(undefined, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })}{l.demo ? ' · demo' : ''}</span>
                    <span class="r">
                      {h ? <>
                        <span class="mono small">{h.procured.toFixed(1)}%</span>
                        <span class="xs muted">{decisionTitle(h.decision as SprtDecision)}</span>
                      </> : <span class="xs muted">{t('home.draft', 'not signed')}</span>}
                    </span>
                  </a>
                );
              })}
            </nav>
          )}
        </section>

        <nav class="footer-links" aria-label={t('home.more', 'More')}>
          <a href="#/fleet">{t('nav.fleet', 'Fleet dashboard')}</a>
          <a href="#/settings">{t('nav.settings', 'Settings & log')}</a>
          <a href="./calibration_mat.pdf" target="_blank" rel="noopener">{t('nav.mat', 'Calibration mat (A4)')}</a>
          <a href="#/about">{t('nav.about', 'How it works & limits')}</a>
        </nav>
        <p class="xs muted">{offlineReady ? t('home.offline.ok', 'Saved on this phone: works without internet.') : t('home.offline.wait', 'Keep this page open online once so it can be saved for offline use.')}</p>
      </main>
    </>
  );
}
