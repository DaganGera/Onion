"""Calibration tests: app/calibration.py -- ECE, reliability bins, threshold
recommendation, temperature scaling.

The ACCEPT/REFER policy promises that a confidence of 0.75+ means a
trustworthy machine call. These tests pin the properties that keep that
promise auditable:

    1. PERFECT CALIBRATION -> ECE ~ 0. Constructed data where each bin's
       accuracy equals its mean confidence must measure as calibrated.
    2. OVERCONFIDENCE IS VISIBLE AND FIXABLE -- conf=0.9 data that is right
       60% of the time must show ECE ~ 0.3, fit temperature T > 1, and the
       scaled confidences must have LOWER ECE than the raw ones.
    3. UNDERCONFIDENCE -> T < 1.
    4. THRESHOLD RECOMMENDATION -- smallest qualifying cut wins; impossible
       targets return None instead of inventing a threshold; min_support
       blocks tiny lucky samples; ties are recounted inclusively.
    5. VALIDATION -- bad inputs raise ValueError (callers map to JSON 400),
       never silently produce a number.
    6. API -- /api/calibration degrades gracefully: missing or corrupt
       report file answers {"available": false}, never a stack trace.

Run:
    py -3.11 -m pytest tests/test_calibration.py -q
"""

import json
import sys
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import calibration as cal         # noqa: E402
from app import main as sama               # noqa: E402

client = TestClient(sama.app, raise_server_exceptions=False)


# --------------------------------------------------------------------------
# Helpers: constructed detector populations with known calibration
# --------------------------------------------------------------------------


def _pairs(mean_conf: float, accuracy: float, n: int = 500,
           seed: int = 7) -> tuple[np.ndarray, np.ndarray]:
    """n detections all at one confidence level with a known hit rate."""
    rng = np.random.default_rng(seed)
    confs = np.full(n, float(mean_conf))
    corrects = (rng.random(n) < accuracy).astype(float)
    return confs, corrects


def _layered_population() -> tuple[np.ndarray, np.ndarray]:
    """Ten layers, each perfectly calibrated within its layer.

    Layer i sits at confidence 0.05 + 0.10*i and is right exactly that
    fraction of the time (large n so sampling noise is negligible).
    """
    confs_l, corr_l = [], []
    rng = np.random.default_rng(11)
    for i in range(10):
        c = 0.05 + 0.10 * i
        n = 2000
        confs_l.append(np.full(n, c))
        corr_l.append((rng.random(n) < c).astype(float))
    return np.concatenate(confs_l), np.concatenate(corr_l)


# --------------------------------------------------------------------------
# ECE / reliability
# --------------------------------------------------------------------------


def test_perfectly_calibrated_population_has_near_zero_ece():
    confs, corr = _layered_population()
    assert cal.ece(confs, corr, n_bins=10) < 0.01


def test_overconfident_population_shows_the_gap():
    """Says 0.9, right 60% of the time -> ECE ~ 0.3, MCE similar."""
    confs, corr = _pairs(0.9, 0.6, n=4000)
    assert cal.ece(confs, corr, n_bins=10) == pytest.approx(0.30, abs=0.02)
    assert cal.mce(confs, corr, n_bins=10) == pytest.approx(0.30, abs=0.02)


def test_underconfident_population_shows_the_gap():
    confs, corr = _pairs(0.5, 0.8, n=4000)
    assert cal.ece(confs, corr, n_bins=10) == pytest.approx(0.30, abs=0.02)


def test_reliability_payload_shape_and_labels():
    confs, corr = _pairs(0.9, 0.6, n=100)
    r = cal.reliability(confs, corr, n_bins=10)
    assert r["kind"] == "reliability_diagram"
    assert r["n"] == 100
    assert len(r["bins"]) == 10
    # All mass in the [0.9, 1.0) bin... plus exact-1.0 closure never triggers.
    filled = [b for b in r["bins"] if b["count"]]
    assert len(filled) == 1 and filled[0]["lo"] == pytest.approx(0.9)
    assert filled[0]["accuracy"] == pytest.approx(0.6, abs=0.06)


