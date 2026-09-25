import { useEffect, useState } from 'preact/hooks';
import { CircleCheck, CircleX, CircleHelp, CircleDashed, FileClock, ChevronRight } from 'lucide-preact';
import type { SprtDecision } from '@parakh/core';
import { db, type CertRow, type LotRow as Lot } from '../lib/db';
import { t } from '../lib/i18n';
import { decisionTitle } from './ui';

export type LotWithCert = Lot & { cert?: CertRow };

export async function loadLots(limit = 200): Promise<LotWithCert[]> {
  const ls = await db.lots.orderBy('createdAt').reverse().limit(limit).toArray();
  return Promise.all(ls.map(async (l) => ({ ...l, cert: l.certHashes.length ? await db.certs.get(l.certHashes[l.certHashes.length - 1]) : undefined })));
}

const ICON: Record<SprtDecision, typeof CircleCheck> = { ACCEPT_LOT: CircleCheck, REJECT_LOT: CircleX, SAMPLE_MORE: CircleDashed, REFER_TO_HUMAN: CircleHelp };

/** First photo of a lot as a small thumbnail (object URL, revoked on unmount). */
function useThumb(lotId: string) {
  const [url, setUrl] = useState<string | null>(null);
  useEffect(() => {
    let u: string | null = null;
    db.captures.where('lotId').equals(lotId).first().then((c) => { if (c) { u = URL.createObjectURL(c.image); setUrl(u); } });
    return () => { if (u) URL.revokeObjectURL(u); };
  }, [lotId]);
  return url;
}

export function LotRow({ l }: { l: LotWithCert }) {
  const thumb = useThumb(l.id);
  const h = l.cert?.signed.core.headline;
  const d = h?.decision as SprtDecision | undefined;
  const Icon = d ? ICON[d] : FileClock;
  return (
    <a class="lotrow" href={`#/lot/${l.id}`}>
      <span class="lotthumb">{thumb ? <img src={thumb} alt="" /> : <Icon size={22} aria-hidden="true" />}</span>
      <span class="lotbody">
        <span class="lottitle">{l.farmerRef || l.id}</span>
        <span class="lotmeta">{new Date(l.createdAt).toLocaleString(undefined, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })} · {l.variety}{l.demo ? ' · demo' : ''}</span>
        <span class="lotstatus" data-d={d ?? 'DRAFT'}><Icon size={14} aria-hidden="true" />{d ? decisionTitle(d) : t('home.draft', 'not signed')}</span>
      </span>
      <span class="lotnum">
        {h ? <><b class="mono">{h.procured.toFixed(0)}%</b><small>{t('lot.bought', 'procurable')}</small></> : null}
      </span>
      <ChevronRight size={18} class="lotchev" aria-hidden="true" />
    </a>
  );
}
