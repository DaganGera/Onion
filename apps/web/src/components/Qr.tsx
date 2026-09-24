import { useMemo } from 'preact/hooks';
import { qrMatrix, qrPath } from '../lib/qr';

export function Qr({ text, label }: { text: string; label: string }) {
  const m = useMemo(() => { try { return qrMatrix(text); } catch { return null; } }, [text]);
  if (!m) return <p class="note">This lot is too large for one QR code. Share the evidence bundle file instead.</p>;
  const n = m.length + 8;
  return (
    <svg viewBox={`0 0 ${n} ${n}`} role="img" aria-label={label} shape-rendering="crispEdges">
      <rect width={n} height={n} fill="oklch(99% 0.004 75)" />
      <path d={qrPath(m)} fill="oklch(18% 0.015 40)" />
    </svg>
  );
}
