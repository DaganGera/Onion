"""LOOP-D2218: the Grade-A interval must not treat two looks as independent bulbs.

RT-001 S-2 (HIGH): merge_looks pools 60 observations of 30 physical onions and
feeds them to Wilson as if independent. Repeat looks re-observe the SAME bulbs,
so the pooled interval can be up to sqrt(2) too narrow. Fix (mirroring D8's
S-3 pattern, grading.py stays frozen): a cluster-aware overlay at /finalize
that reconstructs (k_A, n_obs) from fields merge_looks already published and
recomputes the Wilson interval at effective sample size n_obs / design-effect.
Worst-case assumed intra-bulb correlation rho = 1 -> n_eff = n_obs / n_looks:
never more claimed precision than examining each bulb once.

Contract under test:

  1. design_effect / wilson_pct_effective arithmetic, incl. hand-computed
     anchors verified before being pinned here (z = 1.96):
       Wilson(36,60) = [47.37, 71.43]; Wilson(18,30) = [42.32, 75.41].
  2. grade_a_ci_fields rebuilds its inputs from merge_looks' OWN published
     output (no second implementation of class counting), preserves p_hat
     exactly, keeps the pooled bounds under *_pooled_* keys, floors n_eff.
  3. Single-look lots reproduce the frozen pooled width exactly and are
     labelled wilson-independent; rho=0 degenerates to the same numbers.
  4. Degenerate captures get NO new keys; corrupt counts clamp; NaN rho is
     treated as worst case (never silently as zero).
  5. /finalize attaches the clustered interval BEFORE db.insert_lot, so the
     hash-chain columns ci_low/ci_high carry the honest width; report page
     renders it; empty captures add nothing.

Run:
    python -m pytest tests/test_two_look_ci.py -q
"""

import math
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import arbitration as arb          # noqa: E402
from app import grading                     # noqa: E402
from app import main as sama                # noqa: E402


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def _bulb(cls_name="sound", conf=0.90, grade="B", dia=60.0):
    return {
        "bbox": [10.0, 10.0, 60.0, 50.0],
        "cls": cls_name,
        "cls_name": cls_name,
        "confidence": conf,
        "diameter_mm": dia,
        "size_grade": grade,
        "decision": "ACCEPT" if conf >= 0.75 else "REFER",
        "tray_id": "T1",
    }


def _merge_two_looks_a60():
    """Two looks x 35 bulbs, 21 Grade-A each look: p_hat = 60%, n_obs = 70."""
    def _look():
        return [_bulb(grade="A", dia=90.0)] * 21 + [_bulb()] * 14
    return grading.merge_looks([_look(), _look()])


def _pooled_pct(k, n):
    lo, hi = grading.wilson_interval(k, n)
    return lo * 100.0, hi * 100.0


# --------------------------------------------------------------------------
# 1. design_effect + effective-count Wilson arithmetic
# --------------------------------------------------------------------------


def test_design_effect_bounds():
    assert arb.design_effect(1) == pytest.approx(1.0)
    # Two looks, perfect correlation: repeats carry no extra information.
    assert arb.design_effect(2) == pytest.approx(2.0)
    # Partial correlation interpolates linearly (Kish).
    assert arb.design_effect(3, rho=0.5) == pytest.approx(2.0)
    # rho = 0 means genuinely independent repeats: no penalty.
    assert arb.design_effect(4, rho=0.0) == pytest.approx(1.0)


def test_design_effect_clamps_rho():
    assert arb.design_effect(2, rho=1.7) == pytest.approx(2.0)
    assert arb.design_effect(2, rho=-3.0) == pytest.approx(1.0)


def test_wilson_effective_matches_hand_anchor_at_half_sample():
    # 36/60 pooled with deff=2 must equal plain Wilson on 18/30: scaling BOTH
    # counts by the same factor leaves p_hat -- and the whole interval --
    # pinned to the printed statistic.
    lo, hi = arb.wilson_pct_effective(36, 60, 2.0)
    exp_lo, exp_hi = 42.32, 75.41          # hand-computed Wilson(18,30)
    assert lo == pytest.approx(exp_lo, abs=0.01)
    assert hi == pytest.approx(exp_hi, abs=0.01)
    assert lo < 60.0 < hi


