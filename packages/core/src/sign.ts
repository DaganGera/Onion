import { subtle, sha256Hex, toHex } from './hash';

export type SigAlg = 'Ed25519' | 'ES256';

export interface DeviceKey {
  alg: SigAlg;
  privateKey: CryptoKey;
  publicRaw: Uint8Array;
}

const P256 = { name: 'ECDSA', namedCurve: 'P-256' } as const;
const ES = { name: 'ECDSA', hash: 'SHA-256' } as const;

/**
 * Device-bound key. The private key is created non-extractable, so it can be
 * stored in IndexedDB and used, but never read out by page script.
 * Ed25519 is tried first (smaller, deterministic), ECDSA P-256 as fallback.
 */
export async function generateDeviceKey(prefer: SigAlg = 'Ed25519'): Promise<DeviceKey> {
  if (prefer === 'Ed25519') {
    try {
      const kp = (await subtle().generateKey({ name: 'Ed25519' }, false, ['sign', 'verify'])) as CryptoKeyPair;
      const raw = new Uint8Array(await subtle().exportKey('raw', kp.publicKey));
      return { alg: 'Ed25519', privateKey: kp.privateKey, publicRaw: raw };
    } catch { /* fall through to P-256 */ }
  }
  const kp = (await subtle().generateKey(P256, false, ['sign', 'verify'])) as CryptoKeyPair;
  const raw = new Uint8Array(await subtle().exportKey('raw', kp.publicKey));
  return { alg: 'ES256', privateKey: kp.privateKey, publicRaw: raw };
}

const enc = new TextEncoder();

export async function signHash(key: DeviceKey, hashHex: string): Promise<Uint8Array> {
  const algo = key.alg === 'Ed25519' ? { name: 'Ed25519' } : ES;
  return new Uint8Array(await subtle().sign(algo, key.privateKey, enc.encode(hashHex)));
}

export async function verifyHash(alg: SigAlg, publicRaw: Uint8Array, hashHex: string, sig: Uint8Array): Promise<boolean> {
  try {
    const pub = await subtle().importKey('raw', publicRaw as BufferSource, alg === 'Ed25519' ? { name: 'Ed25519' } : P256, false, ['verify']);
    return await subtle().verify(alg === 'Ed25519' ? { name: 'Ed25519' } : ES, pub, sig as BufferSource, enc.encode(hashHex));
  } catch {
    return false;
  }
}

/** Short, human-comparable key fingerprint: first 16 hex of SHA-256(raw public key), grouped. */
export async function fingerprint(publicRaw: Uint8Array): Promise<string> {
  return (await sha256Hex(publicRaw)).slice(0, 16).replace(/(.{4})/g, '$1 ').trim().toUpperCase();
}

export { toHex };
