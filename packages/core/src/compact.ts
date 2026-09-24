import { b45decode, b45encode } from './base45';
import { canonicalize } from './canonical';
import { fromHex, hashCanonical, toHex } from './hash';
import type { CertCore, SignedCert } from './certificate';
import { DEFECTS, SHAPES, type BulbMeasurement } from './types';

/**
 * QR payload: "PK1:" + base45( alg | pubLen | pub | sig(64) | deflate-raw(headerLen u32 | header JSON | bulbs) ).
 * Bulbs are packed as fixed 32-byte records; the header is the rest of the
 * core as canonical JSON. Decoding reproduces the core exactly, so the
 * verifier hashes the same bytes the issuer signed.
 */
const PREFIX = 'PK1:';
const REC = 32;

async function pipe(data: Uint8Array, stream: CompressionStream | DecompressionStream): Promise<Uint8Array> {
  const out = new Blob([data as BlobPart]).stream().pipeThrough(stream);
  return new Uint8Array(await new Response(out).arrayBuffer());
}

function packBulbs(bulbs: BulbMeasurement[]): Uint8Array {
  const buf = new ArrayBuffer(bulbs.length * REC);
  const dv = new DataView(buf);
  bulbs.forEach((b, i) => {
    if (b.id !== `b${i}`) throw new Error('compact: bulb ids must be b0..bN');
    const o = i * REC;
    let flags = 0;
    SHAPES.forEach((s, j) => { if (b.shape[s]) flags |= 1 << j; });
    DEFECTS.forEach((d, j) => { if (b.frac[d] === null) flags |= 1 << (3 + j); });
    dv.setUint8(o, b.tray); dv.setUint8(o + 1, b.look);
    dv.setUint16(o + 2, b.size.min, true); dv.setUint16(o + 4, b.size.max, true); dv.setUint16(o + 6, b.size.sd, true);
    dv.setUint16(o + 8, b.fsd, true); dv.setUint16(o + 10, b.conf, true); dv.setUint16(o + 12, flags, true);
    DEFECTS.forEach((d, j) => dv.setUint16(o + 14 + 2 * j, b.frac[d] ?? 0, true));
    dv.setUint16(o + 28, b.w, true); dv.setUint16(o + 30, b.wsd, true);
  });
  return new Uint8Array(buf);
}

function unpackBulbs(bytes: Uint8Array): BulbMeasurement[] {
  const dv = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  const out: BulbMeasurement[] = [];
  for (let i = 0; i * REC < bytes.length; i++) {
    const o = i * REC;
    const flags = dv.getUint16(o + 12, true);
    const frac = {} as BulbMeasurement['frac'];
    DEFECTS.forEach((d, j) => { frac[d] = flags & (1 << (3 + j)) ? null : dv.getUint16(o + 14 + 2 * j, true); });
    const shape = {} as BulbMeasurement['shape'];
    SHAPES.forEach((s, j) => { shape[s] = !!(flags & (1 << j)); });
    out.push({
      id: `b${i}`, tray: dv.getUint8(o), look: dv.getUint8(o + 1),
      size: { min: dv.getUint16(o + 2, true), max: dv.getUint16(o + 4, true), sd: dv.getUint16(o + 6, true) },
      frac, fsd: dv.getUint16(o + 8, true), shape, conf: dv.getUint16(o + 10, true),
      w: dv.getUint16(o + 28, true), wsd: dv.getUint16(o + 30, true),
    });
  }
  return out;
}

export async function encodeCompact(c: SignedCert): Promise<string> {
  const { bulbs, ...rest } = c.core;
  const header = new TextEncoder().encode(canonicalize(rest));
  const body = new Uint8Array(4 + header.length + bulbs.length * REC);
  new DataView(body.buffer).setUint32(0, header.length, true);
  body.set(header, 4);
  body.set(packBulbs(bulbs), 4 + header.length);
  const z = await pipe(body, new CompressionStream('deflate-raw'));
  const pub = fromHex(c.sig.pub), sig = fromHex(c.sig.sig);
  const out = new Uint8Array(2 + pub.length + 1 + sig.length + z.length);
  out[0] = c.sig.alg === 'Ed25519' ? 1 : 2;
  out[1] = pub.length;
  out.set(pub, 2);
  out[2 + pub.length] = sig.length;
  out.set(sig, 3 + pub.length);
  out.set(z, 3 + pub.length + sig.length);
  return PREFIX + b45encode(out);
}

export async function decodeCompact(text: string): Promise<SignedCert> {
  const t = text.trim();
  if (!t.startsWith(PREFIX)) throw new Error('Not a Parakh certificate code');
  const raw = b45decode(t.slice(PREFIX.length));
  const alg = raw[0] === 1 ? 'Ed25519' : 'ES256';
  const pl = raw[1];
  const pub = raw.slice(2, 2 + pl);
  const sl = raw[2 + pl];
  const sig = raw.slice(3 + pl, 3 + pl + sl);
  const body = await pipe(raw.slice(3 + pl + sl), new DecompressionStream('deflate-raw'));
  const hl = new DataView(body.buffer, body.byteOffset).getUint32(0, true);
  const rest = JSON.parse(new TextDecoder().decode(body.slice(4, 4 + hl)));
  const bulbs = unpackBulbs(body.slice(4 + hl));
  const core = { ...rest, bulbs } as CertCore;
  return { core, hash: await hashCanonical(core), sig: { alg, pub: toHex(pub), sig: toHex(sig) } };
}
