import type { CertRow } from './db';
import { qrMatrix } from './qr';
import { t } from './i18n';

/** A 1080×1350 image of the receipt, for WhatsApp. Drawn on canvas with the app's own fonts. */
export async function shareImage(c: CertRow, fp: string) {
  await document.fonts.ready;
  const W = 1080, H = 1350;
  const cv = document.createElement('canvas');
  cv.width = W; cv.height = H;
  const g = cv.getContext('2d')!;
  const css = getComputedStyle(document.documentElement);
  const col = (v: string) => css.getPropertyValue(v).trim() || '#222';
  const k = c.signed.core, h = k.headline;
  g.fillStyle = col('--color-paper'); g.fillRect(0, 0, W, H);
  g.fillStyle = col('--color-ink');
  g.font = '600 64px "IBM Plex Sans Condensed"'; g.fillText(t('cert.h', 'Onion lot quality receipt'), 72, 132);
  g.font = '400 30px "IBM Plex Mono"'; g.fillStyle = col('--color-muted');
  g.fillText(`${k.lot.id} · rev ${k.rev} · ${k.lot.farmerRef}`.slice(0, 60), 72, 184);
  g.fillStyle = col('--color-r'); g.font = '600 24px "IBM Plex Mono"';
  g.fillText(t('cert.proto', 'PROTOTYPE · NOT AN OFFICIAL DOCUMENT') + (k.capture.mode === 'replay' ? ' · REPLAY' : ''), 72, 232);
  g.fillStyle = col('--color-ink'); g.font = '600 120px "IBM Plex Sans Condensed"';
  g.fillText(`${h.procured.toFixed(1)}%`, 72, 390);
  g.font = '500 34px "IBM Plex Sans"'; g.fillText(t('cert.proc', 'Procurable by weight'), 72, 440);
  g.font = '400 30px "IBM Plex Mono"'; g.fillStyle = col('--color-muted');
  g.fillText(`95% ${h.procured_ci[0].toFixed(1)}–${h.procured_ci[1].toFixed(1)} · ${k.pack.id}`.slice(0, 60), 72, 488);
  const segs: [string, number][] = [['--color-a', h.gradeA], ['--color-u', h.urs], ['--color-r', h.reject], ['--color-q', h.refer]];
  let x = 72;
  for (const [cc, v] of segs) { const w = ((W - 144) * v) / 100; g.fillStyle = col(cc); g.fillRect(x, 530, w, 40); x += w; }
  g.font = '500 30px "IBM Plex Mono"'; g.fillStyle = col('--color-ink');
  g.fillText(`A ${h.gradeA.toFixed(1)}%   URS ${h.urs.toFixed(1)}%   R ${h.reject.toFixed(1)}%   ? ${h.refer.toFixed(1)}%`, 72, 620);
  if (c.qr) {
    const m = qrMatrix(c.qr), n = m.length + 8, size = 560, s = size / n, qx = (W - size) / 2, qy = 670;
    g.fillStyle = '#fbf9f5'; g.fillRect(qx, qy, size, size);
    g.fillStyle = col('--color-ink');
    m.forEach((row, yy) => row.forEach((on, xx) => { if (on) g.fillRect(qx + (xx + 4) * s, qy + (yy + 4) * s, Math.ceil(s), Math.ceil(s)); }));
  }
  g.fillStyle = col('--color-accent'); g.font = '600 26px "IBM Plex Mono"';
  g.fillText(`${t('cert.signed', 'Signed on device')} · ${c.signed.sig.alg} · ${fp}`, 72, 1290);
  const blob: Blob = await new Promise((r) => cv.toBlob((b) => r(b!), 'image/png'));
  const file = new File([blob], `${k.lot.id}-rev${k.rev}.png`, { type: 'image/png' });
  const nav = navigator as Navigator & { canShare?: (d: object) => boolean };
  if (nav.canShare?.({ files: [file] })) { await navigator.share({ files: [file], title: k.lot.id }); return; }
  const a = document.createElement('a');
  a.href = URL.createObjectURL(file); a.download = file.name; a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 2000);
}
