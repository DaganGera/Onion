import { canonicalize } from './canonical';
import { hashCanonical, sha256Hex, fromHex, toHex } from './hash';
import { gradeLot, type LotResult } from './lot';
import { signHash, verifyHash, type DeviceKey, type SigAlg } from './sign';
import type { CalibrationTier } from './sizing';
import type { BulbMeasurement, Override, RulePack } from './types';
import type { SprtDecision } from './stats';

export interface Headline {
  gradeA: number; urs: number; reject: number; refer: number; // % by weight, point estimates
  gradeA_ci: [number, number];
  procured: number; procured_ci: [number, number];
  decision: SprtDecision;
}

/** Everything a verifier needs to re-grade the lot. This object is what gets hashed and signed. */
export interface CertCore {
  v: 1;
  kind: 'parakh.cert';
  lot: { id: string; centre: string; variety: string; sacks: number; declaredKg: number; farmerRef: string };
  rev: number;
  parent: string | null;   // hash of the previous revision of THIS lot
  prev: string | null;     // hash chain: previous certificate issued on this device
  issuedAt: string;
  capture: { mode: 'live' | 'replay'; device: string; loc: string | null; first: string; last: string };
  calib: { tier: CalibrationTier; scaleSdPpm: number; camHmm: number };
  model: { id: string; hash: string };
  pack: { id: string; version: string; hash: string };
  sampling: { seed: string; draws: string } | null;
  evidence: string | null;  // SHA-256 of the image/mask evidence bundle
  bulbs: BulbMeasurement[];
  overrides: Override[];
  /** Who issued this revision, when the phone uses accounts. Absent on older receipts. */
  issuer?: { id: string; name: string; role: string };
  headline: Headline;
  resultHash: string;
}

export interface SignedCert {
  core: CertCore;
  hash: string;
  sig: { alg: SigAlg; pub: string; sig: string };
}

export async function packHash(pack: RulePack): Promise<string> {
  return hashCanonical(pack);
}

/** Seed for the tray bootstrap. Fixed by the certificate itself so anyone reproduces the intervals. */
export async function resultSeed(core: Pick<CertCore, 'lot' | 'sampling'>): Promise<string> {
  return core.sampling?.seed ?? (await sha256Hex('parakh-bootstrap|' + core.lot.id));
}

export function headlineOf(r: LotResult): Headline {
  return {
    gradeA: r.byWeight.GRADE_A.est, urs: r.byWeight.URS.est, reject: r.byWeight.REJECT.est, refer: r.byWeight.REFER.est,
    gradeA_ci: r.byWeight.GRADE_A.ci,
    procured: r.procured.byWeight.est, procured_ci: r.procured.byWeight.ci,
    decision: r.sprt.decision,
  };
}

/** Grade and fill in headline + resultHash. The only way a CertCore's result fields should be set. */
export async function finalizeCore(core: Omit<CertCore, 'headline' | 'resultHash'>, pack: RulePack): Promise<{ core: CertCore; result: LotResult }> {
  const ph = await packHash(pack);
  if (ph !== core.pack.hash) throw new Error('rule pack hash mismatch');
  const result = gradeLot(core.bulbs, pack, core.overrides, await resultSeed(core));
  return { core: { ...core, headline: headlineOf(result), resultHash: await hashCanonical(result) }, result };
}

export async function signCore(core: CertCore, key: DeviceKey): Promise<SignedCert> {
  const hash = await hashCanonical(core);
  const sig = await signHash(key, hash);
  return { core, hash, sig: { alg: key.alg, pub: toHex(key.publicRaw), sig: toHex(sig) } };
}

export interface VerifyReport {
  hashOk: boolean;
  sigOk: boolean;
  packKnown: boolean;
  regradeOk: boolean | null;   // null = pack unknown, could not re-grade
  headlineOk: boolean | null;
  chainOk: boolean | null;     // null = no predecessor available to check
  result: LotResult | null;
}

/**
 * Independent verification. Recomputes the hash, checks the signature, then
 * re-runs the grading on the stored measurements with the named rule pack
 * (looked up by hash, never by trusting the certificate's copy).
 */
export async function verifyCert(c: SignedCert, packs: RulePack[], predecessor?: SignedCert | null): Promise<VerifyReport> {
  const hash = await hashCanonical(c.core);
  const hashOk = hash === c.hash;
  const sigOk = hashOk && (await verifyHash(c.sig.alg, fromHex(c.sig.pub), hash, fromHex(c.sig.sig)));
  let pack: RulePack | undefined;
  for (const p of packs) if ((await packHash(p)) === c.core.pack.hash) { pack = p; break; }
  let regradeOk: boolean | null = null, headlineOk: boolean | null = null, result: LotResult | null = null;
  if (pack) {
    result = gradeLot(c.core.bulbs, pack, c.core.overrides, await resultSeed(c.core));
    regradeOk = (await hashCanonical(result)) === c.core.resultHash;
    headlineOk = canonicalize(headlineOf(result)) === canonicalize(c.core.headline);
  }
  let chainOk: boolean | null = null;
  if (predecessor !== undefined && predecessor !== null) chainOk = c.core.prev === predecessor.hash;
  return { hashOk, sigOk, packKnown: !!pack, regradeOk, headlineOk, chainOk, result };
}
