"""Digital twin of a SAMA procurement lot -- forward simulation on ledger data.

WHY THIS EXISTS
---------------
The hash-chained ledger is a trustworthy record of what WAS graded. It cannot
answer "what happens to Grade A % and farmer payout if quality degrades 10%"
without waiting for reality to do the experiment. The twin replays a lot's
recorded bulb observations forward under a seeded deterioration scenario and
answers that question in milliseconds, deterministically, offline.

DATA SOURCE (the honest part)
-----------------------------
The twin reads ONLY what the certificate already recorded: lots.result_json
and the per-bulb rows. It never re-runs the model, never touches a camera,
never calls a network. Two data paths:

* per-bulb (preferred): bulbs rows carry the true joint distribution of
  class x size grade, so each sound bulb degrades individually.
* aggregate fallback: when only result_json proportions exist, degraded
  observations must be allocated to size bands under an explicit
  independence assumption (defects hit every size band equally). The
  response says which path ran via "data_source" -- an aggregate-mode number
  must not be mistaken for the per-bulb one.

DETERMINISM
-----------
Same lot + same severity + same seed -> byte-identical output. The default
seed is derived from (lot_id, severity) with SHA-256, NOT Python's hash(),
which is salted per process and would make stage demos irreproducible.

DEGRADATION MODEL (assumptions stated, not hidden)
--------------------------------------------------
1. Each SOUND bulb observation degrades independently with probability =
   severity. Per-bulb uniforms are drawn once and thresholded, so raising
   severity can only enlarge the degraded set (monotonicity by construction).
2. A degraded bulb joins an existing defect class, chosen proportional to
   the lot's current defect mix; a defect-free lot rots (storage failure is
   overwhelmingly microbial). Size grade is unchanged: rot does not shrink
   a bulb inside this model.
3. SALEABLE Grade A means sound AND size-band-A. This differs from the
   certificate's size-only Grade A % on purpose; the twin reports both so
   the gap is visible rather than smuggled.
4. PAYOUT uses arbitration.fair_price_band -- the SAME pricing code as the
   certificate -- on the sound-only mix renormalised to 100% ("cull model":
   defective bulbs leave the saleable pool). Baseline price is recomputed
   under the identical rule, so the delta isolates drift, not accounting.

Every number is labelled measured (read from the ledger) or simulated.
"""

from __future__ import annotations

import hashlib
import math
import random

from app import arbitration, grading

CLASS_NAMES = grading.CLASS_NAMES
DEFECT_CLASSES = grading.DEFECT_CLASSES

DEFAULT_SEVERITY = 0.10

ASSUMPTIONS = [
    "Each sound bulb degrades independently with probability = severity.",
    "Degraded bulbs join existing defect classes proportionally; a "
    "defect-free lot degrades to rotten (storage-rot prior).",
    "Size grade never changes: rot does not shrink a bulb in this model.",
    "Payout is the cull model: defective bulbs are unsaleable and the "
    "sound-only mix is renormalised to 100%; rates are demo defaults.",
    "Per-quintal price of what REMAINS can rise if drift removes low "
    "grades first; value_index (price x saleable fraction, i.e. per "
    "delivered quintal) is the payout figure that can only fall.",
    "Saleable Grade-A intervals use the certificate's cluster-aware width: "
    "repeated looks re-observe the same bulbs (effective sample = "
    "observations / looks at worst case).",
]

_LABELS = {
    "baseline": "measured",
    "scenario": "simulated",
    "price_model": "simulated",
}


# --------------------------------------------------------------------------
# Seeding
# --------------------------------------------------------------------------


def default_seed(lot_id: int) -> int:
    """Stable seed from the LOT ALONE, not (lot, severity).

    One lot therefore has ONE degradation ordering; sweeping severity
    samples that same ordering at different thresholds, so scenarios are
    nested and directly comparable (a 30% run contains the 10% run).
    Deriving per-severity seeds would make each answer reproducible but
    the sweep meaningless. Not Python hash(): salted per process.
    """
    payload = f"sama-twin|{int(lot_id)}"
    return int.from_bytes(hashlib.sha256(payload.encode("utf-8")).digest()[:8],
                          "big")


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------


