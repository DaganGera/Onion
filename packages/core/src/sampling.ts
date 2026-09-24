import { sha256Hex } from './hash';
import { prngFromHex, randInt } from './prng';

export const LAYERS = ['top', 'middle', 'bottom'] as const;

/**
 * Which sacks (and which layer of each) to open. The seed mixes a code
 * typed by the farmer and one typed by the officer, so neither side picks
 * the draw alone, and anyone can recompute it later from the certificate.
 */
export async function drawSample(input: { lotId: string; farmerCode: string; officerCode: string; date: string; nSacks: number; k: number }) {
  const material = [input.lotId, input.farmerCode, input.officerCode, input.date, input.nSacks, input.k].join('|');
  const seed = await sha256Hex(material);
  const next = prngFromHex(seed);
  const k = Math.min(input.k, input.nSacks);
  // Partial Fisher-Yates: uniform k-subset.
  const idx = Array.from({ length: input.nSacks }, (_, i) => i + 1);
  for (let i = 0; i < k; i++) {
    const j = i + randInt(next, input.nSacks - i);
    [idx[i], idx[j]] = [idx[j], idx[i]];
  }
  const draws = idx.slice(0, k).map((sack) => ({ sack, layer: LAYERS[randInt(next, 3)] }));
  return { seed, material, draws };
}

/** Square-root rule of thumb for the number of sacks to draw; ASSUMED (A-SAMPLE-1). */
export function suggestedDraws(nSacks: number): number {
  return Math.max(3, Math.min(nSacks, Math.ceil(Math.sqrt(nSacks))));
}
