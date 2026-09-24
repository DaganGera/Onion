import {
  canonicalize, encodeCompact, finalizeCore, gradeLot, adjudicate, hashCanonical, leafHash, packById, packHash, resultSeed,
  rootOf, sha256Hex, signCore, signHash, toHex, type BulbMeasurement, type BulbVerdict, type CertCore, type LotResult, type Override, type RulePack,
} from '@parakh/core';
import { TIER0, toMeasurement, type BulbResult } from '@parakh/vision';
import { db, kvGet, kvSet, type CaptureRow, type CertRow, type LotRow } from './db';
import { deviceId, deviceKey } from './device';

/** Tier-1 manifest, if a learned model ships in this build (public/models/tier1.json). */
let t1: { ship: boolean; sha256: string; version: string } | null | undefined;
async function tier1Meta() {
  if (t1 !== undefined) return t1;
  try { const r = await fetch('./models/tier1.json'); t1 = r.ok ? await r.json() : null; } catch { t1 = null; }
  return t1?.ship ? t1 : (t1 = null);
}
export async function modelId() {
  const m = await tier1Meta();
  return `${TIER0.id}@${TIER0.version}` + (m ? `+tier1@${m.version}` : '');
}
let modelHashCache = '';
/** Hash of everything that shapes perception: the Tier-0 config and, if present, the Tier-1 weights hash. */
export async function modelHash() {
  const m = await tier1Meta();
  return (modelHashCache ||= await hashCanonical({ tier0: TIER0, tier1: m ? m.sha256 : null }));
}

export interface BulbRef { id: string; captureId: string; idx: number; tray: number; look: number }

/** All usable bulbs of a lot, in capture order, as core measurements with stable ids b0..bN. */
export async function lotMeasurements(lotId: string): Promise<{ bulbs: BulbMeasurement[]; refs: BulbRef[]; captures: CaptureRow[] }> {
  const captures = (await db.captures.where('lotId').equals(lotId).toArray()).sort((a, b) => a.at.localeCompare(b.at));
  const bulbs: BulbMeasurement[] = [], refs: BulbRef[] = [];
  for (const c of captures) {
    for (const b of c.bulbs) {
      if (b.excluded) continue;
      const id = `b${bulbs.length}`;
      bulbs.push(toMeasurement(b, id, c.tray, c.look));
      refs.push({ id, captureId: c.id, idx: b.idx, tray: c.tray, look: c.look });
    }
  }
  return { bulbs, refs, captures };
}

export interface Graded { lot: LotRow; pack: RulePack; bulbs: BulbMeasurement[]; refs: BulbRef[]; captures: CaptureRow[]; ai: BulbVerdict[]; result: LotResult; lastCert?: CertRow }

export async function gradeStoredLot(lotId: string, packId?: string): Promise<Graded | null> {
  const lot = await db.lots.get(lotId);
  if (!lot) return null;
  const pack = packById(packId ?? lot.packId)!;
  const { bulbs, refs, captures } = await lotMeasurements(lotId);
  const seed = await resultSeed({ lot: { id: lot.id } as CertCore['lot'], sampling: lot.sampling ? { seed: lot.sampling.seed, draws: '' } : null });
  const result = gradeLot(bulbs, pack, lot.overrides, seed);
  const lastCert = lot.certHashes.length ? await db.certs.get(lot.certHashes[lot.certHashes.length - 1]) : undefined;
  return { lot, pack, bulbs, refs, captures, ai: adjudicate(bulbs, pack), result, lastCert };
}

/** Evidence hash: every stored image hash plus each bulb's defect-label crop, in capture order. */
async function evidenceHash(captures: CaptureRow[]): Promise<string> {
  const items: string[] = [];
  for (const c of captures) {
    items.push(c.imageHash);
    for (const b of c.bulbs) items.push(await sha256Hex(new Uint8Array(b.labels.data)));
  }
  return sha256Hex(canonicalize(items));
}

/**
 * Issue (or re-issue after human actions) a signed certificate revision.
 * Revisions chain to their parent; every certificate chains to the previous
 * certificate issued on this device; every certificate goes into the log.
 */
