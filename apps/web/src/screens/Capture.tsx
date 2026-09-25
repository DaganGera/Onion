import { useEffect, useRef, useState } from 'preact/hooks';
import { X, RefreshCw, ArrowRight, Check } from 'lucide-preact';
import { evaluateGates, tiltFromOrientation, type Analysis, type Gate } from '@parakh/vision';
import { sha256Hex } from '@parakh/core';
import { db, type CaptureRow, type LotRow } from '../lib/db';
import { loadSettings, type Settings } from '../lib/device';
import { t } from '../lib/i18n';
import { back, go } from '../lib/router';
import { analyzeBitmap, scanBitmap, toEvidenceJpeg } from '../lib/vision';
import { REPLAY_CAM_H, SAMPLES } from '../lib/demo';
import { Overlay } from '../components/Overlay';

type Phase = 'aim' | 'busy' | 'review' | 'error';

const GATE_LABEL: Record<string, () => string> = {
  level: () => t('g.level', 'Level'), sharp: () => t('g.sharp', 'Sharp'), exposure: () => t('g.light', 'Light'),
  glare: () => t('g.glare', 'Glare'), target: () => t('g.target', 'Sheet'), bulbs: () => t('g.bulbs', 'Onions'),
};
const gateMsg = (g: Gate) => ({
  level: () => t('gm.level', 'Hold the phone flat, parallel to the table.'),
  sharp: () => t('gm.sharp', 'Too blurry. Hold still or move a little further away.'),
  exposure: () => (g.value < 50 ? t('gm.dark', 'Too dark. Move to better light.') : t('gm.bright', 'Too bright. Avoid direct sun on the tray.')),
  glare: () => t('gm.glare', 'Glare on the onions. Tilt away from the light or shade the tray.'),
  target: () => t('gm.target', 'Keep the calibration sheet fully in view.'),
  bulbs: () => t('gm.bulbs', 'No onions found. Point the camera at the tray.'),
})[g.id]();

