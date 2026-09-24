# Plan

Status as of the end of the autonomous run is in the "Gate status" column; evidence for each gate is in `reports/` and `docs/screens/`.

| Phase | Scope | Gate | Status |
|---|---|---|---|
| P0 | Audit, brief, sources, open questions, plan, human tasks | Documents exist and every domain number has a status | done (tag p0) |
| P1 | TypeScript core: rule packs, adjudication, lot statistics, SPRT, sampling draw, RFC 8785, Merkle log, signatures, compact QR payload; golden-vector parity with legacy Python | `npm test` green | done (tag p1-core) |
| P2 | Capture Guard, four calibration tiers, Tier-0 perception on device | Airplane-mode grading of a real photo on a phone | software done and tested in headless Chromium with a real photo as the camera feed (tag demo-safe-v1); real-phone check is T9 |
| P3 | Receipt, signing, revisions, contest flow, offline verifier, rule-pack time travel | Two-phone verification works | done in headless Chromium (second browser context, offline, empty database; tag demo-safe-v2); real two-phone check is T9 |
| P4 | Data engine, Tier-1 model, E1-E4 | Holdout report generated; ship decision | Tier 0 and Tier 1 evaluated on the same held-out public real photos; Tier 1 ships as a cross-check (tag p4-public-eval). E1-E4 scripts and templates ready, waiting for field data (T3-T7) |
| P5 | W5 sequential sampling, W6 weight and value, W8 fleet, W9 languages | Each visible in the demo | done |
| P6 | APK, replay demo, docs, pitch | Installable app, demo works in airplane mode | done: web app on GitHub Pages, debug APK in release v0.1.0-demo, offline load tested |

## Order of work after the field data arrives

1. T1 and T4 first (mat check, calipers and weights). Run `npm run eval:e1`; replace A-SCALE-1 and A-WEIGHT-1 with the fitted values.
2. T3 photos. Re-fit the Tier-0 thresholds in `packages/vision/src/config.ts` on the day-1 set only (a small grid search against the E3 labels and in-app corrections; the script is to be written once labelled field photos exist), then run the holdout evaluation on day 2 only.
3. T5 to T7. Run `npm run eval` for E2 to E4 and regenerate docs/EVALUATION.md.
4. T8 label review, then retrain Tier 1 on field crops (`scripts/train_tier1.py`). Ship it for a class only if it beats Tier 0 on the field holdout.
5. Update the pitch numbers slide from docs/EVALUATION.md. Never type a number by hand.

## Cut line

If time runs short before the finals, drop in this order: languages beyond Hindi, Marathi and Tamil; the fleet view; the indicative value. Never drop the receipt and verifier, or the E2, E3 and E4 studies.
