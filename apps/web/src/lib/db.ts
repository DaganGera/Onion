import Dexie, { type Table } from 'dexie';
import type { BulbResult } from '@parakh/vision';
import type { Override, SignedCert } from '@parakh/core';

export interface LotRow {
  id: string;
  createdAt: string;
  centre: string;
  officer: string;
  farmerRef: string;
  variety: string;
  sacks: number;
  declaredKg: number;
  packId: string;
  sampling: { farmerCode: string; officerCode: string; seed: string; draws: { sack: number; layer: string }[] } | null;
  mode: 'live' | 'replay';
  overrides: Override[];
  certHashes: string[];   // revisions, oldest first
  demo?: boolean;
}

export interface CaptureRow {
  id: string;
  lotId: string;
  tray: number;
  look: number;
  at: string;
  mode: 'live' | 'replay';
  image: Blob;            // analysis-resolution JPEG (evidence)
  imageHash: string;
  width: number;
  height: number;
  calib: { tier: string; mmPerPx: number; camHmm: number; scaleSd: number; note: string };
  bulbs: BulbResult[];
  timings: Record<string, number>;
  loc: string | null;
  /** Capture Guard telemetry since the previous photo: scans seen, scans with a failing gate, refused shutter presses. */
  guard?: { scans: number; failed: number; refused: number; byGate: Record<string, number> };
}

export interface CertRow { hash: string; lotId: string; rev: number; issuedAt: string; signed: SignedCert; qr: string; centre: string }
export interface LogRow { idx?: number; leaf: string; certHash: string; at: string }
export interface SthRow { size: number; root: string; at: string; sig: string; alg: string; pub: string }
export interface CorrectionRow { id?: number; lotId: string; bulbId: string; captureId: string; bulbIdx: number; from: string; to: string; reason: string; at: string }
export interface KvRow { k: string; v: unknown }

class ParakhDB extends Dexie {
  lots!: Table<LotRow, string>;
  captures!: Table<CaptureRow, string>;
  certs!: Table<CertRow, string>;
  log!: Table<LogRow, number>;
  sth!: Table<SthRow, number>;
  corrections!: Table<CorrectionRow, number>;
  kv!: Table<KvRow, string>;
  constructor() {
    super('parakh');
    this.version(1).stores({
      lots: 'id, createdAt, centre',
      captures: 'id, lotId, [lotId+tray+look]',
      certs: 'hash, lotId, issuedAt, centre',
      log: '++idx, certHash',
      sth: 'size',
      corrections: '++id, lotId',
      kv: 'k',
    });
  }
}

export const db = new ParakhDB();

export async function kvGet<T>(k: string, dflt: T): Promise<T> {
  const r = await db.kv.get(k);
  return r ? (r.v as T) : dflt;
}
export async function kvSet(k: string, v: unknown) {
  await db.kv.put({ k, v });
}
