# Model card: Tier 0 colour-and-geometry perception

**Id:** `tier0-lab@1.0.0`. The model hash printed on each receipt is the SHA-256 of the canonical JSON of `packages/vision/src/config.ts` (plus the Tier-1 weights hash when a Tier-1 model ships).

## What it does

For each photo it finds a scale (printed marker mat, A4 sheet, coin, or camera geometry), separates onions from the background in CIE Lab colour, removes cast shadows, splits touching bulbs with a distance-transform watershed, and measures every bulb: minimum and maximum Feret diameter in millimetres (corrected for the bulb's equator sitting above the table), a shape check (double, bottleneck, split), and the share of its visible surface in each defect class. Defects are deviations from the bulb's own lit skin: a plane-plus-rings shading model predicts how light each pixel should be, and a pixel is blackening, rot, sunburn, peeled, spots or sprouting depending on how its lightness, chroma and hue depart from that prediction. Rim pixels and glossy highlights are ignored. Pixel shares are weighted by a sphere model so the curved edge counts as much surface as it covers.

## Intended use

Grading onion lots at procurement centres under a rule pack, with a person deciding every bulb the app refers. It is not intended to replace a grader's final decision on a disputed lot.

## Data used to set thresholds

About 28 photos from the public Zenodo dataset 10.5281/zenodo.20254934 (CC-BY 4.0; Pune markets; one phone) were viewed while choosing thresholds. They are excluded from every evaluation. No synthetic images were used.

## Evaluation

See docs/EVALUATION.md (generated from `reports/zenodo_tier0.json`). The public-data test is image-level healthy vs unhealthy on held-out blocks of the same dataset. It does not measure size accuracy or agreement with graders; those are field studies E1 to E4, not yet run.

## Known failure modes

White onions on white backgrounds; piled onions; wooden, tiled or patterned backgrounds; dry root plates read as sunburn; shaded purple skin on red onions (mitigated by a hue gate on rot); cuts are not measured. See docs/LIMITATIONS.md.

## Licence

MIT (this repo). The vendored ArUco detector is js-aruco2 (MIT) with OpenCV's 4x4 dictionary (BSD-3-Clause).
