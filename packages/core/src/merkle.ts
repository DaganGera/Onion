import { sha256, toHex, fromHex } from './hash';

/**
 * RFC 6962 (Certificate Transparency) Merkle tree hashing:
 *   leaf = SHA-256(0x00 || data), node = SHA-256(0x01 || left || right),
 * with the largest-power-of-two split. Anyone holding an old signed tree
 * head (size n, root r) can recompute the root of the first n leaves of a
 * later export and detect any rewritten history.
 */
const cat = (...parts: Uint8Array[]) => {
  const out = new Uint8Array(parts.reduce((s, p) => s + p.length, 0));
  let o = 0;
  for (const p of parts) { out.set(p, o); o += p.length; }
  return out;
};

export async function leafHash(leafHex: string): Promise<string> {
  return toHex(await sha256(cat(new Uint8Array([0]), fromHex(leafHex))));
}
async function nodeHash(l: string, r: string): Promise<string> {
  return toHex(await sha256(cat(new Uint8Array([1]), fromHex(l), fromHex(r))));
}

const split = (n: number) => { let k = 1; while (k * 2 < n) k *= 2; return k; };

/** Root over leaf *hashes* (already passed through leafHash). */
export async function rootOf(leaves: string[]): Promise<string> {
  if (leaves.length === 0) return toHex(await sha256(new Uint8Array()));
  if (leaves.length === 1) return leaves[0];
  const k = split(leaves.length);
  return nodeHash(await rootOf(leaves.slice(0, k)), await rootOf(leaves.slice(k)));
}

export async function inclusionProof(leaves: string[], index: number): Promise<string[]> {
  if (leaves.length <= 1) return [];
  const k = split(leaves.length);
  if (index < k) return [...(await inclusionProof(leaves.slice(0, k), index)), await rootOf(leaves.slice(k))];
  return [...(await inclusionProof(leaves.slice(k), index - k)), await rootOf(leaves.slice(0, k))];
}

/** RFC 9162 section 2.1.3.2 verification. */
export async function verifyInclusion(leaf: string, index: number, size: number, proof: string[], root: string): Promise<boolean> {
  if (index >= size) return false;
  let fn = index, sn = size - 1, r = leaf;
  for (const p of proof) {
    if (sn === 0) return false;
    if (fn % 2 === 1 || fn === sn) {
      r = await nodeHash(p, r);
      if (fn % 2 === 0) { while (fn % 2 === 0 && fn !== 0) { fn >>= 1; sn >>= 1; } }
    } else {
      r = await nodeHash(r, p);
    }
    fn >>= 1; sn >>= 1;
  }
  return sn === 0 && r === root;
}