def test_confidence_exactly_one_lands_in_last_bin_not_nowhere():
    confs = np.array([1.0])
    corr = np.array([1])
    bins = cal.bin_stats(confs, corr, n_bins=10)
    assert sum(b["count"] for b in bins) == 1
    assert bins[-1]["count"] == 1


def test_empty_bin_reads_as_no_evidence_not_perfection():
    """A bin with zero samples must carry None means -- null, not 0.0/1.0,
    so a diagram cannot mistake silence for calibration."""
    confs, corr = _pairs(0.9, 0.6, n=50)
    bins = cal.bin_stats(confs, corr, n_bins=10)
    empty = [b for b in bins if b["count"] == 0]
    assert empty, "test construction expects some empty bins"
    assert all(b["mean_conf"] is None and b["accuracy"] is None for b in empty)


def test_min_bin_count_gates_small_bins():
    confs, corr = _pairs(0.85, 0.5, n=4)
    gated = cal.bin_stats(confs, corr, n_bins=10, min_bin_count=10)
    assert all(b["mean_conf"] is None for b in gated)


def test_ece_deterministic():
    confs, corr = _layered_population()
    a = cal.reliability(confs, corr)
    b = cal.reliability(confs, corr)
    assert a == b


# --------------------------------------------------------------------------
# Threshold recommendation -- feeding the REFER line
# --------------------------------------------------------------------------


def test_recommendation_finds_smallest_qualifying_cut():
    """Layers at 0.5/0.7/0.9 with accuracies 0.55/0.80/0.99. Target 0.95
    needs the cut at 0.9: the 0.7 layer tops out near 0.8 true accuracy, far
    below target even with sampling noise, and the all-in slice is lower
    still."""
    confs = np.concatenate([np.full(100, 0.5), np.full(100, 0.7),
                            np.full(100, 0.9)])
    rng = np.random.default_rng(3)
    corr = np.concatenate([
        (rng.random(100) < 0.55).astype(float),
        (rng.random(100) < 0.80).astype(float),
        (rng.random(100) < 0.99).astype(float),
    ])
    rec = cal.recommend_threshold(confs, corr, target_accuracy=0.95,
                                  min_support=50)
    assert rec is not None
    assert rec["threshold"] == pytest.approx(0.9)
    assert rec["achieved_accuracy"] >= 0.95
    assert rec["support"] == 100 and rec["referred"] == 200


def test_impossible_target_returns_none_keeps_current_threshold():
    """No cut anywhere reaches 0.999 -> None. Keeping the incumbent and
    saying so beats quietly lowering a signed bar."""
    confs, corr = _pairs(0.8, 0.7, n=300)
    assert cal.recommend_threshold(confs, corr, target_accuracy=0.999,
                                   min_support=10) is None


def test_min_support_blocks_tiny_lucky_samples():
    """Three perfect detections at 0.99 must NOT move the threshold when
    min_support=30, even though their slice is 100% accurate."""
    confs = np.concatenate([np.full(297, 0.5), np.full(3, 0.99)])
    rng = np.random.default_rng(5)
    corr = np.concatenate([
        (rng.random(297) < 0.5).astype(float), np.ones(3)])
    assert cal.recommend_threshold(confs, corr, target_accuracy=0.95,
                                   min_support=30) is None
    # Same data, honest support floor: the recommendation appears.
    rec = cal.recommend_threshold(confs, corr, target_accuracy=0.95,
                                  min_support=3)
    assert rec is not None and rec["threshold"] == pytest.approx(0.99)


def test_recommendation_respects_tied_confidences_inclusively():
    """Boundary confidence repeated across a tie group: the inclusive mask
    may pull in more than the prefix -- achieved accuracy is recomputed on
    the REAL mask, never on the convenient prefix."""
    confs = np.array([0.9] * 40 + [0.6] * 60)
    corr = np.array([1.0] * 40 + [0.0] * 60)
    rec = cal.recommend_threshold(confs, corr, target_accuracy=1.0,
                                  min_support=10)
    assert rec is not None
    assert rec["threshold"] == pytest.approx(0.9)
    assert rec["support"] == 40 and rec["achieved_accuracy"] == 1.0


