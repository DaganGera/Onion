import { useEffect, useRef, useState } from 'react';

/**
 * Background slideshow with the brief's FadingVideo timing: rAF-driven opacity
 * fades (500 ms) that resume from the current opacity, no CSS transitions.
 * Each real photo holds for `holdMs`, drifts slowly (Ken Burns), then crossfades.
 */
const FADE_MS = 500;

export function FadingImages({ srcs, holdMs = 4200, className }: { srcs: string[]; holdMs?: number; className?: string }) {
  const refs = useRef<(HTMLImageElement | null)[]>([]);
  const rafs = useRef<Map<number, number>>(new Map());
  const [, force] = useState(0);

  useEffect(() => {
    const fadeTo = (i: number, target: number, duration = FADE_MS) => {
      const img = refs.current[i];
      if (!img) return;
      cancelAnimationFrame(rafs.current.get(i) ?? 0);
      const from = parseFloat(img.style.opacity || '0');
      const t0 = performance.now();
      const step = (now: number) => {
        const k = Math.min(1, (now - t0) / duration);
        img.style.opacity = String(from + (target - from) * k);
        if (k < 1) rafs.current.set(i, requestAnimationFrame(step));
      };
      rafs.current.set(i, requestAnimationFrame(step));
    };
    let cur = 0;
    refs.current.forEach((img, i) => { if (img) img.style.opacity = i === 0 ? '0' : '0'; });
    fadeTo(0, 1);
    const id = setInterval(() => {
      const next = (cur + 1) % srcs.length;
      fadeTo(cur, 0);
      fadeTo(next, 1);
      const img = refs.current[next];
      if (img) { img.style.animation = 'none'; void img.offsetWidth; img.style.animation = ''; }
      cur = next;
    }, holdMs);
    force(1);
    return () => { clearInterval(id); rafs.current.forEach((r) => cancelAnimationFrame(r)); };
  }, [srcs, holdMs]);

  return (
    <div className={className} aria-hidden="true">
      <style>{'@keyframes kb { from { transform: scale(1.08) translate(0,0); } to { transform: scale(1.18) translate(-2%, -2%); } }'}</style>
      {srcs.map((s, i) => (
        <img key={s} ref={(el) => { refs.current[i] = el; }} src={s} alt="" className="absolute inset-0 h-full w-full object-cover"
          style={{ opacity: 0, animation: `kb ${(holdMs + FADE_MS * 2) / 1000}s ease-out both` }} />
      ))}
    </div>
  );
}
