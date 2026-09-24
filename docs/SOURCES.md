# Sources and assumptions

Every domain number the app uses is listed here with a status. `verified` means we read it in the primary document. `press-report` means it comes from news coverage and no official circular was found. `assumed` means we picked a value so the software can run; it must be replaced by a measured or official value. Research was done on 24 Sep 2026.

## Procurement norms (rule packs)

We searched for the NAFED/NCCF circular or tender that sets the 2026 PSF onion specification and did not find it. One NAFED tender PDF that came up (nafed-india.com, 5 Mar 2026) is a sale notice for gram and masoor, not onion. All rule packs are therefore `press-report`.

| ID | Source | What it says | Status |
|---|---|---|---|
| S1 | Free Press Journal, "Nashik: NAFED Relaxes Onion Procurement Norms…", 4 Jun 2026. https://www.freepressjournal.in/pune/nashik-nafed-relaxes-onion-procurement-norms-providing-major-relief-to-farmers-hit-by-crop-damage | Minimum size 45 mm "compared to the earlier requirement of around 55 mm"; one peeled outer layer eligible; up to 30% blackening, up to 40% surface spots or discolouration, up to 10% sunburn; B-grade onions allowed | press-report |
| S2 | The Hitavada, 8 Jun 2026. https://www.thehitavada.com/Encyc/2026/6/8/farmers-seek-rs-3000-per-quintal-support-price-as-centre-eases-onion-procurement-norms.html | Size range widened from 45-65 mm to 35-70 mm; procurement rate around Rs 1,580/quintal | press-report |
| S3 | ETV Bharat / Business Standard, 7 Jun 2026. https://www.etvbharat.com/en/state/as-centre-eases-onion-procurement-norms-farmers-seek-rs-3000-per-quintal-support-price-enn26060701140 | Same 45-65 mm to 35-70 mm change (the Business Standard page returned HTTP 403 to our fetcher) | press-report |
| S4 | Free Press Journal, "Exporter Alleges Substandard Onions Procured At A-Grade Prices…", 3 Aug 2026. https://www.freepressjournal.in/pune/nashik-exporter-alleges-substandard-onions-procured-at-a-grade-prices-seeks-independent-probe-into-nafed-nccf-purchases | "URS (relaxed-specification) category"; URS "include smaller-sized and slightly blemished produce"; URS procurement stopped from 30 Jul 2026, Grade A only, at Rs 2,335/quintal | press-report |
| S5 | Indian Express via SuperKalam, 15 May 2026. https://superkalam.com/current-affairs/daily-news-analysis/15-05-2026/centre-to-begin-onion-procurement-today-2-lakh-tonne-target-set-pg5-a26bd968-b987-4a5f-9327-34ccaa0f5a35 | 2 LMT Rabi PSF target from 15 May 2026 via NAFED and NCCF; price raised from Rs 1,875 to Rs 2,125/quintal from 4 Jul 2026 (per search summary); 72% minimum recovery for Grade A stored six months | press-report |

How the packs use them (packages/core/packs/):

| Pack | Built from | Grade A size | URS size | Procured |
|---|---|---|---|---|
| in-psf-2026-pre-a | S2, S3 | 45-65 mm | none | A |
| in-psf-2026-pre-b | S1 | >= 55 mm | none | A |
| in-psf-2026-06-relaxed-a | S1-S4 | 45-65 mm | 35-70 mm, blackening <= 30%, spots <= 40%, sunburn <= 10% | A, URS |
| in-psf-2026-06-relaxed-b | S1, S4 | >= 55 mm | >= 45 mm, same tolerances | A, URS |
| in-psf-2026-07-30-a-only (default) | S4, S2, S3 | 45-65 mm | measured, not procured | A |

The default is the 30 Jul pack because S4 is the latest report and says it is the rule in force.

## Reference standards (structure only, no numbers copied into packs)

| ID | Source | What we took | Status |
|---|---|---|---|
| R1 | UNECE Standard FFV-25 Onions. https://unece.org/fileadmin/DAM/trade/agr/standard/fresh/FFV-Std/English/25_Onions.pdf | Class tolerances are stated "by number or weight"; Class I allows 10% not meeting the class but meeting Class II, of which at most 1% decay or below minimum; size is the maximum diameter of the equatorial section. We copied the structure: per-bulb classes, a lot tolerance, a separate stricter decay limit, and a configurable size metric | verified (search excerpt of the PDF) |
| R2 | USDA AMS onion grade standards. https://www.ams.usda.gov/grades-standards | Grades settle on sample percentages by weight | assumed (page not read in full) |
| R3 | Agmark Fruits and Vegetables Grading and Marking Rules, 2004, which lists onion among graded commodities. https://agritech.tnau.ac.in/amis/pdf/F_V_G_M_under_Agmark.pdf | Onion has an Agmark schedule; we did not obtain its grade table | verified that it exists; content not read |

