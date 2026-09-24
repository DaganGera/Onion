# Parakh

Parakh grades a lot of onions with a phone camera, following a published rule pack, and issues a signed receipt that anyone can check on another phone. It was built for Smart India Hackathon 2026, problem statement 26031 (Department of Consumer Affairs): onion grading at procurement centres is subjective and varies between centres, which leads to disputes.

The app has three parts. The first is a measuring instrument: it gives each bulb a size in millimetres and the share of its visible surface that is blackened, rotten, sunburnt, spotted, sprouting or peeled, and every number carries an uncertainty. The second is a rulebook: versioned, hashed rule packs turn those measurements into Grade A, URS, Reject or "needs human check", and a bulb that sits within measuring error of a limit goes to a person instead of being guessed. The third is a receipt: the result is signed on the phone, and its QR code lets a farmer, a buyer or an auditor re-run the same grading on their own phone, offline, and see whether it matches.

Everything runs on the phone. Airplane mode is fine.

Open it: https://dagangera.github.io/Onion/ (add it to the home screen to use it offline), or install the Android build from the [v0.1.0-demo release](https://github.com/DaganGera/Onion/releases/tag/v0.1.0-demo). Both are prototypes, not official grading tools.

## Numbers

Generated from `reports/*.json` by `node tools/gen_eval_md.mjs`. Full tables and caveats are in [docs/EVALUATION.md](docs/EVALUATION.md). No number here comes from synthetic images.

<!-- numbers:start -->
| What | Result | Source |
|---|---|---|
| Tier 0 perception, public real photos (holdout) | healthy vs unhealthy AUC 0.773, accuracy 70.9% on 320 photos | reports/zenodo_tier0.json |
| Tier 1 learned cross-check, same data (holdout) | AUC 0.984, accuracy 94.2% on 2234 photos | reports/zenodo_tier1.json |
| Browser end-to-end checks | 15/15 pass | reports/e2e.json |
| E1 size vs caliper | awaiting field data | reports/ |
| E2 repeatability | awaiting field data | reports/ |
| E3 human baseline | awaiting field data | reports/ |
| E4 lot truth | awaiting field data | reports/ |
<!-- numbers:end -->

## Try it

```bash
npm install
npm run dev          # http://localhost:5173, open on a phone on the same Wi-Fi
```

On the home screen, "Load the demo lot" replays four real market photos from a public dataset through the same pipeline. Or start a new lot, print `apps/web/public/calibration_mat.pdf` at 100%, put the onions next to it in a single layer, and point the camera down. The Capture Guard refuses blurry, dark, glary or tilted shots and says why in one sentence; when every check is green it takes the photo by itself.

Other commands:

```bash
npm test                         # grading core and vision unit tests (vitest + fast-check)
npm run build && node tools/e2e.mjs   # headless Chromium end to end, fake camera fed a real photo
node tools/gen_eval_md.mjs       # rebuild docs/EVALUATION.md and the table above
```

The Android build is a Capacitor wrapper around the same web app (`apps/web/android`, `./gradlew assembleDebug`).

## What is different about it

A box detector with a confident label is the common answer to this problem. The published norms are written differently: "up to 30% blackening, up to 40% spots, up to 10% sunburn" are fractions of a bulb's surface. Parakh measures those fractions per bulb (with a correction for the curve of the bulb), compares them with the pack's limits, and prints the reason as a code a machine can read, such as `BLACKENING_34.2PCT_GT_30PCT`.

Lot percentages are estimated by weight, because procurement settles by weight. Intervals come from resampling whole trays, because bulbs in one tray are not independent, and a second look at a shaken tray is never counted as new onions. A sequential test says after each tray whether to accept, reject, sample more, or hand over to an inspector. Which sacks get opened is drawn from codes typed by both the farmer and the officer, so neither side picks the sample alone.

Norms change (they changed twice in 2026, according to press reports). A rule pack is data, so the same stored measurements can be re-graded under any pack in one tap, and each result verifies on its own.

## Honest status

The perception is a colour-and-geometry model (Tier 0) with every threshold in one config file, tuned on public photos from one dataset. Its accuracy against human graders and calipers is unknown until the team runs the field studies in [docs/HUMAN_TASKS.md](docs/HUMAN_TASKS.md). The procurement limits come from press reports, and nobody has confirmed what URS stands for. See [docs/LIMITATIONS.md](docs/LIMITATIONS.md), [docs/SOURCES.md](docs/SOURCES.md) and [docs/OPEN_QUESTIONS.md](docs/OPEN_QUESTIONS.md).

## Map of the repo

| Path | What |
|---|---|
| `packages/core` | Grading core in TypeScript: rule packs, adjudication, lot statistics, SPRT, sampling draw, canonical JSON, Merkle log, signatures, QR payload |
| `packages/vision` | Tier-0 perception, calibration tiers, Capture Guard statistics |
| `apps/web` | The Preact app (PWA) and its Android wrapper |
| `tools` | End-to-end test, evaluation scripts, crop extraction, debug overlay |
| `scripts` | Tier-1 training (Python, PyTorch) |
| `docs` | Brief, architecture, evaluation, limitations, sources, decisions, human tasks, pitch |
| `legacy` | The earlier SAMA prototype, kept for reference; see [AUDIT.md](AUDIT.md) |

Licences: code MIT. Demo photos from Zenodo 10.5281/zenodo.20254934 (CC-BY 4.0). Runtime dependencies are MIT, Apache-2.0, BSD, ISC or OFL (listed in docs/SOURCES.md).

Team AlgoRangersV1.