export function Capture({ lotId, replay }: { lotId: string; replay: boolean }) {
  const [lot, setLot] = useState<LotRow | null>(null);
  const [settings, setSettings] = useState<Settings | null>(null);
  const [tray, setTray] = useState(1);
  const [look, setLook] = useState(1);
  const [phase, setPhase] = useState<Phase>('aim');
  const [gates, setGates] = useState<Gate[]>([]);
  const [hold, setHold] = useState(0);            // consecutive all-pass scans
  const [refusal, setRefusal] = useState('');
  const [noSheet, setNoSheet] = useState(replay);
  const [last, setLast] = useState<{ a: Analysis; url: string; id: string; blob: Blob } | null>(null);
  const [coinMode, setCoinMode] = useState(false);
  const [coinMm, setCoinMm] = useState(27);
  const [count, setCount] = useState(0);
  const [err, setErr] = useState('');
  const [sampleIdx, setSampleIdx] = useState(0);
  const video = useRef<HTMLVideoElement>(null);
  const tilt = useRef<number | null>(null);
  const loc = useRef<string | null>(null);
  const busy = useRef(false);
  const guard = useRef({ scans: 0, failed: 0, refused: 0, byGate: {} as Record<string, number> });

  useEffect(() => {
    db.lots.get(lotId).then((l) => setLot(l ?? null));
    loadSettings().then(setSettings);
    db.captures.where('lotId').equals(lotId).toArray().then((cs) => {
      setCount(cs.length);
      if (cs.length) { const m = cs.reduce((a, c) => (c.tray > a.tray || (c.tray === a.tray && c.look > a.look) ? c : a)); setTray(m.tray); setLook(m.look + 1); }
    });
  }, [lotId]);

  // Live camera + orientation + coarse location.
  useEffect(() => {
    if (replay) return;
    let stream: MediaStream | null = null;
    const onOri = (e: DeviceOrientationEvent) => { tilt.current = tiltFromOrientation(e.beta, e.gamma); };
    addEventListener('deviceorientation', onOri);
    navigator.mediaDevices?.getUserMedia({ video: { facingMode: { ideal: 'environment' }, width: { ideal: 1280 }, height: { ideal: 960 } }, audio: false })
      .then((s) => { stream = s; if (video.current) { video.current.srcObject = s; video.current.play().catch(() => {}); } })
      .catch(() => { setErr(t('cap.nocam', 'The camera could not be opened. Allow camera access for this site, or use Replay.')); setPhase('error'); });
    // Coarse location is optional. Inside the Android app it is never requested:
    // overlapping permission prompts crashed the native permission bridge.
    const native = !!(window as unknown as { Capacitor?: { isNativePlatform?: () => boolean } }).Capacitor?.isNativePlatform?.();
    if (!native) navigator.geolocation?.getCurrentPosition(
      (p) => { loc.current = `${p.coords.latitude.toFixed(2)},${p.coords.longitude.toFixed(2)}`; },
      () => { loc.current = null; }, { maximumAge: 600000, timeout: 8000, enableHighAccuracy: false });
    return () => { removeEventListener('deviceorientation', onOri); stream?.getTracks().forEach((tr) => tr.stop()); };
  }, [replay]);

  // Capture Guard loop.
  useEffect(() => {
    if (phase !== 'aim') return;
    let alive = true;
    const tick = async () => {
      if (!alive) return;
      try {
        let bmp: ImageBitmap | null = null;
        if (replay) {
          const img = document.getElementById('replay-img') as HTMLImageElement | null;
          if (img?.complete && img.naturalWidth) bmp = await createImageBitmap(img, { resizeWidth: 480, resizeQuality: 'medium' });
        } else if (video.current && video.current.readyState >= 2 && video.current.videoWidth) {
          bmp = await createImageBitmap(video.current, { resizeWidth: 480, resizeQuality: 'medium' });
        }
        if (bmp && busy.current) { bmp.close(); bmp = null; }
        if (bmp) {
          const s = await scanBitmap(bmp);
          const g = evaluateGates(s, { tiltDeg: replay ? 0 : tilt.current, targetFound: noSheet || s.target !== null, bulbs: s.bulbs });
          if (!alive) return;
          setGates(g);
          guard.current.scans++;
          const f = g.find((x) => !x.ok);
          if (f) { guard.current.failed++; guard.current.byGate[f.id] = (guard.current.byGate[f.id] ?? 0) + 1; }
          setHold((h) => (g.every((x) => x.ok) ? h + 1 : 0));
        }
      } catch { /* a dropped frame is fine */ }
      if (alive) setTimeout(tick, replay ? 500 : 450); // ~2 scans/s keeps cheap phones responsive
    };
    tick();
    return () => { alive = false; };
  }, [phase, replay, noSheet, sampleIdx]);

  // Auto-shutter: all gates green on 3 consecutive scans (~1 s steady).
  useEffect(() => { if (hold >= 3 && phase === 'aim' && !replay) shoot(); }, [hold]);

  const firstFail = gates.find((g) => !g.ok);

  async function shoot() {
    if (busy.current || !lot) return;
    // Refuse twice with the reason; the third tap takes it anyway and the capture records which check was overridden.
    let forced: string | undefined;
    if (firstFail && !replay) {
      if (guard.current.refused < 2) { guard.current.refused++; setRefusal(gateMsg(firstFail) + ' ' + t('cap.force', 'Tap again to take it anyway.')); return; }
      forced = firstFail.id;
    }
    busy.current = true;
    setRefusal('');
    setPhase('busy');
    try {
      let src: CanvasImageSource, w: number, h: number;
      if (replay) {
        const img = document.getElementById('replay-img') as HTMLImageElement;
        src = img; w = img.naturalWidth; h = img.naturalHeight;
      } else {
        const v = video.current!;
        src = await createImageBitmap(v); w = v.videoWidth; h = v.videoHeight;
      }
      const ev = await toEvidenceJpeg(src, w, h);
      const a = await analyzeBitmap(ev.bitmap, { camHmm: replay ? REPLAY_CAM_H : settings?.camHmm });
      const row: CaptureRow = {
        id: `${lotId}-t${tray}-l${look}-${Date.now().toString(36)}`, lotId, tray, look, at: new Date().toISOString(),
        mode: replay ? 'replay' : 'live', image: ev.blob, imageHash: await sha256Hex(new Uint8Array(await ev.blob.arrayBuffer())),
        width: a.width, height: a.height,
        calib: { tier: a.calib.tier, mmPerPx: a.calib.mmPerPx, camHmm: a.calib.camHmm, scaleSd: a.calib.scaleSd, note: a.calib.note },
        bulbs: a.bulbs, timings: a.timings, loc: loc.current,
        guard: { ...guard.current, forced },
      };
      guard.current = { scans: 0, failed: 0, refused: 0, byGate: {} as Record<string, number> };
      await db.captures.put(row);
      if (last) URL.revokeObjectURL(last.url);
      setLast({ a, url: URL.createObjectURL(ev.blob), id: row.id, blob: ev.blob });
      setCount((c) => c + 1);
      setPhase('review');
      if (navigator.vibrate) navigator.vibrate(30);
    } catch (e) {
      setErr(String(e)); setPhase('error');
    } finally { busy.current = false; setHold(0); }
  }

  /** Coin tier: re-measure the stored photo using a tapped coin of known diameter as the scale. */
  async function useCoin(x: number, y: number) {
    if (!last) return;
    setCoinMode(false);
    setPhase('busy');
    try {
      const a = await analyzeBitmap(await createImageBitmap(last.blob), { coin: { x, y, mm: coinMm } });
      if (a.calib.tier !== 'coin') { setRefusal(t('cap.coin.fail', 'Could not find a coin there. Tap the middle of the coin.')); setPhase('review'); return; }
      await db.captures.update(last.id, { bulbs: a.bulbs, calib: { tier: a.calib.tier, mmPerPx: a.calib.mmPerPx, camHmm: a.calib.camHmm, scaleSd: a.calib.scaleSd, note: a.calib.note }, timings: a.timings });
      setLast({ ...last, a });
      setRefusal('');
      setPhase('review');
    } catch (e) { setErr(String(e)); setPhase('error'); }
  }

  const nextLook = () => { setLook(look + 1); setPhase('aim'); if (replay) setSampleIdx((i) => i + 1); };
  const nextTray = () => { setTray(tray + 1); setLook(1); setPhase('aim'); if (replay) setSampleIdx((i) => i + 1); };
  const sample = SAMPLES[sampleIdx % SAMPLES.length];
  const used = last?.a.bulbs.filter((b) => !b.excluded).length ?? 0;
  const setAside = (last?.a.bulbs.length ?? 0) - used;

  return (
    <div class="cam">
      <div class="cam-top">
        <button class="iconbtn" aria-label={t('cap.close', 'Close camera')} onClick={() => back(count ? `lot/${lotId}` : '')}><X size={24} /></button>
        <span class="grow">{t('cap.tray', 'Tray')} {tray} · {t('cap.look', 'look')} {look} · {count} {t('cap.photos', 'photos')}</span>
      </div>
      <div class="cam-view">
        {replay
          ? <img id="replay-img" class="replay" src={`./samples/${sample.file}`} alt="" crossOrigin="anonymous" />
          : <video ref={video} playsInline muted autoPlay />}
        {replay && <span class="cam-badge">{t('cap.replay', 'REPLAY · stored photo')}</span>}
        {phase === 'aim' && <div class="frame" data-ok={firstFail ? '0' : '1'} />}
        {phase === 'busy' && <div class="busy"><div><div>{t('cap.measuring', 'Measuring…')}</div><div class="bar"><i /></div></div></div>}
        {phase === 'review' && last && (
          <div style={{ position: 'absolute', inset: 0, display: 'grid', placeItems: 'center', background: 'var(--color-cam)' }}>
            <Overlay url={last.url} w={last.a.width} h={last.a.height} bulbs={last.a.bulbs} onImageTap={coinMode ? useCoin : undefined} />
          </div>
        )}
      </div>

      <div class="cam-bottom">
        {phase === 'aim' && (
          <>
            <div class="gates" role="list">
              {(gates.length ? gates : evaluateGates({ sharp: 0, meanL: 50, clipped: 0 }, { tiltDeg: null, targetFound: false, bulbs: 0 }).map((g) => ({ ...g, ok: false }))).map((g) => (
                <div class="gate" role="listitem" key={g.id} data-ok={gates.length ? (g.ok ? '1' : '0') : undefined}><i />{GATE_LABEL[g.id]()}</div>
              ))}
            </div>
            <p class="cam-msg" aria-live="polite">{refusal || (gates.length ? (firstFail ? gateMsg(firstFail) : replay ? t('cap.ready.replay', 'Ready. Tap the shutter to measure this stored photo.') : t('cap.ready', 'Hold steady…')) : t('cap.start', 'Starting camera…'))}</p>
            <div class="cam-actions">
              <label class="cam-side" style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                <input type="checkbox" checked={noSheet} disabled={replay} onChange={(e) => setNoSheet((e.target as HTMLInputElement).checked)} />
                {t('cap.nosheet', 'No sheet (wide size error)')}
              </label>
              <button class="shutter" aria-label={t('cap.shoot', 'Measure')} onClick={shoot}>
                <span />
                <svg viewBox="0 0 84 84" aria-hidden="true"><circle cx="42" cy="42" r="40" fill="none" stroke="var(--color-ok)" stroke-width="4" stroke-dasharray={`${(Math.min(hold, 3) / 3) * 251} 251`} /></svg>
              </button>
              <span class="cam-side r">{replay ? `${sampleIdx % SAMPLES.length + 1}/${SAMPLES.length}` : t('cap.auto', 'auto-shutter')}</span>
            </div>
          </>
        )}
        {phase === 'review' && last && (
          <>
            <p class="cam-msg">
              {t('cap.measured', '{n} onions measured.', { n: used })}{setAside > 0 ? ' ' + t('cap.aside', '{n} set aside (cut off by the frame edge or not onion-shaped).', { n: setAside }) : ''}
              <br /><span class="mono xs">{t('cap.calib', 'Scale')}: {last.a.calib.tier} · {Math.round(last.a.timings.total ?? 0)} ms</span>
              {refusal && <><br />{refusal}</>}
            </p>
            {last.a.calib.tier === 'intrinsics' && !coinMode && !replay && (
              <div class="row">
                <select class="select" style={{ flex: 1, minHeight: 44, background: 'var(--color-cam-2)', color: 'var(--color-cam-ink)', borderColor: 'var(--color-cam-2)' }} value={coinMm} onChange={(e) => setCoinMm(parseFloat((e.target as HTMLSelectElement).value))} aria-label={t('cap.coin.which', 'Which coin')}>
                  {[[27, '₹10 · 27 mm'], [25, '₹5 · 25 mm'], [23, '₹2 · 23 mm'], [20, '₹1 · 20 mm']].map(([mm, l]) => <option key={mm} value={mm}>{l}</option>)}
                </select>
                <button class="btn small" onClick={() => setCoinMode(true)}>{t('cap.coin', 'Use a coin for scale')}</button>
              </div>
            )}
            {coinMode && <p class="cam-msg">{t('cap.coin.tap', 'Tap the coin in the photo.')}</p>}
            <div class={replay ? '' : 'grid2'}>
              {!replay && <button class="btn" onClick={nextLook}><RefreshCw size={18} aria-hidden="true" />{t('cap.shake', 'Shake, look again')}</button>}
              <button class="btn" style={{ width: '100%' }} onClick={nextTray}><ArrowRight size={18} aria-hidden="true" />{replay ? t('cap.nextphoto', 'Next stored photo (new tray)') : t('cap.nexttray', 'Next tray')}</button>
            </div>
            <button class="btn primary block" onClick={() => back(`lot/${lotId}`)}><Check size={20} aria-hidden="true" />{t('cap.finish', 'Finish and grade')}</button>
          </>
        )}
        {phase === 'error' && (
          <>
            <p class="cam-msg">{err}</p>
            <button class="btn primary block" onClick={() => go(`capture/${lotId}?replay=1`)}>{t('cap.toreplay', 'Use Replay instead')}</button>
          </>
        )}
      </div>
    </div>
  );
}
