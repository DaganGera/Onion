"""LOOP-B2258 -- RT-001 T-1 (CRITICAL): result_json joins the hash envelope.

The bug the red-team judge proved by one SQL statement:

    UPDATE lots SET result_json = <rewritten grade_pcts / defect rates>;

Every rendered number on the certificate moved, the price band moved, the
WhatsApp share text moved -- and /api/verify stayed green, because the chain
covered only 11 summary scalars while report.html renders from result_json
(RT-001 question 1: "Edit result_json right now -- why does your verify page
stay green?").

Contract after this pass:
  1. NEW records pin sha256 of their EXACT stored result_json bytes in
     lots.result_sha256 AND bind that digest inside the hashed payload.
     Editing result_json breaks the byte check; editing result_json AND its
     digest column together still breaks the row_hash check. Two locks, one
     key each.
  2. LEGACY records (result_sha256 IS NULL) verify under the old 11-field
     payload byte-for-byte -- a migration must never redden certificates
     that were signed before the column existed. They are reported as
     covered=False honestly, not silently blessed.
  3. The public verdict folds the new check in via audit_chain, so
     /api/verify flips red for a result-tamper with no frontend change.
  4. Mixed v1->v2 chains link and audit correctly.

Grading math untouched; no data/holdout contact.

Run:
    C:/Users/ADMIN/AppData/Local/Programs/Python/Python311/python.exe -m pytest tests/test_result_envelope.py -q
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import db as sama_db  # noqa: E402
from app import main as sama  # noqa: E402

REPORT_HTML = (Path(__file__).resolve().parents[1] / "app" / "static"
               / "report.html").read_text(encoding="utf-8")

client = TestClient(sama.app, raise_server_exceptions=False)


# --------------------------------------------------------------------------
# Fixtures and helpers
# --------------------------------------------------------------------------


@pytest.fixture()
def tmp_db(tmp_path, monkeypatch):
    """Isolated SQLite file so tests never touch data/sama.db."""
    monkeypatch.setattr(sama_db, "DB_PATH", tmp_path / "t1_envelope_test.db")
    sama_db.init_db()
    return sama_db


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


_RESULT = {"n_bulb_observations": 3, "n_looks": 2, "grade_a_pct": 66.7,
           "grade_a_ci_low": 20.0, "grade_a_ci_high": 93.0,
           "defect_rate_corrected": 33.3}


def _make_lot(centre_id: int, lot_ref: str) -> int:
    out = sama_db.insert_lot(
        centre_id, lot_ref, dict(_RESULT),
        {"farmer_name": "F " + lot_ref, "officer_name": "O"},
    )
    return out["lot_id"]


@pytest.fixture()
def three_lots(tmp_db):
    cid = sama_db.upsert_centre("T1 Envelope Centre", "Test")
    return [_make_lot(cid, f"T1ENV-{i}") for i in range(3)]


def _raw_connect(db_mod) -> sqlite3.Connection:
    conn = sqlite3.connect(db_mod.DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _fetch_row(db_mod, lot_id: int) -> sqlite3.Row:
    conn = _raw_connect(db_mod)
    try:
        return conn.execute("SELECT * FROM lots WHERE id = ?",
                            (lot_id,)).fetchone()
    finally:
        conn.close()


def _rewrite_result_json(db_mod, lot_id: int, mutate) -> bytes:
    """The exact RT-001 attack: rewrite the stored result blob in place.

    Returns the ORIGINAL bytes so tests can restore them (the demo's own
    restore sweep relies on this being recoverable).
    """
    row = _fetch_row(db_mod, lot_id)
    original = row["result_json"].encode("utf-8")
    mutated = json.dumps(mutate(json.loads(row["result_json"])))
    conn = _raw_connect(db_mod)
    try:
        conn.execute("UPDATE lots SET result_json = ? WHERE id = ?",
                     (mutated, lot_id))
        conn.commit()
    finally:
        conn.close()
    return original


def _set_result_bytes(db_mod, lot_id: int, raw: bytes) -> None:
    conn = _raw_connect(db_mod)
    try:
        conn.execute("UPDATE lots SET result_json = ? WHERE id = ?",
                     (raw.decode("utf-8"), lot_id))
        conn.commit()
    finally:
        conn.close()


_LEGACY_TS = "2026-08-20T10:00:00+00:00"


def _insert_legacy_row(db_mod, centre_id: int, prev_hash: str) -> str:
    """A pre-T-1 record exactly as the OLD code signed it: 11 fields only."""
    payload = {
        "centre_id": centre_id,
        "lot_ref": "T1ENV-LEGACY",
        "farmer_name": "Old Farmer",
        "officer_name": "Old Officer",
        "created_at": _LEGACY_TS,
        "n_bulbs": 3,
        "n_looks": 1,
        "grade_a_pct": 66.7,
        "ci_low": 20.0,
        "ci_high": 93.0,
        "defect_pct": 33.3,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                           default=str)
    row_hash = hashlib.sha256((canonical + prev_hash).encode("utf-8")).hexdigest()
    conn = _raw_connect(db_mod)
    try:
        conn.execute(
            """INSERT INTO lots (centre_id, lot_ref, farmer_name, officer_name,
                                 created_at, lat, lon, n_looks, n_bulbs,
                                 grade_a_pct, ci_low, ci_high, defect_pct,
                                 n_referred, calibrated, scale_source, scale_conf,
                                 result_json, prev_hash, row_hash)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (centre_id, payload["lot_ref"], payload["farmer_name"],
             payload["officer_name"], payload["created_at"], None, None,
             payload["n_looks"], payload["n_bulbs"], payload["grade_a_pct"],
             payload["ci_low"], payload["ci_high"], payload["defect_pct"],
             0, 0, None, None,
             json.dumps({"grade_a_pct": 66.7}), prev_hash, row_hash),
        )
        conn.commit()
    finally:
        conn.close()
    return row_hash


