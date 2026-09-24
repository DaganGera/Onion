"""Detection-confidence calibration: does a stated 0.9 mean RIGHT 90%?

SAMA's certificate leans on one number the model invents: its confidence.
Everything at or above `accept_threshold` (0.75) is ACCEPTed into the signed
record; everything below is REFERred to a human. That policy only means
something if confidence tracks reality -- if boxes scored 0.9 are right
about 90% of the time. If they are right 60% of the time, the ACCEPT band
is a lie on a signed document.

This module measures that gap and does two things with it:

1. RELIABILITY DIAGRAM + ECE/MCE -- the standard calibration toolkit
   (equal-width binning; expected/maximum calibration error), computed from
   (confidence, was-the-call-correct) pairs produced by scripts/
   eval_calibration.py over hand-labelled trays.
2. FEED THE REFER THRESHOLD -- recommend_accept_threshold() finds the
   smallest confidence cut whose top slice is empirically correct at least
   `target_accuracy` of the time (with a minimum sample support, so five
   lucky detections cannot move a signed threshold). fit_temperature()
   fits the classic Guo et al. temperature-scaling correction adapted to
   detection: treat each box's confidence as P(this call is correct) and
   fit one temperature on binary cross-entropy.

PURE FUNCTIONS ONLY. numpy in, plain dicts out, no torch, no ultralytics,
no file I/O. The measurement lives in scripts/eval_calibration.py; this
module is what tests pin and what both the script and the app import.

Every number this module produces is labelled "measured" only when the
pairs it consumed came from real matched detections -- the caller owns
that labelling (see eval_calibration.py's report).
"""

from __future__ import annotations

import math

import numpy as np

# Clip guard for logits: confidences of exactly 0 or 1 have infinite logit.
# Real detector confidences never hit the ends, but defensive beats clever.
_EPS = 1e-6


# --------------------------------------------------------------------------
# Input validation -- fail loudly here so callers can convert to JSON 400s
# --------------------------------------------------------------------------


def _validate(confs, corrects) -> tuple[np.ndarray, np.ndarray]:
    confs = np.asarray(confs, dtype=float)
    corrects = np.asarray(corrects)
    if confs.ndim != 1 or corrects.ndim != 1:
        raise ValueError("confs and corrects must be 1-D sequences")
    if confs.size == 0:
        raise ValueError("no detections to calibrate on")
    if confs.size != corrects.size:
        raise ValueError(
            f"length mismatch: {confs.size} confidences vs {corrects.size} labels")
    if not np.all(np.isfinite(confs)) or confs.min() < 0.0 or confs.max() > 1.0:
        raise ValueError("confidences must be finite and within [0, 1]")
    corr = corrects.astype(float)
    if not np.all(np.isin(corr, (0.0, 1.0))):
        raise ValueError("corrects must contain only 0 (wrong) and 1 (right)")
    return confs, corr


def _check_bins(n_bins: int) -> int:
    n_bins = int(n_bins)
    if n_bins < 1:
        raise ValueError("n_bins must be >= 1")
    return min(n_bins, 100)


def _bin_edges(n_bins: int) -> np.ndarray:
    return np.linspace(0.0, 1.0, n_bins + 1)


# --------------------------------------------------------------------------
# Reliability diagram data + ECE / MCE
# --------------------------------------------------------------------------


def bin_stats(confs, corrects, n_bins: int = 10,
              min_bin_count: int = 1) -> list[dict]:
    """Equal-width bins over [0, 1]. Bins keep [lo, hi); the last bin is
    closed so confidence exactly 1.0 lands somewhere instead of vanishing.

    Bins with fewer than min_bin_count samples report count but null means --
    an empty bin must NOT read as "perfectly calibrated", it reads as
    "no evidence".
    """
    confs, corr = _validate(confs, corrects)
    n_bins = _check_bins(n_bins)
    edges = _bin_edges(n_bins)

    bins = []
    for i in range(n_bins):
        lo, hi = float(edges[i]), float(edges[i + 1])
        sel = (confs >= lo) & (confs < hi) if i < n_bins - 1 \
            else (confs >= lo) & (confs <= hi)
        count = int(sel.sum())
        bins.append({
            "lo": round(lo, 6),
            "hi": round(hi, 6),
            "count": count,
            "mean_conf": round(float(confs[sel].mean()), 6) if count >= min_bin_count else None,
            "accuracy": round(float(corr[sel].mean()), 6) if count >= min_bin_count else None,
        })
    return bins


