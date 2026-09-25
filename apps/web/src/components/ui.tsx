import type { ComponentChildren } from 'preact';
import { useEffect, useState } from 'preact/hooks';
import { ChevronLeft, WifiOff, Wifi } from 'lucide-preact';
import type { Bucket, ShareEstimate, SprtDecision } from '@parakh/core';
import { t } from '../lib/i18n';
import { back } from '../lib/router';

export const BUCKET_LETTER: Record<Bucket, string> = { GRADE_A: 'A', URS: 'U', REJECT: 'R', REFER: '?' };
export const bucketName = (b: Bucket) =>
  ({ GRADE_A: t('b.a', 'Grade A'), URS: t('b.u', 'URS'), REJECT: t('b.r', 'Reject'), REFER: t('b.q', 'Needs human check') })[b];

export function Letter({ b }: { b: Bucket }) {
  return <span class="b-letter" data-b={b} aria-hidden="true">{BUCKET_LETTER[b]}</span>;
}
export function Pill({ b }: { b: Bucket }) {
  return <span class="b-pill" data-b={b}><Letter b={b} />{bucketName(b)}</span>;
}

export function useOnline() {
  const [on, setOn] = useState(navigator.onLine);
  useEffect(() => {
    const f = () => setOn(navigator.onLine);
    addEventListener('online', f); addEventListener('offline', f);
    return () => { removeEventListener('online', f); removeEventListener('offline', f); };
  }, []);
  return on;
}

export function OnlineChip() {
  const online = useOnline();
  return (
    <span class="status" data-off={online ? '0' : '1'} title={online ? t('st.on.t', 'Online — nothing needs the network') : t('st.off.t', 'Offline — everything still works')}>
      {online ? <Wifi size={13} aria-hidden="true" /> : <WifiOff size={13} aria-hidden="true" />}
      {online ? t('st.on', 'online') : t('st.off', 'offline')}
    </span>
  );
}

/**
 * Screen header. With `backTo` it shows a back arrow that always returns to that
 * parent screen; without it, it is a tab-root header (large title, no arrow).
 */
export function TopBar({ title, backTo, right, subtitle }: { title?: string; backTo?: string; right?: ComponentChildren; subtitle?: string }) {
  if (backTo === undefined) {
    return (
      <header class="topbar root">
        <div class="grow">
          {title ? <h1 class="root-title">{title}</h1> : <a class="wordmark" href="#/"><i />parakh</a>}
          {subtitle && <p class="root-sub">{subtitle}</p>}
        </div>
        {right}
        <OnlineChip />
      </header>
    );
  }
  return (
    <header class="topbar">
      <button class="iconbtn" onClick={() => back(backTo)} aria-label={t('nav.back', 'Back')}><ChevronLeft size={26} /></button>
      <div class="grow"><h1>{title}</h1></div>
      {right}
      <OnlineChip />
    </header>
  );
}

const pctf = (x: number) => x.toFixed(1);

/** Horizontal interval: a range bar and the point estimate, on a 0-100 % axis. */
export function Interval({ e, b }: { e: ShareEstimate; b: Bucket }) {
  return (
    <div class="ci" data-b={b} aria-hidden="true">
      <span class="rng" style={{ left: `${e.ci[0]}%`, width: `${Math.max(0.8, e.ci[1] - e.ci[0])}%` }} />
      <span class="pt" style={{ left: `calc(${e.est}% - 1px)` }} />
    </div>
  );
}

export function Mix({ view, bayes }: { view: Record<Bucket, ShareEstimate>; bayes?: boolean }) {
  const order: Bucket[] = ['GRADE_A', 'URS', 'REJECT', 'REFER'];
  return (
    <div class="mix">
      <div class="mixbar" role="img" aria-label={order.map((b) => `${bucketName(b)} ${pctf(view[b].est)}%`).join(', ')}>
        {order.map((b) => <span key={b} data-b={b} style={{ flexBasis: `${view[b].est}%` }} />)}
      </div>
      {order.map((b) => {
        const e = view[b];
        const ci = bayes ? e.bayes : e.ci;
        return (
          <div class="mixrow" key={b}>
            <Letter b={b} />
            <span class="lbl">{bucketName(b)}</span>
            <span class="val"><b>{pctf(e.est)}%</b><small>{pctf(ci[0])} – {pctf(ci[1])}</small></span>
            <Interval e={{ ...e, ci }} b={b} />
          </div>
        );
      })}
    </div>
  );
}

