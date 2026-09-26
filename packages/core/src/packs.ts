import type { RulePack } from './types';
import preA from '../packs/in-psf-2026-pre-a.json';
import preB from '../packs/in-psf-2026-pre-b.json';
import junA from '../packs/in-psf-2026-06-relaxed-a.json';
import junB from '../packs/in-psf-2026-06-relaxed-b.json';
import jul from '../packs/in-psf-2026-07-30-a-only.json';

/** Bundled rule packs, oldest first. The verifier finds a pack by hash, never by id. */
export const PACKS: RulePack[] = [preA, preB, junA, junB, jul] as RulePack[];
export const DEFAULT_PACK_ID = 'in-psf-2026-07-30-a-only';
export const packById = (id: string) => PACKS.find((p) => p.id === id);