def test_recommendation_validates_arguments():
    confs, corr = _pairs(0.8, 0.8, n=50)
    with pytest.raises(ValueError):
        cal.recommend_threshold(confs, corr, target_accuracy=0.0)
    with pytest.raises(ValueError):
        cal.recommend_threshold(confs, corr, target_accuracy=1.5, min_support=1)
    with pytest.raises(ValueError):
        cal.recommend_threshold(confs, corr, target_accuracy=0.9, min_support=0)


# --------------------------------------------------------------------------
# Temperature scaling
# --------------------------------------------------------------------------


def test_overconfidence_yields_temperature_above_one_and_reduces_ece():
    """Spread cloud above 0.5, right only ~70% as often as claimed --
    the classic detector shape: reliability curve bows under the diagonal
    at the top. Flattening (T > 1) must reduce both BCE and ECE."""
    rng = np.random.default_rng(21)
    n = 6000
    confs = rng.uniform(0.6, 0.95, n)
    corr = (rng.random(n) < confs * 0.7).astype(float)
    assert cal.ece(confs, corr) > 0.05          # visibly miscalibrated first
    fit = cal.fit_temperature(confs, corr)
    assert fit["temperature"] > 1.0
    assert fit["improved"]
    assert fit["bce_after"] < fit["bce_before"]
    assert fit["ece_after"] < fit["ece_before"]


def test_underconfidence_above_half_yields_temperature_below_one():
    """Spread cloud above 0.5 that is right MORE often than claimed:
    sharpening (T < 1) pushes predictions up toward the truth."""
    rng = np.random.default_rng(9)
    n = 6000
    confs = rng.uniform(0.55, 0.95, n)
    truth = np.clip((confs - 0.5) * 1.6 + 0.5, None, 0.98)
    corr = (rng.random(n) < truth).astype(float)
    assert cal.ece(confs, corr) > 0.03
    fit = cal.fit_temperature(confs, corr)
    assert fit["temperature"] < 1.0
    assert fit["improved"]


def test_apply_temperature_monotone_ordering_never_flips():
    """REFER/ACCEPT ordering must survive scaling -- a transform that could
    reorder two boxes could flip a decision without anyone noticing."""
    confs = np.array([0.30, 0.55, 0.74, 0.76, 0.93])
    out = cal.apply_temperature(confs, temperature=2.5)
    assert np.all(np.diff(out) > 0)
    assert np.all(out > 0) and np.all(out < 1)
    # Flattening pulls toward 0.5 from both sides.
    assert abs(out[0] - 0.5) < abs(confs[0] - 0.5)
    assert abs(out[-1] - 0.5) < abs(confs[-1] - 0.5)


def test_apply_temperature_identity_at_one():
    confs = np.array([0.2, 0.5, 0.8])
    assert cal.apply_temperature(confs, 1.0) == pytest.approx(confs, abs=1e-6)


def test_fit_temperature_deterministic():
    confs, corr = _pairs(0.85, 0.65, n=800)
    a = cal.fit_temperature(confs, corr)
    b = cal.fit_temperature(confs, corr)
    assert a == b


def test_perfectly_calibrated_needs_no_scaling():
    confs, corr = _layered_population()
    fit = cal.fit_temperature(confs, corr)
    assert fit["temperature"] == pytest.approx(1.0, abs=0.15)
    # Nothing meaningful to fix: already-tiny ECE stays tiny (a one-parameter
    # fit may shave sampling noise, but it must not move the number).
    assert cal.ece(confs, corr) < 0.01
    assert fit["ece_after"] < 0.02


