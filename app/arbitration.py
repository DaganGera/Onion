"""SAMA arbitration math: dispute verdicts, fair-price bands, sample sufficiency.

Pure functions only. No FastAPI, no model, no database. Everything here is
testable arithmetic -- the kind a judge will probe with "what if I disagree?"

WHY THIS MODULE WINS DISPUTES
-----------------------------
Two people grade the same lot and get 64% and 71% Grade A. Is that fraud,
incompetence, or normal measurement noise? Without statistics the answer is
whoever argues harder. With statistics it is arithmetic:

  * Two independent estimates carry Wilson confidence intervals. If the
    intervals OVERLAP, the readings are consistent with one underlying truth
    and there is nothing to fight about.
  * If they do not overlap, a two-proportion z-test says how implausible
    "same lot, same truth" really is, and the verdict names the gap in
    percentage points instead of naming a villain.

The fair-price band converts the certified grade mix into rupees per quintal,
bracketed by the SAME confidence interval as the percentage itself -- so the
uncertainty the farmer sees is the uncertainty the maths actually has, not a
round number invented for comfort.

Sample sufficiency answers the question every inspector eventually asks:
"how many onions do I actually have to look at?" before the tray hits the
table, not after.
"""

from __future__ import annotations

import math

# --------------------------------------------------------------------------
# Tunables. Deliberately boring and all in one place.
# --------------------------------------------------------------------------

Z95 = 1.96

# Default market rates in rupees per quintal by ICAR-DOGR size grade.
# These are DEMO defaults, clearly labelled as configurable wherever shown;
# a real deployment would load the day's mandi rates from a feed.
DEFAULT_RATES = {
    "A": 2400.0,
    "B": 1800.0,
    "C": 1200.0,
    "UNDERSIZED": 800.0,
    "UNKNOWN": 1000.0,
}

# Planning target for the Grade-A half-interval, in percentage points.
TARGET_HALF_WIDTH_PCT = 6.0


def _clamp_pct(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, float(value)))


# --------------------------------------------------------------------------
# Verdicts: do two gradings of one lot agree?
# --------------------------------------------------------------------------


def intervals_overlap(
    lo_a: float, hi_a: float, lo_b: float, hi_b: float
) -> bool:
    """Do two [lo, hi] intervals share any point?"""
    return max(float(lo_a), float(lo_b)) <= min(float(hi_a), float(hi_b))


def two_proportion_z(k_a: int, n_a: int, k_b: int, n_b: int) -> tuple[float, float]:
    """Pooled two-proportion z-test. Returns (z, two-sided p-value).

    Uses math.erfc so the module stays dependency-free: p = erfc(|z|/sqrt(2)).
    Degenerate inputs (either n is 0, or the pooled proportion is undefined)
    return (0.0, 1.0) -- "no evidence of a difference", which is both the
    statistically humble answer and the safe one for a dispute tool.
    """
    if n_a <= 0 or n_b <= 0:
        return 0.0, 1.0
    p_pool = (k_a + k_b) / (n_a + n_b)
    se = math.sqrt(p_pool * (1.0 - p_pool) * (1.0 / n_a + 1.0 / n_b))
    if se == 0.0:
        # Both samples saw exactly the same proportion; identical outcomes.
        return 0.0, 1.0
    z = ((k_a / n_a) - (k_b / n_b)) / se
    p_value = math.erfc(abs(z) / math.sqrt(2.0))
    return z, p_value


def _lot_fields(lot: dict) -> dict:
    """Accept either stored-lot dicts (percent + CI) or raw count dicts."""
    if "k" in lot and "n" in lot:
        k, n = int(lot["k"]), int(lot["n"])
        if n <= 0:
            raise ValueError("n must be positive")
        centre = 100.0 * k / n
        lo, hi = wilson_pct(k, n)
        return {"pct": centre, "lo": lo, "hi": hi, "k": k, "n": n}
    for field in ("pct", "lo", "hi", "n"):
        if field not in lot:
            raise ValueError(f"lot missing required field: {field}")
    n = int(lot["n"])
    if n <= 0:
        raise ValueError("n must be positive")
    pct = _clamp_pct(lot["pct"])
    lo = min(_clamp_pct(lot["lo"]), pct)
    hi = max(_clamp_pct(lot["hi"]), pct)
    k = int(round(pct * n / 100.0))
    return {"pct": pct, "lo": lo, "hi": hi, "k": k, "n": n}


