/**
 * sfc32: small, fast, well-tested 32-bit PRNG. Seeded from a hex digest so a
 * verifier holding the same seed reproduces every draw exactly (bootstrap
 * resamples, sack selection). Integer-only arithmetic: identical on every
 * JS engine.
 */
export function prngFromHex(seedHex: string): () => number {
  const h = seedHex.padEnd(32, '0');
  let a = parseInt(h.slice(0, 8), 16) >>> 0;
  let b = parseInt(h.slice(8, 16), 16) >>> 0;
  let c = parseInt(h.slice(16, 24), 16) >>> 0;
  let d = parseInt(h.slice(24, 32), 16) >>> 0 || 1;
  const next = () => {
    a >>>= 0; b >>>= 0; c >>>= 0; d >>>= 0;
    let t = (a + b) | 0;
    a = b ^ (b >>> 9);
    b = (c + (c << 3)) | 0;
    c = (c << 21) | (c >>> 11);
    d = (d + 1) | 0;
    t = (t + d) | 0;
    c = (c + t) | 0;
    return t >>> 0;
  };
  for (let i = 0; i < 12; i++) next(); // warm-up
  return next;
}

/** Uniform integer in [0, n) without modulo bias. */
export function randInt(next: () => number, n: number): number {
  if (n <= 0) throw new Error('randInt: n must be > 0');
  const limit = Math.floor(0x100000000 / n) * n;
  let x = next();
  while (x >= limit) x = next();
  return x % n;
}
