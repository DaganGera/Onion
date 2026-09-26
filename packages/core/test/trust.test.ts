import { describe, expect, it } from 'vitest';
import fc from 'fast-check';
import {
  decodeCompact, drawSample, encodeCompact, finalizeCore, generateDeviceKey, hashCanonical, inclusionProof, leafHash, packById,
  packHash, PACKS, rootOf, sha256Hex, signCore, verifyCert, verifyInclusion, type CertCore,
} from '../src';
import { randomLot, resetRnd } from './fixtures';

describe('merkle log (RFC 6962 hashing)', () => {
  it('every inclusion proof verifies for sizes 1..20; a wrong leaf fails', async () => {
    for (let n = 1; n <= 20; n++) {
      const leaves = await Promise.all(Array.from({ length: n }, async (_, i) => leafHash(await sha256Hex('cert' + i))));
      const root = await rootOf(leaves);
      for (let i = 0; i < n; i++) {
        const p = await inclusionProof(leaves, i);
        expect(await verifyInclusion(leaves[i], i, n, p, root)).toBe(true);
        if (n > 1) expect(await verifyInclusion(leaves[(i + 1) % n], i, n, p, root)).toBe(false);
      }
    }
  });
  it('rewriting an old leaf changes the old root (older tree heads catch edits)', async () => {
    const leaves = await Promise.all(Array.from({ length: 9 }, async (_, i) => leafHash(await sha256Hex('c' + i))));
    const oldRoot = await rootOf(leaves.slice(0, 5));
    const edited = [...leaves];
    edited[2] = await leafHash(await sha256Hex('forged'));
    expect(await rootOf(edited.slice(0, 5))).not.toBe(oldRoot);
  });
});

describe('sampling draw', () => {
  it('is reproducible, picks distinct sacks, depends on both codes', async () => {
    const q = { lotId: 'L1', farmerCode: '4821', officerCode: '1177', date: '2026-09-24', nSacks: 40, k: 7 };
    const a = await drawSample(q), b = await drawSample(q), c = await drawSample({ ...q, farmerCode: '4822' });
    expect(a).toEqual(b);
    expect(a.seed).not.toBe(c.seed);
    expect(new Set(a.draws.map((d) => d.sack)).size).toBe(7);
    await fc.assert(fc.asyncProperty(fc.integer({ min: 1, max: 200 }), fc.integer({ min: 1, max: 30 }), async (n, k) => {
      const d = await drawSample({ lotId: 'x', farmerCode: '1', officerCode: '2', date: 'd', nSacks: n, k });
      expect(d.draws.every((x) => x.sack >= 1 && x.sack <= n)).toBe(true);
      expect(new Set(d.draws.map((x) => x.sack)).size).toBe(Math.min(n, k));
    }), { numRuns: 30 });
  });
});

describe('certificate: sign, compact QR payload, verify, tamper', () => {
  resetRnd(11);
  const pack = packById('in-psf-2026-06-relaxed-a')!;
  const bulbs = randomLot(80, 4, 2);
  const base = async (): Promise<Omit<CertCore, 'headline' | 'resultHash'>> => ({
    v: 1, kind: 'parakh.cert',
    lot: { id: 'LOT-TEST-1', centre: 'TEST', variety: 'red', sacks: 20, declaredKg: 1000, farmerRef: 'F-1' },
    rev: 0, parent: null, prev: null, issuedAt: '2026-09-24T10:00:00Z',
    capture: { mode: 'replay', device: 'test', loc: null, first: '2026-09-24T09:58:00Z', last: '2026-09-24T09:59:00Z' },
    calib: { tier: 'a4', scaleSdPpm: 15000, camHmm: 400 },
    model: { id: 'tier0', hash: 'ab'.repeat(32) },
    pack: { id: pack.id, version: pack.version, hash: await packHash(pack) },
    sampling: null, evidence: null, bulbs, overrides: [],
  });

  it('round-trips through the QR encoding and verifies offline (Ed25519 and P-256)', async () => {
    for (const alg of ['Ed25519', 'ES256'] as const) {
      const key = await generateDeviceKey(alg);
      const { core } = await finalizeCore(await base(), pack);
      const signed = await signCore(core, key);
      const qr = await encodeCompact(signed);
      expect(qr.startsWith('PK1:')).toBe(true);
      expect(qr.length).toBeLessThan(4296); // QR v40-L alphanumeric capacity
      const back = await decodeCompact(qr);
      expect(back.hash).toBe(signed.hash);
      const rep = await verifyCert(back, PACKS);
      expect(rep).toMatchObject({ hashOk: true, sigOk: true, packKnown: true, regradeOk: true, headlineOk: true });
    }
  });
  it('an edited measurement breaks the signature; a re-signed forgery fails re-grade', async () => {
    const key = await generateDeviceKey();
    const { core } = await finalizeCore(await base(), pack);
    const signed = await signCore(core, key);
    const tampered = structuredClone(signed);
    for (const b of tampered.core.bulbs) b.frac.rot = 900; // turn the whole lot rotten
    tampered.hash = await hashCanonical(tampered.core);
    expect((await verifyCert(tampered, PACKS)).sigOk).toBe(false);
    const forged = await signCore(tampered.core, key); // re-signed, but the stored result is stale
    const rep = await verifyCert(forged, PACKS);
    expect(rep.sigOk).toBe(true);
    expect(rep.regradeOk).toBe(false);
  });
  it('unknown rule pack is reported, not silently accepted', async () => {
    const key = await generateDeviceKey();
    const { core } = await finalizeCore(await base(), pack);
    const other = structuredClone(core);
    other.pack.hash = '00'.repeat(32);
    const rep = await verifyCert(await signCore(other, key), PACKS);
    expect(rep.packKnown).toBe(false);
    expect(rep.regradeOk).toBeNull();
  });
  it('hash chain link checks against the predecessor', async () => {
    const key = await generateDeviceKey();
    const b = await base();
    const first = await signCore((await finalizeCore(b, pack)).core, key);
    const second = await signCore((await finalizeCore({ ...b, lot: { ...b.lot, id: 'LOT-TEST-2' }, prev: first.hash }, pack)).core, key);
    expect((await verifyCert(second, PACKS, first)).chainOk).toBe(true);
    expect((await verifyCert(second, PACKS, second)).chainOk).toBe(false);
  });
});
