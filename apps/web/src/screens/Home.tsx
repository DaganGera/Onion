import { useEffect, useState } from 'preact/hooks';
import { ScanLine, ShieldCheck, History, LayoutDashboard, Printer, Play, ArrowRight, Scale, Layers, Percent, CloudOff, Sparkles } from 'lucide-preact';
import { packById } from '@parakh/core';
import { loadSettings, type Settings } from '../lib/device';
import { t } from '../lib/i18n';
import { go } from '../lib/router';
import { OnlineChip } from '../components/ui';
import { seedDemoLot } from '../lib/demo';
import { LotRow, loadLots, type LotWithCert } from '../components/LotRow';
import { db } from '../lib/db';

function greeting() {
  const h = new Date().getHours();
  return h < 12 ? t('home.gm', 'Good morning') : h < 17 ? t('home.ga', 'Good afternoon') : t('home.ge', 'Good evening');
}

export function Home() {
  const [lots, setLots] = useState<LotWithCert[] | null>(null);
  const [s, setS] = useState<Settings | null>(null);
  const [busy, setBusy] = useState(false);
  const [offlineReady, setOfflineReady] = useState(false);
  useEffect(() => { navigator.serviceWorker?.ready.then(() => setOfflineReady(!!navigator.serviceWorker.controller)).catch(() => {}); }, []);
  const [bulbs, setBulbs] = useState(0);
  useEffect(() => {
    loadSettings().then(setS); loadLots(50).then(setLots);
    db.captures.toArray().then((cs) => setBulbs(cs.reduce((a, c) => a + c.bulbs.filter((b) => !b.excluded).length, 0)));
  }, []);
  const pack = s ? packById(s.packId) : null;
  const todayKey = new Date().toDateString();
  const today = (lots ?? []).filter((l) => new Date(l.createdAt).toDateString() === todayKey);
  const signed = (lots ?? []).filter((l) => l.cert);
  const avgProc = signed.length ? signed.reduce((a, l) => a + l.cert!.signed.core.headline.procured, 0) / signed.length : null;

  const demo = async () => { setBusy(true); try { const id = await seedDemoLot(); go(`lot/${id}`); } finally { setBusy(false); } };

  return (
    <>
      <header class="homebanner">
        <div class="hb-top">
          <span class="wordmark light"><img src="./icon.svg" alt="" width="30" height="30" />SAMA</span>
          <OnlineChip />
        </div>
        <section class="hello">
          <div class="avatar" aria-hidden="true">{(s?.officer ?? 'O').slice(0, 1)}</div>
          <div class="grow">
            <p class="hello-g">{greeting()}</p>
            <p class="hello-c">{s?.centre} · {s?.officer}</p>
          </div>
        </section>
        <div class="stats" role="list">
          <div class="stat" role="listitem"><Layers size={18} aria-hidden="true" /><b class="mono">{today.length}</b><span>{t('home.st.today', 'lots today')}</span></div>
          <div class="stat" role="listitem"><Scale size={18} aria-hidden="true" /><b class="mono">{bulbs}</b><span>{t('home.st.bulbs', 'onions measured')}</span></div>
          <div class="stat" role="listitem"><Percent size={18} aria-hidden="true" /><b class="mono">{avgProc === null ? '—' : avgProc.toFixed(0) + '%'}</b><span>{t('home.st.proc', 'avg procurable')}</span></div>
        </div>
      </header>
      <main class="page with-tabs home-page">
        <button class="hero-card" onClick={() => go('new')}>
          <span class="hero-icon"><ScanLine size={30} aria-hidden="true" /></span>
          <span class="hero-text">
            <b>{t('home.start', 'Start a new lot')}</b>
            <span>{t('home.start.s', 'Draw sacks, photograph trays, get a signed receipt.')}</span>
          </span>
          <ArrowRight size={22} aria-hidden="true" />
        </button>
        {pack && (
          <a class="packline" href="#/packs">
            <History size={16} aria-hidden="true" />
            <span class="grow">{t('home.pack', 'Rule pack')}: <b>{pack.short}</b></span>
            <span class="chip press">{pack.status}</span>
          </a>
        )}

        <section class="section">
          <div class="section-head"><h2>{t('home.quick', 'Quick actions')}</h2></div>
          <div class="quick">
            <a href="#/verify"><span class="qicon q-leaf"><ShieldCheck size={22} aria-hidden="true" /></span>{t('home.verify', 'Verify a receipt')}</a>
            <a href="#/packs"><span class="qicon q-brand"><History size={22} aria-hidden="true" /></span>{t('home.packs', 'Rule packs')}</a>
            <a href="#/fleet"><span class="qicon q-gold"><LayoutDashboard size={22} aria-hidden="true" /></span>{t('nav.fleet', 'Fleet dashboard')}</a>
            <a href="./calibration_mat.pdf" target="_blank" rel="noopener"><span class="qicon"><Printer size={22} aria-hidden="true" /></span>{t('home.mat', 'Print the mat')}</a>
          </div>
        </section>

        <section class="section">
          <div class="section-head">
            <h2>{t('home.recent', 'Recent lots')}</h2>
            {lots && lots.length > 0 && <a class="seeall" href="#/lots">{t('home.all', 'See all')}</a>}
          </div>
          {lots && lots.length === 0 && (
            <div class="empty">
              <Sparkles size={28} aria-hidden="true" />
              <p>{t('home.empty', 'No lots yet. Grade one with the camera, or load the demo lot: real market photos from Pune, replayed through the same pipeline.')}</p>
              <button class="btn quiet" data-state={busy ? 'loading' : undefined} disabled={busy} onClick={demo}>
                <Play size={18} aria-hidden="true" />{busy ? t('home.demo.busy', 'Measuring demo photos…') : t('home.demo', 'Load the demo lot')}
              </button>
            </div>
          )}
          {lots && lots.length > 0 && <nav class="lotlist" aria-label={t('home.recent', 'Recent lots')}>{lots.slice(0, 4).map((l) => <LotRow key={l.id} l={l} />)}</nav>}
        </section>

        <p class="offline-note">
          <CloudOff size={14} aria-hidden="true" />
          {offlineReady ? t('home.offline.ok', 'Saved on this phone: works without internet.') : t('home.offline.wait', 'Keep this page open online once so it can be saved for offline use.')}
        </p>
      </main>
    </>
  );
}
