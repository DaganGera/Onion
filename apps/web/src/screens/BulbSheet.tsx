import { can, currentUser, useSession, who } from '../lib/auth';
import { useMemo, useState } from 'preact/hooks';
import { DEFECTS, OVERRIDE_REASONS, sizeOf, type Bucket, type BulbVerdict, type Defect } from '@parakh/core';
import { db } from '../lib/db';
import { t } from '../lib/i18n';
import { addOverride, type Graded } from '../lib/lots';
import { bucketName, humanReason, Pill, Sheet } from '../components/ui';
import { DEFECT_COLOUR, MaskCrop } from '../components/Overlay';
import { CODE } from '@parakh/vision';

const DEF_CODE: Record<Exclude<Defect, 'cut'>, number> = { blackening: CODE.blackening, rot: CODE.rot, sunburn: CODE.sunburn, spots: CODE.spots, sprouting: CODE.sprouting, peeled: CODE.peeled };
const DEF_NAME: Record<Defect, () => string> = {
  blackening: () => t('m.black', 'Blackening'), rot: () => t('m.rot', 'Rot / wet lesion'), sunburn: () => t('m.sun', 'Sunburn'),
  spots: () => t('m.spots', 'Spots / discolouration'), sprouting: () => t('m.sprout', 'Sprouting'), peeled: () => t('m.peel', 'Peeled skin'), cut: () => t('m.cut', 'Cuts / damage'),
};
const REASON_TEXT: Record<string, () => string> = {
  MASK_WRONG_BACKGROUND: () => t('or.bg', 'Outline includes background'),
  MASK_MISSED_DEFECT: () => t('or.missed', 'A defect was missed'),
  DEFECT_IS_SOIL_OR_SHADOW: () => t('or.soil', 'Marked area is soil or shadow'),
  SIZE_MEASURED_WRONG: () => t('or.size', 'Size is wrong (checked with ring or caliper)'),
  TWO_BULBS_MERGED: () => t('or.merged', 'Two bulbs were merged'),
  NOT_AN_ONION: () => t('or.notonion', 'Not an onion'),
  VISUAL_REINSPECTION: () => t('or.visual', 'Re-inspected by hand'),
};

