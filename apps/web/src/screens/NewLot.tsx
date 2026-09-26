import { can, currentUser, useSession, who } from '../lib/auth';
import { useEffect, useState } from 'preact/hooks';
import { Camera, Dices, Images } from 'lucide-preact';
import { drawSample, PACKS, suggestedDraws } from '@parakh/core';
import { db, type LotRow } from '../lib/db';
import { loadSettings, type Settings } from '../lib/device';
import { t } from '../lib/i18n';
import { go } from '../lib/router';
import { newLotId } from '../lib/lots';
import { TopBar } from '../components/ui';

const VARIETIES = [['red', () => t('v.red', 'Red')], ['pink', () => t('v.pink', 'Pink')], ['white', () => t('v.white', 'White')], ['mixed', () => t('v.mixed', 'Mixed')]] as const;

export function NewLot() {
  const me = useSession();
  const [s, setS] = useState<Settings | null>(null);
  const [farmer, setFarmer] = useState('');
  const [variety, setVariety] = useState('red');
  const [sacks, setSacks] = useState(20);
  const [kg, setKg] = useState(1000);
  const [packId, setPackId] = useState('');
  const [fc, setFc] = useState('');
  const [oc, setOc] = useState('');
  const [draw, setDraw] = useState<Awaited<ReturnType<typeof drawSample>> | null>(null);
  const [id, setId] = useState('');
  useEffect(() => { loadSettings().then((x) => { setS(x); setPackId(x.packId); setId(newLotId(x.centre)); }); }, []);
  if (!s || !id) return null;
  const k = suggestedDraws(sacks);
  const codesOk = /^\d{4}$/.test(fc) && /^\d{4}$/.test(oc);

  const doDraw = async () => {
    setDraw(await drawSample({ lotId: id, farmerCode: fc, officerCode: oc, date: new Date().toISOString().slice(0, 10), nSacks: sacks, k }));
  };

  const start = async (replay: boolean) => {
    const row: LotRow = {
      id, createdAt: new Date().toISOString(), centre: s.centre, officer: me ? who(me) : s.officer, farmerRef: farmer.trim() || t('nl.anon', 'Unnamed farmer'),
      variety, sacks, declaredKg: kg, packId, mode: replay ? 'replay' : 'live', overrides: [], certHashes: [],
      sampling: draw ? { farmerCode: fc, officerCode: oc, seed: draw.seed, draws: draw.draws } : null,
    };
    await db.lots.put(row);
    go(`capture/${id}${replay ? '?replay=1' : ''}`);
  };

  return (
    <>
      <TopBar title={t('nl.title', 'New lot')} backTo="" />
      <main class="page">
        {!can(me, 'lot.create') && <p class="banner warn">{t('perm.no', 'Your role cannot do this. Ask the centre supervisor.')}</p>}
        <p class="mono xs muted">{id}</p>
        <label class="field">
          <span>{t('nl.farmer', 'Farmer or seller reference')}</span>
          <input class="input" value={farmer} onInput={(e) => setFarmer((e.target as HTMLInputElement).value)} placeholder={t('nl.farmer.ph', 'Name, FPO or receipt number')} autocomplete="off" />
          <small>{t('nl.farmer.s', 'Stored on this phone and printed on the receipt. Use a reference number if the seller prefers.')}</small>
        </label>
        <div class="field">
          <span>{t('nl.variety', 'Variety')}</span>
          <div class="seg" role="group">
            {VARIETIES.map(([v, label]) => <button key={v} aria-pressed={variety === v} onClick={() => setVariety(v)}>{label()}</button>)}
          </div>
        </div>
        <div class="grid2">
          <div class="field">
            <span>{t('nl.sacks', 'Sacks in lot')}</span>
            <div class="stepper">
              <button onClick={() => { setSacks(Math.max(1, sacks - 1)); setDraw(null); }} aria-label="−">−</button>
              <input class="input" inputMode="numeric" value={sacks} onInput={(e) => { setSacks(Math.max(1, Math.min(999, parseInt((e.target as HTMLInputElement).value) || 1))); setDraw(null); }} />
              <button onClick={() => { setSacks(Math.min(999, sacks + 1)); setDraw(null); }} aria-label="+">+</button>
            </div>
          </div>
          <label class="field">
            <span>{t('nl.kg', 'Declared weight, kg')}</span>
            <input class="input mono" inputMode="numeric" value={kg} onInput={(e) => setKg(Math.max(1, parseInt((e.target as HTMLInputElement).value) || 1))} />
          </label>
        </div>
        <label class="field">
          <span>{t('nl.pack', 'Rule pack')}</span>
          <select class="select" value={packId} onChange={(e) => setPackId((e.target as HTMLSelectElement).value)}>
            {PACKS.map((p) => <option key={p.id} value={p.id}>{p.short} ({p.status})</option>)}
          </select>
        </label>

        <section class="card section">
          <h2 class="h3" style={{ fontSize: 'var(--text-lg)' }}>{t('nl.draw.h', 'Which sacks to open')}</h2>
          <p class="small muted">{t('nl.draw.p', 'The farmer and the officer each type any 4 digits. Together they decide which {k} of {n} sacks, and which layer, get sampled. Neither side chooses alone, and anyone can recompute the draw later.', { k, n: sacks })}</p>
          <div class="grid2">
            <label class="field"><span>{t('nl.fc', 'Farmer’s code')}</span><input class="input code" inputMode="numeric" maxLength={4} value={fc} onInput={(e) => { setFc((e.target as HTMLInputElement).value.replace(/\D/g, '')); setDraw(null); }} /></label>
            <label class="field"><span>{t('nl.oc', 'Officer’s code')}</span><input class="input code" inputMode="numeric" maxLength={4} value={oc} onInput={(e) => { setOc((e.target as HTMLInputElement).value.replace(/\D/g, '')); setDraw(null); }} /></label>
          </div>
          <button class="btn quiet" disabled={!codesOk} onClick={doDraw}><Dices size={18} aria-hidden="true" />{t('nl.draw', 'Draw sacks')}</button>
          {draw && (
            <>
              <ol class="draws" aria-label={t('nl.draw.h', 'Which sacks to open')}>
                {draw.draws.map((d, i) => <li key={d.sack}><span class="mono xs muted">{i + 1}</span><b class="mono">{t('nl.sack', 'Sack')} {d.sack}</b><span class="small muted">{t(`layer.${d.layer}`, d.layer)}</span></li>)}
              </ol>
              <p class="hash mono xs muted" style={{ overflowWrap: 'anywhere' }}>seed {draw.seed.slice(0, 32)}…</p>
            </>
          )}
        </section>

        <div class="section">
          <button class="btn primary block" onClick={() => start(false)}><Camera size={20} aria-hidden="true" />{t('nl.go', 'Open camera')}</button>
          <button class="btn quiet block" onClick={() => start(true)}><Images size={18} aria-hidden="true" />{t('nl.replay', 'Replay stored demo photos')}</button>
          <p class="xs muted">{t('nl.replay.s', 'Replay feeds real stored photos through the same pipeline. The receipt is marked REPLAY.')}</p>
        </div>
      </main>
    </>
  );
}
