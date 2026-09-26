"""Digital-twin tests: app/twin.py quality-drift simulation.

The twin replays a certified lot forward under seeded deterioration and
reports what happens to saleable Grade A % and farmer payout. These tests
pin the properties that make it trustworthy enough to sit next to a signed
certificate:

    1. DETERMINISM -- same (lot, severity, seed) -> identical output dict,
       including across calls in one process. The default seed is derived
       with SHA-256, never Python's salted hash().
    2. IDENTITY at severity 0 -- scenario must equal baseline field-for-
       field. A "no drift" run inventing a difference would be worse than
       useless in front of a judge.
    3. LIMIT at severity 1 -- nothing saleable survives; price is None
       rather than an invented number.
    4. MONOTONICITY -- larger severity degrades strictly nested bulb
       subsets (uniforms drawn once, thresholded), so saleable Grade A can
       only fall and defect rate can only rise.
    5. HONEST LABELLING -- measured vs simulated labels present;
       data_source reports which path ran.
    6. API HARDENING -- /api/twin/{lot_id} answers JSON errors, never a
       stack trace, for missing lots and out-of-range severity.

Run:
    py -3.11 -m pytest tests/test_twin.py -q
"""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import db as sama_db          # noqa: E402
from app import main as sama           # noqa: E402
from app import twin                   # noqa: E402

client = TestClient(sama.app, raise_server_exceptions=False)


# --------------------------------------------------------------------------
# Fixtures / helpers
# --------------------------------------------------------------------------


@pytest.fixture()
def tmp_db(tmp_path, monkeypatch):
    """Isolated SQLite file so tests never touch data/sama.db."""
    monkeypatch.setattr(sama_db, "DB_PATH", tmp_path / "twin_test.db")
    sama_db.init_db()
    return sama_db


def _bulb_rows(n_sound_a=20, n_sound_b=10, rotten_a=3):
    rows = ([{"cls": "sound", "size_grade": "A"} for _ in range(n_sound_a)]
            + [{"cls": "sound", "size_grade": "B"} for _ in range(n_sound_b)]
            + [{"cls": "rotten", "size_grade": "A"} for _ in range(rotten_a)])
    return rows


def _lot_dict(rows):
    return {"id": 42, "lot_ref": "TWIN-TEST", "centre_name": "Test Centre",
            "result": {"n_bulb_observations": len(rows)},
            "bulbs": rows}


AGGREGATE_LOT = {
    "id": 7, "lot_ref": "TWIN-AGG", "centre_name": "Agg Centre",
    "result": {
        "n_bulb_observations": 100,
        "class_pcts": {"sound": 90.0, "rotten": 4.0, "sprouted": 2.0,
                       "black_smut": 1.0, "damaged_skin": 2.0, "doubles": 1.0},
        "grade_pcts": {"A": 60.0, "B": 30.0, "C": 8.0,
                       "UNDERSIZED": 2.0, "UNKNOWN": 0.0},
    },
}


# --------------------------------------------------------------------------
# Pure-function properties: per-bulb path
# --------------------------------------------------------------------------


def test_determinism_same_inputs_same_output():
    lot = _lot_dict(_bulb_rows())
    a = twin.simulate_lot(lot, severity=0.10)
    b = twin.simulate_lot(lot, severity=0.10)
    assert a == b


def test_default_seed_is_stable_per_lot_not_python_hash():
    """Seed derives from the LOT alone, so severity sweeps share one
    degradation ordering and stay comparable (nested subsets)."""
    assert twin.default_seed(42) == twin.default_seed(42)
    assert twin.default_seed(43) != twin.default_seed(42)


def test_zero_severity_scenario_equals_baseline():
    lot = _lot_dict(_bulb_rows())
    r = twin.simulate_lot(lot, severity=0.0)
    b, s = r["baseline"], r["scenario"]
    for key in b:
        assert b[key] == s[key], f"field {key} moved at severity 0"
    assert r["delta"]["saleable_grade_a_pts"] == 0.0
    assert r["degraded_observations"]["count"] == 0


