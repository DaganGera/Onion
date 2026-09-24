"""RT-001 T-7 regression tests: the certificate's evidence section.

Before this fix, /analyze returned an annotated JPEG into client memory and
nothing persisted it -- report.html's #shots grid stayed empty forever, so
the printed certificate carried numbers with no photographs. The contract
now:

    1. /finalize accepts {"shots": [{annotated, tray_id}, ...]} and stores
       one validated JPEG per look under data/evidence/lot_<id>/.
    2. A manifest (path + sha256 + size per look) lands in
       lots.evidence_json -- OUTSIDE the hash chain, like result_json;
       storing evidence must leave audit_chain intact.
    3. GET /report/<id> renders the stored photos as data URIs in the page
       payload; older lots without evidence still render, gallery hidden.
    4. Evidence can never block a certificate: corrupt/oversized/garbage
       shots are skipped with a note, a storage failure degrades to a note
       on a SUCCESSFUL 200 response.
    5. Databases created before the evidence_json column existed are
       migrated idempotently at init_db().

Run:
    C:/Users/ADMIN/AppData/Local/Programs/Python/Python311/python.exe -m pytest tests/test_evidence_thumbnails.py -q
"""

import base64
import hashlib
import json
import sqlite3
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import main as sama          # noqa: E402
from app import db as sama_db         # noqa: E402
from app import evidence as ev        # noqa: E402

client = TestClient(sama.app, raise_server_exceptions=False)


# --------------------------------------------------------------------------
# Fixtures / helpers
# --------------------------------------------------------------------------


@pytest.fixture()
def tmp_store(tmp_path, monkeypatch):
    """Isolated SQLite file AND evidence directory per test."""
    monkeypatch.setattr(sama.db, "DB_PATH", tmp_path / "evidence_test.db")
    monkeypatch.setattr(ev, "EVIDENCE_DIR", tmp_path / "evidence")
    sama.db.init_db()
    return tmp_path


def _jpeg_uri(payload: bytes = b"\xff\xd8fake-jpeg-bytes") -> str:
    return "data:image/jpeg;base64," + base64.b64encode(payload).decode("ascii")


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


def _finalize(looks, shots=None):
    body = {
        "looks": looks,
        "lot_ref": "QA-EVIDENCE",
        "farmer_name": "Evidence Farmer",
        "officer_name": "Evidence Officer",
    }
    if shots is not None:
        body["shots"] = shots
    r = client.post("/finalize", json=body)
    assert r.status_code == 200, r.text[:400]
    data = r.json()
    assert "error" not in data, data
    return data


def _manifest(lot_id):
    lot = sama.db.get_lot(lot_id)
    return lot["evidence"], lot


# --------------------------------------------------------------------------
# Unit: extract_shots validation matrix
# --------------------------------------------------------------------------


def test_extract_shots_happy_path():
    shots, skipped = ev.extract_shots([
        {"annotated": _jpeg_uri(b"one"), "tray_id": "T1"},
        {"annotated": _jpeg_uri(b"two"), "tray_id": "T2"},
    ])
    assert skipped == 0
    assert [s["tray_id"] for s in shots] == ["T1", "T2"]
    assert shots[0]["jpeg"] == b"one"
    assert shots[1]["look_index"] == 1


def test_extract_shots_skips_garbage_but_keeps_good():
    raw = [
        {"annotated": _jpeg_uri(b"good"), "tray_id": "T1"},
        "not even a dict",
        {"annotated": "data:image/png;base64,AAAA"},      # wrong prefix
        {"annotated": "data:image/jpeg;base64,!!!!"},     # bad base64
        {"no_image_key": True},
        {"annotated": "data:image/jpeg;base64,"},         # empty payload
    ]
    shots, skipped = ev.extract_shots(raw)
    assert len(shots) == 1 and shots[0]["jpeg"] == b"good"
    assert skipped == 5


def test_extract_shots_rejects_oversized(monkeypatch):
    monkeypatch.setattr(ev, "MAX_SHOT_BYTES", 8)
    shots, skipped = ev.extract_shots([
        {"annotated": _jpeg_uri(b"x" * 64), "tray_id": "T1"},
        {"annotated": _jpeg_uri(b"ok"), "tray_id": "T2"},
    ])
    assert [s["jpeg"] for s in shots] == [b"ok"]
    assert skipped == 1


def test_extract_shots_caps_number_of_looks(monkeypatch):
    monkeypatch.setattr(ev, "MAX_SHOTS_PER_LOT", 3)
    many = [{"annotated": _jpeg_uri(bytes([i])), "tray_id": f"T{i}"}
            for i in range(20)]
    shots, _skipped = ev.extract_shots(many)
    assert len(shots) == 3