def _pct(count: float, n: float) -> float:
    return round(100.0 * count / n, 2) if n > 0 else 0.0


def _sound_mix_pct(sound_by_grade: dict[str, float]) -> dict[str, float] | None:
    """Renormalise the sound-only size mix to 100%, or None if nothing sound."""
    total = sum(max(0.0, v) for v in sound_by_grade.values())
    if total <= 0:
        return None
    return {g: round(100.0 * max(0.0, v) / total, 2)
            for g, v in sound_by_grade.items() if max(0.0, v) > 0}


def _clamp_looks(n_looks, n: int) -> int:
    """Same rule as arbitration._clean_looks: a look has >=1 observation,
    so counts above n_obs are impossible and garbage means ONE look.
    Kept local so arbitration's private helper stays private."""
    try:
        m = int(n_looks)
    except (TypeError, ValueError):
        return 1
    return max(1, min(m, max(1, int(n))))


def _saleable_block(n: int, saleable_a_count: float,
                    sound_by_grade: dict[str, float],
                    defect_count: float, n_looks=None) -> dict:
    """One baseline/scenario block: Grade-A stats + cull-model price.

    LOOP-D2262 / RT-001 S-2a: the interval uses the SAME cluster-aware
    arithmetic as the certificate (arbitration.grade_a_ci_fields): repeated
    looks re-observe the same bulbs, so both Wilson counts scale by the
    worst-case Kish design effect and p_hat is preserved exactly. A twin
    card must never promise less uncertainty than the signed record it
    annotates -- before this fix a two-look lot showed +/-12 pts here while
    its certificate carried +/-16.5. Single-look lots reproduce the legacy
    width bit-for-bit and are labelled wilson-independent.
    """
    looks = _clamp_looks(n_looks, n)
    deff = arbitration.design_effect(looks)
    lo_pct, hi_pct = arbitration.wilson_pct_effective(saleable_a_count, n, deff)
    mix = _sound_mix_pct(sound_by_grade)
    price = None
    if mix is not None:
        band = arbitration.fair_price_band(
            mix, round(lo_pct, 2), round(hi_pct, 2))
        central = band["central_price"]
        # Realisation per ORIGINAL quintal: what a quintal of the as-delivered
        # lot is worth once defective bulbs are culled. Per-quintal price of
        # the REMAINING mix can legitimately RISE if drift kills low grades
        # first; this index cannot -- it is the honest farmer-payout signal.
        value_index = round(central * max(0.0, n - defect_count) / n, 2)
        price = {"central_inr_per_quintal": central,
                 "band_low": band["band_low"], "band_high": band["band_high"],
                 "value_index_inr_per_quintal_delivered": value_index,
                 "rates_used": band["rates_used"]}
    return {
        "n_observations": n,
        "n_effective": int(math.floor(n / deff)) if n > 0 else 0,
        "design_effect": round(deff, 4),
        "ci_method": ("wilson-independent" if deff == 1.0
                      else "wilson-clustered-two-look"),
        "n_sound": round(n - defect_count, 2),
        "defect_rate_pct": _pct(defect_count, n),
        # Certificate convention counts the size band regardless of class,
        # so it CANNOT move under class drift. Callers fill this in from the
        # ledger so the constancy is visible rather than smuggled.
        "grade_a_pct_size_band": None,
        "saleable_grade_a_pct": _pct(saleable_a_count, n),
        "saleable_grade_a_ci_low_pct": round(lo_pct, 2),
        "saleable_grade_a_ci_high_pct": round(hi_pct, 2),
        "sound_size_mix_pct": mix,
        "price": price,
    }