def test_full_severity_nothing_saleable_and_price_withheld():
    lot = _lot_dict(_bulb_rows())
    r = twin.simulate_lot(lot, severity=1.0)
    s = r["scenario"]
    assert s["defect_rate_pct"] == 100.0
    assert s["saleable_grade_a_pct"] == 0.0
    # Nothing saleable -> NO invented price. Withholding beats guessing.
    assert s["price"] is None
    assert s["sound_size_mix_pct"] is None
    assert r["delta"]["payout_inr_per_quintal"] is None


def test_monotone_degradation_nested_subsets():
    lot = _lot_dict(_bulb_rows())
    saleable, defects = [], []
    for sev in (0.0, 0.1, 0.25, 0.5, 0.75, 1.0):
        r = twin.simulate_lot(lot, severity=sev)
        saleable.append(r["scenario"]["saleable_grade_a_pct"])
        defects.append(r["scenario"]["defect_rate_pct"])
    assert all(a >= b for a, b in zip(saleable, saleable[1:])), saleable
    assert all(a <= b for a, b in zip(defects, defects[1:])), defects


def test_value_index_never_rises_under_drift():
    """Per-quintal price of the REMAINING mix can legitimately rise when
    drift removes low grades first. The per-DELIVERED-quintal value index
    (price x saleable fraction) is the payout figure that cannot."""
    lot = _lot_dict(_bulb_rows())
    for sev in (0.05, 0.2, 0.4, 0.6):
        d = twin.simulate_lot(lot, severity=sev)["delta"]
        if d["value_index_inr_per_quintal_delivered"] is not None:
            assert d["value_index_inr_per_quintal_delivered"] <= 0
        if d["payout_inr_per_quintal"] is not None:
            assert d["payout_inr_per_quintal"] <= 0 or \
                d["value_index_inr_per_quintal_delivered"] < 0


def test_saleable_grade_a_distinct_from_size_band_convention():
    """Certificate Grade A counts the size band regardless of health; the
    twin's saleable figure must not silently use that convention."""
    lot = _lot_dict(_bulb_rows())          # 23 size-A bulbs (20 sound + 3 rotten)
    r = twin.simulate_lot(lot, severity=0.0)
    b = r["baseline"]
    assert b["grade_a_pct_size_band"] == pytest.approx(100 * 23 / 33, abs=0.01)
    assert b["saleable_grade_a_pct"] == pytest.approx(100 * 20 / 33, abs=0.01)


def test_degraded_bulbs_join_existing_defect_mix():
    """A lot that already shows sprout damage should sprout some of its new
    defects too -- not collapse everything into rotten."""
    rows = ([{"cls": "sound", "size_grade": "A"} for _ in range(50)]
            + [{"cls": "sprouted", "size_grade": "B"} for _ in range(50)])
    r = twin.simulate_lot(_lot_dict(rows), severity=0.5)
    degraded = r["degraded_observations"]["mix"]
    total_degraded = sum(degraded.values())
    assert total_degraded > 0
    # Existing mix is 100% sprouted -> every newly degraded bulb sprouts.
    assert degraded["sprouted"] == total_degraded
    assert degraded["rotten"] == 0


# --------------------------------------------------------------------------
# Aggregate fallback path
# --------------------------------------------------------------------------


def test_aggregate_path_deterministic_and_labelled():
    a = twin.simulate_lot(AGGREGATE_LOT, severity=0.10)
    b = twin.simulate_lot(AGGREGATE_LOT, severity=0.10)
    assert a == b
    assert a["data_source"] == "aggregate"
    assert "unused" in a["seed_source"]   # no RNG on this path


def test_aggregate_zero_severity_identity():
    r = twin.simulate_lot(AGGREGATE_LOT, severity=0.0)
    for key in r["baseline"]:
        assert r["baseline"][key] == r["scenario"][key], key


def test_aggregate_drift_lowers_saleable_grade_a():
    r = twin.simulate_lot(AGGREGATE_LOT, severity=0.10)
    assert r["scenario"]["saleable_grade_a_pct"] < r["baseline"]["saleable_grade_a_pct"]
    assert r["delta"]["saleable_grade_a_pts"] < 0


