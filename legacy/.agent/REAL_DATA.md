# REAL DATA — provenance & plan

## Acquired (2026-08-25)
**Zenodo 20254934** — "Image Dataset of Red and White Onion Bulbs and Leaves"
- 12,260 real bulb photos, Pune (Maharashtra, India) local markets, Motorola 50 Ultra
- healthy/unhealthy × red/white × single/multiple, 1024×768
- Ingested: 4,800 bulbs (2,400 sound / 2,400 rotten) → data/real/bulbs/
  train 4,317 · holdout 483 (10%, deterministic hash split)
- Bootstrap YOLO boxes via color segmentation (scripts/ingest_real_zenodo.py)
- Full provenance in data/real/bulbs/PROVENANCE.csv (original label kept —
  unhealthy→rotten mapping is approximate; relabeling is lossless)
- Also available if needed: data/public/onion-spoilage (772) + onion-sorting (1616)

## Honest caveats
- "unhealthy" is a coarse label: mostly rot/mold lesions but includes some
  damaged-skin and sprout samples. Fine for sound-vs-defect; per-class
  refinement needs human spot-checks (bootstrap_label philosophy).
- Single-bulb shots dominate; tray-like multi-bulb shots are 2,120 of 4,800.
- No ArUco mat in these photos → they train the DETECTOR, not the sizer.
  Size measurement still needs either the printed mat or the mat-free mode.

## Mat-free sizing (replaces printed sheet dependency)
- Primary: phone ARKit/ARCore depth via WebXR when available (modern phones)
- Fallback: reference-object sizing — any common object of known size in frame
  (₹10 coin = 27mm, ATM card = 85.6×54mm, A4 sheet) with a UI prompt
- Fallback 2: carried homography from last successful mat detection
- Last resort: relative-size grading (bulb-vs-bulb percentile) → certificate
  marked PROVISIONAL, no certified ICAR-DOGR bands
