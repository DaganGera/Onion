import { useEffect, useState } from 'preact/hooks';
import { Download, PenLine } from 'lucide-preact';
import { PACKS, DEFAULT_WEIGHT_MODEL } from '@parakh/core';
import { TIER0 } from '@parakh/vision';
import { db, type SthRow } from '../lib/db';
import { deviceKey, keyFingerprint, loadSettings, saveSettings, type Settings as S } from '../lib/device';
import { LANGS, setLang, t } from '../lib/i18n';
import { exportLog, modelHash, signTreeHead } from '../lib/lots';
import { toast, TopBar } from '../components/ui';

export function Settings() {
  const [s, setS] = useState<S | null>(null);
  const [fp, setFp] = useState('');
  const [alg, setAlg] = useState('');
  const [logSize, setLogSize] = useState(0);
  const [sth, setSth] = useState<SthRow | null>(null);
  const [mh, setMh] = useState('');
  const [corr, setCorr] = useState(0);
  useEffect(() => {
    loadSettings().then(setS);
    keyFingerprint().then(setFp);
    deviceKey().then((k) => setAlg(k.alg));
    db.log.count().then(setLogSize);
    db.sth.orderBy('size').last().then((x) => setSth(x ?? null));
    db.corrections.count().then(setCorr);
    modelHash().then(setMh);
  }, []);
  if (!s) return null;
  const upd = async (p: Partial<S>) => { const n = { ...s, ...p }; setS(n); await saveSettings(n); if (p.lang) await setLang(p.lang); };

  const saveJson = (obj: unknown, name: string) => {
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([JSON.stringify(obj, null, 1)], { type: 'application/json' }));
    a.download = name; a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 2000);
  };

  return (
    <>
      <TopBar title={t('set.title', 'Settings & log')} />
      <main class="page">
        <section class="section">
          <label class="field">
            <span>{t('set.lang', 'Language')}</span>
            <select class="select" value={s.lang} onChange={(e) => upd({ lang: (e.target as HTMLSelectElement).value })}>
              {LANGS.map((l) => <option key={l.code} value={l.code}>{l.name}</option>)}
            </select>
            <small>{t('set.lang.s', 'Translations other than English are machine drafts awaiting a native speaker’s proofread.')}</small>
          </label>
          <label class="row small"><input type="checkbox" checked={s.speak} onChange={(e) => upd({ speak: (e.target as HTMLInputElement).checked })} />{t('set.speak', 'Read the lot decision aloud')}</label>
        </section>

        <section class="section">
          <h2 style={{ fontSize: 'var(--text-lg)' }}>{t('set.centre', 'Centre')}</h2>
          <div class="grid2">
            <label class="field"><span>{t('set.cid', 'Centre code')}</span><input class="input" value={s.centre} onChange={(e) => upd({ centre: (e.target as HTMLInputElement).value })} /></label>
            <label class="field"><span>{t('set.oid', 'Officer ID')}</span><input class="input" value={s.officer} onChange={(e) => upd({ officer: (e.target as HTMLInputElement).value })} /></label>
          </div>
          <label class="field">
            <span>{t('set.pack', 'Default rule pack')}</span>
            <select class="select" value={s.packId} onChange={(e) => upd({ packId: (e.target as HTMLSelectElement).value })}>
              {PACKS.map((p) => <option key={p.id} value={p.id}>{p.short}</option>)}
            </select>
          </label>
          <div class="grid2">
            <label class="field"><span>{t('set.camh', 'Camera height if no sheet, mm')}</span><input class="input mono" inputMode="numeric" value={s.camHmm} onChange={(e) => upd({ camHmm: parseInt((e.target as HTMLInputElement).value) || 380 })} /></label>
            <label class="field"><span>{t('set.rate', 'Default rate ₹/quintal')}</span><input class="input mono" inputMode="numeric" value={s.ratePerQuintal} onChange={(e) => upd({ ratePerQuintal: parseInt((e.target as HTMLInputElement).value) || 0 })} /></label>
          </div>
          <p class="note">{t('set.rate.n', 'Default rate 2125 is from a press report of the July 2026 PSF procurement price (docs/SOURCES.md S5). Indicative only.')}</p>
        </section>

        <section class="section">
          <h2 style={{ fontSize: 'var(--text-lg)' }}>{t('set.key', 'Signing key')}</h2>
          <dl class="kv">
            <dt>{t('set.alg', 'Algorithm')}</dt><dd>{alg}</dd>
            <dt>{t('set.fp', 'Fingerprint')}</dt><dd>{fp}</dd>
          </dl>
          <p class="note">{t('set.key.n', 'Created on this phone and cannot be copied out by the app. Clearing site data destroys it; receipts already issued stay verifiable.')}</p>
        </section>

        <section class="section">
          <h2 style={{ fontSize: 'var(--text-lg)' }}>{t('set.log', 'Transparency log')}</h2>
          <dl class="kv">
            <dt>{t('set.leaves', 'Receipts logged')}</dt><dd>{logSize}</dd>
            <dt>{t('set.sth', 'Last signed tree head')}</dt><dd>{sth ? `#${sth.size} · ${sth.root.slice(0, 16)}…` : '—'}</dd>
            <dt>{t('set.sth.at', 'Signed at')}</dt><dd>{sth ? new Date(sth.at).toLocaleString() : '—'}</dd>
          </dl>
          <div class="grid2">
            <button class="btn quiet" onClick={async () => { const x = await signTreeHead(); setSth(x); toast(t('set.sth.ok', 'Tree head signed.')); }}><PenLine size={18} aria-hidden="true" />{t('set.sign', 'Sign tree head')}</button>
            <button class="btn quiet" onClick={async () => saveJson(await exportLog(), `parakh-log-${new Date().toISOString().slice(0, 10)}.json`)}><Download size={18} aria-hidden="true" />{t('set.export', 'Export log')}</button>
          </div>
          <p class="note">{t('set.log.n', 'RFC 6962 Merkle log of every receipt hash. Publish the export daily: anyone holding an older signed tree head can prove later history was not rewritten.')}</p>
        </section>

        <section class="section">
          <h2 style={{ fontSize: 'var(--text-lg)' }}>{t('set.model', 'Models and calibration')}</h2>
          <dl class="kv">
            <dt>{t('set.percep', 'Perception')}</dt><dd>{TIER0.id}@{TIER0.version}</dd>
            <dt>{t('set.mh', 'Model hash')}</dt><dd>{mh.slice(0, 16)}…</dd>
            <dt>{t('set.wm', 'Weight model')}</dt><dd>{DEFAULT_WEIGHT_MODEL.source} · w = {DEFAULT_WEIGHT_MODEL.a.toExponential(2)}·d^{DEFAULT_WEIGHT_MODEL.b}</dd>
            <dt>{t('set.corr', 'Corrections saved for retraining')}</dt><dd>{corr}</dd>
          </dl>
          <button class="btn quiet" onClick={async () => saveJson({ kind: 'parakh.corrections', rows: await db.corrections.toArray() }, 'parakh-corrections.json')}><Download size={18} aria-hidden="true" />{t('set.corr.x', 'Export corrections')}</button>
        </section>
      </main>
    </>
  );
}