# --------------------------------------------------------------------------
# 1. New records carry the digest, and it is bound INSIDE the payload
# --------------------------------------------------------------------------


def test_new_lots_pin_the_exact_result_bytes(tmp_db, three_lots):
    row = _fetch_row(tmp_db, three_lots[0])
    assert row["result_sha256"], "v2 record must store a result digest"
    assert row["result_sha256"] == sama_db.result_digest(row["result_json"]), (
        "digest must hash the EXACT stored bytes the certificate renders from")


def test_digest_is_inside_the_hashed_payload(tmp_db, three_lots):
    row = _fetch_row(tmp_db, three_lots[0])
    # v2 payload: 11 scalars + the digest -> matches stored row_hash...
    v2_payload = {
        "centre_id": row["centre_id"], "lot_ref": row["lot_ref"],
        "farmer_name": row["farmer_name"] or "",
        "officer_name": row["officer_name"] or "",
        "created_at": row["created_at"], "n_bulbs": row["n_bulbs"],
        "n_looks": row["n_looks"], "grade_a_pct": row["grade_a_pct"],
        "ci_low": row["ci_low"], "ci_high": row["ci_high"],
        "defect_pct": row["defect_pct"],
        "result_sha256": row["result_sha256"],
    }
    assert sama_db.compute_row_hash(v2_payload, row["prev_hash"]) \
        == row["row_hash"]
    # ...and the legacy 11-field computation does NOT match anymore: proof
    # the digest is actually bound into the signature, not stored beside it.
    legacy_payload = {k: v for k, v in v2_payload.items() if k != "result_sha256"}
    assert sama_db.compute_row_hash(legacy_payload, row["prev_hash"]) \
        != row["row_hash"], "digest must be INSIDE the hashed field set"


def test_untouched_v2_chain_audits_green(tmp_db, three_lots):
    intact, audits, n = sama_db.audit_chain(
        _fetch_row(tmp_db, three_lots[0])["centre_id"])
    assert intact is True
    assert n == 3
    assert all(a["ok"] for a in audits)


# --------------------------------------------------------------------------
# 2. THE regression: editing result_json can no longer hide
# --------------------------------------------------------------------------


def test_result_json_tamper_breaks_only_the_victim(tmp_db, three_lots):
    victim = three_lots[1]
    centre_id = _fetch_row(tmp_db, victim)["centre_id"]
    _rewrite_result_json(
        tmp_db, victim,
        lambda res: {**res, "grade_a_pct": 99.9})

    intact, audits, _ = sama_db.audit_chain(centre_id)
    ok_by_id = {a["lot_id"]: a["ok"] for a in audits}
    assert intact is False
    assert ok_by_id[victim] is False, "result-tampered record must go red"
    # Neighbours stay individually green -- no cascade (T-6 semantics kept).
    assert ok_by_id[three_lots[0]] is True
    assert ok_by_id[three_lots[2]] is True