def ece(confs, corrects, n_bins: int = 10) -> float:
    """Expected Calibration Error: |mean confidence - observed accuracy|
    weighted by bin occupancy. 0.0 for a perfectly calibrated detector."""
    confs, corr = _validate(confs, corrects)
    n_bins = _check_bins(n_bins)
    edges = _bin_edges(n_bins)

    total = confs.size
    err = 0.0
    for i in range(n_bins):
        lo, hi = edges[i], edges[i + 1]
        sel = (confs >= lo) & (confs < hi) if i < n_bins - 1 \
            else (confs >= lo) & (confs <= hi)
        count = int(sel.sum())
        if count == 0:
            continue
        err += (count / total) * abs(float(confs[sel].mean()) - float(corr[sel].mean()))
    return round(err, 6)


def mce(confs, corrects, n_bins: int = 10) -> float:
    """Maximum Calibration Error: the WORST single bin. A low ECE with a
    huge MCE hides one badly lying band -- exactly the kind of thing a
    signed certificate may not do."""
    confs, corr = _validate(confs, corrects)
    n_bins = _check_bins(n_bins)
    edges = _bin_edges(n_bins)

    worst = 0.0
    for i in range(n_bins):
        lo, hi = edges[i], edges[i + 1]
        sel = (confs >= lo) & (confs < hi) if i < n_bins - 1 \
            else (confs >= lo) & (confs <= hi)
        if not sel.any():
            continue
        worst = max(worst, abs(float(confs[sel].mean()) - float(corr[sel].mean())))
    return round(worst, 6)


def reliability(confs, corrects, n_bins: int = 10,
                min_bin_count: int = 1) -> dict:
    """Everything a diagram or an API panel needs, JSON-ready and stable."""
    return {
        "kind": "reliability_diagram",
        "n": int(np.asarray(confs).size),
        "n_bins": _check_bins(n_bins),
        "bins": bin_stats(confs, corrects, n_bins=n_bins,
                          min_bin_count=min_bin_count),
        "ece": ece(confs, corrects, n_bins=n_bins),
        "mce": mce(confs, corrects, n_bins=n_bins),
    }


# --------------------------------------------------------------------------
# Feeding the REFER threshold
# --------------------------------------------------------------------------


def recommend_threshold(confs, corrects, target_accuracy: float = 0.95,
                        min_support: int = 30) -> dict | None:
    """Smallest confidence cut t such that calls with conf >= t are right at
    least `target_accuracy` of the time, backed by >= min_support samples.

    This is the operational meaning of the 0.75 ACCEPT line: "above this we
    trust the machine without a human". The recommendation keeps that promise
    honest against measured data instead of folklore.

    Returns None when NO reachable cut meets the target with enough support --
    keeping the current threshold and saying so beats quietly lowering the
    bar. Ties in confidence are handled by recomputing under the inclusive
    mask, never by pretending the tie group splits.

    Also reports how much work stays automated vs referred at the proposed
    cut: raising accuracy always costs human referrals, and hiding that
    trade would be dishonest.
    """
    if not 0.0 < target_accuracy <= 1.0:
        raise ValueError("target_accuracy must be within (0, 1]")
    if min_support < 1:
        raise ValueError("min_support must be >= 1")

    confs, corr = _validate(confs, corrects)
    n = confs.size

    order = np.argsort(-confs, kind="stable")
    sorted_conf = confs[order]
    cum_correct = np.cumsum(corr[order])

    # k = size of the top-k prefix; scan from k=n (smallest possible cut)
    # upward in cut value, first qualifying recomputed mask wins because any
    # later candidate has a strictly higher threshold.
    tol = 1e-12
    for k in range(n, max(min_support, 1) - 1, -1):
        if cum_correct[k - 1] / k < target_accuracy - tol:
            continue
        t = float(sorted_conf[k - 1])
        mask = confs >= t          # ties included, honestly recounted
        support = int(mask.sum())
        achieved = float(corr[mask].mean())
        if support >= min_support and achieved >= target_accuracy - tol:
            return {
                "threshold": round(t, 6),
                "achieved_accuracy": round(achieved, 6),
                "target_accuracy": target_accuracy,
                "support": support,
                "referred": int(n - support),
                "min_support": min_support,
            }
    return None


# --------------------------------------------------------------------------
# Temperature scaling, adapted to detection confidence
# --------------------------------------------------------------------------