def test_wilson_effective_unit_deff_equals_plain_wilson():
    lo_e, hi_e = arb.wilson_pct_effective(36, 60, 1.0)
    lo_p, hi_p = _pooled_pct(36, 60)
    assert lo_e == pytest.approx(lo_p, abs=1e-9)
    assert hi_e == pytest.approx(hi_p, abs=1e-9)


def test_wilson_effective_rejects_nonpositive_deff():
    with pytest.raises(ValueError):
        arb.wilson_pct_effective(36, 60, 0.0)
    with pytest.raises(ValueError):
        arb.wilson_pct_effective(36, 60, -1.0)


# --------------------------------------------------------------------------
# 2. grade_a_ci_fields: reconstruction from published fields only
# --------------------------------------------------------------------------


def test_fields_derive_from_real_merge_output():
    result = _merge_two_looks_a60()
    assert result["n_bulb_observations"] == 70

    out = arb.grade_a_ci_fields(result)

    assert out["grade_a_ci_method"] == "wilson-clustered-two-look"
    assert out["grade_a_n_observations"] == 70
    assert out["grade_a_n_effective"] == 35          # floored, never rounded up
    assert out["grade_a_design_effect"] == pytest.approx(2.0)
    # Point estimate untouched: p_hat sits inside the clustered band.
    assert out["grade_a_ci_low"] <= result["grade_a_pct"] <= out["grade_a_ci_high"]
    # Strictly wider than what shipped before (pooled Wilson on 42/70).
    pool_lo, pool_hi = _pooled_pct(42, 70)
    assert out["grade_a_ci_low"] < pool_lo
    assert out["grade_a_ci_high"] > pool_hi
    # Originals preserved verbatim for provenance.
    assert out["grade_a_ci_pooled_low"] == result["grade_a_ci_low"]
    assert out["grade_a_ci_pooled_high"] == result["grade_a_ci_high"]


def test_clustered_width_matches_direct_single_look_reference():
    # rho=1, two looks: the answer must coincide with Wilson on one look's
    # worth of data at the same proportion (k/n scaled by 1/deff).
    out = arb.grade_a_ci_fields(_merge_two_looks_a60())
    ref_lo, ref_hi = _pooled_pct(21, 35)
    assert out["grade_a_ci_low"] == pytest.approx(ref_lo, abs=0.01)
    assert out["grade_a_ci_high"] == pytest.approx(ref_hi, abs=0.01)


def test_single_look_reproduces_frozen_width_exactly():
    result = grading.merge_looks([[_bulb(grade="A", dia=90.0)] * 21 + [_bulb()] * 14])
    out = arb.grade_a_ci_fields(result)
    assert out["grade_a_ci_method"] == "wilson-independent"
    assert out["grade_a_n_effective"] == result["n_bulb_observations"]
    assert out["grade_a_ci_low"] == result["grade_a_ci_low"]
    assert out["grade_a_ci_high"] == result["grade_a_ci_high"]


def test_measured_rho_zero_degenerates_to_pooled():
    result = _merge_two_looks_a60()
    out = arb.grade_a_ci_fields(result, rho=0.0)
    # rho=0 claims independence: identical to the pooled computation...
    assert out["grade_a_ci_low"] == result["grade_a_ci_low"]
    assert out["grade_a_ci_high"] == result["grade_a_ci_high"]
    # ...and labelled as such rather than dressed up as clustered.
    assert out["grade_a_ci_method"] == "wilson-independent"


def test_odd_observation_count_floors_effective_n():
    # 69 observations over two looks: n_eff = 34.5 -> displayed as 34.
    # Precision is never advertised with a round-UP.
    look_a = [_bulb(grade="A", dia=90.0)] * 20 + [_bulb()] * 15
    look_b = [_bulb(grade="A", dia=90.0)] * 20 + [_bulb()] * 14
    result = grading.merge_looks([look_a, look_b])
    assert result["n_bulb_observations"] == 69
    out = arb.grade_a_ci_fields(result)
    assert out["grade_a_n_effective"] == math.floor(69 / 2)


def test_corrupt_counts_clamp_not_crash():
    result = _merge_two_looks_a60()
    result["grade_counts"]["A"] = 999            # nonsense from upstream
    out = arb.grade_a_ci_fields(result)
    assert 0.0 <= out["grade_a_ci_low"] <= out["grade_a_ci_high"] <= 100.0


