import { describe, expect, it } from 'vitest';
import fc from 'fast-check';
import { b45decode, b45encode, canonicalize, sha256Hex } from '../src';

describe('RFC 8785 canonical JSON', () => {
  it('sorts keys, strips whitespace, formats numbers like ES', () => {
    expect(canonicalize({ b: 1, a: [true, null, 'x'], c: { z: 1e21, y: 0.1, x: -0 } }))
      .toBe('{"a":[true,null,"x"],"b":1,"c":{"x":0,"y":0.1,"z":1e+21}}');
    // RFC 8785 section 3.2.3 sorting example (UTF-16 code unit order)
    const o = { '€': 'Euro Sign', '\r': 'Carriage Return', 'דּ': 'Hebrew Letter Dalet With Dagesh', '1': 'One',
      '😀': 'Emoji: Grinning Face', '\u0080': 'Control', 'ö': 'Latin Small Letter O With Diaeresis' };
    const c = canonicalize(o);
    const order = ['Carriage Return', 'One', 'Control', 'Latin Small Letter O With Diaeresis', 'Euro Sign', 'Emoji: Grinning Face', 'Hebrew Letter Dalet With Dagesh'];
    const pos = order.map((v) => c.indexOf(v));
    expect([...pos].sort((a, b) => a - b)).toEqual(pos);
  });
  it('rejects non-finite numbers', () => expect(() => canonicalize({ a: NaN })).toThrow());
  it('is idempotent and key-order independent (property)', () => {
    fc.assert(fc.property(fc.jsonValue(), (v) => {
      const c = canonicalize(v);
      expect(canonicalize(JSON.parse(c))).toBe(c);
    }));
  });
  it('sha256 known vector', async () => {
    expect(await sha256Hex('abc')).toBe('ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad');
  });
});

describe('base45 (RFC 9285)', () => {
  const enc = (s: string) => b45encode(new TextEncoder().encode(s));
  it('RFC examples', () => {
    expect(enc('AB')).toBe('BB8');
    expect(enc('Hello!!')).toBe('%69 VD92EX0');
    expect(enc('base-45')).toBe('UJCLQE7W581');
    expect(new TextDecoder().decode(b45decode('QED8WEX0'))).toBe('ietf!');
  });
  it('round-trips any bytes (property)', () => {
    fc.assert(fc.property(fc.uint8Array({ maxLength: 300 }), (b) => {
      expect(Array.from(b45decode(b45encode(b)))).toEqual(Array.from(b));
    }));
  });
});
