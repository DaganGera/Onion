# STATISTICS NOTES — data-scientist working notes

## LOOP-D2218 / RT-001 S-2: "Wilson CI treats two looks as independent bulbs"

Status: ANALYSED + FIXED-BY-OVERLAY (grading.py NOT touched). Date: 2026-08-25.
Owner: data-scientist. Related: D4 (max-per-look estimator), D8 (S-3 defect-CI
overlay), RUN_STATE top risk "RT-001 S-1/S-2 open".

---

### 1. The estimand and the sampling unit

The certificate estimates θ = P(a bulb drawn from the LOT lands in size band A,
i.e. diameter ≥ 80 mm by ICAR-DOGR). The unit of inference is the **bulb**.

What we actually observe: `n_looks` photographs of the same tray(s), tray shaken
between looks. Look j yields detections; the SAME physical bulbs appear in more
than one look. `merge_looks` therefore holds **clustered observations**, clusters
= bulbs, cluster size mᵢ ∈ {1, 2} (seen once / seen twice; mᵢ=1 happens via
occlusion or a missed detection). Per CLAUDE.md convention `n_bulb_observations`
is honestly named — the bug is not the name, it is feeding that count to a
Bernoulli-interval formula that assumes independence.

### 2. Actual correlation structure

For bulb i let Yᵢⱼ = 1{look j places bulb i in band A}. Conditional on the bulb,
repeats share its true diameter dᵢ; they differ only by measurement error
(sizing noise, edge occlusion). Standard ANOVA decomposition of the binary
indicator gives intra-class correlation

    ρ = σ²_between-bulbs / (σ²_between + σ²_within)

Variance of the pooled proportion under this one-stage cluster design:

    Var(p̂_pool) ≈ p(1−p) · deff / n_obs,     deff = 1 + (m̄ − 1)·ρ   (Kish)

With m̄ ≤ 2 looks: **deff ∈ [1, 1+ρ] ⊆ [1, 2]**.

* ρ = 1 ⇔ every bulb re-measures identically (sizing error ≪ distance to the
  80 mm edge). Second look adds ZERO information; pooling halves the apparent
  variance for free — pure overconfidence.
* ρ = 0 requires measurement noise large enough that band membership is a coin
  flip re-drawn each look — physically implausible for diameter.
* Reality: sizing MAE at usable calibration rungs is a few mm (caliper per-rung
  tables) while most bulbs sit many-MAE away from a band edge, so flips are rare
  ⇒ ρ high, plausibly ≥ 0.7. We CANNOT estimate ρ from stored data: bulb rows
  carry no cross-look identity (no tracker), so pairing Yᵢ₁↔Yᵢ₂ is impossible
  post hoc. Estimating ρ would need instrumented captures with matched IDs —
  flagged as future work, see §7.

**Quantified overstatement being corrected:** at ρ=1 the pooled Wilson half-
width is short by √deff = √2 ≈ 1.41×. Worked example carried in tests:
n_obs=60, 2 looks, 36 band-A ⇒ p̂=60%. Pooled Wilson(36,60) = [47.37, 71.43],
half-width ±12.03 pts. Clustered Wilson at n_eff=30 = [42.32, 75.41],
half-width ±16.54 pts (+37%). The old interval quietly promised ±12 points
from what is effectively 30 distinct onions.

### 3. The honest fix, given ρ is unmeasurable here

Survey-statistics standard: effective sample size n_eff = n_obs / deff and
Wilson on (k·n_eff/n_obs, n_eff). Scaling BOTH counts preserves p̂ exactly, so
the interval stays centred on the already-printed statistic — the same
"cannot drift from the printed number" property D8 demanded for the defect CI.

ρ default = **1.0 (worst case)**, deliberately:
* Never claims more distinct evidence than "each bulb examined once".
* Mirrors the scale ladder philosophy (`app/scale.py`): conservative rung by
  default, upgrade only with a measured quantity. If someone later fits a real
  ρ (§7), pass it via the `rho` argument — the code refuses to guess silently.
* Cost of conservatism is small: at ρ_true = 0.7 the true deff is 1.7 vs our 2.0,
  i.e. we give up ≤ ~8% interval width vs a measured-ρ interval.

Single-look lots (n_looks = 1): deff = 1, interval identical to the frozen
pooled computation; fields are still emitted so the schema is uniform, labelled
`wilson-independent`.

