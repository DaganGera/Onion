import { fingerprint, generateDeviceKey, type DeviceKey } from '@parakh/core';
import { kvGet, kvSet } from './db';

/**
 * The signing key lives in IndexedDB as a non-extractable CryptoKey: page
 * script can use it to sign but cannot read it out. Clearing site data
 * destroys it, and a new key gets a new fingerprint (visible on every receipt).
 */
let cached: DeviceKey | null = null;

export async function deviceKey(): Promise<DeviceKey> {
  if (cached) return cached;
  const stored = await kvGet<DeviceKey | null>('deviceKey', null);
  if (stored?.privateKey) return (cached = stored);
  const k = await generateDeviceKey();
  await kvSet('deviceKey', k);
  return (cached = k);
}

export async function deviceId(): Promise<string> {
  let id = await kvGet<string>('deviceId', '');
  if (!id) {
    id = 'DEV-' + Array.from(crypto.getRandomValues(new Uint8Array(4)), (b) => b.toString(16).padStart(2, '0')).join('').toUpperCase();
    await kvSet('deviceId', id);
  }
  return id;
}

export async function keyFingerprint(): Promise<string> {
  return fingerprint((await deviceKey()).publicRaw);
}

export interface Settings {
  centre: string;
  officer: string;
  lang: string;
  speak: boolean;
  packId: string;
  coin: number;       // mm, for the coin calibration tier
  camHmm: number;     // fallback camera height for the intrinsics tier
  ratePerQuintal: number;
}

export const DEFAULT_SETTINGS: Settings = {
  centre: 'LSG-01 (demo)',
  officer: 'OFF-07 (demo)',
  lang: 'en',
  speak: false,
  packId: 'in-psf-2026-07-30-a-only',
  coin: 27,
  camHmm: 380,
  ratePerQuintal: 2125,
};

export async function loadSettings(): Promise<Settings> {
  return { ...DEFAULT_SETTINGS, ...(await kvGet<Partial<Settings>>('settings', {})) };
}
export async function saveSettings(s: Settings) {
  await kvSet('settings', s);
}