def wilson_pct(k: int, n: int, z: float = Z95) -> tuple[float, float]:
    """Wilson interval on a percentage scale. Mirrors grading.wilson_interval."""
    if n <= 0:
        return 0.0, 100.0
    p = k / n
    denom = 1.0 + (z * z) / n
    centre = p + (z * z) / (2 * n)
    margin = z * math.sqrt(p * (1 - p) / n + (z * z) / (4 * n * n))
    lo = (centre - margin) / denom
    hi = (centre + margin) / denom
    return (max(0.0, lo) * 100.0, min(1.0, hi) * 100.0)


VERDICT_TEXT = {
    "AGREE": ("WITHIN MEASUREMENT UNCERTAINTY",
              "Both readings describe the same lot. The gap between them is "
              "smaller than what sampling alone can produce. No dispute."),
    "REVIEW": ("BORDERLINE — RESAMPLE",
               "The readings are close but their intervals barely disagree. "
               "One more tray photographed into EITHER record settles it."),
    "DISPUTE": ("MATERIAL DISCREPANCY",
                "The intervals do not overlap and the gap is too large to "
                "explain by sampling luck. Re-grade together; if the gap "
                "persists, escalate."),
}


def compare_lots(lot_a: dict, lot_b: dict, alpha: float = 0.05) -> dict:
    """Verdict on whether two independent gradings describe the same lot.

    Each argument needs either {pct, lo, hi, n} (as stored on a finished
    lot) or raw {k, n}. Returns a JSON-safe verdict with plain-language
    text, the gap in points, and a combined best estimate when they agree.
    """
    a = _lot_fields(lot_a)
    b = _lot_fields(lot_b)

    overlap = intervals_overlap(a["lo"], a["hi"], b["lo"], b["hi"])
    z_score, p_value = two_proportion_z(a["k"], a["n"], b["k"], b["n"])

    gap = abs(a["pct"] - b["pct"])

    if overlap:
        verdict = "AGREE"
    elif p_value < alpha and gap >= 10.0:
        verdict = "DISPUTE"
    else:
        verdict = "REVIEW"

    title, explanation = VERDICT_TEXT[verdict]

    combined = None
    if verdict != "DISPUTE":
        # Inverse-variance weighting on the Wilson variance. The narrower
        # interval is trusted more; both remain visible on the card.
        w_a = max(1e-9, (a["hi"] - a["lo"]) ** 2)
        w_b = max(1e-9, (b["hi"] - b["lo"]) ** 2)
        combined = round((a["pct"] / w_a + b["pct"] / w_b)
                         / (1.0 / w_a + 1.0 / w_b), 2)

    return {
        "verdict": verdict,
        "title": title,
        "explanation": explanation,
        "gap_points": round(gap, 2),
        "overlap": overlap,
        "p_value": round(p_value, 4),
        "z_score": round(z_score, 3),
        "alpha": alpha,
        "combined_estimate_pct": combined,
        "lot_a": {"pct": a["pct"], "ci_low": a["lo"], "ci_high": a["hi"],
                  "n": a["n"]},
        "lot_b": {"pct": b["pct"], "ci_low": b["lo"], "ci_high": b["hi"],
                  "n": b["n"]},
    }


# --------------------------------------------------------------------------
# Money: what should this lot be PAID?
# --------------------------------------------------------------------------


