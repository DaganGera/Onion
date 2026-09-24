# Project brief (as given by the team, 24 Sep 2026)

This is the brief the build follows, kept verbatim apart from formatting. Where the build deviates, docs/DECISIONS.md says so and why.

## Problem statement

ID 26031 (the old README said 26046; verify on the SIH portal). Ministry of Consumer Affairs, Food & Public Distribution, Department of Consumer Affairs. Category Software, theme Smart Automation.

Title: Quality assessment and grading of onions is often subjective and varies across procurement centres, resulting in disputes and inconsistencies.

Expected: an AI-based mobile app that (1) uses image processing to assess onion quality, (2) identifies damaged, rotten, sprouted or undersized onions, (3) estimates Grade A and URS percentages, (4) generates a digital quality report instantly, (5) reduces human bias and improves transparency.

## What existed

Repo github.com/DaganGera/Onion (branch agent/frontier-2258), an earlier LLM-built prototype called SAMA: FastAPI + two static HTML pages, YOLO26 detector, lot-level statistical grading (Wilson CI, REFER band below 0.75 confidence, two-look merge), SQLite hash chain, ArUco calibration mat, replay mode, gates T0-T12. Its README admits all model metrics are from synthetic data. The team's technical-approach and research slides were LLM-written: treat every claim in them as an unverified hypothesis.

## The bar

Many teams answer this PS with the same pattern: YOLO box detector + classifier + PDF report. Ours must be recognisably different in three ways:
(a) it works on real onions photographed with ordinary phones in ordinary light;
(b) it is a measurement instrument with honest uncertainty, not a classifier with a confident label;
(c) every verdict is contestable, reproducible and verifiable by the party who disagrees.
We are building three things: an instrument, a rulebook, and a receipt.

## Non-negotiables