def _logit(p: np.ndarray) -> np.ndarray:
    p = np.clip(p, _EPS, 1.0 - _EPS)
    return np.log(p / (1.0 - p))


def _sigmoid(z: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-z))


def apply_temperature(confs, temperature: float) -> np.ndarray:
    """Scale confidences through logit/T -> sigmoid. T > 1 flattens toward
    0.5 (fixes overconfidence); T < 1 sharpens (fixes underconfidence).
    Monotone in the input, so ACCEPT/REFER ordering never flips."""
    if not math.isfinite(temperature) or temperature <= 0.0:
        raise ValueError("temperature must be finite and > 0")
    confs, _ = _validate(confs, np.ones_like(np.asarray(confs, dtype=float)))
    scaled = _sigmoid(_logit(confs) / float(temperature))
    return np.round(scaled, 8)


def _bce(p: np.ndarray, y: np.ndarray) -> float:
    p = np.clip(p, _EPS, 1.0 - _EPS)
    return float(-(y * np.log(p) + (1 - y) * np.log(1 - p)).mean())


def fit_temperature(confs, corrects, t_min: float = 0.05,
                    t_max: float = 20.0) -> dict:
    """Fit ONE temperature on binary cross-entropy by golden-section search
    over log-temperature. Deterministic, derivative-free, ~60 evaluations --
    trivially fast at our scale and impossible for a solver hiccup to derail.

    Honest framing: Guo et al.'s temperature scaling calibrates a softmax;
    detectors give us per-box confidence instead. The standard adaptation
    treats confidence as P(the call is correct), with correctness defined by
    the same-class IoU matching in eval_calibration.py. Three honest limits:
    it fixes SYSTEMATIC miscalibration, not bad RANKING (a wrong call scored
    above a right one stays wrong); its helpful direction depends on which
    side of 0.5 the confidence mass sits (T>1 pulls toward 0.5, T<1 pushes
    away from it -- so "underconfident" clouds below half need T>1); and a
    cloud pinned at exactly 0.5 is unfittable and reported as such.
    """
    if t_min <= 0 or t_max <= t_min:
        raise ValueError("require 0 < t_min < t_max")
    confs, corr = _validate(confs, corrects)
    z = _logit(confs)

    # Degenerate input guard: confidences pinned AT 0.5 give z == 0 for every
    # sample, so every temperature maps them back to exactly 0.5 -- the loss
    # is flat, T is unidentifiable, and the search would return wherever it
    # happened to stop. Report identity + say so instead. (A constant cloud
    # at any OTHER level is still fittable: T shifts that one level.)
    if float(np.ptp(z)) < 1e-9 and abs(float(np.median(z))) < 1e-6:
        return {
            "kind": "temperature_scaling_binary",
            "temperature": 1.0,
            "bce_before": round(_bce(confs, corr), 6),
            "bce_after": round(_bce(confs, corr), 6),
            "ece_before": ece(confs, corr),
            "ece_after": ece(confs, corr),
            "improved": False,
            "note": "degenerate_input_confidences_pinned_at_half",
        }

    def loss(log_t: float) -> float:
        return _bce(_sigmoid(z / math.exp(log_t)), corr)

    # Golden-section search on log T within [log t_min, log t_max].
    inv_phi = (math.sqrt(5.0) - 1.0) / 2.0
    lo_log, hi_log = math.log(t_min), math.log(t_max)
    c = hi_log - inv_phi * (hi_log - lo_log)
    d = lo_log + inv_phi * (hi_log - lo_log)
    fc, fd = loss(c), loss(d)
    for _ in range(80):
        if fc < fd:
            hi_log, d, fd = d, c, fc
            c = hi_log - inv_phi * (hi_log - lo_log)
            fc = loss(c)
        else:
            lo_log, c, fc = c, d, fd
            d = lo_log + inv_phi * (hi_log - lo_log)
            fd = loss(d)
    temperature = math.exp((lo_log + hi_log) / 2.0)

    ece_before = ece(confs, corr)
    scaled = apply_temperature(confs, temperature)
    ece_after = ece(scaled, corr)
    return {
        "kind": "temperature_scaling_binary",
        "temperature": round(temperature, 4),
        "bce_before": round(_bce(confs, corr), 6),
        "bce_after": round(_bce(scaled, corr), 6),
        "ece_before": ece_before,
        "ece_after": ece_after,
        "improved": bool(ece_after < ece_before),
    }
