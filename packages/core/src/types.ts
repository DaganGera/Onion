/**
 * Units are integers on purpose. Adjudication compares integers to integers,
 * so a verifier on any device reaches the same verdict bit-for-bit.
 *   size: tenths of a millimetre (523 = 52.3 mm)
 *   fractions: per-mille of visible surface (342 = 34.2 %)
 *   weight: decigrams (1234 = 123.4 g)
 */
export const DEFECTS = ['blackening', 'rot', 'sunburn', 'spots', 'sprouting', 'peeled', 'cut'] as const;
export type Defect = (typeof DEFECTS)[number];
export const SHAPES = ['double', 'bottleneck', 'split'] as const;
export type Shape = (typeof SHAPES)[number];

export type Bucket = 'GRADE_A' | 'URS' | 'REJECT' | 'REFER';
export const BUCKETS: Bucket[] = ['GRADE_A', 'URS', 'REJECT', 'REFER'];

export interface BulbMeasurement {
  id: string;
  tray: number;          // 1-based sample unit (tray / sack draw)
  look: number;          // 1-based look within the tray (shake = new look)
  size: { min: number; max: number; sd: number }; // Feret diameters, 0.1 mm
  frac: Record<Defect, number | null>;           // per-mille; null = not assessed
  fsd: number;           // per-mille, 1-sigma uncertainty of every fraction
  shape: Record<Shape, boolean>;
  conf: number;          // perception confidence, per-mille
  w: number;             // estimated weight, dg
  wsd: number;           // 1-sigma weight uncertainty, dg
}

export type Op = '<=' | '<' | '>=' | '>' | '==';

export interface Rule {
  m: Defect | Shape | 'size';
  op: Op;
  v: number;             // same unit as the measure (bool rules: 0/1)
  /** How to treat a null (not-assessed) measure. Default 'pass' + NOT_ASSESSED note. */
  na?: 'pass' | 'refer';
}

export interface RulePack {
  id: string;
  version: string;
  title: string;
  short: string;
  status: 'verified' | 'press-report' | 'assumed';
  effective_from: string;
  effective_to?: string;
  sources: string[];
  notes: string[];
  size_metric: 'min_feret' | 'max_feret' | 'mean_feret';
  /** Sigma multiplier for borderline detection (1.96 = 95 % two-sided). */
  k_sigma: number;
  /** Bulbs failing any of these are REJECT regardless of bucket. */
  reject_rules: Rule[];
  /** Evaluated in order; first bucket whose rules all pass wins. */
  buckets: { id: 'GRADE_A' | 'URS'; label: string; rules: Rule[] }[];
  /** Which buckets this pack's buyer actually procures. */
  procured: Bucket[];
  urs_definition: string;
  refer: { min_conf: number };
  lot: {
    look_merge: 'max_nonA' | 'mean';
    occlusion_factor: number;
    sprt: { bucket_set: Bucket[]; p0: number; p1: number; alpha: number; beta: number };
    max_trays: number;
    refer_share_max: number; // fraction 0..1
    bootstrap_b: number;
  };
}

export interface BulbVerdict {
  id: string;
  bucket: Bucket;
  codes: string[];     // machine-readable reason codes
  notes: string[];     // e.g. NOT_ASSESSED_CUT
}

export type Actor = 'officer' | 'farmer';
export interface Override {
  bulb: string;
  by: Actor;
  kind: 'override' | 'contest';
  to?: Bucket;          // required for override
  reason: string;       // reason code from OVERRIDE_REASONS
  note?: string;
  at: string;           // ISO time
}

export const OVERRIDE_REASONS = [
  'MASK_WRONG_BACKGROUND',
  'MASK_MISSED_DEFECT',
  'DEFECT_IS_SOIL_OR_SHADOW',
  'SIZE_MEASURED_WRONG',
  'TWO_BULBS_MERGED',
  'NOT_AN_ONION',
  'VISUAL_REINSPECTION',
] as const;
