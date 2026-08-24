"""Wow-pass W2213 regression tests: the live tamper attack demo contract.

The stage moment of SAMA is verification flipping RED live. That only works
if the mechanics are honest and the recovery is bulletproof:

    1. ONE round trip: /tamper/attack edits the row AND re-audits the chain,
       returning exactly which certificate went red -- the UI flips from
       this response alone, no second fetch (<1s on venue wifi).
    2. Restore survives a server restart: the true value lives in
       result_json (written once at insert, never edited, not needed for
       the recomputed hash to match once the column is put back).
    3. /tamper/restore-all sweeps BOTH in-memory attack state AND any row
       whose stored grade_a_pct disagrees with its own result_json copy --
       i.e. orphaned attacks from before a restart. Nothing else in the app
       ever UPDATEs lots, so a mismatch IS an attack; restoring from
       result_json puts back the exact hashed value.
    4. Every failure path stays JSON, never a raw 500.

Run:
    C:/Users/ADMIN/AppData/Local/Programs/Python/Python311/python.exe -m pytest tests/test_tamper_demo.py -q
"""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import main as sama  # noqa: E402

client = TestClient(sama.app, raise_server_exceptions=False)


# --------------------------------------------------------------------------
# Fixtures / helpers
# --------------------------------------------------------------------------


@pytest.fixture()
def tmp_db(tmp_path, monkeypatch):
    """Isolated SQLite file + clean in-memory tamper state per test."""
    monkeypatch.setattr(sama.db, "DB_PATH", tmp_path / "tamper_test.db")
    sama.db.init_db()
    sama._TAMPER_STATE.clear()
    return sama.db


def _seed_lot(centre_id: int, ref: str, grade_a: float = 62.4) -> int:
    result = {
        "n_bulb_observations": 35,
        "n_looks": 2,
        "grade_a_pct": grade_a,
        "grade_a_ci_low": grade_a - 10.0,
        "grade_a_ci_high": grade_a + 10.0,
        "defect_rate_corrected": 4.0,
    }
    meta = {"farmer_name": "F", "officer_name": "O", "looks": []}
    return sama.db.insert_lot(centre_id, ref, result, meta)["lot_id"]


@pytest.fixture()
def centre(tmp_db):
    return tmp_db.upsert_centre("Tamper Test Mandi", "Nashik")


@pytest.fixture()
def three_lots(centre):
    return [_seed_lot(centre, f"QA-TAMPER-{i}") for i in range(3)]


def _db_value(lot_id):
    lot = sama.db.get_lot(lot_id)
    return float(lot["grade_a_pct"])


# --------------------------------------------------------------------------
# Attack: one round trip, honest verdict
# --------------------------------------------------------------------------


def test_attack_edits_row_and_audit_names_exactly_that_lot(tmp_db, three_lots):
    victim, bystander = three_lots[1], three_lots[0]
    before = _db_value(victim)

    r = client.post(f"/tamper/attack/{victim}")
    assert r.status_code == 200, r.text[:400]
    d = r.json()
    assert "error" not in d

    # the edit really happened -- no simulation flag anywhere
    assert _db_value(victim) == pytest.approx(min(before + 25.0, 99.9))
    # ...and nobody else was touched
    assert _db_value(bystander) != pytest.approx(_db_value(victim))

    # single-response verdict: the UI must not need a second fetch to flip red
    assert d["was"] == pytest.approx(before)
    assert d["now"] == pytest.approx(_db_value(victim))
    assert d["lot_ref"].startswith("QA-TAMPER-")
    assert d["audit"]["intact"] is False
    assert d["audit"]["broken_lot_ids"] == [victim]
    assert d["audit"]["records_checked"] == 3


def test_chain_red_after_attack_green_after_restore(tmp_db, three_lots):
    victim = three_lots[0]
    original = _db_value(victim)

    client.post(f"/tamper/attack/{victim}")
    intact, audits, _ = sama.db.audit_chain(sama.db.get_lot(victim)["centre_id"])
    assert intact is False
    assert [a["lot_id"] for a in audits if not a["ok"]] == [victim]

    r = client.post(f"/tamper/restore/{victim}")
    d = r.json()
    assert d["ok"] is True
    assert d["restored_to"] == pytest.approx(original)
    assert d["intact_after"] is True
    assert _db_value(victim) == pytest.approx(original)


# --------------------------------------------------------------------------
# Bulletproofing: restarts, double attacks, the sweep
# --------------------------------------------------------------------------


def test_restore_survives_server_restart_via_result_json(tmp_db, three_lots):
    """Server dies mid-demo: memory gone, red value left in the DB."""
    victim = three_lots[1]
    original = _db_value(victim)

    client.post(f"/tamper/attack/{victim}")
    sama._TAMPER_STATE.clear()          # <-- simulated restart

    d = client.post(f"/tamper/restore/{victim}").json()
    assert d["ok"] is True
    assert d["restored_to"] == pytest.approx(original)
    assert d["intact_after"] is True


def test_double_attack_then_single_restore_is_green(tmp_db, three_lots):
    victim = three_lots[0]
    original = _db_value(victim)

    client.post(f"/tamper/attack/{victim}")
    client.post(f"/tamper/attack/{victim}")   # judge presses ATTACK twice
    assert _db_value(victim) == pytest.approx(original + 25.0)

    d = client.post(f"/tamper/restore/{victim}").json()
    assert d["ok"] is True
    assert _db_value(victim) == pytest.approx(original)
    assert d["intact_after"] is True


def test_restore_all_sweeps_memory_state_and_restarted_orphans(tmp_db, three_lots):
    a, b = three_lots[0], three_lots[1]
    orig_a, orig_b = _db_value(a), _db_value(b)

    client.post(f"/tamper/attack/{a}")
    client.post(f"/tamper/attack/{b}")
    sama._TAMPER_STATE.clear()   # attack happened before a restart -> orphans

    d = client.post("/tamper/restore-all").json()
    assert d["ok"] is True
    assert d["n_restored"] == 2
    assert d["intact_after"] is True
    assert _db_value(a) == pytest.approx(orig_a)
    assert _db_value(b) == pytest.approx(orig_b)

    # idempotent: pressing it again changes nothing and stays green
    again = client.post("/tamper/restore-all").json()
    assert again["ok"] is True
    assert again["n_restored"] == 0
    assert again["intact_after"] is True


def test_restore_all_leaves_clean_rows_alone(tmp_db, three_lots):
    d = client.post("/tamper/restore-all").json()
    assert d["ok"] is True
    assert d["n_restored"] == 0
    assert d["intact_after"] is True
    for lot_id in three_lots:
        assert _db_value(lot_id) == pytest.approx(62.4)


# --------------------------------------------------------------------------
# Failure paths stay readable JSON
# --------------------------------------------------------------------------


def test_unknown_lot_is_json_404(tmp_db, three_lots):
    for path in ("/tamper/attack/999999", "/tamper/restore/999999"):
        r = client.post(path)
        assert r.status_code == 404
        assert set(r.json().keys()) == {"error"}
