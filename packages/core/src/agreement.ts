/** Agreement and method-comparison statistics for the field studies (E1-E4). */

/** Fleiss' kappa. counts[i][j] = number of raters who put subject i in category j (same rater count per subject). */
export function fleissKappa(counts: number[][]): number {
  const N = counts.length;
  const n = counts[0].reduce((a, b) => a + b, 0);
  const k = counts[0].length;
  const pj = Array.from({ length: k }, (_, j) => counts.reduce((s, r) => s + r[j], 0) / (N * n));
  const Pi = counts.map((r) => (r.reduce((s, x) => s + x * x, 0) - n) / (n * (n - 1)));
  const Pbar = Pi.reduce((a, b) => a + b, 0) / N;
  const Pe = pj.reduce((s, p) => s + p * p, 0);
  return (Pbar - Pe) / (1 - Pe);
}

/** Cohen's kappa for two raters over the same items. */
export function cohenKappa(a: string[], b: string[]): { kappa: number; agreement: number } {
  const cats = [...new Set([...a, ...b])];
  const n = a.length;
  let agree = 0;
  for (let i = 0; i < n; i++) if (a[i] === b[i]) agree++;
  const po = agree / n;
  const pe = cats.reduce((s, c) => s + (a.filter((x) => x === c).length / n) * (b.filter((x) => x === c).length / n), 0);
  return { kappa: pe === 1 ? 1 : (po - pe) / (1 - pe), agreement: po };
}

/** Bland-Altman: bias and 95% limits of agreement of (method - reference). */
export function blandAltman(method: number[], ref: number[]) {
  const d = method.map((m, i) => m - ref[i]);
  const n = d.length;
  const bias = d.reduce((a, b) => a + b, 0) / n;
  const sd = Math.sqrt(d.reduce((s, x) => s + (x - bias) ** 2, 0) / Math.max(1, n - 1));
  const mae = d.reduce((s, x) => s + Math.abs(x), 0) / n;
  return { n, bias, sd, mae, loa: [bias - 1.96 * sd, bias + 1.96 * sd] as [number, number] };
}

/**
 * One-way random-effects ICC(1,1): how much of the variance in a repeated
 * measurement is between subjects (lots) rather than between repeats.
 * groups[i] = repeated measurements of subject i.
 */
export function icc1(groups: number[][]): number {
  const k = groups.reduce((s, g) => s + g.length, 0) / groups.length;
  const all = groups.flat();
  const grand = all.reduce((a, b) => a + b, 0) / all.length;
  const ssb = groups.reduce((s, g) => s + g.length * ((g.reduce((a, b) => a + b, 0) / g.length) - grand) ** 2, 0);
  const ssw = groups.reduce((s, g) => { const m = g.reduce((a, b) => a + b, 0) / g.length; return s + g.reduce((t, x) => t + (x - m) ** 2, 0); }, 0);
  const msb = ssb / (groups.length - 1), msw = ssw / (all.length - groups.length);
  return (msb - msw) / (msb + (k - 1) * msw);
}

/** Majority label; ties return '?'. */
export function majority(labels: string[]): string {
  const c = new Map<string, number>();
  for (const l of labels) c.set(l, (c.get(l) ?? 0) + 1);
  const sorted = [...c.entries()].sort((a, b) => b[1] - a[1]);
  return sorted.length > 1 && sorted[0][1] === sorted[1][1] ? '?' : sorted[0][0];
}
