"""QA task LOOP-Q2216 -- adversarial pass 2, six NEW failure modes.

test_failure_injection.py covers garbage uploads and malformed JSON. This
pass attacks the states AROUND the happy path that no test touched:

    1. CONCURRENT WRITES     two /finalize-equivalents racing on one centre
                             used to be able to read the same chain tip and
                             fork the hash chain -- every later certificate
                             at that centre then verifies as "tampered".
                             Plus: parallel /analyze must not cross-talk.
    2. DUPLICATE FINALIZE    a double-tap (or a retry after a wifi timeout)
                             used to certify the SAME lot twice; two signed
                             certificates for one physical lot is exactly
                             the dispute this product exists to settle.
    3. UNICODE GARBAGE       emoji/Devanagari names are the NORM here; lone
                             surrogates and control bytes are not. Worse:
                             farmer_name flowed into report/verify pages as
                             raw JSON inside <script>, so "</script>" in a
                             name could break out of the public trust page.
    4. CLOCK SKEW            the client's created_at was hashed and stored
                             verbatim -- a phone with a dead battery button
                             could mint a certificate dated 1970.
    5. DB DISK FULL          SQLITE_FULL during finalize used to surface as
                             a generic 500 with no hint whether the record
                             was saved (it was not) or what to do next.
    6. OVERSIZED MULTIPART   /analyze read the whole upload into RAM with no
                             cap; a curl probe or broken client could hand
                             it gigabytes, and a valid-but-huge image could
                             decode into a pixel bomb.

Contract under test is unchanged from Q-001: every failure answers JSON
{"error": <non-empty string>}, sane status, no traceback, and a path
forward. app/grading.py stays untouched.

Run:
    C:/Users/ADMIN/AppData/Local/Programs/Python/Python311/python.exe -m pytest tests/test_adversarial_q2216.py -q
"""

from __future__ import annotations

import json
import sqlite3
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import db as sama_db  # noqa: E402
from app import main as sama  # noqa: E402

client = TestClient(sama.app, raise_server_exceptions=False)


# --------------------------------------------------------------------------
# Helpers -- house style, self-contained on purpose
# --------------------------------------------------------------------------


def _expect_json_error(response, status=None):
    """The Q-001 contract every failure path must satisfy."""
    if status is not None:
        assert response.status_code == status, (
            f"expected HTTP {status}, got {response.status_code}: "
            f"{response.text[:400]!r}"
        )
    assert response.headers["content-type"].startswith("application/json"), (
        f"failure must be JSON: {response.text[:400]!r}"
    )
    body = response.json()
    assert isinstance(body, dict) and "error" in body, body
    message = body["error"]
    assert isinstance(message, str) and message.strip(), body
    assert "Traceback" not in response.text
    return body


@pytest.fixture()
def tmp_db(tmp_path, monkeypatch):
    """Isolated SQLite file so tests never touch data/sama.db."""
    monkeypatch.setattr(sama_db, "DB_PATH", tmp_path / "q2216_test.db")
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


def _finalize_payload(**overrides) -> dict:
    payload = {
        "looks": [[_bulb(), _bulb("rotten", grade="B", dia=65.0)],
                  [_bulb()]],
        "lot_ref": "QA-2216",
        "farmer_name": "Test Farmer",
        "officer_name": "Test Officer",
    }
    payload.update(overrides)
    return payload


def _finalize(**overrides) -> dict:
    r = client.post("/finalize", json=_finalize_payload(**overrides))
    assert r.status_code == 200, r.text[:400]
    body = r.json()
    assert "error" not in body, body
    return body


def _lot_count() -> int:
    conn = sama_db.connect()
    try:
        return conn.execute("SELECT COUNT(*) AS n FROM lots").fetchone()["n"]
    finally:
        conn.close()


