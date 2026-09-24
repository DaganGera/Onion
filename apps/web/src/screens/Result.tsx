import { useEffect, useMemo, useState } from 'preact/hooks';
import { Stamp, History, Camera, Info } from 'lucide-preact';
import { indicativeValue, type Bucket, type BulbVerdict } from '@parakh/core';
import { db } from '../lib/db';
import { loadSettings, type Settings } from '../lib/device';
import { getLang, speak, t } from '../lib/i18n';
import { go } from '../lib/router';
import { gradeStoredLot, issueCertificate, type Graded } from '../lib/lots';
import { bucketName, decisionTitle, Mix, toast, TopBar } from '../components/ui';
import { Overlay } from '../components/Overlay';
import { BulbSheet } from './BulbSheet';

export function decisionLine(g: Graded): string {
  const r = g.result, s = g.pack.lot.sprt;
  const bad = s.bucket_set.map(bucketName).join(' + ');
  switch (r.sprt.decision) {
    case 'ACCEPT_LOT': return t('dl.accept', 'The share of {bad} is below {p0}% with the chosen risk levels. Sequential test (SPRT) stopped.', { bad, p0: s.p0 * 100 });
    case 'REJECT_LOT': return t('dl.reject', 'The share of {bad} is above {p1}% with the chosen risk levels. Sequential test (SPRT) stopped.', { bad, p1: s.p1 * 100 });
    case 'SAMPLE_MORE': return r.sprt.traysMore > 0
      ? t('dl.more', 'Not enough evidence yet. Sample about {k} more tray(s) from the drawn sacks.', { k: r.sprt.traysMore })
      : t('dl.more0', 'Not enough evidence yet. Sample more trays from the drawn sacks.');
    default: return r.referShare > g.pack.lot.refer_share_max * 100
      ? t('dl.refer', '{p}% of bulbs need a human check, more than this pack allows for an automatic decision.', { p: r.referShare.toFixed(0) })
      : t('dl.refermax', 'Reached the tray limit without a clear answer. An inspector decides.');
  }
}