def test_verify_api_flips_red_on_result_tamper(tmp_db, three_lots):
    victim = three_lots[1]
    _rewrite_result_json(
        tmp_db, victim,
        lambda res: {**res, "grade_pcts": {"A": 100.0}})

    body = client.get(f"/api/verify/{victim}").json()
    assert body["lot"]["this_record_ok"] is False, (
        "RT-001 question 1 must now answer: it does NOT stay green")
    assert body["result_integrity"]["covered"] is True
    assert body["result_integrity"]["ok"] is False
    assert body["envelope"] == "v2-numbers-covered"


def test_consistent_attacker_still_caught_by_the_chain(tmp_db, three_lots):
    """Editing result_json AND its digest column together cannot pass: the
    digest sits inside the row hash, which the attacker did not recompute."""
    victim = three_lots[0]
    row = _fetch_row(tmp_db, victim)
    forged = json.dumps({**json.loads(row["result_json"]),
                         "grade_a_pct": 99.9})
    new_digest = hashlib.sha256(forged.encode("utf-8")).hexdigest()

    conn = _raw_connect(tmp_db)
    try:
        conn.execute(
            "UPDATE lots SET result_json = ?, result_sha256 = ? WHERE id = ?",
            (forged, new_digest, victim))
        conn.commit()
    finally:
        conn.close()

    intact, audits, _ = sama_db.audit_chain(row["centre_id"])
    ok_by_id = {a["lot_id"]: a["ok"] for a in audits}
    assert intact is False
    assert ok_by_id[victim] is False


def test_restoring_the_original_bytes_restores_green(tmp_db, three_lots):
    victim = three_lots[2]
    centre_id = _fetch_row(tmp_db, victim)["centre_id"]
    original = _rewrite_result_json(
        tmp_db, victim, lambda res: {**res, "defect_rate_corrected": 0.0})
    assert sama_db.audit_chain(centre_id)[0] is False

    _set_result_bytes(tmp_db, victim, original)
    intact, audits, _ = sama_db.audit_chain(centre_id)
    assert intact is True
    assert all(a["ok"] for a in audits)


# --------------------------------------------------------------------------
# 3. Legacy records: honest, unchanged, not falsely reddened
# --------------------------------------------------------------------------


def test_legacy_null_digest_verifies_under_old_payload(tmp_db):
    cid = sama_db.upsert_centre("T1 Legacy Centre", "Test")
    _insert_legacy_row(tmp_db, cid, sama_db.GENESIS_HASH)

    intact, audits, n = sama_db.audit_chain(cid)
    assert intact is True, "migration must not redden pre-T-1 certificates"
    assert n == 1 and audits[0]["ok"] is True

    lot_id = audits[0]["lot_id"]
    body = client.get(f"/api/verify/{lot_id}").json()
    assert body["lot"]["this_record_ok"] is True
    assert body["result_integrity"] == {"covered": False, "ok": None}
    assert body["envelope"] == "v1-legacy-summary"


def test_mixed_legacy_then_v2_chain_links_and_audits(tmp_db):
    cid = sama_db.upsert_centre("T1 Mixed Centre", "Test")
    legacy_tip = _insert_legacy_row(tmp_db, cid, sama_db.GENESIS_HASH)
    v2 = _make_lot(cid, "T1ENV-AFTER-LEGACY")

    row = _fetch_row(tmp_db, v2)
    assert row["prev_hash"] == legacy_tip, "v2 must chain off the real tip"
    intact, audits, n = sama_db.audit_chain(cid)
    ok_by_id = {a["lot_id"]: a["ok"] for a in audits}
    assert intact is True and n == 2
    assert all(ok_by_id.values()), "mixed envelopes must coexist green"