def _gray_jpeg(width=32, height=32, level=127) -> bytes:
    """A decodable, mid-gray JPEG: passes quality gates, finds no markers."""
    img = np.full((height, width, 3), level, dtype=np.uint8)
    ok, buf = cv2.imencode(".jpg", img)
    assert ok, "fixture JPEG failed to encode"
    return buf.tobytes()


class _MustNotPredict:
    """Sentinel model: any call proves a rejection happened too late."""

    def predict(self, *args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("predict() ran on a payload that should have "
                             "been rejected before inference")


class _FakeResult:
    boxes = None


class _FakeModel:
    """Minimal stand-in: no boxes, tiny delay so requests can interleave."""

    def __init__(self, delay: float = 0.02):
        self.delay = delay
        self.calls = 0
        self._lock = threading.Lock()

    def predict(self, *args, **kwargs):  # noqa: ANN002, ANN003
        with self._lock:
            self.calls += 1
        time.sleep(self.delay)
        return [_FakeResult()]


# ==========================================================================
# 1. CONCURRENCY
# ==========================================================================


def test_concurrent_inserts_cannot_fork_the_hash_chain(tmp_db):
    """Two writers picking the same chain tip used to fork the chain: both
    rows carried prev_hash=H0, audit_chain flagged the second as tampered,
    and an honest officer's certificate went red. BEGIN IMMEDIATE must make
    tip-read + insert one serialized critical section."""
    centre_id = sama_db.upsert_centre("Race Centre")

    result = {"n_bulb_observations": 3, "n_looks": 1,
              "grade_a_pct": 66.67, "grade_a_ci_low": 12.5,
              "grade_a_ci_high": 98.16, "defect_rate_corrected": 0.0}

    def worker(i: int) -> int:
        return sama_db.insert_lot(
            centre_id=centre_id,
            lot_ref=f"QA-RACE-{i}",
            result=dict(result),
            meta={"farmer_name": f"Farmer {i}", "looks": [[_bulb()]]},
        )["lot_id"]

    for _round in range(3):
        barrier = threading.Barrier(8)

        def gated(i: int) -> int:
            barrier.wait(timeout=10)   # all threads hit the DB together
            return worker(i)

        with ThreadPoolExecutor(max_workers=8) as pool:
            ids = list(pool.map(gated, range(8)))

        assert len(set(ids)) == 8, "each writer must produce its own row"
        intact, audits, n = sama_db.audit_chain(centre_id)
        assert intact is True, (
            f"chain forked after concurrent inserts: "
            f"{[a for a in audits if not a['ok']]}"
        )
        assert n == (_round + 1) * 8


def test_concurrent_analyze_uploads_never_cross_talk(monkeypatch):
    """Six phones posting at once (venue wifi retry storm): every response
    must succeed AND echo its own lot_ref back -- no bleed between requests."""
    fake = _FakeModel()
    monkeypatch.setattr(sama, "MODEL", fake)
    monkeypatch.setattr(sama, "MODEL_ERROR", None)
    jpeg = _gray_jpeg()

    def upload(i: int) -> dict:
        r = client.post(
            "/analyze",
            files={"file": (f"tray{i}.jpg", jpeg, "image/jpeg")},
            data={"lot_ref": f"QA-PAR-{i}", "look_index": str(i)},
        )
        assert r.status_code == 200, r.text[:300]
        return r.json()

    with ThreadPoolExecutor(max_workers=6) as pool:
        bodies = list(pool.map(upload, range(6)))

    assert fake.calls == 6
    for i, body in enumerate(bodies):
        assert body["lot_ref"] == f"QA-PAR-{i}", body
        assert body["look_index"] == i
        assert body["n_bulbs"] == 0


def test_scale_cache_survives_a_thread_hammer_bounded(monkeypatch):
    """_LAST_GOOD_SCALE is shared mutable state across request threads; the
    hammer pins its two promises: never raises, never exceeds its bound."""
    monkeypatch.setattr(sama, "_LAST_GOOD_SCALE", {})
    errors: list[Exception] = []

    class _Scale:
        calibrated = True
        source = "homography"

    def hammer(i: int) -> None:
        try:
            for j in range(40):
                sama._remember_scale(f"lot-{j % 40}", _Scale())
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    with ThreadPoolExecutor(max_workers=16) as pool:
        list(pool.map(hammer, range(64)))

    assert not errors, errors
    assert len(sama._LAST_GOOD_SCALE) <= sama._MAX_REMEMBERED_LOTS


# ==========================================================================
# 2. DUPLICATE LOT FINALIZATION
# ==========================================================================


def test_duplicate_finalize_returns_the_same_certificate(tmp_db):
    """Retry after a network timeout must not mint a second certificate for
    the same physical lot. The second POST is answered from the first row."""
    first = _finalize()
    second_raw = client.post("/finalize", json=_finalize_payload())
    assert second_raw.status_code == 200, second_raw.text[:400]
    second = second_raw.json()

    assert second.get("duplicate") is True, (
        f"retry was silently certified again: {second}"
    )
    assert second["lot_id"] == first["lot_id"]
    assert second["row_hash"] == first["row_hash"]


def test_duplicate_finalize_writes_exactly_one_row_and_keeps_chain_intact(tmp_db):
    body = _finalize()
    _finalize()
    assert _lot_count() == 1, "double-tap must not double-certify"

    centre_id = sama_db.get_lot(body["lot_id"])["centre_id"]
    intact, _, n = sama_db.audit_chain(centre_id)
    assert intact is True and n == 1


def test_retry_without_created_at_still_dedupes(tmp_db):
    """The dedupe key excludes created_at ON PURPOSE: a retry seconds later
    carries a fresh server timestamp but is still the same certification."""
    first = _finalize(created_at="2026-08-24T08:00:00+00:00")
    second = _finalize()   # no created_at at all
    assert second.get("duplicate") is True
    assert second["lot_id"] == first["lot_id"]
    assert _lot_count() == 1


def test_duplicate_response_rebuilds_bulb_ids_shaped_like_looks(tmp_db):
    """The UI wires contest buttons to bulb ids; a duplicate answer must
    carry the same [look][bulb] shape as the original insert did."""
    first = _finalize()
    second = _finalize()
    assert second["bulb_ids"] == first["bulb_ids"]
    assert [len(look) for look in second["bulb_ids"]] == [2, 1]
    flat = second["bulb_ids"][0] + second["bulb_ids"][1]
    rows = sama_db.get_lot(first["lot_id"])["bulbs"]
    assert sorted(flat) == sorted(b["id"] for b in rows)


def test_changed_content_same_ref_is_a_new_certificate(tmp_db):
    """Dedupe must catch retries, not edits: different numbers under the
    same lot_ref is a genuine regrade and MUST create a new row."""
    first = _finalize(lot_ref="QA-REGRADE")
    second = _finalize(lot_ref="QA-REGRADE",
                       looks=[[_bulb("sprouted", grade="C", dia=40.0)]])
    assert second.get("duplicate") is False
    assert second["lot_id"] != first["lot_id"]
    assert _lot_count() == 2


def test_same_content_different_centre_is_not_deduped(tmp_db):
    """Scoping check: identical numbers at two centres are two lots."""
    c1 = sama_db.upsert_centre("Centre One")
    c2 = sama_db.upsert_centre("Centre Two")
    a = _finalize(centre_id=c1, lot_ref="QA-SHARED")
    b = _finalize(centre_id=c2, lot_ref="QA-SHARED")
    assert a.get("duplicate") is False and b.get("duplicate") is False
    assert a["lot_id"] != b["lot_id"]
    assert _lot_count() == 2


# ==========================================================================
# 3. UNICODE / MULTIBYTE GARBAGE
# ==========================================================================


def test_real_world_unicode_names_roundtrip_intact(tmp_db):
    """Devanagari + emoji + Tamil are NORMAL input here, not edge cases."""
    farmer = "प्याज़ किसान 🧅 விவசாயி"
    body = _finalize(farmer_name=farmer)
    stored = sama_db.get_lot(body["lot_id"])
    assert stored["farmer_name"] == farmer
    intact, _, _ = sama_db.audit_chain(stored["centre_id"])
    assert intact is True
    page = client.get(f"/report/{body['lot_id']}")
    assert page.status_code == 200
    assert farmer in page.text


def test_script_injection_in_farmer_name_cannot_break_report_page(tmp_db):
    """farmer_name used to reach the certificate page as RAW JSON inside a
    <script> block; '</script>' in a name closed the element early and let
    an attacker run markup on the PUBLIC verify/report surface."""
    hostile = '</script><img src=x onerror="window.__pwned=1">'
    body = _finalize(farmer_name=hostile)

    page = client.get(f"/report/{body['lot_id']}")
    assert page.status_code == 200
    # The breakout SEQUENCE must not survive raw into the page...
    assert "</script><img" not in page.text, "script breakout on /report"
    # ...and the name must ship ESCAPED (a JS string reading \u003c still
    # displays '<' to the officer -- escaping changes parsing, not content).
    assert "\\u003c/script\\u003e" in page.text
    assert "Traceback" not in page.text


def test_script_injection_cannot_break_public_verify_page(tmp_db):
    hostile = "<script>alert('sama')</script>"
    body = _finalize(officer_name=hostile)

    page = client.get(f"/verify/{body['lot_id']}")
    assert page.status_code == 200
    assert "<script>alert" not in page.text, "raw script tag on /verify"
    assert "Traceback" not in page.text


def test_unicode_line_separator_never_reaches_page_raw(tmp_db):
    """U+2028 is valid inside a JSON string but terminates JS string
    literals on pre-ES2019 engines -- exactly the cheap Android WebView this
    product targets. It must ship escaped, like any other hazard char."""
    body = _finalize(farmer_name="Line\u2028Sep")
    page = client.get(f"/report/{body['lot_id']}")
    assert "\u2028" not in page.text, "raw U+2028 shipped to a JS context"


def test_lone_surrogate_rejected_with_named_field_and_no_row(tmp_db):
    """A lone surrogate cannot be encoded to UTF-8; binding it used to blow
    up deep inside sqlite as a generic 500. Now: 400, field named, and the
    ledger untouched."""
    # Send raw bytes: httpx's own JSON encoder politely refuses surrogates,
    # but a hostile client has no such manners.
    raw = json.dumps(_finalize_payload(farmer_name="\ud800")).encode(
        "utf-8", "surrogatepass")
    before = _lot_count()
    r = client.post("/finalize", content=raw,
                    headers={"Content-Type": "application/json"})
    body = _expect_json_error(r, status=400)
    assert "farmer_name" in body["error"], body["error"]
    assert _lot_count() == before, "rejected payload must write nothing"


def test_null_byte_is_stripped_not_stored(tmp_db):
    """NUL in TEXT truncates the value for every C-string consumer of the
    database. Transport junk is stripped; the readable name survives."""
    body = _finalize(officer_name="Offi\x00cer")
    stored = sama_db.get_lot(body["lot_id"])
    assert stored["officer_name"] == "Officer"
    intact, _, _ = sama_db.audit_chain(stored["centre_id"])
    assert intact is True


def test_overlong_text_field_rejected_400(tmp_db):
    """Silent truncation would ALTER a signed record without trace; over-
    limit text is refused with the limit named instead."""
    r = client.post("/finalize", json=_finalize_payload(farmer_name="अ" * 600))
    body = _expect_json_error(r, status=400)
    assert "farmer_name" in body["error"]
    assert "600" in body["error"] or "long" in body["error"].lower()


def test_nested_surrogate_in_bulb_rows_is_400_not_500(tmp_db):
    """Top-level fields are cleaned per-field; garbage hiding INSIDE look
    bulbs only surfaces at the bulbs INSERT. That must still answer 400
    with guidance, never the generic 500 'Could not save lot' shrug."""
    # NOTE: the garbage must be an UNPAIRED surrogate. A \ud83f\udfff-style
    # pair is valid UTF-16 -- json.loads legitimately folds it into one
    # astral char (U+1FFFF), which stores fine and would make this test
    # assert the wrong thing.
    looks = [[{"bbox": [0, 0, 5, 5], "cls": 0, "cls_name": "\ud800",
               "confidence": 0.9, "size_grade": "A", "decision": "ACCEPT"}]]
    # Raw bytes again -- the surrogate must actually reach the server.
    raw = json.dumps(_finalize_payload(looks=looks)).encode(
        "utf-8", "surrogatepass")
    r = client.post("/finalize", content=raw,
                    headers={"Content-Type": "application/json"})
    body = _expect_json_error(r, status=400)
    assert "storing" in body["error"] or "character" in body["error"], (
        body["error"]
    )
    assert "Traceback" not in r.text


# ==========================================================================
# 4. CLOCK SKEW IN LOT TIMESTAMPS
# ==========================================================================

_SKEW_CASES = {
    "garbage": "when the mangoes ripened",
    "ancient": "1999-12-31T23:59:59+00:00",
    "future": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
}


@pytest.mark.parametrize("case", sorted(_SKEW_CASES))
def test_implausible_client_timestamps_fall_back_to_server_time(tmp_db, case):
    """The server vouches for every certificate timestamp. A client clock
    that is wrong by more than the skew window loses its vote."""
    body_raw = client.post(
        "/finalize", json=_finalize_payload(created_at=_SKEW_CASES[case]))
    assert body_raw.status_code == 200, body_raw.text[:400]
    body = body_raw.json()
    assert body.get("server_timestamp_used") is True, (
        f"{case}: client timestamp accepted uncritically"
    )

    stored = sama_db.get_lot(body["lot_id"])
    stored_dt = datetime.fromisoformat(stored["created_at"])
    skew = abs(stored_dt - datetime.now(timezone.utc))
    assert skew < timedelta(minutes=10), (
        f"{case}: stored {stored['created_at']!r} is not server-present time"
    )


def test_plausible_offset_timestamp_preserved_verbatim(tmp_db):
    """Overzealous normalization would be its own defect: an officer phone
    with a correct IST offset keeps its exact string (and its hash)."""
    plausible = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    body = _finalize(created_at=plausible)

    # Absent (or false) -- no substitution happened, no flag is owed.
    assert not body.get("server_timestamp_used"), body
    stored = sama_db.get_lot(body["lot_id"])
    assert stored["created_at"] == plausible


# ==========================================================================
# 5. DB DISK FULL
# ==========================================================================


class _DiskFullConnection:
    """Delegates everything to a real connection except COMMIT, which fails
    the way SQLite does on a full volume (SQLITE_FULL surfaces at commit,
    when the WAL has nowhere left to grow)."""

    def __init__(self, conn: sqlite3.Connection):
        object.__setattr__(self, "_conn", conn)

    def __getattr__(self, name):
        return getattr(self._conn, name)

    def __setattr__(self, name, value):
        setattr(self._conn, name, value)

    def execute(self, sql, *args, **kwargs):
        if sql.lstrip().upper().startswith("COMMIT"):
            raise sqlite3.OperationalError("database or disk is full")
        return self._conn.execute(sql, *args, **kwargs)


def test_disk_full_finalize_is_actionable_and_writes_nothing(tmp_db, monkeypatch):
    """SQLITE_FULL used to escape as 500 'Could not save lot:
    OperationalError' -- technically JSON, practically useless: the officer
    cannot tell whether the certificate exists (half-saved evidence in a
    dispute!) or what to do. Contract now: 503, storage named, NOT saved,
    free-space instruction, zero partial rows, chain intact."""
    centre_id = sama_db.upsert_centre("Full Disk Centre")
    before = _lot_count()

    real_connect = sama_db.connect

    def full_connect():
        return _DiskFullConnection(real_connect())

    monkeypatch.setattr(sama_db, "connect", full_connect)
    r = client.post("/finalize", json=_finalize_payload(centre_id=centre_id))
    # Targeted restore: a blanket monkeypatch.undo() here would also undo
    # the tmp_db fixture's DB_PATH patch (same MonkeyPatch instance) and
    # silently point the assertions below at the real demo database.
    monkeypatch.setattr(sama_db, "connect", real_connect)

    body = _expect_json_error(r, status=503)
    lowered = body["error"].lower()
    assert "storage" in lowered or "disk" in lowered or "space" in lowered, (
        body["error"]
    )
    assert "not saved" in lowered or "wasn't saved" in lowered, body["error"]
    assert _lot_count() == before, "failed commit must leave zero partial rows"

    intact, _, _ = sama_db.audit_chain(centre_id)
    assert intact is True, "a failed finalize must not damage the chain"


# ==========================================================================
# 6. OVERSIZED MULTIPART / PIXEL BOMBS
# ==========================================================================


def test_upload_over_cap_rejected_before_inference(monkeypatch):
    """/analyze used to slurp the entire upload into RAM unbounded. Over
    the cap must short-circuit as 413 with the limit named -- and the
    sentinel model proves nothing reached inference."""
    monkeypatch.setattr(sama, "MODEL", _MustNotPredict())
    monkeypatch.setattr(sama, "MODEL_ERROR", None)

    blob = np.random.default_rng(7).bytes(sama.MAX_UPLOAD_BYTES + 1)
    r = client.post(
        "/analyze",
        files={"file": ("huge.bin", blob, "application/octet-stream")},
        data={"lot_ref": "QA-BIG"},
    )
    body = _expect_json_error(r, status=413)
    mb = sama.MAX_UPLOAD_BYTES // (1024 * 1024)
    assert str(mb) in body["error"], body["error"]
    assert "retake" in body["error"].lower() or "lower" in body["error"].lower(), (
        body["error"]
    )


def test_huge_dimension_image_is_downscaled_not_rejected(monkeypatch):
    """A small FILE can still decode into a huge frame (pixel bomb: a
    100 MP JPEG costs ~300 MB of RAM mid-request). Oversized frames are
    resized down and graded anyway -- refusing a valid tray photo helps
    nobody -- but the response says it happened."""
    monkeypatch.setattr(sama, "MODEL", _FakeModel(delay=0.0))
    monkeypatch.setattr(sama, "MODEL_ERROR", None)

    big = np.full((8000, 8000, 3), 127, dtype=np.uint8)   # 64 MP > guard
    ok, buf = cv2.imencode(".jpg", big)
    assert ok
    r = client.post(
        "/analyze",
        files={"file": ("bomb.jpg", buf.tobytes(), "image/jpeg")},
        data={"lot_ref": "QA-BOMB"},
    )
    assert r.status_code == 200, r.text[:300]
    body = r.json()
    assert body.get("resized_from") == [8000, 8000], (
        "oversized decode must announce its downscale"
    )


def test_normal_photo_is_unaffected_by_both_caps(monkeypatch):
    monkeypatch.setattr(sama, "MODEL", _FakeModel(delay=0.0))
    monkeypatch.setattr(sama, "MODEL_ERROR", None)
    r = client.post(
        "/analyze",
        files={"file": ("tray.jpg", _gray_jpeg(), "image/jpeg")},
        data={"lot_ref": "QA-NORMAL"},
    )
    assert r.status_code == 200, r.text[:300]
    body = r.json()
    assert body["n_bulbs"] == 0
    assert "resized_from" not in body
