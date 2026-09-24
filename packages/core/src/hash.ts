import { canonicalize } from './canonical';

const enc = new TextEncoder();

function subtle(): SubtleCrypto {
  const c = (globalThis as { crypto?: Crypto }).crypto;
  if (!c?.subtle) throw new Error('WebCrypto unavailable (needs a secure context: https or localhost)');
  return c.subtle;
}

export async function sha256(data: Uint8Array | string): Promise<Uint8Array> {
  const bytes = typeof data === 'string' ? enc.encode(data) : data;
  return new Uint8Array(await subtle().digest('SHA-256', bytes as BufferSource));
}

export const toHex = (b: Uint8Array): string =>
  Array.from(b, (x) => x.toString(16).padStart(2, '0')).join('');

export function fromHex(hex: string): Uint8Array {
  if (hex.length % 2) throw new Error('odd hex length');
  const out = new Uint8Array(hex.length / 2);
  for (let i = 0; i < out.length; i++) out[i] = parseInt(hex.slice(2 * i, 2 * i + 2), 16);
  return out;
}

export async function sha256Hex(data: Uint8Array | string): Promise<string> {
  return toHex(await sha256(data));
}

/** SHA-256 over the RFC 8785 canonical form. The one hash used for every signed object. */
export async function hashCanonical(value: unknown): Promise<string> {
  return sha256Hex(canonicalize(value));
}

export { subtle };
