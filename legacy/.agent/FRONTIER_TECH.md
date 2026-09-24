# FRONTIER TECH — adoption ledger
(working-code adoptions of booming tech, with honest rationale)

## Adopted

### 1. DIGITAL TWIN — quality-drift simulator (LOOP-T2214)
**Files:** `app/twin.py` (pure functions), `/api/twin/{lot_id}` in `app/main.py`,
panel in `app/static/dashboard.html`, `tests/test_twin.py` (17 tests),
smoke-test block in `scripts/smoke_test.py`.

**What it is:** a forward simulator over the hash-chained ledger. It replays a
certified lot's recorded bulb observations under a seeded deterioration
scenario and answers, in milliseconds and offline: *"if quality degrades X%,
what happens to saleable Grade A % and farmer payout?"*

**Why this is a real twin and not a slide word:**
- Data source IS the ledger (`lots.result_json` + `bulbs` rows) — the tamper-
  evident record gives the twin a trustworthy initial condition; simulation
  gives the record predictive power. Neither alone does that.
- Payout reuses `arbitration.fair_price_band` — the SAME pricing code as the
  certificate — under an explicit "cull model" (defective bulbs unsaleable).
- Deterministic: default seed derives from lot id alone via SHA-256 (never
  Python's salted `hash()`), so one lot has ONE degradation ordering;
  severity sweeps are nested and comparable. Same question -> same answer,
  every time, on stage.
- Two data paths with honest labelling: per-bulb (true class x size joint
  distribution, `data_source:"bulbs"`) vs aggregate fallback from
  proportions only (documented independence assumption). Every block is
  labelled measured vs simulated.

**What the model assumes (stated in every API response):**
1. Each sound bulb degrades independently with probability = severity.
2. New defects join existing defect classes proportionally; a defect-free
   lot rots (storage failure is microbial).
3. Size grade never changes (rot doesn't shrink bulbs here).
4. Per-quintal price of what REMAINS can rise if drift kills low grades
   first — so the response also carries `value_index` = price x saleable
   fraction per delivered quintal, which can only fall. On live demo data
   (lot SMOKE-01 @ 20% drift): price +16 INR/q but value index −140.75 INR/q
   — exactly why both numbers are reported.

**Honest limitations:** it simulates bulb-level deterioration, not storage
physics; the aggregate path cannot know the joint size-defect distribution;
rates are demo defaults; nothing here predicts WHEN drift happens — only its
impact if it does.

**Verification:** `py -3.11 -m pytest tests/test_twin.py -q` (17 passed);
full suite 190 passed; smoke test twin block all PASS against a live server;
`GET /api/twin/45?severity=0.2` returns labelled deterministic JSON.

### 2. DL GOOD PRACTICE — reliability diagram + ECE feeding the REFER threshold (LOOP-T2258)
**Files:** `app/calibration.py` (pure functions, numpy only),
`scripts/eval_calibration.py` (the measurement), `/api/calibration` in
`app/main.py`, panel in `app/static/dashboard.html`,
`tests/test_calibration.py` (31 tests), smoke-test block,
`runs/report/calibration.json` + `reliability_diagram.png`.

**What it is:** the standard deep-learning calibration toolkit pointed at
the one number our certificate leans on: detector confidence. The
ACCEPT/REFER policy promises that a call ≥ 0.75 needs no human double-check.
This adoption measures whether the promise holds and turns the answer into
policy input.

- `eval_calibration.py` runs the PINNED deployment path (end2end from
  constants.json, imgsz 1024, max_det 300) over hand-labelled trays and
  treats every detection as one (confidence, was-it-right) sample via
  same-class IoU≥0.5 greedy matching.
- Outputs ECE/MCE, a reliability diagram, a binary temperature-scaling fit,
  and a RECOMMENDED accept cut: smallest threshold whose top slice is right
  ≥95% of the time with ≥30 samples of support.
- The dashboard panel renders the curve offline from binned data — no model
  call, no network; unmeasured deployments get a hint, not a dead panel.

**Measured result (valid split, n=1646 detections / 1623 GT boxes):**
ECE 0.0314 — confidence is within ~3 points of true accuracy on average.
Top band: stated 0.967 vs observed 0.996 (slightly underconfident).
Temperature T=0.61 would sharpen ECE to 0.0032. Precision at the current
0.75 line: 0.994. The recommender reports "any cut ≥ 0.05 is ~98% right"
— and the script's safety band REFUSES to write that into constants.json:
moving a signed-certificate threshold stays a human decision; on this model
confidence is so concentrated that the binding constraint is recall, not
the cut. That refusal path IS the feature working as designed.

**Why this is real practice, not a slide word:** it changed what we can
CLAIM about the demo ("ECE 3.1 points, measured") instead of asserting the
0.75 line means something; tests pin the math (perfect calibration → ECE≈0;
overconfidence → T>1 fixes it; pinned-at-half confidences reported as
unfittable rather than fitted). Supersedes train.py's ad-hoc centre-distance
reliability plot with standard IoU matching + actual error numbers.

**Honest limitations:** correctness = IoU match, not semantic truth;
temperature scaling cannot fix bad RANKING, only systematic bias, and its
helpful direction depends on which side of 0.5 the mass sits (documented in
the module); measurement is per-split — recalibrate after any retrain or
venue-machine change.

**Verification:** `py -3.11 -m pytest tests/test_calibration.py -q`
(31 passed); full suite 375 passed; smoke test ALL PASS against a live
server (`/api/calibration answers … carries measured ECE … ECE 0.03136`).

## Considered and rejected
- external LLM in demo path: rejected (offline-first, network risk on stage)
- deriving twin seeds from (lot, severity): rejected after testing — makes
  each answer reproducible but severity sweeps non-comparable (different
  random orderings); seed now derives from lot only.