export const decisionTitle = (d: SprtDecision) =>
  ({
    ACCEPT_LOT: t('d.accept', 'Accept lot'),
    REJECT_LOT: t('d.reject', 'Reject lot'),
    SAMPLE_MORE: t('d.more', 'Sample more'),
    REFER_TO_HUMAN: t('d.refer', 'Needs human check'),
  })[d];

export function Sheet({ onClose, children, label }: { onClose: () => void; children: ComponentChildren; label: string }) {
  useEffect(() => {
    const k = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    addEventListener('keydown', k);
    return () => removeEventListener('keydown', k);
  }, [onClose]);
  return (
    <>
      <div class="scrim" onClick={onClose} />
      <section class="sheet" role="dialog" aria-modal="true" aria-label={label}>
        <div class="grab" />
        {children}
      </section>
    </>
  );
}

let toastSet: ((s: string | null) => void) | null = null;
export function toast(s: string) { toastSet?.(s); }
export function ToastHost() {
  const [msg, setMsg] = useState<string | null>(null);
  useEffect(() => { toastSet = setMsg; return () => { toastSet = null; }; }, []);
  useEffect(() => { if (!msg) return; const id = setTimeout(() => setMsg(null), 2600); return () => clearTimeout(id); }, [msg]);
  return msg ? <div class="toast" role="status">{msg}</div> : null;
}

const MEASURE: Record<string, () => string> = {
  SIZE: () => t('m.size', 'Size'), BLACKENING: () => t('m.black', 'Blackening'), ROT: () => t('m.rot', 'Rot / wet lesion'),
  SUNBURN: () => t('m.sun', 'Sunburn'), SPOTS: () => t('m.spots', 'Spots / discolouration'), SPROUTING: () => t('m.sprout', 'Sprouting'),
  PEELED: () => t('m.peel', 'Peeled skin'), CUT: () => t('m.cut', 'Cuts / damage'), DOUBLE: () => t('m.double', 'Double bulb'),
  BOTTLENECK: () => t('m.bottle', 'Bottleneck'), SPLIT: () => t('m.split', 'Split'),
};
const unit = (s: string) => s.replace(/PCT$/, '%').replace(/MM$/, ' mm');

/** Machine reason code -> one plain sentence. The code itself is shown beside it. */
export function humanReason(code: string): string {
  let m = code.match(/^LOW_CONFIDENCE_(\d+)_LT_(\d+)$/);
  if (m) return t('r.conf', 'The picture of this bulb is unclear (confidence {a}‰, needs {b}‰).', { a: m[1], b: m[2] });
  m = code.match(/^NOT_ASSESSED_(\w+)$/);
  if (m) return t('r.na', '{m} is not measured by this model version.', { m: (MEASURE[m[1]] ?? (() => m![1]))() });
  const border = code.startsWith('BORDERLINE_');
  m = code.replace(/^BORDERLINE_/, '').match(/^([A-Z]+)_([\d.]+(?:PCT|MM)|YES|NO)_(GT|GE|LT|LE|NE)_([\d.]+(?:PCT|MM)|YES|NO)$/);
  if (!m) return code;
  const [, meas, v, op, lim] = m;
  const name = (MEASURE[meas] ?? (() => meas))();
  if (v === 'YES' || v === 'NO') return t('r.shape', '{m} detected.', { m: name });
  if (border) return t('r.border', '{m} {v} is within measuring error of the {l} limit.', { m: name, v: unit(v), l: unit(lim) });
  return op === 'GT' || op === 'GE'
    ? t('r.gt', '{m} {v} — above the {l} limit.', { m: name, v: unit(v), l: unit(lim) })
    : t('r.lt', '{m} {v} — below the {l} limit.', { m: name, v: unit(v), l: unit(lim) });
}