def _delta(baseline: dict, scenario: dict) -> dict:
    def _pt(key):
        b, s = baseline[key], scenario[key]
        if b is None or s is None:
            return None
        return round(s - b, 2)

    payout_b = (baseline.get("price") or {}).get("central_inr_per_quintal")
    payout_s = (scenario.get("price") or {}).get("central_inr_per_quintal")
    payout_delta = (round(payout_s - payout_b, 2)
                    if payout_b is not None and payout_s is not None else None)
    payout_pct = (round(100.0 * (payout_s - payout_b) / payout_b, 2)
                  if payout_b not in (None, 0) and payout_s is not None
                  else None)

    def _vi(block):
        return ((block.get("price") or {})
                .get("value_index_inr_per_quintal_delivered"))

    vi_b, vi_s = _vi(baseline), _vi(scenario)
    vi_delta = (round(vi_s - vi_b, 2)
                if vi_b is not None and vi_s is not None else None)
    vi_pct = (round(100.0 * (vi_s - vi_b) / vi_b, 2)
              if vi_b not in (None, 0) and vi_s is not None else None)
    return {
        "saleable_grade_a_pts": _pt("saleable_grade_a_pct"),
        "defect_rate_pts": _pt("defect_rate_pct"),
        "payout_inr_per_quintal": payout_delta,
        "payout_pct": payout_pct,
        "value_index_inr_per_quintal_delivered": vi_delta,
        "value_index_pct": vi_pct,
    }


# --------------------------------------------------------------------------
# Per-bulb path
# --------------------------------------------------------------------------


def _bulb_class(row: dict) -> str:
    raw = row.get("cls")
    if isinstance(raw, str) and raw in CLASS_NAMES:
        return raw
    try:
        idx = int(raw)
        if 0 <= idx < len(CLASS_NAMES):
            return CLASS_NAMES[idx]
    except (TypeError, ValueError):
        pass
    return "sound"


def simulate_from_bulbs(rows: list[dict], severity: float,
                        rng: random.Random, n_looks=None) -> tuple[dict, dict]:
    """Degrade individual bulb rows. Returns (baseline, scenario) blocks.

    `n_looks` is the recorded look design of the source lot; it only affects
    the confidence-interval width (cluster-aware, see _saleable_block), never
    the simulation itself.
    """
    n = len(rows)
    classes = [_bulb_class(r) for r in rows]
    grades = [(r.get("size_grade") or "UNKNOWN") for r in rows]

    defect_counts = {c: 0 for c in CLASS_NAMES}
    n_sound_obs = 0
    for c in classes:
        if c != "sound":
            defect_counts[c] += 1
        else:
            n_sound_obs += 1
    total_defects = n - n_sound_obs
    target_classes = [c for c in DEFECT_CLASSES if defect_counts[c] > 0]
    weights = [defect_counts[c] for c in target_classes]

    # One uniform per sound bulb, drawn BEFORE any class assignment, then
    # thresholded: larger severities degrade strictly nested subsets.
    uniforms = [rng.random() for _ in range(n)]
    degraded_flags = [u < severity for u in uniforms]

    new_classes = list(classes)
    degraded_mix = {c: 0 for c in DEFECT_CLASSES}
    for i, flag in enumerate(degraded_flags):
        if not flag or classes[i] != "sound":
            continue
        if target_classes:
            pick = rng.choices(target_classes, weights=weights, k=1)[0]
        else:
            pick = "rotten"
        new_classes[i] = pick
        degraded_mix[pick] += 1

    base_sound_by_grade: dict[str, float] = {g: 0.0 for g in grades}
    scen_sound_by_grade: dict[str, float] = {g: 0.0 for g in grades}
    base_saleable_a = 0.0
    scen_saleable_a = 0.0
    scen_defects = 0
    for i in range(n):
        g = grades[i]
        base_sound_by_grade[g] += classes[i] == "sound"
        scen_sound_by_grade[g] += new_classes[i] == "sound"
        base_saleable_a += (classes[i] == "sound" and g == "A")
        scen_saleable_a += (new_classes[i] == "sound" and g == "A")
        scen_defects += new_classes[i] != "sound"

    # Certificate-convention size-band A% (class-blind), read off the ledger.
    band_a_base = sum(1 for g in grades if g == "A")
    size_band_pct = _pct(band_a_base, n)

    base = _saleable_block(n, base_saleable_a, base_sound_by_grade,
                           total_defects, n_looks)
    scen = _saleable_block(n, scen_saleable_a, scen_sound_by_grade,
                           scen_defects, n_looks)
    for block in (base, scen):
        block["grade_a_pct_size_band"] = size_band_pct

    k_degraded = sum(degraded_flags)
    return base, scen, {"count": k_degraded, "mix": degraded_mix}