### 4. What this fix does NOT claim (scope limits, stated on purpose)

1. **Not whole-lot variance.** Between-tray heterogeneity (lots spanning
   n_trays > 1 trays sampled from a larger lot) is a second design stage the
   clustered interval still ignores. Same caveat D8 wrote for defects; the
   report's method note already says "sample, not census".
2. **Defect rate unaffected — by construction.** D8's defect CI runs Wilson on
   the worst SINGLE look's (k,n), which is already the ρ=1 answer. After this
   change BOTH certificate intervals are effectively single-look-width. That
   symmetry is intentional and worth saying out loud at the demo.
3. **No backfill of legacy certificates.** `row_hash` covers `ci_low`/`ci_high`;
   rewriting stored rows is exactly what the hash chain exists to prevent. Old
   lots keep pooled-width intervals; the UI prints the method/effective-n chips
   ONLY when the new keys exist, so legacy rows self-label by absence.
4. **Downstream consumers widen, correctly.** `fair_price_band` inherits
   [ci_low, ci_high] → wider rupee band. `compare_lots` overlap verdicts use
   stored widths → narrower-interval false DISPUTEs become rarer (a dispute
   alleges fraud; the clustered width is the defensible one to allege with).
   `scripts/seed_demo` writes rows directly via `insert_lot` and bypasses the
   overlay — demo data, accepted.
5. **Follow-ups flagged, not done here (one-task discipline):**
   - S-2a: `twin.py::_saleable_block` computes Wilson on pooled n for the
     digital-twin price band — same duplication issue in a what-if context.
   - S-2b: `sample_sufficiency` plans in "observations"; under two looks its
     n_required should be quoted in bulbs (×n_looks) or switched to n_eff.

### 5. Where the fix lives (frozen-file discipline)

* `app/arbitration.py`: `design_effect`, `wilson_pct_effective`,
  `grade_a_ci_fields(result, rho)` — pure functions, reconstruction strictly
  from fields `merge_looks` already publishes (`grade_counts["A"]`,
  `n_bulb_observations`, `n_looks`; fallback to `grade_a_pct` reconstruction),
  clamps and NaN guards in the house style of `defect_rate_interval`.
* `app/main.py` `/finalize`: ONE added line `result.update(arbitration.
  grade_a_ci_fields(result))` beside the D8 line, so the clustered interval is
  what `insert_lot` hashes into `ci_low`/`ci_high`.
* `grading.py` UNTOUCHED. Its pooled fields remain in every payload as
  `grade_a_ci_pooled_low/high` for provenance; the overlay renames nothing it
  does not replace.

New result_json keys (all optional-consumers, absent only on degenerate input):
`grade_a_ci_low`, `grade_a_ci_high` (now clustered), `grade_a_ci_pooled_low`,
`grade_a_ci_pooled_high`, `grade_a_ci_method` (`wilson-clustered-two-look` |
`wilson-independent`), `grade_a_n_observations`, `grade_a_n_effective`
(floored — never rounds precision UP), `grade_a_design_effect`,
`grade_a_intra_class_corr`.

### 6. Verification

    python -m pytest tests/test_two_look_ci.py -q      # new contract tests
    python -m pytest -q                                # full suite stays green

Anchors used by the tests (hand-computed, z=1.96):
Wilson(36,60) = [47.37, 71.43]; Wilson(18,30) = [42.32, 75.41];
Wilson(21,35) = [43.57, 74.45] (the p̂=60% single-look reference point).
All three verified numerically before being pinned in tests.

### 7. To actually measure ρ later (pre-registration)

During captures, persist per-look bbox centres; match bulbs across looks by IoU
after shake (shake displacement is bounded, mat homography maps both looks to
one plane). Pair (Yᵢ₁, Yᵢ₂) over many lots → ρ̂ = P(agree) correction /
ANOVA estimator; feed back as `rho=` and record the fitted value in
constants.json next to the occlusion factors. Until then ρ=1 is the only
number the certificate is allowed to assume.

---

## LOOP-D2262 — S-2 executed everywhere it lived (S-2a + S-2b)

Date: 2026-08-25. Owner: data-scientist. grading.py STILL untouched; both
fixes reuse the D11 machinery (`arbitration.design_effect`,
`wilson_pct_effective`) so there is exactly ONE implementation of the
cluster-aware arithmetic in the codebase.

### 8a. Where the same bug still lived, and what changed