def fair_price_band(
    grade_pcts: dict,
    ci_low_pct: float,
    ci_high_pct: float,
    rates: dict | None = None,
) -> dict:
    """Rupees-per-quintal band implied by the grade mix and its uncertainty.

    grade_pcts maps size grade -> percent of the lot (A/B/C/UNDERSIZED, plus
    UNKNOWN if sizing was withheld). The central price uses the observed mix.
    For the band, Grade A is walked down/up to its CI bounds and the
    difference is absorbed by B/C/UNDERSIZED in proportion to how the lot is
    actually distributed -- never by inventing grade C onions that were not
    measured.

    Rates are rupees per quintal and default to DEFAULT_RATES; pass today's
    mandi rates to override.
    """
    r = dict(DEFAULT_RATES)
    if rates:
        for key, value in rates.items():
            key_u = str(key).upper()
            if key_u in r and value is not None:
                r[key_u] = float(value)

    clean: dict[str, float] = {}
    for grade, pct in (grade_pcts or {}).items():
        g = str(grade).upper()
        if g in r:
            clean[g] = max(0.0, float(pct))

    total = sum(clean.values())
    if total <= 0:
        raise ValueError("grade_pcts must sum to a positive percentage")

    def _price(mix: dict[str, float]) -> float:
        return sum(r[g] * (pct / 100.0) for g, pct in mix.items())

    central_mix = {g: p * 100.0 / total for g, p in clean.items()}
    central = _price(central_mix)

    ci_low_pct = _clamp_pct(ci_low_pct)
    ci_high_pct = _clamp_pct(ci_high_pct)
    if ci_high_pct < ci_low_pct:
        ci_low_pct, ci_high_pct = ci_high_pct, ci_low_pct

    def _shifted(target_a: float) -> dict[str, float]:
        """Move Grade A to `target_a` (points), redistribute the delta over
        the non-A grades pro-rata so the mix still sums to 100."""
        mix = dict(central_mix)
        if "A" not in mix:
            return mix
        others_total = 100.0 - mix["A"]
        delta = target_a - mix["A"]
        if others_total <= 0:
            # Degenerate 100%-A lot: clamp rather than fabricate grades.
            mix["A"] = target_a
            return mix
        scale = (others_total - delta) / others_total
        for g in mix:
            if g != "A":
                mix[g] *= scale
        mix["A"] = target_a
        return mix

    low_price = _price(_shifted(ci_low_pct))
    high_price = _price(_shifted(ci_high_pct))

    floor_g = min(r, key=lambda g: r[g])
    ceiling_g = max(r, key=lambda g: r[g])

    return {
        "currency": "INR",
        "unit": "quintal",
        "rates_used": r,
        "central_price": round(central, 0),
        "band_low": round(min(low_price, high_price), 0),
        "band_high": round(max(low_price, high_price), 0),
        "theoretical_floor": round(r[floor_g], 0),
        "theoretical_ceiling": round(r[ceiling_g], 0),
        "note": ("Rates are configurable demo defaults. The band carries the "
                 "same statistical uncertainty as the Grade-A percentage."),
    }


# --------------------------------------------------------------------------
# Sampling: have we looked at ENOUGH onions?
# --------------------------------------------------------------------------


def sample_sufficiency(
    n_obs: int,
    p_hat_pct: float | None = None,
    target_half_width_pct: float = TARGET_HALF_WIDTH_PCT,
) -> dict:
    """Is this many bulb-observations enough for the promised precision?

    Planning uses the worst case p=0.5 (maximising p(1-p)); once data exists
    the observed proportion sharpens the requirement. Returns how many more
    observations reach the target half-width, or an explicit SUFFICIENT.
    """
    if n_obs < 0:
        raise ValueError("n_obs cannot be negative")
    target_half_width_pct = float(target_half_width_pct)
    if target_half_width_pct <= 0:
        raise ValueError("target half-width must be positive")

    p_hat = 0.5 if p_hat_pct is None else _clamp_pct(p_hat_pct) / 100.0

    current_lo, current_hi = wilson_pct(int(round(p_hat * n_obs)), n_obs) \
        if n_obs > 0 else (0.0, 100.0)
    current_hw = (current_hi - current_lo) / 2.0

    # Normal-approximation planning size; fine for choosing a sample plan.
    w = target_half_width_pct / 100.0
    n_required = math.ceil(Z95 * Z95 * p_hat * (1.0 - p_hat) / (w * w)) \
        if w > 0 else 0
    extra_needed = max(0, n_required - n_obs)

    if extra_needed == 0:
        verdict = "SUFFICIENT"
        advice = (f"{n_obs} observations hold the Grade-A estimate to about "
                  f"+/-{current_hw:.1f} points -- inside the "
                  f"+/-{target_half_width_pct:g}-point promise.")
    else:
        verdict = "MORE_DATA"
        advice = (f"At {n_obs} observations the interval spans "
                  f"+/-{current_hw:.1f} points. Photographing roughly "
                  f"{extra_needed} more bulb-observations reaches the "
                  f"+/-{target_half_width_pct:g}-point promise.")

    return {
        "n_obs": n_obs,
        "observed_p_pct": round(p_hat * 100.0, 2) if n_obs else None,
        "current_half_width_pct": round(current_hw, 2) if n_obs else None,
        "target_half_width_pct": target_half_width_pct,
        "n_required": n_required,
        "extra_needed": extra_needed,
        "verdict": verdict,
        "advice": advice,
    }
