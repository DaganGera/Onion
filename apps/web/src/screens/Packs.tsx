import { useEffect, useState } from 'preact/hooks';
import { gradeLot, packHash, PACKS, resultSeed, type CertCore, type LotResult } from '@parakh/core';
import { db, type LotRow } from '../lib/db';
import { t } from '../lib/i18n';
import { go } from '../lib/router';
import { lotMeasurements } from '../lib/lots';
import { decisionTitle, toast, TopBar } from '../components/ui';

const SOURCES: Record<string, string> = {
  S1: 'Free Press Journal, 4 Jun 2026', S2: 'The Hitavada, 8 Jun 2026', S3: 'ETV Bharat / Business Standard, 7 Jun 2026',
  S4: 'Free Press Journal, 3 Aug 2026', S5: 'Indian Express (via SuperKalam), 15 May 2026',
};

export function Packs({ lotId }: { lotId?: string }) {
  const [hashes, setHashes] = useState<Record<string, string>>({});
  const [lots, setLots] = useState<LotRow[]>([]);
  const [sel, setSel] = useState(lotId ?? '');
  const [rows, setRows] = useState<{ id: string; r: LotResult }[] | null>(null);
  const [open, setOpen] = useState<string | null>(null);

  useEffect(() => {
    Promise.all(PACKS.map(async (p) => [p.id, await packHash(p)] as const)).then((xs) => setHashes(Object.fromEntries(xs)));
    db.lots.orderBy('createdAt').reverse().toArray().then((ls) => { setLots(ls); if (!sel && ls[0]) setSel(ls[0].id); });
  }, []);
  useEffect(() => {
    if (!sel) return;
    (async () => {
      const lot = await db.lots.get(sel);
      if (!lot) return;
      const { bulbs } = await lotMeasurements(sel);
      const seed = await resultSeed({ lot: { id: lot.id } as CertCore['lot'], sampling: lot.sampling ? { seed: lot.sampling.seed, draws: '' } : null });
      setRows(PACKS.map((p) => ({ id: p.id, r: gradeLot(bulbs, p, lot.overrides, seed) })));
    })();
  }, [sel]);
  const lot = lots.find((l) => l.id === sel);

  const adopt = async (packId: string) => {
    await db.lots.update(sel, { packId });
    toast(t('pk.adopted', 'Lot now graded under this pack. Sign a new revision to issue it.'));
    go(`lot/${sel}`);
  };

  return (
    <>
      <TopBar title={t('pk.title', 'Rule packs')} />
      <main class="page">
        <p class="small muted">{t('pk.intro', 'A rule pack is the rulebook: size window, defect limits, which buckets are bought. Packs are versioned and hashed. The same stored measurements can be re-graded under any pack, and each result can be verified on its own.')}</p>
        <div class="banner warn"><span>{t('pk.warn', 'No official circular was found. Every pack here is built from press reports and marked so. Unknown limits are marked as assumptions in the pack notes.')}</span></div>

        <ol class="timeline">
          {PACKS.map((p) => (
            <li key={p.id} aria-current={lot?.packId === p.id ? 'true' : undefined}>
              <span class="dot" />
              <div class="section" style={{ gap: 4 }}>
                <span class="when">{p.effective_from}{p.effective_to ? ` → ${p.effective_to}` : ' →'}</span>
                <b>{p.short}</b>
                <span class="row wrap" style={{ gap: 6 }}>
                  <span class={'chip ' + (p.status === 'press-report' ? 'press' : p.status === 'assumed' ? 'assumed' : '')}>{p.status}</span>
                  <span class="chip mono">{(hashes[p.id] ?? '').slice(0, 12)}</span>
                  {lot?.packId === p.id && <span class="chip accent">{t('pk.current', 'this lot')}</span>}
                </span>
                <button class="linkbtn small" style={{ alignSelf: 'flex-start' }} onClick={() => setOpen(open === p.id ? null : p.id)}>{open === p.id ? t('pk.hide', 'Hide rules') : t('pk.show', 'Show rules and sources')}</button>
                {open === p.id && (
                  <div class="card tint section small">
                    <p>{p.title}</p>
                    {p.buckets.map((b) => (
                      <p key={b.id} class="mono xs">{b.label}: {b.rules.map((r) => `${r.m} ${r.op} ${r.m === 'size' ? r.v / 10 + 'mm' : ['double', 'bottleneck', 'split'].includes(r.m) ? (r.v ? 'yes' : 'no') : r.v / 10 + '%'}`).join(' · ')}</p>
                    ))}
                    <p class="mono xs">{t('pk.reject', 'Always reject')}: {p.reject_rules.map((r) => `${r.m} > ${r.v / 10}%`).join(' · ')}</p>
                    <p class="xs">{t('pk.buys', 'Procured')}: {p.procured.join(', ')}</p>
                    <ul class="xs" style={{ margin: 0, paddingLeft: '1.2em' }}>{p.notes.map((n) => <li key={n}>{n}</li>)}</ul>
                    <p class="xs muted">{t('pk.src', 'Sources')}: {p.sources.map((s) => SOURCES[s] ?? s).join('; ')}</p>
                  </div>
                )}
              </div>
            </li>
          ))}
        </ol>

        <section class="section">
          <div class="section-head"><h2>{t('pk.tt', 'Time travel')}</h2></div>
          {lots.length === 0 ? <p class="small muted">{t('pk.nolots', 'Grade a lot first; then compare it under every pack here.')}</p> : (
            <>
              <label class="field">
                <span class="small">{t('pk.lot', 'Lot')}</span>
                <select class="select" value={sel} onChange={(e) => setSel((e.target as HTMLSelectElement).value)}>
                  {lots.map((l) => <option key={l.id} value={l.id}>{l.farmerRef} · {l.id}</option>)}
                </select>
              </label>
              {rows && (
                <div class="scrollx">
                  <table class="tbl">
                    <thead><tr><th>{t('pk.pack', 'Pack')}</th><th class="n">A</th><th class="n">URS</th><th class="n">{t('pk.rej', 'Rej.')}</th><th class="n">{t('pk.proc', 'Bought')}</th></tr></thead>
                    <tbody>
                      {rows.map(({ id, r }) => {
                        const p = PACKS.find((x) => x.id === id)!;
                        return (
                          <tr key={id} aria-current={lot?.packId === id ? 'true' : undefined}>
                            <td><b class="small">{p.short}</b><br /><span class="xs muted">{decisionTitle(r.sprt.decision)}</span>
                              {lot?.packId !== id && <><br /><button class="linkbtn xs" onClick={() => adopt(id)}>{t('pk.use', 'Grade this lot under this pack')}</button></>}</td>
                            <td class="n">{r.byWeight.GRADE_A.est.toFixed(1)}</td>
                            <td class="n">{r.byWeight.URS.est.toFixed(1)}</td>
                            <td class="n">{r.byWeight.REJECT.est.toFixed(1)}</td>
                            <td class="n"><b>{r.procured.byWeight.est.toFixed(1)}</b></td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
              <p class="note">{t('pk.tt.n', 'Percent by estimated weight. Same measurements, same human actions; only the rulebook changes. Different pack hash, different result, both verifiable.')}</p>
            </>
          )}
        </section>
      </main>
    </>
  );
}