def test_extract_shots_non_list_payload_is_empty_not_fatal():
    for junk in (None, "shots", {"0": {}}, 42):
        shots, skipped = ev.extract_shots(junk)
        assert shots == [] and skipped == 0


# --------------------------------------------------------------------------
# Unit: save + read back
# --------------------------------------------------------------------------


def test_save_lot_evidence_writes_files_and_manifest(tmp_path, monkeypatch):
    monkeypatch.setattr(ev, "EVIDENCE_DIR", tmp_path / "evidence")
    shots, _ = ev.extract_shots([
        {"annotated": _jpeg_uri(b"A" * 100), "tray_id": "T1"},
        {"annotated": _jpeg_uri(b"B" * 50), "tray_id": "T1"},
    ])
    manifest = ev.save_lot_evidence(7, shots)

    assert [m["look_index"] for m in manifest] == [0, 1]
    first = manifest[0]
    assert first["path"].replace("\\", "/") == "lot_7/look_0.jpg"
    assert first["bytes"] == 100
    assert first["sha256"] == hashlib.sha256(b"A" * 100).hexdigest()

    written = (tmp_path / "evidence" / "lot_7" / "look_0.jpg").read_bytes()
    assert written == b"A" * 100

    # Round trip through parse_manifest like the DB cell would carry it.
    assert ev.parse_manifest(json.dumps(manifest)) == manifest


def test_parse_manifest_tolerates_corrupt_cells():
    assert ev.parse_manifest(None) == []
    assert ev.parse_manifest("") == []
    assert ev.parse_manifest("{not json") == []
    assert ev.parse_manifest('{"a": 1}') == []          # not a list
    assert ev.parse_manifest('[{"look_index": 0}, 5]') == [{"look_index": 0}]


def test_page_views_escape_guard(tmp_path, monkeypatch):
    """A tampered manifest path must not escape the evidence directory."""
    monkeypatch.setattr(ev, "EVIDENCE_DIR", tmp_path / "evidence")
    secret = tmp_path / "secret.txt"
    secret.write_bytes(b"top secret")
    views = ev.page_views([
        {"look_index": 0, "path": "../secret.txt"},
        {"look_index": 1, "path": str(secret)},
        {"look_index": 2, "path": ""},
    ])
    assert views == []


def test_page_views_skips_missing_files(tmp_path, monkeypatch):
    monkeypatch.setattr(ev, "EVIDENCE_DIR", tmp_path / "evidence")
    shots, _ = ev.extract_shots([
        {"annotated": _jpeg_uri(b"kept"), "tray_id": "T1"},
        {"annotated": _jpeg_uri(b"gone"), "tray_id": "T1"},
    ])
    manifest = ev.save_lot_evidence(3, shots)
    (tmp_path / "evidence" / "lot_3" / "look_1.jpg").unlink()

    views = ev.page_views(manifest)
    assert len(views) == 1
    assert views[0]["look_index"] == 0
    assert views[0]["data_uri"].startswith("data:image/jpeg;base64,")
    assert base64.b64decode(views[0]["data_uri"].split(",", 1)[1]) == b"kept"


# --------------------------------------------------------------------------
# Integration: /finalize persists, /report shows
# --------------------------------------------------------------------------


def test_finalize_stores_evidence_and_report_renders_it(tmp_store):
    body = _finalize(
        [[_bulb()], [_bulb(cls_name="rotten", grade="B", dia=60.0)]],
        shots=[{"annotated": _jpeg_uri(b"look zero"), "tray_id": "T1"},
               {"annotated": _jpeg_uri(b"look one"), "tray_id": "T1"}],
    )
    assert body["evidence_saved"] == 2
    manifest, lot = _manifest(body["lot_id"])
    assert len(manifest) == 2
    assert lot["result"]["grade_a_pct"] is not None  # certificate intact

    page = client.get(f"/report/{body['lot_id']}")
    assert page.status_code == 200
    # The annotated thumbnails reach the page payload as fresh data URIs...
    assert "data:image/jpeg;base64," in page.text
    assert '"look_index": 1' in page.text.replace(", ", ", ")
    # ...and the template placeholder is fully substituted.
    assert "__LOT_DATA__" not in page.text


def test_finalize_without_shots_still_works_and_reports_zero(tmp_store):
    body = _finalize([[_bulb()]])
    assert body["evidence_saved"] == 0
    manifest, _lot = _manifest(body["lot_id"])
    assert manifest == []

    page = client.get(f"/report/{body['lot_id']}")
    assert page.status_code == 200
    assert "data:image/jpeg;base64," not in page.text


def test_corrupt_shot_never_blocks_the_certificate(tmp_store):
    body = _finalize(
        [[_bulb()]],
        shots=[{"annotated": "data:image/jpeg;base64,$$$not-b64$$$",
                "tray_id": "T1"}],
    )
    assert body["evidence_saved"] == 0
    assert "could not be stored" in body.get("evidence_note", "")