def test_nan_rho_treated_as_worst_case_not_zero():
    # A broken rho must WIDEN the interval (rho->1), never shrink it.
    result = _merge_two_looks_a60()
    out_nan = arb.grade_a_ci_fields(result, rho=float("nan"))
    out_worst = arb.grade_a_ci_fields(result, rho=1.0)
    assert out_nan["grade_a_ci_low"] == out_worst["grade_a_ci_low"]
    assert out_nan["grade_a_ci_high"] == out_worst["grade_a_ci_high"]


def test_degenerate_result_yields_no_fields():
    assert arb.grade_a_ci_fields({}) == {}
    assert arb.grade_a_ci_fields({"n_bulb_observations": 0}) == {}


# --------------------------------------------------------------------------
# 3. /finalize integration: the signed columns carry the clustered interval
# --------------------------------------------------------------------------

client = TestClient(sama.app, raise_server_exceptions=False)


@pytest.fixture()
def tmp_db(tmp_path, monkeypatch):
    """Isolated SQLite file so tests never touch data/sama.db."""
    monkeypatch.setattr(sama.db, "DB_PATH", tmp_path / "two_look_ci_test.db")
    sama.db.init_db()
    return sama.db


def _finalize(looks):
    r = client.post("/finalize", json={
        "looks": looks, "lot_ref": "QA-TWO-LOOK-CI",
        "farmer_name": "Test Farmer", "officer_name": "Test Officer",
    })
    assert r.status_code == 200, r.text[:400]
    body = r.json()
    assert "error" not in body, body
    return body


def test_finalize_attaches_clustered_grade_a_interval(tmp_db):
    body = _finalize([
        [_bulb(grade="A", dia=90.0)] * 21 + [_bulb()] * 14,
        [_bulb(grade="A", dia=90.0)] * 21 + [_bulb()] * 14,
    ])
    res = body["result"]
    assert res["grade_a_n_effective"] == 35
    assert res["grade_a_ci_method"] == "wilson-clustered-two-look"
    # Wider than what shipped before: clustered lo sits below pooled lo,
    # clustered hi above pooled hi (pooled Wilson(42,70) = [48.29, 71.71]).
    assert res["grade_a_ci_low"] < res["grade_a_ci_pooled_low"]
    assert res["grade_a_ci_high"] > res["grade_a_ci_pooled_high"]
    # The response's primary CI keys ARE the clustered ones.
    assert res["grade_a_ci_low"] <= res["grade_a_pct"] <= res["grade_a_ci_high"]


def test_finalize_empty_capture_adds_nothing(tmp_db):
    res = _finalize([[], []])["result"]
    assert "grade_a_ci_method" not in res
    assert "grade_a_n_effective" not in res


def test_clustered_interval_is_what_gets_signed_and_stored(tmp_db):
    lot_id = _finalize([
        [_bulb(grade="A", dia=90.0)] * 21 + [_bulb()] * 14,
        [_bulb(grade="A", dia=90.0)] * 21 + [_bulb()] * 14,
    ])["lot_id"]
    stored = sama.db.get_lot(lot_id)
    # Hash-covered columns match the clustered interval, not the pooled one.
    assert stored["ci_low"] == stored["result"]["grade_a_ci_low"]
    assert stored["ci_high"] == stored["result"]["grade_a_ci_high"]

    page = client.get(f"/report/{lot_id}")
    assert page.status_code == 200
    assert '"grade_a_n_effective"' in page.text   # payload reaches report.html
    assert "__LOT_DATA__" not in page.text        # template fully substituted


def test_dispute_input_inherits_clustered_width(tmp_db):
    """compare_lots reads stored pct/lo/hi: the wider (honest) band must flow
    into dispute verdicts for newly finalized lots."""
    lot_id = _finalize([
        [_bulb(grade="A", dia=90.0)] * 21 + [_bulb()] * 14,
        [_bulb(grade="A", dia=90.0)] * 21 + [_bulb()] * 14,
    ])["lot_id"]
    lot = sama.db.get_lot(lot_id)
    verdict = arb.compare_lots(
        {"pct": lot["grade_a_pct"], "lo": lot["ci_low"],
         "hi": lot["ci_high"], "n": lot["n_bulbs"]},
        {"pct": lot["grade_a_pct"], "lo": lot["ci_low"],
         "hi": lot["ci_high"], "n": lot["n_bulbs"]},
    )
    assert verdict["verdict"] == "AGREE"          # identical readings overlap