def test_migration_adds_column_and_keeps_old_rows_green(tmp_path, monkeypatch):
    """A database created BEFORE T-1 upgrades in place; old rows stay green,
    the next finalize on the same file signs under v2."""
    db_file = tmp_path / "upgrade_me.db"
    legacy_schema = """
    CREATE TABLE IF NOT EXISTS centres (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE, district TEXT, created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS lots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        centre_id INTEGER NOT NULL REFERENCES centres(id),
        lot_ref TEXT NOT NULL, farmer_name TEXT, officer_name TEXT,
        created_at TEXT NOT NULL, lat REAL, lon REAL, n_looks INTEGER,
        n_bulbs INTEGER, grade_a_pct REAL, ci_low REAL, ci_high REAL,
        defect_pct REAL, n_referred INTEGER, calibrated INTEGER,
        scale_source TEXT, scale_conf REAL, result_json TEXT,
        evidence_json TEXT,
        prev_hash TEXT NOT NULL, row_hash TEXT NOT NULL);
    """
    conn = sqlite3.connect(db_file)
    try:
        conn.executescript(legacy_schema)
        conn.execute("INSERT INTO centres (name, district, created_at) "
                     "VALUES ('Upgrade Centre', 'Test', '2026-08-20')")
        conn.commit()
    finally:
        conn.close()

    monkeypatch.setattr(sama_db, "DB_PATH", db_file)
    sama_db.init_db()                      # must migrate quietly
    cid = 1
    legacy_tip = _insert_legacy_row(sama_db, cid, sama_db.GENESIS_HASH)
    assert sama_db.audit_chain(cid)[0] is True

    v2 = _make_lot(cid, "T1ENV-POST-UPGRADE")
    assert _fetch_row(sama_db, v2)["prev_hash"] == legacy_tip
    intact, _, n = sama_db.audit_chain(cid)
    assert intact is True and n == 2

    # Idempotent second init stays quiet and keeps working.
    sama_db.init_db()
    conn = sqlite3.connect(db_file)
    try:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(lots)")}
    finally:
        conn.close()
    assert {"evidence_json", "result_sha256"} <= cols


# --------------------------------------------------------------------------
# 4. End-to-end through the HTTP surface
# --------------------------------------------------------------------------


def test_finalize_signs_v2_and_verify_stays_green_until_edited(tmp_db):
    r = client.post("/finalize", json={
        "looks": [[_bulb()] * 3],
        "lot_ref": "T1ENV-E2E",
        "farmer_name": "E2E Farmer",
        "officer_name": "E2E Officer",
    })
    assert r.status_code == 200, r.text[:400]
    lot_id = r.json()["lot_id"]

    body = client.get(f"/api/verify/{lot_id}").json()
    assert body["result_integrity"] == {"covered": True, "ok": True}
    assert body["envelope"] == "v2-numbers-covered"
    assert body["lot"]["this_record_ok"] is True

    # NOTE: a lot of three sound A-grade bulbs certifies grade_a_pct=100.0,
    # so "bump it to 100" would rewrite byte-identical JSON -- not an attack.
    # Force a value the honest payload cannot hold.
    _rewrite_result_json(
        tmp_db, lot_id, lambda res: {**res, "grade_a_pct": 42.0})
    body = client.get(f"/api/verify/{lot_id}").json()
    assert body["lot"]["this_record_ok"] is False
    assert body["result_integrity"]["ok"] is False


def test_finalize_response_contract_unchanged(tmp_db):
    """The UI reads lot_id/row_hash/bulb_ids/result/evidence_saved/duplicate;
    the envelope work must not have reshaped that contract."""
    r = client.post("/finalize", json={
        "looks": [[_bulb()], []],
        "lot_ref": "T1ENV-SHAPE", "farmer_name": "A", "officer_name": "B",
    })
    body = r.json()
    for key in ("lot_id", "row_hash", "bulb_ids", "result",
                "evidence_saved", "duplicate"):
        assert key in body, key
    again = client.post("/finalize", json={
        "looks": [[_bulb()], []],
        "lot_ref": "T1ENV-SHAPE", "farmer_name": "A", "officer_name": "B",
    }).json()
    assert again["duplicate"] is True
    assert again["lot_id"] == body["lot_id"]
    assert again["row_hash"] == body["row_hash"]


def test_report_page_states_coverage_from_injected_data(tmp_db):
    cid = sama_db.upsert_centre("T1 Coverage Centre", "Test")
    lot_id = _make_lot(cid, "T1ENV-COV")
    html = client.get(f"/report/{lot_id}")
    assert html.status_code == 200
    assert '"result_integrity"' in html.text
    assert '"covered": true' in html.text or '"covered":true' in html.text


# --------------------------------------------------------------------------
# 5. Static contracts on the certificate page
# --------------------------------------------------------------------------


def test_report_has_guarded_coverage_line():
    assert 'id="hashCoverage"' in REPORT_HTML
    # The render block fills the line via textContent only -- certificate
    # fields must never inject markup there.
    render_block = REPORT_HTML.split("$('hash').textContent", 1)[1]
    assert "$('hashCoverage').textContent =" in render_block
    assert "innerHTML" not in render_block.split("$('wa')")[0]


def test_report_coverage_line_never_claims_without_data():
    # Missing result_integrity -> stay silent rather than claim anything.
    assert "ri.covered === true" in REPORT_HTML
    assert "ri.covered === false" in REPORT_HTML