def test_mixed_good_and_bad_shots_store_only_the_good(tmp_store):
    body = _finalize(
        [[_bulb()], [_bulb()], [_bulb()]],
        shots=[{"annotated": _jpeg_uri(b"a"), "tray_id": "T1"},
               {"garbage": True},
               {"annotated": _jpeg_uri(b"c"), "tray_id": "T2"}],
    )
    assert body["evidence_saved"] == 2
    assert "could not be stored" in body.get("evidence_note", "")
    manifest, _ = _manifest(body["lot_id"])
    assert sorted(m["look_index"] for m in manifest) == [0, 2]


def test_deduped_retry_overwrites_same_files_not_new_ones(tmp_store, tmp_path):
    looks = [[_bulb()]]
    shots = [{"annotated": _jpeg_uri(b"same image"), "tray_id": "T1"}]

    first = _finalize(looks, shots=shots)
    # Byte-identical certified numbers -> dedupe returns the SAME lot.
    second = _finalize(looks, shots=shots)
    assert second["duplicate"] is True
    assert second["lot_id"] == first["lot_id"]
    assert second["evidence_saved"] == 1

    lot_dir = tmp_path / "evidence" / f"lot_{first['lot_id']}"
    assert sorted(p.name for p in lot_dir.iterdir()) == ["look_0.jpg"]

    manifest, _ = _manifest(first["lot_id"])
    assert manifest[0]["sha256"] == hashlib.sha256(b"same image").hexdigest()


def test_storage_failure_degrades_to_note_on_successful_certificate(
        tmp_store, monkeypatch):
    def explode(lot_id, shots):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(ev, "save_lot_evidence", explode)
    body = _finalize([[ _bulb() ]],
                     shots=[{"annotated": _jpeg_uri(b"doomed"), "tray_id": "T1"}])
    assert body["evidence_saved"] == 0
    assert "could not be saved to storage" in body.get("evidence_note", "")
    # The certificate itself exists and is whole.
    assert sama.db.get_lot(body["lot_id"]) is not None
    centre_id = sama.db.get_lot(body["lot_id"])["centre_id"]
    intact, audits, n = sama.db.audit_chain(centre_id)
    assert intact is True and n >= 1 and all(a["ok"] for a in audits)


def test_recording_evidence_leaves_hash_chain_intact(tmp_store):
    body = _finalize(
        [[_bulb(), _bulb(cls_name="black_smut", grade="C", dia=45.0)]],
        shots=[{"annotated": _jpeg_uri(b"photo"), "tray_id": "T1"}],
    )
    lot = sama.db.get_lot(body["lot_id"])
    intact, audits, n = sama.db.audit_chain(lot["centre_id"])
    assert intact is True
    assert all(a["ok"] for a in audits) and n >= 1

    # ...and the row hash matches the pre-evidence value: the hashed payload
    # does not know evidence_json exists.
    conn = sama_db.connect()
    try:
        row = conn.execute(
            "SELECT row_hash FROM lots WHERE id = ?", (body["lot_id"],)).fetchone()
    finally:
        conn.close()
    assert row["row_hash"] == body["row_hash"]


# --------------------------------------------------------------------------
# Migration: legacy database without the column
# --------------------------------------------------------------------------


def test_init_db_migrates_legacy_database_without_column(tmp_path, monkeypatch):
    db_file = tmp_path / "legacy.db"

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
        prev_hash TEXT NOT NULL, row_hash TEXT NOT NULL);
    """
    conn = sqlite3.connect(db_file, check_same_thread=False)
    try:
        conn.executescript(legacy_schema)
        conn.commit()
        cols_before = {r[1] for r in conn.execute("PRAGMA table_info(lots)")}
    finally:
        conn.close()
    assert "evidence_json" not in cols_before

    monkeypatch.setattr(sama_db, "DB_PATH", db_file)
    sama_db.init_db()   # must migrate quietly, not crash

    conn = sqlite3.connect(db_file, check_same_thread=False)
    try:
        cols_after = {r[1] for r in conn.execute("PRAGMA table_info(lots)")}
    finally:
        conn.close()
    assert "evidence_json" in cols_after

    # Idempotent: a second init on the migrated file stays quiet and green.
    sama_db.init_db()


def test_get_lot_on_legacy_row_without_manifest(tmp_store):
    """A lot finalized before T-7 reads back with an empty manifest."""
    body = _finalize([[_bulb()]])
    conn = sama_db.connect()
    try:
        conn.execute("UPDATE lots SET evidence_json = NULL WHERE id = ?",
                     (body["lot_id"],))
        conn.commit()
    finally:
        conn.close()
    lot = sama.db.get_lot(body["lot_id"])
    assert lot["evidence"] == []
    page = client.get(f"/report/{body['lot_id']}")
    assert page.status_code == 200
