/**
 * RFC 8785 JSON Canonicalization Scheme (JCS).
 *
 * Keys sorted by UTF-16 code units, no whitespace, numbers in ECMAScript
 * shortest round-trip form (which JSON.stringify already uses), strings
 * escaped the way JSON.stringify escapes them. Non-finite numbers and
 * undefined values inside arrays are rejected rather than silently mangled.
 */
export function canonicalize(value: unknown): string {
  if (value === null) return 'null';
  switch (typeof value) {
    case 'boolean':
      return value ? 'true' : 'false';
    case 'number':
      if (!Number.isFinite(value)) throw new Error('JCS: non-finite number');
      return Object.is(value, -0) ? '0' : JSON.stringify(value);
    case 'string':
      return JSON.stringify(value);
    case 'object': {
      if (Array.isArray(value)) {
        return '[' + value.map((v) => {
          if (v === undefined) throw new Error('JCS: undefined in array');
          return canonicalize(v);
        }).join(',') + ']';
      }
      const obj = value as Record<string, unknown>;
      const keys = Object.keys(obj).filter((k) => obj[k] !== undefined).sort(cmpUtf16);
      return '{' + keys.map((k) => JSON.stringify(k) + ':' + canonicalize(obj[k])).join(',') + '}';
    }
    default:
      throw new Error(`JCS: unsupported type ${typeof value}`);
  }
}

function cmpUtf16(a: string, b: string): number {
  // String comparison in JS is already by UTF-16 code unit.
  return a < b ? -1 : a > b ? 1 : 0;
}
