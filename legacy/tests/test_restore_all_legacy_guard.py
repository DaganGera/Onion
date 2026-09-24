"""LOOP-I858 incident regression: /tamper/restore-all must not corrupt
legacy records by trusting result_json they never signed.

WHAT HAPPENED (2026-08-25, live on :8000)
-----------------------------------------
A routine demo drill (attack lot 58 -> restore-all) silently corrupted an
UNRELATED legacy certificate: lot 51, a v1 row (result_sha256 NULL) from the
seeded Chennai-11 demo centre. Its result_json carried pre-envelope demo
damage (grade_a_pct 99.9 inside the blob) that the v1 hash never covered --
verify honestly reports "legacy: summary-only" for such rows. restore-all's
fallback sweep treated that UNTRUSTED blob as ground truth, wrote 99.9 into
the signed grade_a_pct column, and broke the centre's chain. The signed value
(4.05) had to be recovered by brute-forcing the pinned row_hash.

CONTRACT UNDER TEST
-------------------
restore-all's sweep 2 may use result_json as restore-truth ONLY when the row
itself vouches for those bytes -- i.e. result_sha256 is present AND the
stored blob's digest matches it. Rows are otherwise SKIPPED and named in the
response (skipped_unverifiable), never rewritten:

  1. legacy row (no digest), valid column, damaged blob -> untouched, chain
     stays intact;
  2. v2 row, column-only attack -> restored as before (behaviour preserved);
  3. v2 row with BOTH blob and column edited -> not "restored" from the
     attacker's own bytes; stays flagged for a human.

Run:
    python -m pytest tests/test_restore_all_legacy_guard.py -q
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
    monkeypatch.setattr(sama.db, "DB_PATH", tmp_path / "restore_guard.db")
    sama.db.init_db()
    return sama.db


def _finalize(tmp_db, lot_ref):
    r = client.post("/finalize", json={
        "lot_ref": lot_ref, "farmer_name": "Restore Guard",
        "officer_name": "Tester",
        "looks": [[{"cls": 0, "size_grade": "B"},
                   {"cls": 0, "size_grade": "B"},
                   {"cls": 1, "size_grade": "B"}]],
    })
    assert r.status_code == 200, r.text[:300]
    body = r.json()
    assert "error" not in body, body
    return body


def _col(tmp_db, lot_id):
    conn = sama.db.connect()
    try:
        return conn.execute("SELECT grade_a_pct FROM lots WHERE id=?",
                            (lot_id,)).fetchone()["grade_a_pct"]
    finally:
        conn.close()


def _set_col(tmp_db, lot_id, value):
    conn = sama.db.connect()
    try:
        conn.execute("UPDATE lots SET grade_a_pct=? WHERE id=?", (value, lot_id))
        conn.commit()
    finally:
        conn.close()


def _set_blob_pct(tmp_db, lot_id, value):
    """Edit ONLY the stored result_json blob (what a pre-envelope attacker
    with database access could do to a v1 row undetectably)."""
    import json
    conn = sama.db.connect()
    try:
        row = conn.execute("SELECT result_json FROM lots WHERE id=?",
                           (lot_id,)).fetchone()
        blob = json.loads(row["result_json"])
        blob["grade_a_pct"] = value
        conn.execute("UPDATE lots SET result_json=? WHERE id=?",
                     (json.dumps(blob), lot_id))
        conn.commit()
    finally:
        conn.close()


def _degrade_to_legacy(tmp_db, lot_id):
    """Make the row look EXACTLY like a genuine pre-T-1 record: no pinned
    digest AND a row_hash that was computed without one. (Just NULLing the
    column on a v2 row would itself break the hash -- the digest sits INSIDE
    a v2 signed payload.)"""
    import json
    conn = sama.db.connect()
    try:
        row = conn.execute("SELECT * FROM lots WHERE id=?", (lot_id,)).fetchone()
        payload = {
            "centre_id": row["centre_id"], "lot_ref": row["lot_ref"],
            "farmer_name": row["farmer_name"] or "",
            "officer_name": row["officer_name"] or "",
            "created_at": row["created_at"], "n_bulbs": row["n_bulbs"],
            "n_looks": row["n_looks"], "grade_a_pct": row["grade_a_pct"],
            "ci_low": row["ci_low"], "ci_high": row["ci_high"],
            "defect_pct": row["defect_pct"],
        }
        conn.execute(
            "UPDATE lots SET result_sha256=NULL, row_hash=? WHERE id=?",
            (sama.db.compute_row_hash(payload, row["prev_hash"]), lot_id))
        conn.commit()
    finally:
        conn.close()
    # Sanity: the degraded row must still verify before we damage its blob.
    integrity = sama.db.result_integrity(sama.db.get_lot(lot_id))
    assert integrity == {"covered": False, "ok": None}


def test_legacy_row_with_damaged_blob_is_skipped_not_corrupted(tmp_db):
    lot = _finalize(tmp_db, "GUARD-LEGACY")
    lid = lot["lot_id"]
    original = lot["result"]["grade_a_pct"]
    _degrade_to_legacy(tmp_db, lid)
    _set_blob_pct(tmp_db, lid, 99.9)          # damage the UNTRUSTED blob
    assert _col(tmp_db, lid) == original      # column still signed-valid

    r = client.post("/tamper/restore-all")
    assert r.status_code == 200, r.text[:300]
    out = r.json()

    assert _col(tmp_db, lid) == original, \
        "restore-all rewrote a legacy column from an unverifiable blob"
    assert lid in out.get("skipped_unverifiable", []), \
        "skipped legacy row must be named in the response"


def test_chain_survives_restore_all_with_only_legacy_damage(tmp_db):
    lot = _finalize(tmp_db, "GUARD-LEGACY-CHAIN")
    lid = lot["lot_id"]
    original = lot["result"]["grade_a_pct"]
    centre_id = 1                              # first upserted centre in tmp db
    _degrade_to_legacy(tmp_db, lid)
    _set_blob_pct(tmp_db, lid, 99.9)

    client.post("/tamper/restore-all")
    intact, audits, n = sama.db.audit_chain(centre_id)
    assert intact, f"chain broke: {[a for a in audits if not a['ok']]}"
    assert _col(tmp_db, lid) == original


def test_v2_column_attack_is_still_restored(tmp_db):
    lot = _finalize(tmp_db, "GUARD-V2")
    lid = lot["lot_id"]
    original = lot["result"]["grade_a_pct"]
    _set_col(tmp_db, lid, min(99.9, original + 25.0))

    out = client.post("/tamper/restore-all").json()
    assert {"lot_id": lid, "restored_to": original} in out["restored"]
    assert _col(tmp_db, lid) == original


def test_v2_double_tamper_is_not_restored_from_attacker_bytes(tmp_db):
    lot = _finalize(tmp_db, "GUARD-V2-BOTH")
    lid = lot["lot_id"]
    original = lot["result"]["grade_a_pct"]
    _set_col(tmp_db, lid, 12.34)
    _set_blob_pct(tmp_db, lid, 99.9)           # digest now mismatches too

    out = client.post("/tamper/restore-all").json()
    assert lid in out.get("skipped_unverifiable", []), (
        "a row whose blob fails its own digest must not be used as truth")
    assert all(r["lot_id"] != lid for r in out["restored"])
    # The row keeps FLAGGING rather than being silently rewritten.
    integrity = sama.db.result_integrity(sama.db.get_lot(lid))
    assert integrity["covered"] and integrity["ok"] is False