## Datasets

| ID | Source | Licence | Used for |
|---|---|---|---|
| D1 | "Image Dataset of Red and White Onion Bulbs and Leaves", Zenodo, doi:10.5281/zenodo.20254934. Real photos from Pune markets, one phone (motorola edge 50 ultra), 1024x768. | CC-BY 4.0 | Tuning Tier-0 thresholds on a small viewed set; the image-level evaluation in reports/zenodo_tier0.json; the replay demo photos in apps/web/public/samples; Tier-1 training crops |

No synthetic or copy-paste images are used anywhere in this build.

## Third-party code in the runtime path

| Package | Licence | Why |
|---|---|---|
| preact | MIT | UI rendering, 4 KB |
| dexie | Apache-2.0 | IndexedDB wrapper for lots, captures, receipts, log |
| js-aruco2 (vendored in packages/vision/vendor/aruco) | MIT | ArUco marker detection for the printed mat |
| OpenCV ARUCO_4X4_1000 dictionary (inside the vendored file) | BSD-3-Clause | Marker codes matching the legacy mat (DICT_4X4_50 is its prefix) |
| qrcode-generator | MIT | Makes the receipt QR |
| jsqr | Apache-2.0 | Reads QR codes where BarcodeDetector is missing |
| lucide-preact | ISC | Icons |
| @fontsource IBM Plex Sans / Condensed / Mono, Noto Sans (Indic scripts) | OFL-1.1 | Fonts bundled for offline use |
| vite-plugin-pwa / workbox | MIT | Service worker and offline precache |
| onnxruntime-web (if a Tier-1 model ships) | MIT | Runs the ONNX model on the phone |

Development only: vite, vitest, fast-check, typescript, playwright, tsx, pngjs, jpeg-js (MIT/BSD/Apache).

## Assumed values (replace with measurements)

| ID | Value | Where | How to replace |
|---|---|---|---|
| A-GRADEA-1 | Grade A defect limits: blackening 5%, spots 10%, sunburn 2%, peeled 10% | packs | No source gives pre-relaxation tolerances. Ask a procurement officer (OQ3) |
| A-REJECT-1 | Hard reject if rot > 1%, sprouting > 1%, cut > 2% of surface | packs | These are detection floors, not norms (OQ4) |
| A-PEEL-1 | "One peeled outer layer" scored as peeled-skin area fraction | packs | Layers cannot be counted from a photo (OQ5) |
| A-LOT-1 | SPRT p0 = 10%, p1 = 25%, alpha 5%, beta 10%, max 8 trays, REFER if > 25% of bulbs need a human | packs | Official lot acceptance rule unknown (OQ6) |
| A-SCALE-1 | Relative scale sigma: mat 0.6%, A4 1.5%, coin 3%, camera-only 25% | core/sizing.ts | E1 size study |
| A-SEG-1 | 1.5 px boundary jitter in size sigma | core/sizing.ts | E1 |
| A-FSD-1 | 2.5% (1 sigma) uncertainty on area fractions at 50% coverage, shrinking toward 0 and 100% | vision/config.ts, core/adjudicate.ts | E2 repeatability |
| A-WEIGHT-1 | Weight = sphere of density 0.95 g/cm3 on mean Feret diameter, 18% residual | core/sizing.ts | Kitchen-scale fit (HUMAN_TASKS T4) |
| A-FOV-1 | Camera horizontal field of view 66 degrees; camera-only tier uses 380 mm height with 25% uncertainty | vision/config.ts | Read from the phone, or measure once per phone |
| A-REPLAY-1 | Stored demo photos analysed as if taken from 260 mm | web/lib/demo.ts | Replace the demo photos with the team's own photos on the mat |
| A-SAMPLE-1 | Draw ceil(sqrt(sacks)) sacks, at least 3 | core/sampling.ts | Official sampling plan unknown (OQ7) |
| A-RATE-1 | Indicative rate Rs 2,125/quintal (S5; S4 says Rs 2,335 from 30 Jul) | web settings | User types the day's rate |
| A-T0-* | Every Tier-0 colour threshold in packages/vision/src/config.ts | vision | Fit on field photos (scripts to come with field data) |
