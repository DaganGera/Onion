"""LOOP-D2262: close S-2a + S-2b, the follow-ups D11 flagged.

D11 fixed the CERTIFICATE's Grade-A interval (cluster-aware overlay at
/finalize, worst-case rho=1). Two consumers of the same pooled counts were
left quoting the old independent-observation width:

  S-2a  twin.py::_saleable_block -- the digital-twin's saleable Grade-A
        band ran grading.wilson_interval on POOLED observations. On a
        two-look lot that band is up to sqrt(2) too narrow AND now
        inconsistent with the certificate it sits beside: the report says
        +/-16.5 pts while the twin card promises +/-12 on the same data.
  S-2b  arbitration.sample_sufficiency -- evaluates current precision on
        pooled observations and quotes n_required in independent units,
        so the officer's card can say SUFFICIENT while the signed
        interval disagrees.

Design contract (mirrors D11 exactly):
  * deff = Kish 1+(n_looks-1)*rho with worst-case rho=1 -> a repeat look
    credits each physical bulb once. Never more claimed precision than
    examining each bulb once.
  * BOTH Wilson counts scale by 1/deff -> p_hat preserved exactly; the
    interval cannot drift from the printed statistic.
  * Single-look inputs reproduce the legacy numbers bit-for-bit and are
    labelled wilson-independent.
  * Corrupt/garbage look counts clamp conservatively, never crash.

Hand-computed anchors (z=1.96, verified before pinning):
  Wilson(36,60) = [47.37, 71.43]   Wilson(18,30) = [42.32, 75.41]
  Wilson(21,35) = [43.57, 74.45]   Wilson(40,60) = [54.06, 77.27]
  Wilson(20,30) = [48.78, 80.77]
  n_req(p=50%, w=6) = 267 distinct bulbs; n_req(p=60%, w=6) = 257.

Run:
    python -m pytest tests/test_two_look_followups.py -q
"""

import math
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import arbitration as arb          # noqa: E402
from app import main as sama                # noqa: E402
from app import twin                        # noqa: E402

client = TestClient(sama.app, raise_server_exceptions=False)


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def _agg_result(n_looks=None):
    """Aggregate-mode result_json: 60 observations, 100% sound, 60% band A."""
    result = {
        "n_bulb_observations": 60,
        "class_pcts": {"sound": 100.0, "rotten": 0.0, "sprouted": 0.0,
                       "black_smut": 0.0, "damaged_skin": 0.0, "doubles": 0.0},
        "grade_pcts": {"A": 60.0, "B": 40.0, "C": 0.0,
                       "UNDERSIZED": 0.0, "UNKNOWN": 0.0},
    }
    if n_looks is not None:
        result["n_looks"] = n_looks
    return result


def _agg_lot(n_looks=None):
    return {"id": 7, "lot_ref": "TWIN-S2A", "centre_name": "Agg Centre",
            "result": _agg_result(n_looks), "bulbs": []}


def _duplicated_rows():
    """Two looks x (20 sound-A + 10 sound-B): same physical tray shaken."""
    one_look = ([{"cls": "sound", "size_grade": "A"} for _ in range(20)]
                + [{"cls": "sound", "size_grade": "B"} for _ in range(10)])
    return one_look + one_look


def _bulb_lot(n_looks=None):
    rows = _duplicated_rows()
    result = {"n_bulb_observations": len(rows)}
    if n_looks is not None:
        result["n_looks"] = n_looks
    return {"id": 42, "lot_ref": "TWIN-BULBS", "centre_name": "Bulb Centre",
            "result": result, "bulbs": rows}


# --------------------------------------------------------------------------
# S-2a: twin saleable Grade-A interval honours the cluster design
# --------------------------------------------------------------------------


