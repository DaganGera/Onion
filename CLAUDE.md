# Parakh (SIH 2026, PS 26031): onion lot grading instrument

Read docs/BRIEF.md for the full brief and docs/DECISIONS.md for deviations.

## Rules
- Real photos only for any reported number. No synthetic images anywhere. Every metric comes from a script writing `reports/*.json`; docs quote those files, never typed numbers.
- Perception (packages/vision) is probabilistic; adjudication (packages/core) is deterministic integer math. The verdict is a pure function of (measurements, rule pack, overrides, seed).
- Unknown domain facts are config + a row in docs/SOURCES.md (verified / press-report / assumed) + a line in docs/OPEN_QUESTIONS.md.
- Runtime dependencies MIT/Apache/BSD/ISC/OFL only. No AGPL (no Ultralytics).
- Offline-first: everything runs on the phone. No server in this build.
- The receipt is tamper-evident, not tamper-proof. Say exactly that.
- Docs in plain prose: no em dashes, no bold-label lists (humanizer rules).

## Layout
- packages/core: rule packs (packs/*.json), adjudicate, lot stats, SPRT, sampling, JCS, Merkle, signing, QR payload. Tests in packages/core/test.
- packages/vision: Tier-0 pipeline (config.ts holds every threshold; its hash is the model hash), calibration tiers, Capture Guard stats.
- apps/web: Preact PWA. screens/, lib/ (db, lots, vision worker, qr, i18n), locales/.
- tools/: e2e.mjs (Playwright), eval_*.ts, extract_crops.ts, viz.ts, make_golden.py.
- scripts/: Python training for Tier 1.
- legacy/: the old SAMA prototype, read-only.

## Commands
- `npm test` (vitest, core) · `npm run typecheck` · `npm run build` · `npm run dev`
- `node tools/e2e.mjs` after a build: headless Chromium end to end, writes reports/e2e.json and docs/screens/
- `node --import tsx tools/viz.ts <img> <out.png>`: debug overlay of Tier-0
- `node --import tsx tools/eval_zenodo.ts <zenodo "2. Bulb" dir>`: public-data evaluation
- `node tools/gen_eval_md.mjs`: regenerate docs/EVALUATION.md from reports/

## Gate status
P0 done · P1 done (p1-core) · P2/P3 software done (demo-safe-v1/v2), real-phone check pending (HUMAN_TASKS T9) · P4 public-data eval done, Tier 1 ships as cross-check, field studies pending · P5 done · P6 done (Pages: https://dagangera.github.io/Onion/, APK: release v0.1.0-demo)

## Deploy
- Web: `npm run build && bash tools/deploy_pages.sh`
- APK: `cd apps/web && npx cap sync android && cd android && gradlew assembleDebug` with JAVA_HOME=JDK 21 and sdk.dir in android/local.properties
