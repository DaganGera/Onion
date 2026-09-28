# SAMA

SAMA grades a lot of onions from a phone photo, follows a published rulebook, and issues a signed receipt that anyone can check on their own phone. It was built for Smart India Hackathon 2026, problem statement SIH26031 (Department of Consumer Affairs): onion grading at procurement centres is done by eye, varies between centres, and leads to disputes.

The name comes from the Sanskrit and Hindi *sam*, meaning same or equal. We want the same onions to get the same grade at every centre.

- Landing page and in-browser demo: https://dagangera.github.io/Onion/
- Web app: https://dagangera.github.io/Onion/app/
- Android APK (latest): https://github.com/DaganGera/Onion/releases/latest/download/sama.apk

Everything runs on the phone, including the models, storage and signing, so airplane mode is fine. SAMA is a prototype and not an official grading tool.

## How it works

1. Sign in. Supervisors, officers and auditors each have a PIN on the phone. Farmers never need an account.
2. Draw the sample. The farmer and the officer each type a code, and the two codes together pick which sacks to open.
3. Capture. The camera checks level, blur, glare, exposure and scale before the shutter fires, and explains any refusal in one sentence. A printed ArUco mat, an A4 sheet or a ₹5 coin sets the scale.
4. Measure. A U-Net model outlines every onion, including touching ones in a heap. Each onion gets a diameter in mm, an estimated weight, and the share of its visible skin with black mould, rot, spots, sunburn, sprouting or peel. A MobileNetV3 health check clears false marks caused by light or natural skin streaks.
5. Grade. A versioned, fingerprinted rule pack turns the measurements into Grade A, URS, Reject or "needs human check". An onion within measuring error of a limit goes to a person. Lot shares are reported by weight with 95% ranges, and a sequential test says whether to sample another tray.
6. Review. The officer can override a verdict with a reason and the farmer can contest one. The AI verdict is kept beside both, under the name of whoever acted.
7. Sign. The result is written as canonical JSON (RFC 8785), fingerprinted with SHA-256, signed with a key held on the phone, and packed into a QR code. Receipts form a hash chain and go into an append-only Merkle log (RFC 6962).
8. Verify. Any phone can scan the QR offline, check the signature, re-run the grading and confirm that the numbers match. Changing one character of the code makes it fail.

Norms changed twice in 2026, according to press reports. Rule packs are data, so the same stored measurements can be re-graded under any pack, and every receipt names the pack it used.

## Numbers

Generated from `reports/*.json` by `node tools/gen_eval_md.mjs`. Full tables and caveats are in [docs/EVALUATION.md](docs/EVALUATION.md). No number here comes from synthetic images.

<!-- numbers:start -->
| What | Result | Source |
|---|---|---|
| Tier 0 perception, public real photos (holdout) | healthy vs unhealthy AUC 0.765, accuracy 69.1% on 320 photos | reports/zenodo_tier0.json |
| Tier 1 vs Tier 0 on the same 306 held-out photos | AUC 0.975 vs 0.756; accuracy 90.8% vs 68.3% (single-bulb photos likely inflated, see caveats) | reports/zenodo_tier1.json |
| Onion counting, held-out photos counted by eye | mean error 0.56 onions (was 11.17 with colour rules); exact on 61.0% | reports/count_eval.json |
| Healthy onions wrongly failing Grade A (held-out) | 10.1% (was 91.9%); rot/mould photos caught 85.0% | reports/fit_gate.json |
| Browser end-to-end checks | 21/21 pass | reports/e2e.json |
| E1 size vs caliper | awaiting field data | reports/ |
| E2 repeatability | awaiting field data | reports/ |
| E3 human baseline | awaiting field data | reports/ |
| E4 lot truth | awaiting field data | reports/ |
<!-- numbers:end -->