* **S-2a (`app/twin.py::_saleable_block`)** — the digital twin computed its
  saleable Grade-A band with plain `grading.wilson_interval` on pooled n.
  After D11 this was not just overconfident (√2 too narrow on two-look lots)
  but INTERNALLY INCONSISTENT: report page ±16.5 pts vs twin card ±12 pts for
  the same lot. Fix: `_saleable_block` takes `n_looks`, computes the band at
  deff = design_effect(m), and publishes `n_effective`, `design_effect`,
  `ci_method` alongside the existing keys. Threaded from result_json's
  recorded look design through BOTH simulators (per-bulb and aggregate), so
  baseline and scenario share one design basis and stay comparable.
  Single-look lots reproduce legacy numbers bit-for-bit.
* **S-2b (`arbitration.sample_sufficiency`)** — evaluated current precision
  with pooled Wilson and quoted `n_required` in independent units: the
  officer's card could print SUFFICIENT while the signed certificate carried
  a wider interval. Fix: optional `n_looks` (default 1 = exact legacy
  behaviour); current half-width now comes from `wilson_pct_effective`, i.e.
  the SAME numbers as `grade_a_ci_fields`. Requirements are reported in both
  units:
    - `n_required_distinct_bulbs` = ⌈z²·p̂(1−p̂)/w²⌉ — design-invariant;
      this is "how many onions examined once".
    - `n_required_observations`   = distinct × deff — what THIS design must
      photograph. At ρ=1 more shakes of one tray buy nothing; only new trays
      do. The advice copy says exactly that.
  `/api/sufficiency/{lot_id}` passes stored n_looks; index.html appends a
  bilingual "≈N distinct bulbs" chip when deff > 1.

### 8b. Correlation structure of the SIMULATED blocks (why deff on the scenario is honest)

Baseline blocks describe the measured lot → identical clustering argument as
§2, deff applies directly.

Scenario blocks are subtler. On the per-bulb path each ROW draws an
INDEPENDENT degradation uniform, so two rows of the same physical bulb can
simulate apart (one rots, one survives). Real repeats would degrade TOGETHER
(one bulb, one fate): simulated duplicates therefore correlate LESS than real
ones, which means the scenario interval WITHOUT deff would understate
variance less than the raw duplication suggests but still sit on duplicated
evidence. Applying deff = m to the scenario is thus CONSERVATIVE (never
anti-conservative), keeps both blocks on one comparable basis, and matches
the house rule: broken/unknown correlation widens, never shrinks. The
aggregate path has no RNG at all — its scenario uncertainty is purely the
sampling error of the measured mix propagated through the cull model — so
deff applies there for the same reason it applies to the baseline.

Monte-Carlo noise of the simulation itself remains uncovered by either
interval (as before D2262); it is seeded, deterministic, and small next to
sampling error. Stated here so nobody rediscovers it in front of a jury.

### 8c. Input hygiene (shared rule)

`n_looks` is clamped into [1, max(1, n_obs)] — more looks than observations
is impossible by construction (each look contributes ≥1 row) and clamping
there bounds deff ≤ n_obs. Garbage (None / non-numeric / ≤0) means ONE look:
inventing a multi-look design that was never recorded would silently widen
intervals nobody signed for. NaN raises inside int() and lands in the same
fallback. Implemented twice, deliberately small (`_clean_looks` private to
arbitration, `_clamp_looks` private to twin) rather than exporting a new
public helper mid-loop.

### 8d. Verification

    python -m pytest tests/test_two_look_followups.py -q   # 22 contracts
    python -m pytest tests/test_twin.py tests/test_two_look_ci.py -q
    python -m pytest -q                                    # 434 passed

Anchors reused from §6 (all hand-verified at z=1.96): pooled Wilson(36,60) =
[47.37, 71.43] ↔ clustered Wilson(18,30) = [42.32, 75.41]; Wilson(21,35) =
[43.57, 74.45]. New pins: Wilson(40,60) = [54.06, 77.27] ↔ Wilson(20,30) =
[48.78, 80.77]; planning sizes 267 distinct bulbs @ p=50%, 257 @ p=60%
(→ 534 / 514 observations at two looks).

### 8e. Still open

* §7 pre-registration: fit real ρ via cross-look IoU matching; pass through
  `rho=` / constants.json.
* S-1 (max-per-look defect estimator) remains a frozen-file decision —
  unchanged by this loop.
