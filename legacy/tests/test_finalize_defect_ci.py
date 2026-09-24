"""Loop I2211: the certificate's defect rate carries its own interval.

RT-001 S-3 (HIGH): Grade A shipped with a Wilson CI but `defect_rate_corrected`
-- the number that actually drives rejection in procurement -- was a bare
point estimate. Contract under test:

  1. /finalize attaches defect_ci_{k,n,low,high} to result_json, describing
     exactly the worst per-look statistic already printed above it.
  2. Degenerate captures (all-empty looks) get NO interval keys -- the UI
     renders no band rather than an invented one.
  3. The stored certificate payload (db.get_lot) exposes those keys to
     report.html, and the rendered page prints them.

Run:
    python -m pytest tests/test_finalize_defect_ci.py -q
"""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import main as sama  # noqa: E402

client = TestClient(sama.app, raise_server_exceptions=False)


@pytest.fixture()
def tmp_db(tmp_path, monkeypatch):
    """Isolated SQLite file so tests never touch data/sama.db."""
    monkeypatch.setattr(sama.db, "DB_PATH", tmp_path / "defect_ci_test.db")
    sama.db.init_db()
    return sama.db


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


def _finalize(looks):
    r = client.post("/finalize", json={
        "looks": looks, "lot_ref": "QA-DEFECT-CI",
        "farmer_name": "Test Farmer", "officer_name": "Test Officer",
    })
    assert r.status_code == 200, r.text[:400]
    body = r.json()
    assert "error" not in body, body
    return body


def test_finalize_attaches_defect_interval(tmp_db):
    # Look 0: 3 defects / 35. Look 1 (the shake): 7 defects / 35 -> worst.
    look0 = [_bulb("sound")] * 32 + [_bulb("rotten")] * 3
    look1 = [_bulb("sound")] * 28 + [_bulb("rotten")] * 7
    result = _finalize([look0, look1])["result"]

    assert result["defect_ci_k"] == 7, result
    assert result["defect_ci_n"] == 35
    assert result["defect_rate_per_look"] == [8.57, 20.0]
    assert 0 < result["defect_ci_low"] < result["defect_rate_corrected"] \
        < result["defect_ci_high"] <= 100.0


def test_defect_interval_is_wider_than_point_under_occlusion_correction(
        tmp_db):
    # constants.json ships occlusion factors below 1, so the corrected point
    # sits ABOVE the raw rate; the interval must bracket that shift.
    look0 = [_bulb("black_smut", grade="C", dia=40.0)] * 5 + \
            [_bulb()] * 30
    result = _finalize([look0])["result"]
    factor = result["occlusion_factor_applied"]
    if factor < 1.0:
        assert result["defect_rate_corrected"] > result["defect_rate_raw"]
    assert result["defect_ci_low"] <= result["defect_rate_corrected"] \
        <= result["defect_ci_high"]


def test_degenerate_capture_gets_no_invented_interval(tmp_db):
    # Two empty looks: merge_looks yields n=0 and no per-look rates, so the
    # CI fields must be absent entirely -- never a fabricated band.
    body = _finalize([[], []])
    result = body["result"]
    assert "defect_ci_low" not in result
    assert "defect_ci_high" not in result


def test_interval_keys_survive_into_the_certificate_payload(tmp_db):
    look0 = [_bulb("sprouted", grade="C", dia=45.0)] * 6 + [_bulb()] * 29
    lot_id = _finalize([look0])["lot_id"]
    stored = sama.db.get_lot(lot_id)
    res = stored["result"]
    assert res["defect_ci_n"] == 35
    assert res["defect_ci_k"] == 6

    page = client.get(f"/report/{lot_id}")
    assert page.status_code == 200
    assert '"defect_ci_low"' in page.text      # payload reaches report.html
    assert "__LOT_DATA__" not in page.text     # template fully substituted