export async function issueCertificate(lotId: string): Promise<CertRow> {
  const lot = (await db.lots.get(lotId))!;
  const pack = packById(lot.packId)!;
  const { bulbs, captures } = await lotMeasurements(lotId);
  const key = await deviceKey();
  const prev = await kvGet<string | null>('chainHead', null);
  const parent = lot.certHashes.length ? lot.certHashes[lot.certHashes.length - 1] : null;
  const times = captures.map((c) => c.at).sort();
  const cal = captures[0]?.calib;
  const draws = lot.sampling ? lot.sampling.draws.map((d) => `${d.sack}${d.layer[0].toUpperCase()}`).join(' ') : '';
  const base: Omit<CertCore, 'headline' | 'resultHash'> = {
    v: 1, kind: 'parakh.cert',
    lot: { id: lot.id, centre: lot.centre, variety: lot.variety, sacks: lot.sacks, declaredKg: lot.declaredKg, farmerRef: lot.farmerRef },
    rev: lot.certHashes.length, parent, prev, issuedAt: new Date().toISOString(),
    capture: { mode: captures.some((c) => c.mode === 'replay') || lot.mode === 'replay' ? 'replay' : 'live', device: await deviceId(), loc: captures.find((c) => c.loc)?.loc ?? null, first: times[0] ?? '', last: times[times.length - 1] ?? '' },
    calib: { tier: (cal?.tier ?? 'intrinsics') as CertCore['calib']['tier'], scaleSdPpm: Math.round((cal?.scaleSd ?? 0.12) * 1e6), camHmm: Math.round(cal?.camHmm ?? 0) },
    model: { id: await modelId(), hash: await modelHash() },
    pack: { id: pack.id, version: pack.version, hash: await packHash(pack) },
    sampling: lot.sampling ? { seed: lot.sampling.seed, draws } : null,
    evidence: await evidenceHash(captures),
    bulbs, overrides: lot.overrides,
  };
  const { core } = await finalizeCore(base, pack);
  const signed = await signCore(core, key);
  let qr = '';
  try { qr = await encodeCompact(signed); } catch { qr = ''; }
  const row: CertRow = { hash: signed.hash, lotId, rev: core.rev, issuedAt: core.issuedAt, signed, qr, centre: lot.centre };
  await db.transaction('rw', db.certs, db.lots, db.log, db.kv, async () => {
    await db.certs.put(row);
    await db.lots.update(lotId, { certHashes: [...lot.certHashes, signed.hash] });
    await db.log.add({ leaf: await leafHash(signed.hash), certHash: signed.hash, at: core.issuedAt });
    await kvSet('chainHead', signed.hash);
  });
  // Signed tree head at least once a day, so the log can be audited from any day's export.
  const last = await db.sth.orderBy('size').last();
  if (!last || last.at.slice(0, 10) !== new Date().toISOString().slice(0, 10)) await signTreeHead();
  return row;
}

export async function addOverride(lotId: string, o: Override) {
  const lot = (await db.lots.get(lotId))!;
  await db.lots.update(lotId, { overrides: [...lot.overrides, o] });
}

/** Signed tree head over the whole local transparency log. */
export async function signTreeHead() {
  const leaves = (await db.log.orderBy('idx').toArray()).map((r) => r.leaf);
  const root = await rootOf(leaves);
  const at = new Date().toISOString();
  const key = await deviceKey();
  const body = canonicalize({ size: leaves.length, root, at });
  const sig = toHex(await signHash(key, await sha256Hex(body)));
  const sth = { size: leaves.length, root, at, sig, alg: key.alg, pub: toHex(key.publicRaw) };
  await db.sth.put(sth);
  return sth;
}

export async function exportLog() {
  const leaves = await db.log.orderBy('idx').toArray();
  const sths = await db.sth.toArray();
  return { kind: 'parakh.log', rfc6962: true, leaves: leaves.map((l) => ({ i: l.idx, cert: l.certHash, leaf: l.leaf, at: l.at })), sths };
}

export async function evidenceBundle(certHash: string) {
  const cert = (await db.certs.get(certHash))!;
  const caps = await db.captures.where('lotId').equals(cert.lotId).toArray();
  const toB64 = async (b: Blob) => btoa(String.fromCharCode(...new Uint8Array(await b.arrayBuffer())));
  return {
    kind: 'parakh.bundle', cert: cert.signed,
    captures: await Promise.all(caps.map(async (c) => ({ id: c.id, tray: c.tray, look: c.look, at: c.at, imageHash: c.imageHash, jpegBase64: await toB64(c.image), calib: c.calib, guard: c.guard ?? null, timings: c.timings }))),
  };
}

export function newLotId(centre: string): string {
  const d = new Date();
  const ymd = `${d.getFullYear()}${String(d.getMonth() + 1).padStart(2, '0')}${String(d.getDate()).padStart(2, '0')}`;
  const rnd = Array.from(crypto.getRandomValues(new Uint8Array(2)), (b) => b.toString(16).padStart(2, '0')).join('').toUpperCase();
  return `${centre.split(' ')[0]}-${ymd}-${rnd}`;
}

export type { BulbResult };
