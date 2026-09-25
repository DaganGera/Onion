import { useEffect, useRef, useState } from 'preact/hooks';
import { Check, X, Minus, ScanLine, ClipboardPaste, FileUp } from 'lucide-preact';
import { decodeCompact, fingerprint, fromHex, packById, PACKS, verifyCert, type SignedCert, type VerifyReport } from '@parakh/core';
import { db } from '../lib/db';
import { t } from '../lib/i18n';
import { scanFrame } from '../lib/qr';
import { bucketName, decisionTitle, Mix, TopBar } from '../components/ui';

type State = { cert: SignedCert; rep: VerifyReport; fp: string; inLog: number | null; predLocal: boolean } | null;

export function Verify({ code }: { code: string }) {
  const [state, setState] = useState<State>(null);
  const [err, setErr] = useState('');
  const [scanning, setScanning] = useState(false);
  const [paste, setPaste] = useState('');
  const video = useRef<HTMLVideoElement>(null);

  const run = async (text: string, cert?: SignedCert) => {
    setErr('');
    try {
      const c = cert ?? (await decodeCompact(text));
      const pred = c.core.prev ? await db.certs.get(c.core.prev) : undefined;
      const rep = await verifyCert(c, PACKS, pred ? pred.signed : undefined);
      const log = await db.log.where('certHash').equals(c.hash).first();
      setState({ cert: c, rep, fp: await fingerprint(fromHex(c.sig.pub)), inLog: log?.idx ?? null, predLocal: !!pred });
    } catch (e) {
      setState(null);
      setErr(t('v.bad', 'This code is damaged, altered, or not a Parakh receipt. Nothing could be verified.'));
    }
  };

  useEffect(() => { if (code) run(code); }, [code]);

  useEffect(() => {
    if (!scanning) return;
    let stream: MediaStream | null = null, alive = true;
    navigator.mediaDevices?.getUserMedia({ video: { facingMode: { ideal: 'environment' }, width: { ideal: 1920 } } }).then((s) => {
      stream = s;
      if (video.current) { video.current.srcObject = s; video.current.play().catch(() => {}); }
      const loop = async () => {
        if (!alive) return;
        const r = video.current ? await scanFrame(video.current).catch(() => null) : null;
        if (r && r.startsWith('PK1:')) { setScanning(false); run(r); return; }
        setTimeout(loop, 250);
      };
      loop();
    }).catch(() => { setErr(t('v.nocam', 'Camera unavailable. Paste the code or open the evidence file instead.')); setScanning(false); });
    return () => { alive = false; stream?.getTracks().forEach((x) => x.stop()); };
  }, [scanning]);

  const openFile = (f: File) => f.text().then((s) => {
    try { const j = JSON.parse(s); run('', j.cert ?? j); } catch { setErr(t('v.file', 'That file is not a Parakh evidence file.')); }
  });

  const r = state?.rep;
  const item = (ok: boolean | null, title: string, sub: string) => (
    <li>
      <span class="ic" data-s={ok === null ? 'na' : ok ? 'ok' : 'bad'}>{ok === null ? <Minus size={16} /> : ok ? <Check size={16} /> : <X size={16} />}</span>
      <span><b>{title}</b><small>{sub}</small></span>
    </li>
  );
  const pack = state ? packById(state.cert.core.pack.id) : null;
  const allOk = r && r.sigOk && r.hashOk && r.regradeOk && r.headlineOk && r.chainOk !== false;

  return (
    <>
      <TopBar title={t('v.title', 'Verify a receipt')} subtitle={t('v.sub', 'Scan a receipt QR. Works without internet.')} />
      <main class="page">
        {!state && (
          <>
            <p class="small muted">{t('v.intro', 'Nothing is sent anywhere. This phone checks the signature, then re-runs the grading on the stored measurements with the named rule pack.')}</p>
            {scanning
              ? <div class="scanner"><video ref={video} playsInline muted /><div class="aim" /></div>
              : <button class="btn primary block" onClick={() => setScanning(true)}><ScanLine size={20} aria-hidden="true" />{t('v.scan', 'Scan QR code')}</button>}
            <label class="field">
              <span>{t('v.paste', 'Or paste the code')}</span>
              <textarea class="input mono" rows={3} style={{ padding: 12, minHeight: 88 }} value={paste} onInput={(e) => setPaste((e.target as HTMLTextAreaElement).value)} placeholder="PK1:…" />
            </label>
            <div class="grid2">
              <button class="btn quiet" disabled={!paste.trim()} onClick={() => run(paste)}><ClipboardPaste size={18} aria-hidden="true" />{t('v.check', 'Check')}</button>
              <label class="btn quiet"><FileUp size={18} aria-hidden="true" />{t('v.file.b', 'Evidence file')}<input type="file" accept=".json,application/json" class="sr-only" onChange={(e) => { const f = (e.target as HTMLInputElement).files?.[0]; if (f) openFile(f); }} /></label>
            </div>
          </>
        )}
        {err && <p class="banner warn" role="alert">{err}</p>}
        {state && r && (
          <>
            <section class={'verdict'} data-d={allOk ? 'ACCEPT_LOT' : 'REJECT_LOT'}>
              <span class="kicker">{state.cert.core.lot.id} · rev {state.cert.core.rev}</span>
              <h2>{allOk ? t('v.ok', 'Receipt checks out') : t('v.fail', 'Receipt does not check out')}</h2>
              <p>{allOk ? t('v.ok.p', 'Signed by key {fp}. Re-graded here with the same result.', { fp: state.fp }) : t('v.fail.p', 'At least one check below failed. Do not rely on this receipt.')}</p>
            </section>
            <ul class="checks">
              {item(r.sigOk, t('v.sig', 'Signature valid'), `${state.cert.sig.alg} · ${t('v.key', 'device key')} ${state.fp}`)}
              {item(r.hashOk, t('v.hash', 'Record not altered'), `sha256 ${state.cert.hash.slice(0, 32)}…`)}
              {item(r.packKnown ? true : null, t('v.pack', 'Rule pack recognised'), r.packKnown ? `${pack?.short} · ${pack?.status}` : t('v.pack.u', 'Unknown pack hash: this phone cannot re-grade it.'))}
              {item(r.regradeOk, t('v.regrade', 'Re-graded on this phone: matches'), t('v.regrade.s', '{n} measurements → same bucket shares, intervals and decision.', { n: state.cert.core.bulbs.length }))}
              {item(r.headlineOk, t('v.head', 'Printed numbers match the re-grade'), t('v.head.s', 'Headline on the receipt equals the recomputed one.'))}
              {item(r.chainOk, t('v.chain', 'Hash-chain link'), r.chainOk === null ? (state.cert.core.prev ? t('v.chain.na', 'Previous receipt from that device is not on this phone.') : t('v.chain.first', 'First receipt from that device.')) : t('v.chain.s', 'Points to the previous receipt issued on that device.'))}
              {item(state.inLog !== null ? true : null, t('v.log', 'In this phone’s transparency log'), state.inLog !== null ? `${t('v.log.i', 'leaf')} #${state.inLog}` : t('v.log.na', 'Not in this phone’s log (normal for a second phone). Check the centre’s published log.'))}
            </ul>
            {r.result && (
              <section class="section">
                <h2 style={{ fontSize: 'var(--text-lg)' }}>{decisionTitle(r.result.sprt.decision)} · {r.result.procured.byWeight.est.toFixed(1)}% {t('res.proc', 'procurable')}</h2>
                <Mix view={r.result.byWeight} />
                <p class="note">{t('v.who', 'Seller {s} · centre {c} · {n} bulb-observations · URS: {u}', { s: state.cert.core.lot.farmerRef, c: state.cert.core.lot.centre, n: r.result.n_bulb_observations, u: bucketName('URS') })}</p>
              </section>
            )}
            <button class="btn quiet block" onClick={() => { setState(null); setPaste(''); }}>{t('v.again', 'Verify another')}</button>
          </>
        )}
      </main>
    </>
  );
}
