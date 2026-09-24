"""SAMA grading math.

Pure functions only. No FastAPI, no model loading, no file I/O beyond reading
constants.json once at import. Every function is testable in isolation.

FROZEN after tests/test_grading.py passes. Do not edit.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

from app import mat_layout
from app import scale as scale_mod
from app.scale import ScaleResult, measure_bbox_mm

# --------------------------------------------------------------------------
# Domain constants. Do not invent your own -- these come from CLAUDE.md.
# --------------------------------------------------------------------------

CLASS_NAMES = ["sound", "rotten", "sprouted", "black_smut", "damaged_skin", "doubles"]
DEFECT_CLASSES = [c for c in CLASS_NAMES if c != "sound"]

MARKER_MM = mat_layout.MARKER_MM   # printed side of each ArUco black square
ARUCO_DICT = scale_mod.ARUCO_DICT

# ICAR-DOGR size bands by bulb diameter, in mm.
# Boundaries are inclusive on the LOWER edge: exactly 80.0 mm is Grade A,
# exactly 50.0 mm is Grade B, exactly 30.0 mm is Grade C.
GRADE_A_MIN = 80.0
GRADE_B_MIN = 50.0
GRADE_C_MIN = 30.0

SKEW_TOLERANCE = scale_mod.SKEW_TOLERANCE

_DEFAULTS = {
    "height_correction": 1.0,
    "occlusion_correction_1look": 1.0,
    "occlusion_correction_2look": 1.0,
    "accept_threshold": 0.75,
    "e2e_mode": False,
}

_CONSTANTS_PATH = Path(__file__).with_name("constants.json")


def _load_constants() -> dict:
    """Read constants.json, falling back to defaults for anything absent."""
    values = dict(_DEFAULTS)
    try:
        with open(_CONSTANTS_PATH, "r", encoding="utf-8") as fh:
            values.update(json.load(fh))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass
    return values


CONSTANTS = _load_constants()


def reload_constants() -> dict:
    """Re-read constants.json. Used by scripts that have just rewritten it."""
    global CONSTANTS
    CONSTANTS = _load_constants()
    return CONSTANTS


# --------------------------------------------------------------------------
# Scale detection -- delegates to app/scale.py
# --------------------------------------------------------------------------


def detect_scale(image_bgr, carried: ScaleResult | None = None) -> ScaleResult:
    """Find a millimetre reference, degrading down a ladder of fallbacks.

    See app/scale.py. Returns a ScaleResult, not a plain dict: callers that
    want JSON should use .to_dict().
    """
    return scale_mod.detect_scale(image_bgr, carried)


# --------------------------------------------------------------------------
# Sizing and grading
# --------------------------------------------------------------------------


def bulb_diameter_mm(bbox_xyxy, scale) -> float | None:
    """Bulb diameter in mm, perspective-corrected when a homography exists.

    Accepts either a ScaleResult or a bare mm-per-pixel float, so older call
    sites and tests keep working.

    height_correction compensates for the bulb sitting above the mat plane:
    it is nearer the camera than the marker, so it images larger.
    """
    if scale is None:
        return None

    if isinstance(scale, (int, float)):
        x0, y0, x1, y1 = (float(v) for v in bbox_xyxy)
        raw = min(abs(x1 - x0), abs(y1 - y0)) * float(scale)
    else:
        raw = measure_bbox_mm(bbox_xyxy, scale)
        if raw is None:
            return None

    return raw * CONSTANTS["height_correction"]


def size_grade(diameter_mm: float | None) -> str:
    """ICAR-DOGR size band. Lower edge inclusive."""
    if diameter_mm is None:
        return "UNKNOWN"
    if diameter_mm >= GRADE_A_MIN:
        return "A"
    if diameter_mm >= GRADE_B_MIN:
        return "B"
    if diameter_mm >= GRADE_C_MIN:
        return "C"
    return "UNDERSIZED"


def decide(confidence: float) -> str:
    """ACCEPT the model's call, or REFER it to a human inspector."""
    return "ACCEPT" if confidence >= CONSTANTS["accept_threshold"] else "REFER"


# --------------------------------------------------------------------------
# Statistics
# --------------------------------------------------------------------------


