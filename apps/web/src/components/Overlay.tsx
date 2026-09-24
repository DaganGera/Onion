import { useEffect, useRef } from 'preact/hooks';
import type { Bucket } from '@parakh/core';
import { CODE, type BulbResult } from '@parakh/vision';
import { BUCKET_LETTER } from './ui';

const STROKE: Record<Bucket | 'none', string> = {
  GRADE_A: 'var(--color-a)', URS: 'var(--color-u)', REJECT: 'var(--color-r)', REFER: 'oklch(80% 0.02 240)', none: 'oklch(94% 0.008 75)',
};

/** Photo with each bulb's outline, coloured by its verdict, tappable. */
export function Overlay({ url, w, h, bulbs, verdict, onTap, selected, caption }: {
  url: string; w: number; h: number; bulbs: BulbResult[];
  verdict?: (idx: number) => Bucket | undefined; onTap?: (idx: number) => void; selected?: number; caption?: string;
}) {
  return (
    <figure class="shot" style={{ margin: 0, aspectRatio: `${w} / ${h}`, width: '100%', maxHeight: '100%' }}>
      <img src={url} alt="" width={w} height={h} />
      <svg viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none">
        {bulbs.map((b) => {
          const v = b.excluded ? undefined : verdict?.(b.idx);
          const pts = b.hull.map((p) => `${p.x},${p.y}`).join(' ');
          const col = STROKE[v ?? 'none'];
          return (
            <g key={b.idx}>
              <polygon class={'poly' + (b.excluded ? ' x' : '')} points={pts} stroke={col}
                style={{ strokeWidth: selected === b.idx ? 4 : undefined, fill: selected === b.idx ? 'oklch(94% 0.008 75 / 0.18)' : undefined }}
                onClick={b.excluded || !onTap ? undefined : () => onTap(b.idx)}>
                <title>{b.excluded ? 'set aside' : v ?? ''}</title>
              </polygon>
              {v && (
                <>
                  <rect x={b.centroid.x - 9} y={b.centroid.y - 9} width={18} height={18} rx={4} fill={col} style={{ pointerEvents: 'none' }} />
                  <text class="tag" x={b.centroid.x} y={b.centroid.y + 4} text-anchor="middle" fill="var(--color-on-ink)">{BUCKET_LETTER[v]}</text>
                </>
              )}
            </g>
          );
        })}
      </svg>
      {caption && <figcaption>{caption}</figcaption>}
    </figure>
  );
}

export const DEFECT_COLOUR: Record<number, string> = {
  [CODE.blackening]: 'oklch(22% 0.02 280)',
  [CODE.rot]: 'oklch(52% 0.13 50)',
  [CODE.sunburn]: 'oklch(88% 0.16 100)',
  [CODE.spots]: 'oklch(65% 0.14 230)',
  [CODE.sprouting]: 'oklch(70% 0.2 145)',
  [CODE.peeled]: 'oklch(70% 0.18 340)',
};
const RGB: Record<number, [number, number, number]> = {
  [CODE.blackening]: [20, 16, 40], [CODE.rot]: [168, 86, 25], [CODE.sunburn]: [240, 220, 60],
  [CODE.spots]: [40, 150, 230], [CODE.sprouting]: [60, 200, 90], [CODE.peeled]: [230, 80, 180],
};

/** One bulb, cropped, with its defect mask painted over it (the evidence behind the verdict). */
export function MaskCrop({ url, bulb, showMask }: { url: string; bulb: BulbResult; showMask: boolean }) {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const img = new Image();
    img.onload = () => {
      const c = ref.current;
      if (!c) return;
      const L = bulb.labels, pad = 6;
      const x0 = Math.max(0, L.x0 - pad), y0 = Math.max(0, L.y0 - pad);
      const cw = Math.min(img.naturalWidth - x0, L.w + 2 * pad), ch = Math.min(img.naturalHeight - y0, L.h + 2 * pad);
      c.width = cw; c.height = ch;
      const g = c.getContext('2d')!;
      g.drawImage(img, x0, y0, cw, ch, 0, 0, cw, ch);
      if (showMask) {
        const d = g.getImageData(0, 0, cw, ch);
        for (let y = 0; y < L.h; y++) for (let x = 0; x < L.w; x++) {
          const code = L.data[y * L.w + x];
          const rgb = RGB[code];
          const X = x + L.x0 - x0, Y = y + L.y0 - y0;
          if (X < 0 || Y < 0 || X >= cw || Y >= ch) continue;
          const o = (Y * cw + X) * 4;
          if (rgb) { d.data[o] = d.data[o] * 0.35 + rgb[0] * 0.65; d.data[o + 1] = d.data[o + 1] * 0.35 + rgb[1] * 0.65; d.data[o + 2] = d.data[o + 2] * 0.35 + rgb[2] * 0.65; }
          else if (code === CODE.bg) { d.data[o] *= 0.4; d.data[o + 1] *= 0.4; d.data[o + 2] *= 0.4; }
        }
        g.putImageData(d, 0, 0);
      }
    };
    img.src = url;
  }, [url, bulb, showMask]);
  return <canvas ref={ref} style={{ width: '100%', maxHeight: '42dvh', objectFit: 'contain', borderRadius: 'var(--radius-md)', background: 'var(--color-cam)' }} />;
}