export function BulbSheet({ g, refIdx, url, ai, onClose, onChanged }: { g: Graded; refIdx: number; url: string; ai: BulbVerdict; onClose: () => void; onChanged: () => void }) {
  const ref = g.refs[refIdx];
  const m = g.bulbs[refIdx];
  const cap = g.captures.find((c) => c.id === ref.captureId)!;
  const bulb = cap.bulbs.find((b) => b.idx === ref.idx)!;
  const me = useSession();
  const [mask, setMask] = useState(true);
  const [mode, setMode] = useState<'view' | 'officer' | 'farmer'>('view');
  const [to, setTo] = useState<Bucket>('GRADE_A');
  const [reason, setReason] = useState<string>(OVERRIDE_REASONS[0]);
  const history = g.lot.overrides.filter((o) => o.bulb === m.id);
  const last = history[history.length - 1];
  const final: Bucket = last ? (last.kind === 'contest' ? 'REFER' : last.to ?? ai.bucket) : ai.bucket;

  // Limits from the pack, for the little markers on each fraction bar.
  const limits = useMemo(() => {
    const l: Partial<Record<Defect, number>> = {};
    for (const b of [...g.pack.buckets].reverse()) for (const r of b.rules) if (r.m in DEF_CODE || r.m === 'cut') l[r.m as Defect] = r.v;
    for (const r of g.pack.reject_rules) if (l[r.m as Defect] === undefined) l[r.m as Defect] = r.v;
    return l;
  }, [g.pack]);
  const size = sizeOf(m, g.pack);

  const save = async (kind: 'override' | 'contest') => {
    const o = { bulb: m.id, by: kind === 'override' ? 'officer' as const : 'farmer' as const, kind, to: kind === 'override' ? to : undefined, reason, at: new Date().toISOString(), ...(currentUser() ? { user: currentUser()!.id } : {}) };
    await addOverride(g.lot.id, o);
    // Data engine: every human correction is kept as a labelled example for retraining.
    await db.corrections.add({ lotId: g.lot.id, bulbId: m.id, captureId: cap.id, bulbIdx: bulb.idx, from: ai.bucket, to: o.to ?? 'REFER', reason, at: o.at });
    onChanged();
  };

  return (
    <Sheet onClose={onClose} label={t('bs.label', 'Bulb {id}', { id: m.id })}>
      <div class="section-head">
        <h2 style={{ fontSize: 'var(--text-lg)' }}>{t('bs.title', 'Bulb {id}', { id: m.id })} <span class="mono xs muted">{t('cap.tray', 'Tray')} {m.tray} · {t('cap.look', 'look')} {m.look}</span></h2>
        <Pill b={final} />
      </div>
      <MaskCrop url={url} bulb={bulb} showMask={mask} />
      <label class="row small"><input type="checkbox" checked={mask} onChange={(e) => setMask((e.target as HTMLInputElement).checked)} />{t('bs.mask', 'Show defect mask')}</label>

      <section class="section" data-b={ai.bucket}>
        <h3 class="small" style={{ fontFamily: 'var(--font-body)' }}>{t('bs.why', 'Why: AI verdict {b}', { b: bucketName(ai.bucket) })}</h3>
        {ai.codes.length === 0 && <p class="small">{t('bs.clean', 'Within every limit of the first bucket in this rule pack.')}</p>}
        <ul class="reasons">
          {[...ai.codes, ...ai.notes].map((c) => <li key={c}><span>{humanReason(c)}<code>{c}</code></span></li>)}
        </ul>
      </section>

      <section class="section">
        <dl class="kv">
          <dt>{t('bs.size', 'Size ({metric})', { metric: g.pack.size_metric.replace('_', ' ') })}</dt><dd>{(size.v / 10).toFixed(1)} ± {(size.sd / 10).toFixed(1)} mm</dd>
          <dt>{t('bs.feret', 'Min / max Feret')}</dt><dd>{(m.size.min / 10).toFixed(1)} / {(m.size.max / 10).toFixed(1)} mm</dd>
          <dt>{t('bs.weight', 'Estimated weight')}</dt><dd>{(m.w / 10).toFixed(0)} ± {(m.wsd / 10).toFixed(0)} g</dd>
          <dt>{t('bs.conf', 'Picture confidence')}</dt><dd>{(m.conf / 10).toFixed(0)}%</dd>
          <dt>{t('bs.shape', 'Shape flags')}</dt><dd>{Object.entries(m.shape).filter(([, v]) => v).map(([k]) => k).join(', ') || '—'}</dd>
          {bulb.p1 !== undefined && <><dt>{t('bs.t1', 'Learned cross-check (Tier 1)')}</dt><dd>{t('bs.t1v', '{p}% unhealthy', { p: Math.round(bulb.p1 * 100) })}</dd></>}
        </dl>
        {bulb.gated && <p class="note">{t('bs.gated', 'The learned check rates this bulb healthy, so colour marks from light and natural skin streaks were cleared.')}</p>}
        {bulb.disagree && <p class="banner warn">{t('bs.disagree', 'The learned model thinks this bulb is unhealthy, but the colour model found no rot or blackening. It goes to a person.')}</p>}
        <div class="fracs">
          {DEFECTS.map((d) => {
            const v = m.frac[d];
            const lim = limits[d];
            const col = d === 'cut' ? 'var(--color-rule)' : DEFECT_COLOUR[DEF_CODE[d as Exclude<Defect, 'cut'>]];
            return (
              <div class="frac" key={d}>
                <span><i class="swatch" style={{ ['--sw' as string]: col }} />{DEF_NAME[d]()}</span>
                <span class="bar" style={{ ['--sw' as string]: col }}>
                  {v !== null && <i style={{ width: `${Math.min(100, v / 10)}%` }} />}
                  {lim !== undefined && <s style={{ left: `${Math.min(100, lim / 10)}%` }} title={`${t('bs.limit', 'limit')} ${lim / 10}%`} />}
                </span>
                <span class="v">{v === null ? t('bs.na', 'n/a') : `${(v / 10).toFixed(1)}%`}</span>
              </div>
            );
          })}
        </div>
        <p class="note">{t('bs.frac.n', 'Area fractions of the visible surface, corrected for the curve of the bulb. Black ticks mark the nearest limit in this rule pack.')}</p>
      </section>

      {history.length > 0 && (
        <ul class="reasons">
          {history.map((o, i) => <li key={i}><span>{o.by === 'officer' ? t('who.officer', 'Officer') : t('who.farmer', 'Farmer')}: {o.kind === 'override' ? `→ ${bucketName(o.to!)}` : t('bs.contest', 'contested')}<code>{o.reason}{o.user ? ` · ${o.user}` : ''}</code></span></li>)}
        </ul>
      )}

      {mode === 'view' && (
        <div class="grid2">
          {can(me, 'bulb.override') && <button class="btn quiet" onClick={() => setMode('officer')}>{t('bs.override', 'Officer: change')}</button>}
          {can(me, 'bulb.contest') && <button class="btn quiet" onClick={() => setMode('farmer')}>{t('bs.contestbtn', 'Farmer: contest')}</button>}
        </div>
      )}
      {mode !== 'view' && (
        <section class="card tint section">
          {mode === 'officer' && (
            <div class="field">
              <span>{t('bs.to', 'New verdict')}</span>
              <div class="seg" role="group">
                {(['GRADE_A', 'URS', 'REJECT'] as Bucket[]).map((b) => <button key={b} aria-pressed={to === b} onClick={() => setTo(b)}>{bucketName(b)}</button>)}
              </div>
            </div>
          )}
          <label class="field">
            <span>{t('bs.reason', 'Reason')}</span>
            <select class="select" value={reason} onChange={(e) => setReason((e.target as HTMLSelectElement).value)}>
              {OVERRIDE_REASONS.map((r) => <option key={r} value={r}>{REASON_TEXT[r]()}</option>)}
            </select>
          </label>
          <p class="note">{mode === 'officer'
            ? t('bs.o.n', 'The AI verdict stays on record. Your change is added beside it and needs a new signed revision.')
            : t('bs.f.n', 'A contest moves this bulb to “needs human check” until an officer decides. Both steps stay on the record.')}</p>
          <div class="row">
            <button class="btn quiet" onClick={() => setMode('view')}>{t('cancel', 'Cancel')}</button>
            <button class="btn primary" onClick={() => save(mode === 'officer' ? 'override' : 'contest')}>{mode === 'officer' ? t('bs.save', 'Record change') : t('bs.savec', 'Record contest')}</button>
          </div>
        </section>
      )}
    </Sheet>
  );
}
