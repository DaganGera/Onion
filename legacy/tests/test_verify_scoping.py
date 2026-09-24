"""LOOP-I2222 -- RT-001 T-6: the verify verdict belongs to ONE record.

The bug: verify.html computed its banner as
    okRecord = chain.intact && lot.this_record_ok
but chain.intact is CENTRE-WIDE. Tamper lot #3 at a centre and intact
lot #7 used to show "TAMPERED RECORD DETECTED" -- a false accusation on a
legitimate certificate, exactly what a hostile judge would poke (RT-001
question 6), while the audit list on the same page said the later rows were
fine. The page contradicted itself by construction.

Contract after this pass:
  1. /api/verify/{id} keeps reporting BOTH signals independently:
     lot.this_record_ok (this record only) and chain.intact (whole centre).
     No db.py change -- audit_chain already computes per-record truth
     correctly; only the frontend gate was wrong.
  2. An intact record stays green while another record at the centre is
     broken, with a separate amber explanation naming the localization.
  3. A genuinely altered record still goes red.
  4. Copy matches implementation: no "breaks every hash after it"
     overclaim, no "signed on-device" signature claim (RT-001 T-2 /
     EVIDENCE_AUDIT V1 wording: integrity is not accuracy).

Run:
    C:/Users/ADMIN/AppData/Local/Programs/Python/Python311/python.exe -m pytest tests/test_verify_scoping.py -q
"""

from __future__ import annotations

import re
import sqlite3
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import db as sama_db  # noqa: E402
from app import main as sama  # noqa: E402

STATIC = Path(__file__).resolve().parents[1] / "app" / "static"
VERIFY_HTML = (STATIC / "verify.html").read_text(encoding="utf-8")
REPORT_HTML = (STATIC / "report.html").read_text(encoding="utf-8")

client = TestClient(sama.app, raise_server_exceptions=False)


@pytest.fixture()
def tmp_db(tmp_path, monkeypatch):
    """Isolated SQLite file so tests never touch data/sama.db."""
    monkeypatch.setattr(sama_db, "DB_PATH", tmp_path / "i2222_test.db")
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


def _make_lot(centre_id: int, lot_ref: str) -> int:
    out = sama_db.insert_lot(
        centre_id, lot_ref,
        {"n_bulb_observations": 3, "n_looks": 2, "grade_a_pct": 66.7,
         "grade_a_ci_low": 20.0, "grade_a_ci_high": 93.0,
         "defect_rate_corrected": 33.3},
        {"farmer_name": "F " + lot_ref, "officer_name": "O"},
    )
    return out["lot_id"]


@pytest.fixture()
def three_lots(tmp_db):
    cid = sama_db.upsert_centre("I2222 Centre", "Test")
    return [_make_lot(cid, f"I2222-{i}") for i in range(3)]


def _tamper_grade_a(db_mod, lot_id: int) -> None:
    """Edit a HASHED column directly, like the tamper demo does."""
    conn = sqlite3.connect(db_mod.DB_PATH)
    try:
        conn.execute("UPDATE lots SET grade_a_pct = 99.9 WHERE id = ?", (lot_id,))
        conn.commit()
    finally:
        conn.close()


# --------------------------------------------------------------------------
# Backend contract: the two signals stay independent
# --------------------------------------------------------------------------


def test_all_records_intact_when_untouched(tmp_db, three_lots):
    body = client.get(f"/api/verify/{three_lots[1]}").json()
    assert body["lot"]["this_record_ok"] is True
    assert body["chain"]["intact"] is True


def test_tampered_record_flags_itself_only(tmp_db, three_lots):
    victim = three_lots[1]
    _tamper_grade_a(tmp_db, victim)

    bad = client.get(f"/api/verify/{victim}").json()
    assert bad["chain"]["intact"] is False
    assert bad["lot"]["this_record_ok"] is False

    # THE REGRESSION: neighbours of a broken record are NOT falsely accused.
    # Their hashes verify against their own stored contents (audit_chain
    # continues from the stored hash by design).
    for neighbour in (three_lots[0], three_lots[2]):
        ok = client.get(f"/api/verify/{neighbour}").json()
        assert ok["lot"]["this_record_ok"] is True, (
            f"intact lot {neighbour} accused of tampering")
        assert ok["chain"]["intact"] is False


def test_verify_payload_carries_both_signals(tmp_db, three_lots):
    _tamper_grade_a(tmp_db, three_lots[1])
    body = client.get(f"/api/verify/{three_lots[2]}").json()
    # Both keys must exist so the page can separate verdict from context.
    assert set(body) >= {"lot", "chain"}
    assert "this_record_ok" in body["lot"]
    assert "audit" in body["chain"] and len(body["chain"]["audit"]) == 3
    # The audit list itself must localize the break to the victim alone.
    audit_ok = {a["lot_id"]: a["ok"] for a in body["chain"]["audit"]}
    assert audit_ok == {three_lots[0]: True,
                        three_lots[1]: False,
                        three_lots[2]: True}


def test_verify_page_renders_for_intact_lot_in_broken_centre(tmp_db, three_lots):
    """The public page must build even when the centre chain is broken --
    a verifier scanning the paper QR mid-dispute is exactly when it matters."""
    _tamper_grade_a(tmp_db, three_lots[1])
    r = client.get(f"/verify/{three_lots[2]}")
    assert r.status_code == 200
    assert '"this_record_ok": true' in r.text or '"this_record_ok":true' in r.text


# --------------------------------------------------------------------------
# Frontend static contracts: the verdict gate and the honest copy
# --------------------------------------------------------------------------


def test_verdict_gated_on_this_record_alone():
    assert re.search(r"okRecord\s*=\s*!!lot\.this_record_ok", VERIFY_HTML), (
        "verdict must key off lot.this_record_ok alone")


def test_old_cascading_gate_is_gone():
    assert not re.search(
        r"okRecord\s*=\s*chain\.intact\s*&&\s*lot\.this_record_ok", VERIFY_HTML), (
        "centre-wide chain.intact must never gate THIS record's verdict")


def test_amber_context_card_exists_and_is_wired():
    assert 'id="otherBreak"' in VERIFY_HTML
    assert re.search(r"otherBreak['\"]\)\.classList\.toggle\(\s*'hidden',\s*"
                     r"!\(okRecord && !chain\.intact\)", VERIFY_HTML)


def test_integrity_vs_accuracy_wording():
    # EVIDENCE_AUDIT V1: "CERTIFICATE VERIFIED" read as an accuracy claim.
    assert "RECORD INTACT" in VERIFY_HTML
    assert "CERTIFICATE VERIFIED" not in VERIFY_HTML
    assert "does not re-measure the onions" in VERIFY_HTML


def test_no_unsupported_signature_claim():
    # RT-001 T-2 / research P4: taps are confirmations, not signatures.
    assert "signed on-device by both parties" not in VERIFY_HTML
    assert "not a" in VERIFY_HTML and "cryptographic signature" in VERIFY_HTML


def test_no_cascade_overclaim_on_report():
    # Copy must match audit_chain's real behaviour (db.py docstring aligned).
    assert "breaks every hash" not in REPORT_HTML
    assert re.search(r"individually\s+detectable", REPORT_HTML)