def test_degenerate_pinned_at_half_reports_unidentifiable():
    """Every detection at exactly 0.5 -> no temperature changes anything.
    The honest answer is identity + a note, not wherever the search stops."""
    confs, corr = _pairs(0.5, 0.6, n=200)
    fit = cal.fit_temperature(confs, corr)
    assert fit["temperature"] == 1.0
    assert fit["improved"] is False
    assert fit["note"] == "degenerate_input_confidences_pinned_at_half"


def test_constant_confidence_away_from_half_is_still_fittable():
    """A single-level cloud at 0.9 CAN be shifted by T (toward 0.5 as T
    grows) -- so it must NOT be flagged degenerate."""
    confs, corr = _pairs(0.9, 0.6, n=200)
    fit = cal.fit_temperature(confs, corr)
    assert "note" not in fit
    assert fit["temperature"] > 1.0
    assert fit["improved"]


# --------------------------------------------------------------------------
# Validation -- loud failures, mapped by callers to JSON errors
# --------------------------------------------------------------------------


@pytest.mark.parametrize("confs,corrects", [
    ([], []),                                    # empty
    ([0.5], [1, 0]),                             # length mismatch
    ([0.5, 1.7], [1, 0]),                        # confidence out of range
    ([0.5, -0.1], [1, 0]),                       # negative confidence
    ([0.5, 0.6], [1, 2]),                        # label not binary
    ([[0.5]], [[1]]),                            # wrong dimensionality
])
def test_invalid_inputs_raise_value_error(confs, corrects):
    with pytest.raises(ValueError):
        cal.ece(confs, corrects)
    with pytest.raises(ValueError):
        cal.reliability(confs, corrects)


def test_bad_bins_and_temperature_rejected():
    confs, corr = _pairs(0.5, 0.5, n=10)
    with pytest.raises(ValueError):
        cal.bin_stats(confs, corr, n_bins=0)
    with pytest.raises(ValueError):
        cal.apply_temperature(confs, temperature=0.0)
    with pytest.raises(ValueError):
        cal.apply_temperature(confs, temperature=float("nan"))
    with pytest.raises(ValueError):
        cal.fit_temperature(confs, corr, t_min=2.0, t_max=1.0)


# --------------------------------------------------------------------------
# HTTP endpoint: graceful degradation, JSON always
# --------------------------------------------------------------------------


def _write_report(tmp_path, payload):
    p = tmp_path / "calibration.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    return p


def test_endpoint_missing_report_is_available_false(tmp_path, monkeypatch):
    monkeypatch.setattr(sama, "CALIBRATION_REPORT", tmp_path / "absent.json")
    resp = client.get("/api/calibration")
    assert resp.status_code == 200
    body = resp.json()
    assert body["available"] is False
    assert "eval_calibration" in body.get("hint", "")


def test_endpoint_corrupt_report_degrades_gracefully(tmp_path, monkeypatch):
    bad = tmp_path / "calibration.json"
    bad.write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(sama, "CALIBRATION_REPORT", bad)
    resp = client.get("/api/calibration")
    assert resp.status_code == 200
    body = resp.json()
    assert body["available"] is False
    assert body["reason"] == "corrupt"


def test_endpoint_serves_measured_report(tmp_path, monkeypatch):
    payload = {
        "kind": "detection_calibration",
        "labels": {"ece": "measured"},
        "reliability": {"kind": "reliability_diagram", "n": 1234,
                        "ece": 0.042, "mce": 0.31,
                        "bins": [{"lo": 0.0, "hi": 0.1, "count": 5,
                                  "mean_conf": None, "accuracy": None}]},
        "current_threshold": 0.75,
        "recommendation": {"threshold": 0.83, "achieved_accuracy": 0.96},
        "temperature_fit": {"temperature": 1.4, "improved": True},
    }
    monkeypatch.setattr(sama, "CALIBRATION_REPORT",
                        _write_report(tmp_path, payload))
    resp = client.get("/api/calibration")
    assert resp.status_code == 200
    body = resp.json()
    assert body["available"] is True
    assert body["labels"]["ece"] == "measured"
    assert body["reliability"]["ece"] == 0.042
    assert body["recommendation"]["threshold"] == 0.83