export function Result({ lotId }: { lotId: string }) {
  const [g, setG] = useState<Graded | null>(null);
  const [urls, setUrls] = useState<Record<string, string>>({});
  const [view, setView] = useState<'w' | 'c' | 'b'>('w');
  const [sel, setSel] = useState<{ cap: string; idx: number } | null>(null);
  const [s, setS] = useState<Settings | null>(null);
  const [rate, setRate] = useState(0);
  const [signing, setSigning] = useState(false);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    loadSettings().then((x) => { setS(x); setRate(x.ratePerQuintal); });
  }, []);
  useEffect(() => {
    gradeStoredLot(lotId).then((x) => {
      setG(x);
      if (!x) return;
      const u: Record<string, string> = {};
      for (const c of x.captures) u[c.id] = URL.createObjectURL(c.image);
      setUrls((old) => { Object.values(old).forEach(URL.revokeObjectURL); return u; });
    });
  }, [lotId, tick]);
  useEffect(() => {
    if (!g || !s?.speak) return;
    const h = g.result.procured.byWeight;
    speak(`${decisionTitle(g.result.sprt.decision)}. ${t('sp.proc', 'Procurable share by weight')} ${h.est.toFixed(0)} ${t('sp.pct', 'percent')}.`);
  }, [g?.result.sprt.decision, s?.speak, getLang()]);

  const verdictByRef = useMemo(() => {
    const m = new Map<string, Bucket>();
    if (!g) return m;
    const last = new Map(g.lot.overrides.map((o) => [o.bulb, o]));
    g.refs.forEach((r, i) => {
      const o = last.get(r.id);
      const final: Bucket = o ? (o.kind === 'contest' ? 'REFER' : o.to ?? g.ai[i].bucket) : g.ai[i].bucket;
      m.set(`${r.captureId}#${r.idx}`, final);
    });
    return m;
  }, [g]);

  if (!g) return <><TopBar title={t('res.title', 'Lot result')} /><main class="page"><p class="muted">{t('loading', 'Loading…')}</p></main></>;
  const r = g.result;
  if (r.n_bulb_observations === 0) {
    return (
      <>
        <TopBar title={t('res.title', 'Lot result')} />
        <main class="page">
          <p>{t('res.none', 'No onions have been measured in this lot yet.')}</p>
          <button class="btn primary" onClick={() => go(`capture/${lotId}${g.lot.mode === 'replay' ? '?replay=1' : ''}`)}><Camera size={20} />{t('res.capture', 'Open camera')}</button>
        </main>
      </>
    );
  }
  const vw = view === 'c' ? r.byCount : r.byWeight;
  const proc = view === 'c' ? r.procured.byCount : r.procured.byWeight;
  const iv = indicativeValue(g.lot.declaredKg, rate, r.procured.byWeight);
  const lastCert = g.lot.certHashes[g.lot.certHashes.length - 1];
  const dirty = !g.lastCert || g.lastCert.signed.core.overrides.length !== g.lot.overrides.length || g.lastCert.signed.core.pack.id !== g.lot.packId;
  const secondLook = r.perLookNonA.filter((x) => x.length > 1).map((x) => x[1] - x[0]);
  const selRef = sel && g.refs.find((x) => x.captureId === sel.cap && x.idx === sel.idx);
  const selIdx = selRef ? g.refs.indexOf(selRef) : -1;

  const sign = async () => {
    setSigning(true);
    try { const c = await issueCertificate(lotId); go(`cert/${c.hash}`); }
    catch (e) { toast(String(e)); }
    finally { setSigning(false); }
  };

  return (
    <>
      <TopBar title={g.lot.farmerRef} />
      <main class="page">
        <section class="verdict" data-d={r.sprt.decision} aria-live="polite">
          <span class="kicker">{g.lot.id} · {g.pack.short}</span>
          <h2>{decisionTitle(r.sprt.decision)}</h2>
          <div class="headline">
            <span class="big">{proc.est.toFixed(1)}</span><span class="unit">% {t('res.proc', 'procurable')}</span>
            <span class="rng">95% {proc.ci[0].toFixed(1)}–{proc.ci[1].toFixed(1)} · {view === 'c' ? t('res.bycount', 'by count') : t('res.byweight', 'by weight')}</span>
          </div>
          <p>{decisionLine(g)}</p>
        </section>

        {g.captures.some((c) => c.calib.tier === 'intrinsics') && (
          <p class="banner warn">{t('res.nosheet', 'Some photos had no calibration sheet, so sizes come from the camera alone (about ±25%). Bulbs near a size limit go to a person. Use the printed mat or an A4 sheet for real grading.')}</p>
        )}
        <section class="section">
          <div class="section-head">
            <h2>{t('res.mix', 'Grade mix')}</h2>
            <div class="seg" role="group" style={{ minWidth: 0 }}>
              <button aria-pressed={view === 'w'} onClick={() => setView('w')}>{t('res.w', 'Weight')}</button>
              <button aria-pressed={view === 'c'} onClick={() => setView('c')}>{t('res.c', 'Count')}</button>
              <button aria-pressed={view === 'b'} onClick={() => setView('b')}>{t('res.b', 'Bayes')}</button>
            </div>
          </div>
          <Mix view={view === 'b' ? r.byWeight : vw} bayes={view === 'b'} />
          <p class="note">
            {view === 'b'
              ? t('res.bayes.n', 'Bayesian view: Jeffreys credible interval on an effective sample of {n} bulbs (design effect {d}). Use it when there are only one or two trays.', { n: Math.round(r.n_bulb_observations / Math.max(1, r.n_looks) / Math.max(1, r.deff)), d: r.deff.toFixed(2) })
              : t('res.ci.n', 'Intervals: {m}, resampling whole trays, never single bulbs. {n} bulb-observations from {tr} tray(s) × {lk} look(s). Looks re-observe the same onions, so they are not counted as new samples.', { m: vw.GRADE_A.method === 'cluster-bootstrap' ? t('res.boot', 'tray bootstrap') : t('res.wilson', 'Wilson with design effect (fewer than 3 trays)'), n: r.n_bulb_observations, tr: r.n_trays, lk: r.n_looks })}
          </p>
          {secondLook.length > 0 && (() => {
            const spreads = r.perLookNonA.filter((x) => x.length > 1).map((x) => Math.max(...x) - Math.min(...x));
            const mean = spreads.reduce((a, b) => a + b, 0) / spreads.length;
            return <p class="note"><b>{t('res.rep', 'Repeat-capture spread')}:</b> {t('res.rep.v', '{m} percentage points on average between looks at the same tray (largest {x}). A big spread means the result depends on which face is up; shake and look once more.', { m: mean.toFixed(1), x: Math.max(...spreads).toFixed(1) })}</p>;
          })()}
          {secondLook.length > 0 && (
            <p class="note">{t('res.look2', 'Second look changed the non-Grade-A share by {d} percentage points (per tray). Hidden faces are why we shake and look again.', { d: secondLook.map((x) => (x >= 0 ? '+' : '') + x.toFixed(1)).join(', ') })}</p>
          )}
          <div class="row wrap">
            <a class="btn quiet small" href={`#/packs/${lotId}`}><History size={16} aria-hidden="true" />{t('res.travel', 'Re-grade under other rule packs')}</a>
          </div>
        </section>

        <section class="section">
          <div class="section-head"><h2>{t('res.bulbs', 'Every bulb')}</h2><span class="xs muted">{t('res.tap', 'Tap a bulb for its reasons')}</span></div>
          {g.captures.map((c) => (
            <Overlay key={c.id} url={urls[c.id] ?? ''} w={c.width} h={c.height} bulbs={c.bulbs}
              caption={`${t('cap.tray', 'Tray')} ${c.tray} · ${t('cap.look', 'look')} ${c.look} · ${c.calib.tier}${c.mode === 'replay' ? ' · replay' : ''}`}
              verdict={(i) => verdictByRef.get(`${c.id}#${i}`)} onTap={(i) => setSel({ cap: c.id, idx: i })}
              selected={sel?.cap === c.id ? sel.idx : undefined} />
          ))}
          <div class="row wrap">
            <button class="btn quiet small" onClick={() => go(`capture/${lotId}${g.lot.mode === 'replay' ? '?replay=1' : ''}`)}><Camera size={16} aria-hidden="true" />{t('res.more', 'Add a tray')}</button>
          </div>
        </section>

        <section class="card section">
          <h2 style={{ fontSize: 'var(--text-lg)' }}>{t('res.value', 'Indicative value')}</h2>
          <label class="field">
            <span class="small">{t('res.rate', 'Rate, ₹ per quintal')}</span>
            <input class="input mono" inputMode="numeric" value={rate} onInput={(e) => setRate(parseInt((e.target as HTMLInputElement).value) || 0)} />
          </label>
          <p class="mono" style={{ fontSize: 'var(--text-lg)' }}>₹{iv.low.toLocaleString('en-IN')} – ₹{iv.high.toLocaleString('en-IN')}</p>
          <p class="note">{t('res.value.n', 'For {kg} kg declared, using the procurable share by weight and its interval. Indicative only, never an official price.', { kg: g.lot.declaredKg })}</p>
        </section>

        {g.lot.overrides.length > 0 && (
          <section class="section">
            <h2 style={{ fontSize: 'var(--text-lg)' }}>{t('res.audit', 'Human actions')}</h2>
            <ul class="reasons">
              {g.lot.overrides.map((o, i) => (
                <li key={i} data-b={o.to ?? 'REFER'}>
                  <span>{o.by === 'officer' ? t('who.officer', 'Officer') : t('who.farmer', 'Farmer')} {o.kind === 'override' ? t('res.overrode', 'changed') : t('res.contested', 'contested')} {o.bulb}{o.to ? ` → ${bucketName(o.to)}` : ''}<code>{o.reason} · {new Date(o.at).toLocaleTimeString()}</code></span>
                </li>
              ))}
            </ul>
            <p class="note">{t('res.audit.n', 'The AI verdicts are kept unchanged beside these actions. Signing creates a new revision; the earlier one stays valid and linked.')}</p>
          </section>
        )}

        <div class="section no-print">
          {dirty
            ? <button class="btn primary block" onClick={sign} disabled={signing} data-state={signing ? 'loading' : undefined}><Stamp size={20} aria-hidden="true" />{lastCert ? t('res.resign', 'Sign new revision') : t('res.sign', 'Sign and issue receipt')}</button>
            : <a class="btn primary block" href={`#/cert/${lastCert}`}><Stamp size={20} aria-hidden="true" />{t('res.view', 'View receipt')}</a>}
          {lastCert && dirty && <a class="btn quiet block" href={`#/cert/${lastCert}`}>{t('res.viewprev', 'View last receipt')}</a>}
          <p class="xs muted row"><Info size={14} aria-hidden="true" />{t('res.model', 'Perception: Tier-0 colour model, runs on this phone. Adjudication: rule pack {id}.', { id: g.pack.id })}</p>
        </div>
      </main>
      {sel && selRef && (
        <BulbSheet g={g} refIdx={selIdx} url={urls[selRef.captureId]} onClose={() => setSel(null)}
          onChanged={() => { setSel(null); setTick((x) => x + 1); }} ai={g.ai[selIdx] as BulbVerdict} />
      )}
    </>
  );
}
