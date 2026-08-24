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

## Considered and rejected
- external LLM in demo path: rejected (offline-first, network risk on stage)
- deriving twin seeds from (lot, severity): rejected after testing — makes
  each answer reproducible but severity sweeps non-comparable (different
  random orderings); seed now derives from lot only.