# --------------------------------------------------------------------------
# Input validation
# --------------------------------------------------------------------------


def test_rejects_severity_out_of_range():
    lot = _lot_dict(_bulb_rows())
    for bad in (-0.01, 1.01, 99.0):
        with pytest.raises(ValueError):
            twin.simulate_lot(lot, severity=bad)


def test_rejects_empty_lot():
    with pytest.raises(ValueError):
        twin.simulate_lot({"result": {}}, severity=0.1)


# --------------------------------------------------------------------------
# HTTP endpoint (JSON errors everywhere, demo-safe)
# --------------------------------------------------------------------------


def _seed_one_lot(centre="Twin Centre", ref="TWIN-E2E"):
    centre_id = sama_db.upsert_centre(centre, "Test District")
    rows = _bulb_rows()
    result = {
        "n_looks": 1,
        "n_bulb_observations": len(rows),
        "grade_a_pct": round(100 * sum(1 for r in rows if r["size_grade"] == "A") / len(rows), 2),
        "grade_a_ci_low": 45.0, "grade_a_ci_high": 78.0,
        "defect_rate_corrected": round(100 * 3 / len(rows), 2),
        "class_counts": {"sound": 30, "rotten": 3, "sprouted": 0,
                         "black_smut": 0, "damaged_skin": 0, "doubles": 0},
        "class_pcts": {"sound": 90.91, "rotten": 9.09, "sprouted": 0.0,
                       "black_smut": 0.0, "damaged_skin": 0.0, "doubles": 0.0},
        "grade_counts": {"A": 21, "B": 10, "C": 0, "UNDERSIZED": 0, "UNKNOWN": 0},
        "grade_pcts": {"A": 63.64, "B": 36.36, "C": 0.0,
                       "UNDERSIZED": 0.0, "UNKNOWN": 0.0},
    }
    # looks must be shaped [look][bulb] -- insert_lot writes one bulbs row
    # per entry, and the twin prefers those rows over aggregate proportions.
    meta = {"farmer_name": "Test Farmer", "calibrated": True,
            "looks": [rows]}
    return sama_db.insert_lot(centre_id, ref, result, meta)["lot_id"], len(rows)


def test_endpoint_returns_simulation(tmp_db):
    lot_id, n_rows = _seed_one_lot()
    resp = client.get(f"/api/twin/{lot_id}?severity=0.10")
    assert resp.status_code == 200
    body = resp.json()
    assert body["kind"] == "digital_twin_quality_drift"
    assert body["labels"]["baseline"] == "measured"
    assert body["labels"]["scenario"] == "simulated"
    assert body["data_source"] == "bulbs"
    assert body["baseline"]["n_observations"] == n_rows
    assert body["scenario"]["saleable_grade_a_pct"] \
        <= body["baseline"]["saleable_grade_a_pct"]
    assert isinstance(body["assumptions"], list) and body["assumptions"]


def test_endpoint_is_reproducible(tmp_db):
    lot_id, _ = _seed_one_lot()
    a = client.get(f"/api/twin/{lot_id}?severity=0.15").json()
    b = client.get(f"/api/twin/{lot_id}?severity=0.15").json()
    assert a == b
    c = client.get(f"/api/twin/{lot_id}?severity=0.15&seed=123").json()
    assert c["seed_source"] == "explicit"
    assert c["scenario"]["saleable_grade_a_pct"] \
        <= c["baseline"]["saleable_grade_a_pct"]


def test_endpoint_unknown_lot_is_json_404(tmp_db):
    resp = client.get("/api/twin/999999")
    assert resp.status_code == 404
    assert "error" in resp.json()


def test_endpoint_bad_severity_is_json_400(tmp_db):
    lot_id, _ = _seed_one_lot()
    resp = client.get(f"/api/twin/{lot_id}?severity=7")
    assert resp.status_code == 400
    assert "error" in resp.json()
    assert "severity" in resp.json()["error"].lower()