class TestTwinClusteredInterval:
    def test_two_look_aggregate_baseline_is_clustered(self):
        """36/60 pooled over two looks must read as Wilson(18,30), not
        Wilson(36,60): the repeats are the SAME onions."""
        out = twin.simulate_lot(_agg_lot(n_looks=2), severity=0.0)
        base = out["baseline"]
        assert base["saleable_grade_a_pct"] == pytest.approx(60.0)
        assert base["saleable_grade_a_ci_low_pct"] == pytest.approx(42.32, abs=0.01)
        assert base["saleable_grade_a_ci_high_pct"] == pytest.approx(75.41, abs=0.01)
        assert base["ci_method"] == "wilson-clustered-two-look"
        assert base["design_effect"] == pytest.approx(2.0)
        assert base["n_effective"] == 30

    def test_clustered_band_strictly_wider_than_pooled_reference(self):
        out = twin.simulate_lot(_agg_lot(n_looks=2), severity=0.0)
        base = out["baseline"]
        # Pooled anchor Wilson(36,60): what shipped before D2262.
        assert base["saleable_grade_a_ci_low_pct"] < 47.37
        assert base["saleable_grade_a_ci_high_pct"] > 71.43

    def test_single_look_reproduces_legacy_numbers_bit_for_bit(self):
        """No n_looks key AND n_looks=1 must equal the pre-D2262 width."""
        legacy = twin.simulate_lot(_agg_lot(), severity=0.0)["baseline"]
        explicit_one = twin.simulate_lot(_agg_lot(n_looks=1), severity=0.0)["baseline"]
        assert legacy == explicit_one
        assert legacy["saleable_grade_a_ci_low_pct"] == pytest.approx(47.37, abs=0.01)
        assert legacy["saleable_grade_a_ci_high_pct"] == pytest.approx(71.43, abs=0.01)
        assert legacy["ci_method"] == "wilson-independent"
        assert legacy["n_effective"] == 60
        assert legacy["design_effect"] == pytest.approx(1.0)

    def test_per_bulb_path_threads_n_looks(self):
        """The preferred per-bulb path carries duplicated rows too."""
        out = twin.simulate_lot(_bulb_lot(n_looks=2), severity=0.0)
        assert out["data_source"] == "bulbs"
        base = out["baseline"]
        # 40/60 saleable-A pooled, two looks -> Wilson(20,30), not Wilson(40,60).
        assert base["saleable_grade_a_pct"] == pytest.approx(100 * 40 / 60, abs=0.01)
        assert base["saleable_grade_a_ci_low_pct"] == pytest.approx(48.78, abs=0.01)
        assert base["saleable_grade_a_ci_high_pct"] == pytest.approx(80.77, abs=0.01)
        assert base["n_effective"] == 30
        assert base["ci_method"] == "wilson-clustered-two-look"

    def test_per_bulb_without_n_looks_stays_legacy(self):
        rows = _duplicated_rows()
        lot = {"id": 42, "lot_ref": "X", "centre_name": "C",
               "result": {"n_bulb_observations": len(rows)}, "bulbs": rows}
        base = twin.simulate_lot(lot, severity=0.0)["baseline"]
        assert base["ci_method"] == "wilson-independent"
        assert base["saleable_grade_a_ci_low_pct"] == pytest.approx(54.06, abs=0.01)
        assert base["saleable_grade_a_ci_high_pct"] == pytest.approx(77.27, abs=0.01)

    def test_scenario_and_baseline_share_the_same_design_basis(self):
        """Both blocks describe the same evidence base; their intervals must
        be comparable, so the scenario carries the same design effect."""
        out = twin.simulate_lot(_agg_lot(n_looks=2), severity=0.25)
        b, s = out["baseline"], out["scenario"]
        assert s["design_effect"] == b["design_effect"]
        assert s["ci_method"] == b["ci_method"] == "wilson-clustered-two-look"
        assert s["n_effective"] == b["n_effective"]

    def test_zero_severity_identity_survives_new_fields(self):
        """Existing contract: severity 0 => scenario equals baseline
        field-for-field, new keys included."""
        r = twin.simulate_lot(_agg_lot(n_looks=2), severity=0.0)
        for key in r["baseline"]:
            assert r["baseline"][key] == r["scenario"][key], key

    def test_determinism_preserved(self):
        a = twin.simulate_lot(_bulb_lot(n_looks=2), severity=0.10)
        b = twin.simulate_lot(_bulb_lot(n_looks=2), severity=0.10)
        assert a == b

    def test_corrupt_n_looks_clamps_never_crashes(self):
        """More looks than observations is impossible; garbage is treated as
        one look rather than inventing a design."""
        lot = _agg_lot()
        lot["result"]["n_looks"] = 99          # impossible: > observations
        base = twin.simulate_lot(lot, severity=0.0)["baseline"]
        assert base["design_effect"] <= 60     # clamped to n_obs at most
        lot["result"]["n_looks"] = "garbage"   # non-integer -> one look
        base = twin.simulate_lot(lot, severity=0.0)["baseline"]
        assert base["design_effect"] == pytest.approx(1.0)

    def test_assumptions_state_the_clustering(self):
        out = twin.simulate_lot(_agg_lot(n_looks=2), severity=0.0)
        assert any("cluster" in a.lower() or "effective" in a.lower()
                   for a in out["assumptions"])


