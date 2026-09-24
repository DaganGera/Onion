/**
 * Every Tier-0 threshold in one place. The canonical hash of this object is
 * pinned into each certificate as the perception "model hash", so a changed
 * threshold is a changed model. Values marked (fit) are to be re-fitted on
 * field photos by scripts/fit_tier0.mjs; current values were tuned on the
 * public Zenodo 20254934 onion photos (see docs/SOURCES.md D1).
 */
export const TIER0 = {
  id: 'tier0-lab',
  version: '1.0.0',
  workSide: 1024,              // analysis resolution, long side px
  seg: {
    borderFrac: 0.04,          // image border ring used to model background
    minDeltaE: 14,             // (fit) minimum colour distance from background
    closeR: 2, openR: 2,
    shadowMaxC: 10, shadowMaxL: 62, shadowMinL: 28,  // (fit) dark near-neutral = shadow/crevice
    smallHoleFrac: 0.0008,
    minAreaFrac: 0.0015,       // components smaller than this share of the image are dropped
    maxAspect: 3.0,
    minSolidity: 0.6,
    wsMinPeakFrac: 0.012,      // peak distance >= this * long side
    wsNms: 1.35,               // peaks closer than nms*radius are the same bulb
  },
  defects: {
    erode: 3,                  // px shaved off the bulb edge before colour analysis
    refLo: 0.35, refHi: 0.9,   // L quantiles defining "healthy skin" reference pixels
    blackDL: 22, blackMaxL: 45, blackMaxC: 16, blackAbsL: 30, blackAbsC: 9,                  // (fit)
    rotDL: 20, rotMinC: 12, rotMinHue: 35, rotMaxHue: 95,                                      // (fit)
    brightDL: 18, sunburnMaxCRatio: 0.55,
    specMinRefC: 16, specMaxC: 12, specDL: 14,                   // (fit) highlights on glossy skin                        // (fit)
    spotDE: 18,                                                  // (fit)
    sproutMinHue: 95, sproutMaxHue: 170, sproutMinC: 14,         // (fit) degrees in Lab a*b* plane
    minBlob: 6,                // px; smaller defect specks are noise
    minBlobFrac: 0.004,        // ... or smaller than this share of the bulb
    fsdBase: 25,               // per-mille, 1-sigma fraction uncertainty (ASSUMED A-FSD-1)
    rhoCap: 0.9,
    rimRho: 0.92,              // rim pixels are too foreshortened/shaded to classify
  },
  shape: { doubleSolidity: 0.86, splitSolidity: 0.78, bottleneckAspect: 1.55 },
  conf: { minPx: 900 },        // bulbs smaller than this many px get low confidence
  guard: {
    minSharp: 55,              // Laplacian variance on the 480px preview (fit)
    minMeanL: 28, maxMeanL: 88,
    maxClipped: 0.05,          // fraction of near-saturated pixels
    maxTiltDeg: 12,
    minBulbs: 1,
  },
  intrinsics: { hfovDeg: 66, defaultCamHmm: 380, camHsdFrac: 0.12 },
} as const;

export type Tier0Config = typeof TIER0;