1. Real-world first. Synthetic or copy-paste-augmented images may be used for training and stress tests, never for any reported accuracy. All reported numbers come from scripts that write to reports/*.json and are rendered into docs. Never type a metric by hand. Never quote a number a script did not print.
2. No dataset applications, no annotation vendors, no paid APIs. Free and open-source only. Anything shipped in the runtime path must be MIT/Apache/BSD (no AGPL). Teacher models used only for offline labelling must have their licence noted in docs/SOURCES.md.
3. Offline-first. All inference runs on the phone. A server is optional (sync, transparency log, fleet dashboard) and the demo must work with airplane mode on.
4. Perception is probabilistic; adjudication is deterministic. Keep them in separate layers. The verdict is a pure function of (stored per-bulb measurements, rule pack), so anyone can recompute it.
5. Do not invent domain facts. Anything unknown becomes a configurable value plus a flag in docs/SOURCES.md (status: verified / press-report / assumed) and a line in docs/OPEN_QUESTIONS.md.
6. Always demoable: main is never broken. Tag after every gate. Small commits.
7. Solo-scale engineering: boring, reliable tech; every dependency justified in one line; no rewrites for taste. Where there is a choice between clever and verifiable, pick verifiable.
8. Verify, don't assume: read installed package versions and docs before using an API; run everything; test the capture flow in headless Chromium (Playwright with a fake video/image capture device) and on a real phone.

## Domain facts to encode

- Procurement norms for NAFED/NCCF buffer stock were relaxed around June 2026. Press reports disagree on the numbers (size window 35-70 mm vs. minimum 45 mm; previously about 45-65 mm or a ~55 mm minimum). Reported tolerances: blackening up to 30%, surface spots/discolouration up to 40%, sunburn up to 10% of the bulb, one peeled outer layer allowed. Find the official circular or tender; if not found, encode both variants as separate rule packs labelled press-report.
- These tolerances are per-bulb surface-area fractions, so perception must do dense segmentation with area fractions, not box classification.
- URS is undefined. Do not invent an expansion. Implement URS as a rule-pack-defined bucket with an explicit default assumption stated on the certificate, and list it first in OPEN_QUESTIONS.md.
- Procurement is settled by weight, not count. Percentages must be estimated by weight.
- Use the structure (not the numbers) of the UNECE/EU onion marketing standard (Class I/II tolerances) and the USDA onion standards (sample-based percent-by-weight settlement); check Agmark for onion specifications.

## Architecture

Six layers, one TypeScript grading core shared by phone, verifier page and tests.

- App: TypeScript PWA (Vite + Preact, IndexedDB via Dexie) wrapped with Capacitor into an Android APK. Camera via getUserMedia, offline via service worker, mid-range Android in Chrome.
- On-device ML: ONNX Runtime Web (WebGPU when available, WASM SIMD fallback). INT8 models, total <= 15 MB. Capture-to-verdict p95 <= 4 s on the test phone.
- packages/core (pure TypeScript, vitest + fast-check): rule-pack engine, sizing math, lot statistics, canonical serialisation. Port app/grading.py with golden-vector parity tests, then retire the Python copy.
- Server optional (FastAPI allowed): certificate sync, Merkle transparency log, fleet dashboard. The verifier re-runs the TS core in the browser.
- Offline training/eval scripts in Python (PyTorch).

L1 Capture Guard: live camera only; gates for level, blur, glare, exposure, calibration target, enough bulbs; auto-shutter; one plain sentence for every refusal; tag time, coarse location, device id.
L2 Perception: calibrate to mm, segment each bulb, split touching bulbs; per-bulb size, shape flags (double, bottleneck, split) and dense defect masks with area fractions for blackening/black mould, rot/wet lesions, sunburn, spots/discolouration, sprouting, peeled skin, cuts.
L3 Adjudication: versioned, hashed rule packs map measurements to GRADE_A / URS / REJECT / REFER with reason codes such as BLACKENING_34PCT_GT_30PCT. Deterministic.
L4 Lot inference, including sampling advice.
L5 Trust: evidence bundle, signatures, hash chain, transparency log, offline QR verification, contest workflow.
L6 Fleet: per-centre calibration drift, inspector-vs-AI disagreement, repeatability trends.

## Size and calibration

Calibration tiers with propagated uncertainty: (1) printed ArUco mat, (2) plain A4 sheet, (3) known-diameter coin, (4) camera intrinsics + tilt (wide uncertainty; forces REFER for size-borderline bulbs). Tier printed on the certificate. Correct for the bulb equator sitting about one radius above the plane. Report min and max Feret; the pack chooses which one is the ring-gauge size. Fit weight = a * d^b from kitchen-scale data and propagate its error.

## Perception without a dataset

Tier 0 (day 1, no training): Lab segmentation against the mat, distance-transform watershed, per-bulb robust colour model so defects are deviations from that bulb's healthy skin, thresholds in config fitted on field photos; a complete demoable pipeline by itself.
Tier 1: a foundation-model teacher proposes masks on the team's photos, a human corrects them in an existing open-source tool, a small permissive student is trained and exported to ONNX INT8, with real-cutout copy-paste augmentation.
Tier 2: every in-app correction is saved as a labelled example; scripts/retrain.py rebuilds the student; models are versioned and hash-pinned into certificates.
Holdout captured on a different day/place/phone, never touched in training. If Tier 1 does not beat Tier 0 on a class, ship Tier 0 for that class and say so.

## Lot statistics

Cluster-aware intervals (bootstrap over trays), honest "bulb-observations", fitted two-look correction, Grade A / URS / Reject by count and by weight with 95% intervals, Bayesian Beta view for small samples, SPRT sequential sampling advisor (ACCEPT_LOT / REJECT_LOT / SAMPLE_MORE / REFER_TO_HUMAN), randomised sack/layer selection with a visible seed, and an indicative value range labelled indicative.

## Trust layer

Tamper-evident, not tamper-proof. Evidence bundle; RFC 8785 canonical JSON + SHA-256; per-centre hash chain; device-bound WebCrypto signature (ECDSA P-256, try Ed25519); append-only Merkle log with daily signed tree heads; QR with a compact proof verifiable offline on a second phone, including a re-grade; contest flow where overrides need a reason code, never overwrite the AI verdict, and create a new signed revision.

## Wow factors

Must: W1 rule-pack time travel, W2 area-fraction explainable grading, W3 offline QR receipt, W4 measured credibility (repeat-capture spread, Gauge R&R and human baseline). Should: W5 sequential sampling with randomised sacks, W6 weight-based percentages and indicative value, W7 correct-retrain-fix data engine. Could: W8 fleet dashboard, W9 English/Hindi/Marathi/Tamil UI with spoken read-out.

## Evaluation

E1 size vs caliper (bias, MAE, Bland-Altman per tier). E2 Gauge R&R (5 captures x 3 phones x 3 lights; SD and ICC of Grade A %; guard rejection rate). E3 human baseline (3 people x 60 bulbs; Fleiss kappa; AI vs majority). E4 lot truth (10 hand-sorted lots; Grade A % error; interval coverage). E5 robustness sweep. E6 on-device performance. Limitations published plainly.

## UX

Mobile-first, one thumb, readable in sunlight, no onboarding, three taps from launch to certificate. Result leads with the lot verdict and interval, then per-bulb tap-through. REFER is a neutral "needs human check". Print-ready A4 certificate and a WhatsApp image.

## Phases

P0 audit and plan; P1 core (tests green); P2 Capture Guard + calibration + Tier 0 on device (tag demo-safe-v1); P3 trust layer, certificate, verifier, contest, W1, W3 (tag demo-safe-v2); P4 data engine, Tier 1, E1-E4; P5 W5, W6, W8, W9; P6 hardening, APK, demo mode, docs, pitch. Cut from P5 bottom-up; never drop P3 or E2/E3/E4.

## Deliverables

README with a generated numbers table, docs/ARCHITECTURE.md, docs/EVALUATION.md, docs/LIMITATIONS.md, docs/SOURCES.md, model cards, docs/PITCH (10-slide outline, 3-minute video script, 25 hardest judge questions with honest answers).

## Answers given before the autonomous run (24 Sep 2026)

Repo is public; push occasionally. The two slide images are the research table and the technical-approach slide. Skip fill-ins and finish faster. Commits as DaganGera. Do not stall for approval; ask nothing. Install whatever is needed. Deploy if possible; use the Android SDK only if necessary. Use real onion images from the internet, never synthetic; phases are mine to decide. Pick the best options for SIH 2026 for default pack, URS wording, server, name, design, branding. Cover as many languages as is easy. Make demo data if needed. Use the humanizer, hallmark, ui-ux-pro-max and caveman skills. Be token efficient.