# --------------------------------------------------------------------------
# S-2b: sample sufficiency plans in effective bulbs, speaks observations
# --------------------------------------------------------------------------


class TestSufficiencyEffectiveN:
    def test_legacy_default_callers_unchanged(self):
        """Pre-D2262 keys keep their semantics when n_looks defaults to 1."""
        out = arb.sample_sufficiency(500)
        assert out["verdict"] == "SUFFICIENT"
        assert out["extra_needed"] == 0
        plan = arb.sample_sufficiency(0, p_hat_pct=50.0, target_half_width_pct=6.0)
        assert plan["n_required"] == 267      # z^2 * .25 / .06^2, hand-checked
        small = arb.sample_sufficiency(30)
        assert small["extra_needed"] > 0
        assert small["n_required"] >= 30

    def test_n_looks_one_equals_default_exactly(self):
        assert arb.sample_sufficiency(70, p_hat_pct=60.0) == \
            arb.sample_sufficiency(70, p_hat_pct=60.0, n_looks=1)

    def test_deff_one_new_fields_are_trivial(self):
        out = arb.sample_sufficiency(70, p_hat_pct=60.0, n_looks=1)
        assert out["design_effect"] == pytest.approx(1.0)
        assert out["n_effective_current"] == 70
        assert out["n_required_distinct_bulbs"] == out["n_required"]

    def test_two_look_current_width_matches_certificate_anchor(self):
        """70 obs / 2 looks / p_hat 60%: current precision must be quoted at
        n_eff=35 -- Wilson(21,35), the same anchor as the certificate's."""
        out = arb.sample_sufficiency(70, p_hat_pct=60.0, n_looks=2)
        hw = (out["current_half_width_pct"])
        assert hw == pytest.approx((74.45 - 43.57) / 2, abs=0.01)
        assert out["n_effective_current"] == 35
        assert out["design_effect"] == pytest.approx(2.0)

    def test_two_look_requirements_quoted_in_both_units(self):
        """p=60% needs 257 DISTINCT bulbs; a 2-look design must photograph
        twice that many observations to deliver them."""
        out = arb.sample_sufficiency(70, p_hat_pct=60.0, n_looks=2)
        assert out["n_required_distinct_bulbs"] == 257
        assert out["n_required_observations"] == 514
        assert out["n_required"] == 514       # observations stay the headline
        assert out["extra_needed"] == 514 - 70
        assert out["verdict"] == "MORE_DATA"

    def test_more_looks_never_narrows_claimed_precision(self):
        widths = []
        for m in (1, 2, 3, 4):
            out = arb.sample_sufficiency(80, p_hat_pct=55.0, n_looks=m)
            lo = out["current_half_width_pct"]
            widths.append(lo)
        assert all(a <= b for a, b in zip(widths, widths[1:])), widths

    def test_advice_names_distinct_bulbs_when_clustered(self):
        clustered = arb.sample_sufficiency(70, p_hat_pct=60.0, n_looks=2)
        assert "distinct bulb" in clustered["advice"]
        single = arb.sample_sufficiency(70, p_hat_pct=60.0, n_looks=1)
        assert "distinct bulb" not in single["advice"]

    def test_impossible_look_count_clamps_to_observations(self):
        out = arb.sample_sufficiency(10, p_hat_pct=50.0, n_looks=999)
        assert out["design_effect"] <= 10     # cannot exceed n_obs
        assert out["current_half_width_pct"] >= 0
        assert out["verdict"] in ("SUFFICIENT", "MORE_DATA")

    def test_garbage_look_counts_fall_back_to_one_look(self):
        for bad in (-5, 0, "two", None):
            out = arb.sample_sufficiency(70, p_hat_pct=60.0, n_looks=bad)
            assert out["design_effect"] == pytest.approx(1.0)

    def test_validation_errors_unchanged(self):
        with pytest.raises(ValueError):
            arb.sample_sufficiency(10, target_half_width_pct=0)
        with pytest.raises(ValueError):
            arb.sample_sufficiency(-1)


