"""Task B-002 fix 1 regression tests: the farmer can actually contest a bulb.

RT-001 T-4 found the contest workflow was dead code: index.html's dispute
button fired no request, and /finalize never returned bulb row ids, so the
UI had nothing to POST against. The contract now:

    1. /finalize returns bulb_ids shaped exactly like the request's looks
       ([look][bulb] -> bulbs.id), so every on-screen bulb maps to its row.
    2. POST /dispute/{id} flips bulbs.disputed and answers {"ok": true}.
    3. Unknown ids are a JSON 404 -- the client must never be able to show
       "logged" without a row actually changing.
    4. Disputes are annotations on evidence: they sit OUTSIDE the hash chain
       and leave it intact (tamper-EVIDENT chain untouched by disputes).
    5. The certificate page payload carries the disputed flag, so
       report.html's counter finally counts real rows.

Run:
    C:/Users/ADMIN/AppData/Local/Programs/Python/Python311/python.exe -m pytest tests/test_dispute_flow.py -q
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
    """Isolated SQLite file so tests never touch data/sama.db."""
    monkeypatch.setattr(sama.db, "DB_PATH", tmp_path / "dispute_test.db")
    sama.db.init_db()
    return sama.db


def _bulb(cls_name="sound", conf=0.90, grade="A", dia=85.0):
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
        "looks": looks,
        "lot_ref": "QA-DISPUTE",
        "farmer_name": "Test Farmer",
        "officer_name": "Test Officer",
    })
    assert r.status_code == 200, r.text[:400]
    body = r.json()
    assert "error" not in body, body
    return body


# --------------------------------------------------------------------------
# /finalize exposes per-look bulb row ids
# --------------------------------------------------------------------------


def test_finalize_returns_bulb_ids_shaped_like_looks(tmp_db):
    body = _finalize([[_bulb(), _bulb("rotten", grade="B", dia=60.0)],
                      [_bulb()]])
    ids = body["bulb_ids"]
    assert isinstance(ids, list) and len(ids) == 2, body
    assert [len(look) for look in ids] == [2, 1], body
    flat = ids[0] + ids[1]
    assert all(isinstance(i, int) and i > 0 for i in flat), body
    assert len(set(flat)) == len(flat), "bulb ids must be distinct rows"


def test_finalize_bulb_ids_match_db_rows_and_order(tmp_db):
    looks = [[_bulb(), _bulb(cls_name="sprouted", grade="C", dia=40.0)],
             [_bulb(cls_name="rotten", grade="B", dia=65.0)]]
    ids = _finalize(looks)["bulb_ids"]

    conn = sama.db.connect()
    try:
        rows = conn.execute(
            "SELECT id, look_index FROM bulbs ORDER BY id").fetchall()
    finally:
        conn.close()

    # Insertion order is look-major: all of look 0, then look 1.
    assert [r["id"] for r in rows] == ids[0] + ids[1]
    assert [r["look_index"] for r in rows] == [0, 0, 1]


def test_finalize_with_empty_look_entries_still_yields_ids(tmp_db):
    # merge_looks tolerates null entries; insert_lot must too.
    body = _finalize([[_bulb()], None, [_bulb()]])
    ids = body["bulb_ids"]
    assert len(ids) == 3 and ids[1] == [], body
    assert len(ids[0]) == len(ids[2]) == 1, body


# --------------------------------------------------------------------------
# POST /dispute/{bulb_id}
# --------------------------------------------------------------------------


def test_dispute_flips_row_and_answers_ok(tmp_db):
    bulb_id = _finalize([[_bulb()]])["bulb_ids"][0][0]

    r = client.post(f"/dispute/{bulb_id}")
    assert r.status_code == 200, r.text
    assert r.json() == {"ok": True, "bulb_id": bulb_id}

    conn = sama.db.connect()
    try:
        row = conn.execute(
            "SELECT disputed FROM bulbs WHERE id = ?", (bulb_id,)).fetchone()
    finally:
        conn.close()
    assert row["disputed"] == 1


def test_dispute_is_repeatable_without_error(tmp_db):
    bulb_id = _finalize([[_bulb()]])["bulb_ids"][0][0]
    for _ in range(2):
        r = client.post(f"/dispute/{bulb_id}")
        assert r.status_code == 200
        assert r.json()["ok"] is True


def test_dispute_unknown_bulb_is_json_404(tmp_db):
    r = client.post("/dispute/987654321")
    assert r.status_code == 404
    body = r.json()
    assert set(body.keys()) == {"error"}
    assert "987654321" in body["error"]


def test_dispute_never_touches_the_hash_chain(tmp_db):
    lot_id = _finalize([[_bulb(), _bulb(cls_name="rotten", grade="B")]])["lot_id"]
    centre_id = sama.db.get_lot(lot_id)["centre_id"]

    ids = sama.db.get_lot(lot_id)["bulbs"]
    r = client.post(f"/dispute/{ids[0]['id']}")
    assert r.json()["ok"] is True

    intact, audits, n = sama.db.audit_chain(centre_id)
    assert intact is True
    assert all(a["ok"] for a in audits)
    assert n >= 1


def test_disputed_flag_reaches_the_certificate_payload(tmp_db):
    # report.html renders its dispute counter from LOT.bulbs[].disputed,
    # injected server-side into the page. After a real dispute the page text
    # must carry the flag; before B-002 this stayed at zero forever.
    lot_id = _finalize([[_bulb()]])["lot_id"]
    bulb_id = sama.db.get_lot(lot_id)["bulbs"][0]["id"]
    assert client.post(f"/dispute/{bulb_id}").json()["ok"] is True

    page = client.get(f"/report/{lot_id}")
    assert page.status_code == 200
    assert '"disputed": 1' in page.text
    assert "__LOT_DATA__" not in page.text  # template fully substituted


def test_second_lot_keeps_its_own_disputes(tmp_db):
    first = _finalize([[_bulb()]])
    second = _finalize([[_bulb(cls_name="rotten", grade="B", dia=70.0)]])

    first_bulb = sama.db.get_lot(first["lot_id"])["bulbs"][0]["id"]
    second_bulb = sama.db.get_lot(second["lot_id"])["bulbs"][0]["id"]
    client.post(f"/dispute/{first_bulb}")

    conn = sama.db.connect()
    try:
        d1 = conn.execute("SELECT disputed FROM bulbs WHERE id = ?",
                          (first_bulb,)).fetchone()["disputed"]
        d2 = conn.execute("SELECT disputed FROM bulbs WHERE id = ?",
                          (second_bulb,)).fetchone()["disputed"]
    finally:
        conn.close()
    assert (d1, d2) == (1, 0)