# --------------------------------------------------------------------------
# Aggregate path (no per-bulb rows)
# --------------------------------------------------------------------------


def simulate_from_aggregates(result: dict, severity: float) -> tuple[dict, dict]:
    """Degrade expected counts from result_json proportions alone.

    Independence assumption: defects hit every size band equally within the
    sound population, so the sound pool shrinks uniformly across bands.
    Fully deterministic -- no RNG involved, seed unused on this path.
    """
    n = int(result.get("n_bulb_observations") or 0)
    if n <= 0:
        raise ValueError("lot has no recorded bulb observations")

    class_pcts = result.get("class_pcts") or {}
    grade_pcts = result.get("grade_pcts") or {}

    n_sound_f = n * (float(class_pcts.get("sound", 0.0)) / 100.0)
    total_defects_f = n - n_sound_f

    sound_share = {}            # each band's share of the whole lot
    for g in ("A", "B", "C", "UNDERSIZED", "UNKNOWN"):
        sound_share[g] = float(grade_pcts.get(g, 0.0)) / 100.0

    k = math.floor(max(0.0, min(1.0, severity)) * n_sound_f)

    def _pool(scale: float) -> dict[str, float]:
        return {g: n * share * scale for g, share in sound_share.items()}

    base_pool = _pool(n_sound_f / n if n else 0.0)
    scen_pool = _pool((n_sound_f - k) / n if n else 0.0)

    base = _saleable_block(n, base_pool.get("A", 0.0), base_pool,
                           total_defects_f, result.get("n_looks"))
    scen = _saleable_block(n, scen_pool.get("A", 0.0), scen_pool,
                           total_defects_f + k, result.get("n_looks"))
    size_band_pct = _pct(n * sound_share.get("A", 0.0), n)
    for block in (base, scen):
        block["grade_a_pct_size_band"] = size_band_pct

    degraded_mix = {c: 0 for c in DEFECT_CLASSES}
    degraded_mix["rotten"] = k   # aggregate mode carries no defect-mix detail
    return base, scen, {"count": k, "mix": degraded_mix}


# --------------------------------------------------------------------------
# Public entry point
# --------------------------------------------------------------------------


def simulate_lot(lot: dict, severity: float = DEFAULT_SEVERITY,
                 seed: int | None = None) -> dict:
    """Replay one certified lot forward under `severity` quality drift.

    `lot` is a db.get_lot()-shaped dict: needs `result` and optionally
    `bulbs`. Deterministic for fixed (lot id, severity, seed).
    """
    severity = float(severity)
    if not (0.0 <= severity <= 1.0):
        raise ValueError("severity must be within [0.0, 1.0]")

    result = lot.get("result") or {}
    rows = [b for b in (lot.get("bulbs") or [])
            if b.get("size_grade") or b.get("cls") is not None]

    if len(rows) >= int(result.get("n_bulb_observations") or 0) > 0:
        data_source = "bulbs"
        if seed is None:
            used_seed = default_seed(lot.get("id", 0))
            seed_source = "derived(lot_id)"
        else:
            used_seed = int(seed)
            seed_source = "explicit"
        rng = random.Random(used_seed)
        # LOOP-D2262: the recorded look design rides along so the twin's
        # intervals match the certificate's cluster-aware width.
        base, scen, degraded = simulate_from_bulbs(
            rows, severity, rng, (result or {}).get("n_looks"))
    else:
        data_source = "aggregate"
        used_seed = seed
        seed_source = "unused(no randomness on the aggregate path)"
        base, scen, degraded = simulate_from_aggregates(result, severity)

    return {
        "kind": "digital_twin_quality_drift",
        "labels": dict(_LABELS),
        "data_source": data_source,
        "seed": used_seed,
        "seed_source": seed_source,
        "severity": round(severity, 4),
        "lot_id": lot.get("id"),
        "lot_ref": lot.get("lot_ref"),
        "centre_name": lot.get("centre_name"),
        "baseline": base,
        "scenario": scen,
        "delta": _delta(base, scen),
        "degraded_observations": degraded,
        "assumptions": list(ASSUMPTIONS),
    }