The models were trained and tested on 12,260 real market photos from a public dataset (Zenodo 10.5281/zenodo.20254934, CC BY 4.0). Photos are split in blocks of 25 so near-duplicates cannot leak between training and testing. The accuracy and dataset details are in [docs/pitch-kit/06_Model_Accuracy_and_Datasets.md](docs/pitch-kit/06_Model_Accuracy_and_Datasets.md), and the model cards are in `docs/MODEL_CARD_*.md`.

## Try it

```bash
npm install
npm run dev            # web app on http://localhost:5173
npm -w @parakh/landing run dev   # landing page
```

Phones only allow the camera and the signing key over HTTPS, so on a phone use the hosted web app or the APK rather than the dev server's LAN address.

On first launch, tap **Explore the demo** to get three sample accounts: supervisor `1111`, officer `2222` and auditor `3333`. As the officer, **Load the demo lot** replays real market photos through the full pipeline. To grade real onions, print `apps/web/public/calibration_mat.pdf` at 100%, lay the onions on it in one layer, and point the camera straight down.

```bash
npm test                               # grading core and vision unit tests (vitest + fast-check)
npm run build && node tools/e2e.mjs    # headless Chromium end to end, fake camera fed a real photo
node tools/gen_eval_md.mjs             # rebuild docs/EVALUATION.md and the table above
bash tools/deploy_pages.sh             # publish landing (root) and web app (/app/) to GitHub Pages
```

The Android build is a Capacitor wrapper around the same web app (`apps/web/android`, `./gradlew assembleDebug`).

## Honest status

- The training photos come from one phone in one city. Field photos will look different, and the team's own photos still need to be added and the models retrained.
- Size against calipers, repeatability, and agreement with human graders are not measured yet. The field studies are in [docs/HUMAN_TASKS.md](docs/HUMAN_TASKS.md).
- The procurement limits come from press reports. No official circular was found, and nobody has confirmed what URS stands for.
- A camera sees only the outer skin. Weight is estimated from size until a kitchen-scale fit is loaded.
- A receipt is tamper-evident, not tamper-proof. It cannot prove that the photographed onions came from the sacks that were sold.

See [docs/LIMITATIONS.md](docs/LIMITATIONS.md), [docs/SOURCES.md](docs/SOURCES.md), [docs/OPEN_QUESTIONS.md](docs/OPEN_QUESTIONS.md) and [docs/DECISIONS.md](docs/DECISIONS.md).

**Phase 2:**
- an optional NIR sensor for internal rot
- linking rejected lots to dehydration, biogas and compost buyers
- sharing grades with e-NAM
- a conveyor sorter that runs the same models
- per-officer signing keys approved by the supervisor

## Map of the repo

| Path | What |
|---|---|
| `packages/core` | Grading core in TypeScript: rule packs, adjudication, lot statistics, SPRT, sampling draw, canonical JSON, Merkle log, signatures, QR payload |
| `packages/vision` | Capture guard, calibration, segmentation post-processing, colour defect measurement |
| `apps/web` | The Preact app (PWA), its models in `public/models`, and the Android wrapper |
| `apps/landing` | Landing page with a 3D onion and an in-browser onion counter |
| `scripts` | Model training in Python (PyTorch): teacher masks, segmentation, health check |
| `tools` | End-to-end tests, evaluation scripts, deploy script |
| `docs` | Brief, architecture, evaluation, model cards, limitations, sources, decisions, pitch kit |
| `legacy` | The earlier prototype, kept for reference; see [AUDIT.md](AUDIT.md) |

**Licences:**
- Code: MIT.
- Onion photos: Zenodo 10.5281/zenodo.20254934 (CC BY 4.0).
- 3D onion: Poly Haven (CC0).
- Background photos: Wikimedia Commons (credits in `apps/landing/public/photos/CREDITS.txt`).
- Runtime dependencies: MIT, Apache-2.0, BSD, ISC or OFL (listed in docs/SOURCES.md).

Team AlgoRangersV1.
