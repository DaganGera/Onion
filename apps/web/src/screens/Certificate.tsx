import { useEffect, useState } from 'preact/hooks';
import { Printer, Share2, FileJson, ShieldCheck, ListChecks } from 'lucide-preact';
import { fingerprint, fromHex, packById, type Bucket } from '@parakh/core';
import { db, type CertRow } from '../lib/db';
import { t } from '../lib/i18n';
import { go } from '../lib/router';
import { evidenceBundle } from '../lib/lots';
import { shareImage } from '../lib/share';
import { bucketName, decisionTitle, Letter, toast, TopBar } from '../components/ui';
import { Qr } from '../components/Qr';

const TIER_NAME: Record<string, () => string> = {
  aruco: () => t('tier.aruco', 'Printed marker mat (best)'), a4: () => t('tier.a4', 'Plain A4 sheet'),
  coin: () => t('tier.coin', 'Known coin'), intrinsics: () => t('tier.intr', 'Camera estimate only (wide uncertainty)'),
};

export function Certificate({ hash }: { hash: string }) {
  const [c, setC] = useState<CertRow | null>(null);
  const [revs, setRevs] = useState<CertRow[]>([]);
  const [fp, setFp] = useState('');
  useEffect(() => {
    db.certs.get(hash).then(async (x) => {
      if (!x) return;
      setC(x);
      setFp(await fingerprint(fromHex(x.signed.sig.pub)));
      setRevs((await db.certs.where('lotId').equals(x.lotId).toArray()).sort((a, b) => a.rev - b.rev));
    });
  }, [hash]);
  if (!c) return <><TopBar title={t('cert.title', 'Receipt')} /><main class="page"><p class="muted">{t('loading', 'Loading…')}</p></main></>;
  const k = c.signed.core;
  const h = k.headline;
  const pack = packById(k.pack.id);
  const rows: [Bucket, number][] = [['GRADE_A', h.gradeA], ['URS', h.urs], ['REJECT', h.reject], ['REFER', h.refer]];

  const download = async () => {
    const b = await evidenceBundle(hash);
    const blob = new Blob([JSON.stringify(b)], { type: 'application/json' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `${k.lot.id}-rev${k.rev}.parakh.json`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 2000);
  };

  return (
    <>
      <TopBar title={t('cert.title', 'Receipt')} backTo={`lot/${k.lot.id}`} />
      <main class="page">
        <article class="receipt" aria-label={t('cert.aria', 'Lot quality receipt')}>
          <span class="proto">{t('cert.proto', 'PROTOTYPE · NOT AN OFFICIAL DOCUMENT')}{k.capture.mode === 'replay' ? ' · REPLAY' : ''}</span>
          <div>
            <h1 style={{ fontSize: 'var(--text-xl)' }}>{t('cert.h', 'Onion lot quality receipt')}</h1>
            <p class="mono xs muted">{k.lot.id} · {t('cert.rev', 'revision')} {k.rev}</p>
          </div>
          <dl class="kv">
            <dt>{t('cert.seller', 'Seller')}</dt><dd>{k.lot.farmerRef}</dd>
            <dt>{t('cert.centre', 'Centre')}</dt><dd>{k.lot.centre}</dd>
            <dt>{t('cert.variety', 'Variety · sacks · declared')}</dt><dd>{k.lot.variety} · {k.lot.sacks} · {k.lot.declaredKg} kg</dd>
            <dt>{t('cert.issued', 'Issued')}</dt><dd>{new Date(k.issuedAt).toLocaleString()}</dd>
          </dl>
          <div class="rule" />
          <div>
            <p class="small muted">{t('cert.decision', 'Decision')}</p>
            <p style={{ font: '600 var(--text-2xl)/1.1 var(--font-display)' }}>{decisionTitle(h.decision)}</p>
            <p class="small">{t('cert.proc', 'Procurable by weight')}: <b class="mono">{h.procured.toFixed(1)}%</b> <span class="mono muted">(95% {h.procured_ci[0].toFixed(1)}–{h.procured_ci[1].toFixed(1)})</span></p>
          </div>
          <table>
            <tbody>
              {rows.map(([b, v]) => (
                <tr key={b}><th><span class="row" style={{ gap: 8 }}><Letter b={b} />{bucketName(b)}</span></th><td>{v.toFixed(1)}%</td></tr>
              ))}
            </tbody>
          </table>
          <p class="note">{t('cert.bw', 'Shares by estimated weight. Grade A 95% interval: {a}–{b}%. {n} bulb-observations, tray-level intervals.', { a: h.gradeA_ci[0].toFixed(1), b: h.gradeA_ci[1].toFixed(1), n: k.bulbs.length })}</p>
          <div class="rule" />
          <dl class="kv">
            <dt>{t('cert.pack', 'Rule pack')}</dt><dd>{pack?.short ?? k.pack.id} · {pack?.status}</dd>
            <dt>{t('cert.scale', 'Size calibration')}</dt><dd>{TIER_NAME[k.calib.tier]?.()}</dd>
            <dt>{t('cert.model', 'Perception model')}</dt><dd>{k.model.id}</dd>
            <dt>{t('cert.sample', 'Sacks drawn')}</dt><dd>{k.sampling ? k.sampling.draws : t('cert.nodraw', 'not drawn')}</dd>
            <dt>{t('cert.actions', 'Human actions')}</dt><dd>{k.overrides.length}</dd>
          </dl>
          {pack && <p class="note"><b>URS.</b> {pack.urs_definition}</p>}
          <div class="qrbox">
            {c.qr ? <Qr text={c.qr} label={t('cert.qr', 'Verification code')} /> : <p class="note">{t('cert.noqr', 'Too many bulbs for one QR code; verify with the evidence file.')}</p>}
            <p class="xs muted">{t('cert.scan', 'Scan with Parakh → Verify. Checks the signature and re-grades the lot on the scanning phone, offline.')}</p>
          </div>
          <div class="stamp">{t('cert.signed', 'Signed on device')}<br />{c.signed.sig.alg} · {fp}</div>
          <p class="hash">sha256 {c.hash}<br />pack {k.pack.hash.slice(0, 24)}… · model {k.model.hash.slice(0, 16)}…<br />{k.parent ? `parent ${k.parent.slice(0, 24)}… · ` : ''}{k.prev ? `chain ${k.prev.slice(0, 24)}…` : t('cert.first', 'first on this device')}</p>
          <p class="note">{t('cert.te', 'Tamper-evident, not tamper-proof: any change to this record breaks the signature or the re-grade. It does not prove the photos show the sacks that were sold.')}</p>
        </article>

        {revs.length > 1 && (
          <section class="section no-print">
            <h2 style={{ fontSize: 'var(--text-lg)' }}>{t('cert.revs', 'Revisions')}</h2>
            <nav class="ledger">
              {revs.map((r) => (
                <a key={r.hash} href={`#/cert/${r.hash}`} aria-current={r.hash === hash ? 'page' : undefined}>
                  <span class="t">{t('cert.rev', 'revision')} {r.rev} · {r.signed.core.overrides.length} {t('cert.acts', 'human actions')}</span>
                  <span class="s">{r.hash.slice(0, 20)}… · {new Date(r.issuedAt).toLocaleTimeString()}</span>
                  <span class="r"><span class="mono small">{r.signed.core.headline.procured.toFixed(1)}%</span></span>
                </a>
              ))}
            </nav>
          </section>
        )}

        <div class="grid2 no-print">
          <button class="btn quiet" onClick={() => window.print()}><Printer size={18} aria-hidden="true" />{t('cert.print', 'Print A4')}</button>
          <button class="btn quiet" onClick={() => shareImage(c, fp).catch((e) => toast(String(e)))}><Share2 size={18} aria-hidden="true" />{t('cert.share', 'Share image')}</button>
          <button class="btn quiet" onClick={download}><FileJson size={18} aria-hidden="true" />{t('cert.bundle', 'Evidence file')}</button>
          <button class="btn quiet" onClick={() => go(`verify?c=${encodeURIComponent(c.qr)}`)}><ShieldCheck size={18} aria-hidden="true" />{t('cert.verify', 'Verify here')}</button>
        </div>
        <a class="btn primary block no-print" href={`#/lot/${k.lot.id}`}><ListChecks size={18} aria-hidden="true" />{t('cert.back', 'Back to bulbs')}</a>
      </main>
    </>
  );
}