def wilson_interval(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval for a proportion.

    Better than the normal approximation at the small sample sizes and
    extreme proportions we actually hit -- a tray of 35 onions with zero
    defects would give a nonsensical zero-width Wald interval.
    """
    if n <= 0:
        return (0.0, 1.0)

    p = k / n
    denom = 1.0 + (z * z) / n
    centre = p + (z * z) / (2 * n)
    margin = z * math.sqrt(p * (1 - p) / n + (z * z) / (4 * n * n))

    lo = (centre - margin) / denom
    hi = (centre + margin) / denom
    return (max(0.0, lo), min(1.0, hi))


# --------------------------------------------------------------------------
# Lot-level merge -- this is the product's actual output
# --------------------------------------------------------------------------


def merge_looks(looks: list[list[dict]], n_trays: int | None = None) -> dict:
    """Pool per-bulb observations across looks into one lot result.

    Each look is a list of per-bulb dicts carrying at least `cls` (int index
    or class name) and optionally `size_grade`, `decision`, `tray_id`.

    Reports n as BULB-OBSERVATIONS, not onions: shaking the tray and looking
    again re-observes the same physical bulbs. Calling them independent
    samples would overstate our confidence, so the field is named for what
    it actually is.
    """
    bulbs: list[dict] = []
    for look in looks or []:
        bulbs.extend(look or [])

    n = len(bulbs)
    n_looks = len(looks or [])

    if n_trays is None:
        tray_ids = {b.get("tray_id") for b in bulbs if b.get("tray_id") is not None}
        n_trays = len(tray_ids) if tray_ids else (1 if n else 0)

    def _class_name(bulb: dict) -> str:
        raw = bulb.get("cls")
        if isinstance(raw, str):
            return raw
        if isinstance(raw, (int, float)) and 0 <= int(raw) < len(CLASS_NAMES):
            return CLASS_NAMES[int(raw)]
        return "sound"

    class_counts = {name: 0 for name in CLASS_NAMES}
    grade_counts = {"A": 0, "B": 0, "C": 0, "UNDERSIZED": 0, "UNKNOWN": 0}
    n_referred = 0

    for bulb in bulbs:
        class_counts[_class_name(bulb)] += 1
        grade = bulb.get("size_grade", "UNKNOWN")
        grade_counts[grade if grade in grade_counts else "UNKNOWN"] += 1
        if bulb.get("decision") == "REFER":
            n_referred += 1

    def _pct(count: int) -> float:
        return round(100.0 * count / n, 2) if n else 0.0

    # SIZE: pool every observation. A bulb's diameter does not hide when the
    # tray is shaken, so more observations genuinely tighten the interval.
    n_grade_a = grade_counts["A"]
    ci_lo, ci_hi = wilson_interval(n_grade_a, n)

    # DEFECTS: do NOT pool. Two looks re-observe the SAME bulbs, and a defect
    # hidden in look 1 shows up in look 2 as a different observation of the
    # same onion. Averaging the two looks would keep the occlusion bias and
    # merely halve it -- the tray would still read cleaner than it is.
    # The less-occluded view is the better estimate of the lot, so take the
    # highest per-look rate. This also matches how measure_occlusion.py fits
    # occlusion_correction_2look; if the two disagreed, the correction would
    # be applied to a quantity it was never measured against.
    per_look_rates: list[float] = []
    for look in looks or []:
        if look:
            n_bad = sum(1 for b in look if _class_name(b) != "sound")
            per_look_rates.append(n_bad / len(look))
    defect_rate_raw = max(per_look_rates) if per_look_rates else 0.0

    factor_key = "occlusion_correction_2look" if n_looks >= 2 else "occlusion_correction_1look"
    factor = CONSTANTS[factor_key] or 1.0
    # Observed = factor x true, so true = observed / factor.
    defect_rate_corrected = min(1.0, defect_rate_raw / factor)

    return {
        "n_bulb_observations": n,
        "n_looks": n_looks,
        "n_trays": n_trays,
        "class_counts": class_counts,
        "class_pcts": {name: _pct(c) for name, c in class_counts.items()},
        "grade_counts": grade_counts,
        "grade_pcts": {name: _pct(c) for name, c in grade_counts.items()},
        "grade_a_pct": _pct(n_grade_a),
        "grade_a_ci_low": round(100.0 * ci_lo, 2),
        "grade_a_ci_high": round(100.0 * ci_hi, 2),
        "defect_rate_raw": round(100.0 * defect_rate_raw, 2),
        "defect_rate_corrected": round(100.0 * defect_rate_corrected, 2),
        "defect_rate_per_look": [round(100.0 * r, 2) for r in per_look_rates],
        "occlusion_factor_applied": factor,
        "n_referred": n_referred,
    }
