/** RFC 9285 Base45: fits the QR alphanumeric mode (the EU DCC uses the same trick). */
const ALPHA = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ $%*+-./:';

export function b45encode(bytes: Uint8Array): string {
  let out = '';
  for (let i = 0; i < bytes.length; i += 2) {
    if (i + 1 < bytes.length) {
      let x = bytes[i] * 256 + bytes[i + 1];
      const c = x % 45; x = (x - c) / 45;
      const d = x % 45; const e = (x - d) / 45;
      out += ALPHA[c] + ALPHA[d] + ALPHA[e];
    } else {
      const x = bytes[i];
      out += ALPHA[x % 45] + ALPHA[Math.floor(x / 45)];
    }
  }
  return out;
}

export function b45decode(s: string): Uint8Array {
  const v = Array.from(s, (ch) => {
    const i = ALPHA.indexOf(ch);
    if (i < 0) throw new Error(`base45: bad char ${JSON.stringify(ch)}`);
    return i;
  });
  const out: number[] = [];
  for (let i = 0; i < v.length; i += 3) {
    if (i + 2 < v.length) {
      const x = v[i] + v[i + 1] * 45 + v[i + 2] * 2025;
      if (x > 0xffff) throw new Error('base45: overflow');
      out.push(x >> 8, x & 0xff);
    } else if (i + 1 < v.length) {
      const x = v[i] + v[i + 1] * 45;
      if (x > 0xff) throw new Error('base45: overflow');
      out.push(x);
    } else throw new Error('base45: dangling char');
  }
  return new Uint8Array(out);
}