# --------------------------------------------------------------------------
# API integration: the officer's card agrees with the certificate
# --------------------------------------------------------------------------


def _bulb(conf=0.90, grade="B", dia=60.0):
    return {
        "bbox": [10.0, 10.0, 60.0, 50.0],
        "cls": "sound", "cls_name": "sound", "confidence": conf,
        "diameter_mm": dia, "size_grade": grade,
        "decision": "ACCEPT" if conf >= 0.75 else "REFER", "tray_id": "T1",
    }


@pytest.fixture()
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(sama.db, "DB_PATH", tmp_path / "d2262_test.db")
    sama.db.init_db()
    return sama.db


def _finalize(looks):
    r = client.post("/finalize", json={
        "looks": looks, "lot_ref": "QA-D2262",
        "farmer_name": "Test Farmer", "officer_name": "Test Officer",
    })
    assert r.status_code == 200, r.text[:400]
    body = r.json()
    assert "error" not in body, body
    return body


def test_api_sufficiency_agrees_with_certificate_on_two_look_lot(tmp_db):
    """The exact inconsistency S-2b existed to prevent: certificate says
    +/-16 pts while the sufficiency card promised +/-12. Both must now be
    computed at the same effective n."""
    lot_id = _finalize([
        [_bulb(grade="A", dia=90.0)] * 21 + [_bulb()] * 14,
        [_bulb(grade="A", dia=90.0)] * 21 + [_bulb()] * 14,
    ])["lot_id"]
    res = client.get(f"/api/sufficiency/{lot_id}").json()
    assert res.get("error") is None
    assert res["design_effect"] == pytest.approx(2.0)
    assert res["n_effective_current"] == 35
    cert_hw = None
    stored = sama.db.get_lot(lot_id)["result"]
    cert_hw = (stored["grade_a_ci_high"] - stored["grade_a_ci_low"]) / 2
    assert res["current_half_width_pct"] == pytest.approx(cert_hw, abs=0.05)


def test_api_sufficiency_single_look_stays_independent(tmp_db):
    lot_id = _finalize([[_bulb(grade="A", dia=90.0)] * 21 + [_bulb()] * 14])["lot_id"]
    res = client.get(f"/api/sufficiency/{lot_id}").json()
    assert res.get("error") is None
    assert res["design_effect"] == pytest.approx(1.0)
    assert res["n_effective_current"] == res["n_obs"]
