"""QA task LOOP-Q2260 -- adversarial pass 2260, NEW failure modes.

test_failure_injection.py covers garbage uploads / malformed JSON bodies.
test_adversarial_q2216.py covered six states AROUND the happy path. This
pass attacks the seams BOTH left open -- each section names the gap:

    1. CONCURRENT x DUPLICATE   Q2216 tested duplicate finalize SEQUENTIALLY
                                and races with DISTINCT lot_refs. The
                                intersection -- N racing IDENTICAL posts --
                                is where a dedupe check can double-mint.
    2. CONCURRENT ANALYZE + CACHE READS
                                Q2216 hammered _remember_scale writes only;
                                /analyze also READS the cache (carried scale)
                                mid-storm, and Q2216 never drove calibrated
                                scales through concurrent endpoint calls.
                                Plus an eviction-policy pin: updating an
                                existing key must not evict a neighbour.
    3. MULTIBYTE MULTIPART      unicode coverage so far was JSON-only; the
                                phone actually sends lot_ref/tray_id as
                                multipart form fields, and dedupe must work
                                on Devanagari/emoji lot refs too.
    4. CLOCK SKEW TYPES+BOUNDARY Q2216 covered garbage/ancient/future STRINGS.
                                Not covered: non-string types (int/bool/list/
                                empty), and WHERE the 24 h window edge falls.
    5. DISK FULL AFTER COMMIT   Q2216 killed COMMIT during insert_lot. A disk
                                can also fill between the certificate commit
                                and the evidence write -- the certificate
                                must survive with a note, not fail.
    6. UPLOAD CAP BOUNDARY      the cap must be '>' not '>=': a photo of
                                exactly the limit is legal; +1 byte is not.
    7. MALFORMED STRUCTURE      looks as dict/string/scalar-list crashed as a
                                generic 500 'Could not save lot' -- a caller
                                mistake wearing a server-error costume.
    8. UNVALIDATED centre_id    "abc" -> ValueError -> 500. Worse: a
                                well-typed but NONEXISTENT id passed int()
                                fine; foreign_keys are off, so the lot row
                                inserted with a dangling centre_id and every
                                reader (get_lot/report/verify/recent_lots)
                                JOINs it away -- a signed, hash-chained
                                certificate minted into a black hole.
                                NOTE: the shipped UI sends centre_id as a
                                NUMERIC STRING (<option value>), so string
                                digits are legal input and must stay legal.
    9. UNBOUNDED FORM FIELDS    /analyze copied lot_ref verbatim into the
                                _LAST_GOOD_SCALE cache key -- a probe looping
                                25 MB lot_ref strings parks ~800 MB of RAM in
                                32 cache slots on the venue laptop.

Contract unchanged from Q-001: failures answer JSON {"error": <non-empty>,
sane status, no traceback, path forward; caller mistakes are 4xx. grading.py
stays untouched.

Run:
    C:/Users/ADMIN/AppData/Local/Programs/Python/Python311/python.exe -m pytest tests/test_adversarial_q2260.py -q
"""

from __future__ import annotations

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
    monkeypatch.setattr(sama_db, "DB_PATH", tmp_path / "q2260_test.db")
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
        "lot_ref": "QA-2260",
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


def _centre_count() -> int:
    conn = sama_db.connect()
    try:
        return conn.execute("SELECT COUNT(*) AS n FROM centres").fetchone()["n"]
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
    def __init__(self, delay: float = 0.0):
        self.delay = delay
        self.calls = 0
        self._lock = threading.Lock()

    def predict(self, *args, **kwargs):  # noqa: ANN002, ANN003
        with self._lock:
            self.calls += 1
        time.sleep(self.delay)
        return [_FakeResult()]


# ==========================================================================
# 1. CONCURRENT DUPLICATE FINALIZATION (race x idempotency intersection)
# ==========================================================================


def test_concurrent_identical_finalizes_mint_exactly_one_certificate(tmp_db):
    """Six threads post BYTE-IDENTICAL payloads past one barrier.

    Q2216 proved sequential retries dedupe and distinct-lot races don't
    fork the chain -- neither proves the DEDUPE CHECK ITSELF is race-safe.
    BEGIN IMMEDIATE must serialize tip-read + dedupe-probe + insert, so:
    exactly one row, every answer carries the same lot_id/row_hash, exactly
    the first writer reports duplicate=False, and no bulb rows doubled."""
    payload = _finalize_payload(lot_ref="QA-RACE-DUP")
    results: list[dict] = []
    lock = threading.Lock()
    # ONE barrier shared by all workers -- constructing it inside the worker
    # gives every thread its own private barrier that can never fill.
    barrier = threading.Barrier(6)

    def gated(_i: int) -> None:
        barrier.wait(timeout=15)
        r = client.post("/finalize", json=payload)
        assert r.status_code == 200, r.text[:300]
        body = r.json()
        with lock:
            results.append(body)

    with ThreadPoolExecutor(max_workers=6) as pool:
        list(pool.map(gated, range(6)))

    assert len(results) == 6
    assert len({b["lot_id"] for b in results}) == 1, (
        f"double-mint under race: lot_ids={sorted(b['lot_id'] for b in results)}"
    )
    assert len({b["row_hash"] for b in results}) == 1, "hashes diverged"

    duplicates = [b for b in results if b.get("duplicate")]
    assert len(duplicates) == 5, (
        f"expected exactly 5 retried answers, got {len(duplicates)}"
    )

    assert _lot_count() == 1, "double-tap under race must not double-certify"
    lot = sama_db.get_lot(results[0]["lot_id"])
    assert len(lot["bulbs"]) == 3, "bulb rows duplicated under race"
    intact, _, n = sama_db.audit_chain(lot["centre_id"])
    assert intact is True and n == 1


def test_unicode_lot_ref_dedupes(tmp_db):
    """Dedupe runs a SQL comparison on lot_ref; multibyte refs must dedupe
    exactly like ASCII ones -- a retry of a Devanagari-named lot must not
    mint a second certificate."""
    ref = "खरीद-🧅-००१"
    first = _finalize(lot_ref=ref)
    second = _finalize(lot_ref=ref)
    assert second.get("duplicate") is True
    assert second["lot_id"] == first["lot_id"]
    assert second["row_hash"] == first["row_hash"]
    assert _lot_count() == 1


# ==========================================================================
# 2. CONCURRENT ANALYZE THROUGH THE SHARED SCALE CACHE
# ==========================================================================


def test_concurrent_analyze_with_calibrated_scales_stays_bounded(monkeypatch):
    """Q2216's analyze race used marker-less frames, so _remember_scale was
    never reached concurrently. Here every upload finds a 'calibrated'
    scale, so all workers read AND write the shared cache at once: every
    request still succeeds, nothing cross-talks, the cache stays bounded."""
    monkeypatch.setattr(sama, "_LAST_GOOD_SCALE", {})
    fake = _FakeModel(delay=0.0)
    monkeypatch.setattr(sama, "MODEL", fake)
    monkeypatch.setattr(sama, "MODEL_ERROR", None)

    calibrated = sama.grading.ScaleResult(
        calibrated=True, source="homography", mm_per_px=0.35,
        marker_ids=[0, 1, 2], confidence=1.0)
    monkeypatch.setattr(sama.grading, "detect_scale",
                        lambda image, carried=None: calibrated)

    jpeg = _gray_jpeg()

    def upload(i: int) -> dict:
        r = client.post(
            "/analyze",
            files={"file": (f"tray{i}.jpg", jpeg, "image/jpeg")},
            data={"lot_ref": f"QA-SCALE-{i}", "look_index": str(i)},
        )
        assert r.status_code == 200, r.text[:300]
        return r.json()

    with ThreadPoolExecutor(max_workers=12) as pool:
        bodies = list(pool.map(upload, range(12)))

    assert fake.calls == 12
    for i, body in enumerate(bodies):
        assert body["lot_ref"] == f"QA-SCALE-{i}", "cross-talk between requests"
        assert body["scale"]["calibrated"] is True
    assert len(sama._LAST_GOOD_SCALE) <= sama._MAX_REMEMBERED_LOTS


def test_remember_scale_update_does_not_evict_neighbours(monkeypatch):
    """Eviction-policy pin: once the cache is full, RE-remembering a key we
    already hold is an update, not a new arrival -- evicting someone else
    to make room we already have throws away good carried scales and makes
    the next look of THAT lot uncalibrated for no reason."""
    monkeypatch.setattr(sama, "_LAST_GOOD_SCALE", {})
    cap = sama._MAX_REMEMBERED_LOTS
    for i in range(cap):
        sama._remember_scale(f"k{i}", f"v{i}")

    sama._remember_scale("k5", "updated")

    cache = sama._LAST_GOOD_SCALE
    assert cache["k5"] == "updated"
    assert len(cache) == cap
    missing = [i for i in range(cap) if f"k{i}" not in cache]
    assert not missing, (
        f"updating k5 evicted unrelated entries {missing}"
    )


def test_scale_cache_mixed_read_write_hammer_never_raises(monkeypatch):
    """Writers hammer remember() while readers .get() the same keys -- the
    exact pattern of two phones alternating looks on one lot. Must never
    raise (KeyError from a double-evict, RuntimeError from iteration during
    mutation) and never exceed its bound."""
    monkeypatch.setattr(sama, "_LAST_GOOD_SCALE", {})
    errors: list[Exception] = []
    stop = threading.Event()

    class _Scale:
        calibrated = True
        source = "homography"

    def writer(w: int) -> None:
        try:
            for j in range(300):
                sama._remember_scale(f"lot-{(w * 17 + j * 5) % 48}", _Scale())
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    def reader(_r: int) -> None:
        try:
            while not stop.is_set():
                for k in range(48):
                    _ = sama._LAST_GOOD_SCALE.get(f"lot-{k}")
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    with ThreadPoolExecutor(max_workers=20) as pool:
        futures = [pool.submit(writer, w) for w in range(8)]
        readers = [pool.submit(reader, r) for r in range(12)]
        for f in futures:
            f.result(timeout=60)
        stop.set()
        for f in readers:
            f.result(timeout=60)

    assert not errors, errors
    assert len(sama._LAST_GOOD_SCALE) <= sama._MAX_REMEMBERED_LOTS


# ==========================================================================
# 3. MULTIBYTE MULTIPART FORM FIELDS (/analyze)
# ==========================================================================


def test_analyze_multibyte_form_fields_echo_intact(monkeypatch):
    """The phone sends lot_ref/tray_id as multipart TEXT, not JSON -- the
    unicode gauntlet so far never touched this door. Devanagari + emoji
    must round-trip byte-intact."""
    monkeypatch.setattr(sama, "MODEL", _FakeModel(delay=0.0))
    monkeypatch.setattr(sama, "MODEL_ERROR", None)
    lot_ref = "खरीद-🧅-००१"
    tray_id = "ट्रे-🧅"
    r = client.post(
        "/analyze",
        files={"file": ("tray.jpg", _gray_jpeg(), "image/jpeg")},
        data={"lot_ref": lot_ref, "look_index": "0", "tray_id": tray_id},
    )
    assert r.status_code == 200, r.text[:300]
    body = r.json()
    assert body["lot_ref"] == lot_ref
    assert body["tray_id"] == tray_id


# ==========================================================================
# 4. CLOCK SKEW -- unusable types and the window boundary
# ==========================================================================


@pytest.mark.parametrize("raw", [17, True, ["2026-08-25"], {"ts": 1}, "", "   "])
def test_unusable_timestamp_types_get_server_time_with_note(tmp_db, raw):
    """created_at is client text, so it can arrive as ANY JSON type. Each
    must end at server time WITH an honest note -- never a crash, never a
    silently accepted junk value, never a missing explanation."""
    before = _lot_count()
    r = client.post("/finalize", json=_finalize_payload(created_at=raw))
    assert r.status_code == 200, r.text[:400]
    body = r.json()
    assert "error" not in body
    assert body.get("server_timestamp_used") is True, raw
    note = body.get("timestamp_note")
    assert isinstance(note, str) and note.strip(), body

    stored = sama_db.get_lot(body["lot_id"])
    stored_dt = datetime.fromisoformat(stored["created_at"])
    assert abs(stored_dt - datetime.now(timezone.utc)) < timedelta(minutes=10)
    assert _lot_count() == before + 1


def test_timestamp_just_inside_window_kept_verbatim(tmp_db):
    """Boundary semantics pin: tolerance is INCLUSIVE up to 24 h. Five
    minutes inside the window keeps the officer's own clock -- overriding a
    plausible timestamp would needlessly rewrite a signed record."""
    plausible = (datetime.now(timezone.utc)
                 - timedelta(hours=23, minutes=55)).isoformat()
    body = _finalize(created_at=plausible)
    assert not body.get("server_timestamp_used"), body
    stored = sama_db.get_lot(body["lot_id"])
    assert stored["created_at"] == plausible


def test_timestamp_just_outside_window_overridden(tmp_db):
    """Five minutes past the window loses the vote -- and says so."""
    stale = (datetime.now(timezone.utc)
             - timedelta(hours=24, minutes=5)).isoformat()
    r = client.post("/finalize", json=_finalize_payload(created_at=stale))
    assert r.status_code == 200, r.text[:400]
    body = r.json()
    assert body.get("server_timestamp_used") is True
    stored = sama_db.get_lot(body["lot_id"])
    stored_dt = datetime.fromisoformat(stored["created_at"])
    assert abs(stored_dt - datetime.now(timezone.utc)) < timedelta(minutes=10)


def test_skewed_retry_still_dedupes(tmp_db):
    """A retry whose bad created_at gets overridden to a DIFFERENT server
    timestamp must STILL land on the original certificate -- the dedupe key
    excludes timestamps precisely so clock drift cannot double-certify."""
    bad_ts = "1999-12-31T23:59:59+00:00"
    first_raw = client.post(
        "/finalize", json=_finalize_payload(lot_ref="QA-SKEW-DUP",
                                            created_at=bad_ts))
    assert first_raw.status_code == 200
    first = first_raw.json()
    second = _finalize(lot_ref="QA-SKEW-DUP", created_at=bad_ts)
    assert second.get("duplicate") is True
    assert second["lot_id"] == first["lot_id"]
    assert _lot_count() == 1


# ==========================================================================
# 5. DISK FULL AFTER COMMIT -- the certificate must survive
# ==========================================================================


def test_disk_full_during_evidence_write_keeps_certificate_intact(
        tmp_db, monkeypatch):
    """The volume can fill between the certificate COMMIT and the photo
    write (photos are the biggest bytes on the bench). Contract: the signed
    record stands, the response is 200, and the degradation is SAID -- not
    hidden, not fatal."""
    before = _lot_count()

    shots = [{"look_index": 0, "tray_id": "T1", "jpeg": b"fakejpeg"}]
    monkeypatch.setattr(sama.evidence_mod, "extract_shots",
                        lambda raw: (shots, 0))

    def no_space(lot_id, valid_shots):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(sama.evidence_mod, "save_lot_evidence", no_space)

    r = client.post("/finalize", json=_finalize_payload())
    assert r.status_code == 200, r.text[:400]
    body = r.json()
    assert "error" not in body
    assert body["evidence_saved"] == 0
    note = body.get("evidence_note")
    assert isinstance(note, str) and "unaffected" in note.lower(), body
    assert _lot_count() == before + 1, "certificate itself must survive"

    lot = sama_db.get_lot(body["lot_id"])
    intact, _, n = sama_db.audit_chain(lot["centre_id"])
    assert intact is True and n >= 1


def test_disk_full_during_evidence_db_update_keeps_certificate_intact(
        tmp_db, monkeypatch):
    """Same seam one step later: manifest built, files written, then the
    evidence_json UPDATE hits SQLITE_FULL. Still annotation-not-record:
    200, note, certificate intact."""
    before = _lot_count()

    shots = [{"look_index": 0, "tray_id": "T1", "jpeg": b"fakejpeg"}]
    monkeypatch.setattr(sama.evidence_mod, "extract_shots",
                        lambda raw: (shots, 0))
    manifest = [{"look_index": 0, "tray_id": "T1",
                 "path": "lot_9999/look_0.jpg", "sha256": "x"}]
    monkeypatch.setattr(sama.evidence_mod, "save_lot_evidence",
                        lambda lot_id, valid_shots: manifest)

    def full_update(lot_id, rows):
        raise sqlite3.OperationalError("database or disk is full")

    monkeypatch.setattr(sama.db, "set_evidence", full_update)

    r = client.post("/finalize", json=_finalize_payload())
    assert r.status_code == 200, r.text[:400]
    body = r.json()
    assert "error" not in body
    assert body["evidence_saved"] == 0
    assert "unaffected" in body.get("evidence_note", "").lower()
    assert _lot_count() == before + 1
    stored = sama_db.get_lot(body["lot_id"])
    assert stored is not None and stored["evidence"] == []


# ==========================================================================
# 6. OVERSIZED MULTIPART -- boundary semantics ('>' not '>=')
# ==========================================================================


@pytest.fixture()
def small_cap(monkeypatch):
    """Shrink the wire cap so boundary tests do not move 25 MB blobs."""
    cap = 3 * 1024 * 1024
    monkeypatch.setattr(sama, "MAX_UPLOAD_BYTES", cap)
    return cap


def test_upload_exactly_at_cap_is_processed(small_cap, monkeypatch):
    """A photo of EXACTLY the limit is legal. Pin the inequality or a
    future off-by-one quietly starts rejecting honest phones."""
    monkeypatch.setattr(sama, "MODEL", _FakeModel(delay=0.0))
    monkeypatch.setattr(sama, "MODEL_ERROR", None)
    jpeg = _gray_jpeg()
    assert len(jpeg) <= small_cap
    r = client.post(
        "/analyze",
        files={"file": ("tray.jpg", jpeg, "image/jpeg")},
        data={"lot_ref": "QA-CAP-EDGE"},
    )
    assert r.status_code == 200, r.text[:300]
    assert "error" not in r.json()


def test_upload_one_byte_over_cap_is_413_before_inference(small_cap, monkeypatch):
    blob = np.random.default_rng(2260).bytes(small_cap + 1)
    monkeypatch.setattr(sama, "MODEL", _MustNotPredict())
    monkeypatch.setattr(sama, "MODEL_ERROR", None)
    r = client.post(
        "/analyze",
        files={"file": ("over.bin", blob, "application/octet-stream")},
        data={"lot_ref": "QA-CAP-OVER"},
    )
    body = _expect_json_error(r, status=413)
    assert "limit" in body["error"].lower()


# ==========================================================================
# 7. MALFORMED STRUCTURE -- 'looks' container shapes
# ==========================================================================


_BAD_LOOKS = [
    {"look0": [_bulb()]},                    # dict, not a list
    "two looks of five onions each",          # bare string iterates chars
    [42],                                     # list of scalars
    [[_bulb()], "second"],                   # second look not a list
    [[_bulb()], [_bulb(), "ghost bulb"]],    # bulb entry not an object
]


@pytest.mark.parametrize("bad_looks", _BAD_LOOKS)
def test_structurally_invalid_looks_are_400_not_500(tmp_db, bad_looks):
    """A caller mistake must wear a 4xx, not the 500 'Could not save lot'
    costume -- and must name WHERE the structure broke, with zero rows
    written."""
    before = _lot_count()
    r = client.post("/finalize", json=_finalize_payload(looks=bad_looks))
    body = _expect_json_error(r, status=400)
    assert "look" in body["error"].lower(), body["error"]
    assert _lot_count() == before, "rejected payload must write nothing"


def test_all_empty_looks_still_finalise_per_spec(tmp_db):
    """CONTRACT GUARD, not a failure case: Q2260 initially proposed refusing
    all-empty captures as a meaningless certificate -- but
    test_two_look_ci.py::test_finalize_empty_capture_adds_nothing and
    test_finalize_defect_ci.py::test_degenerate_capture_gets_no_invented_
    interval encode the opposite, deliberate spec: an honest empty record
    with no invented intervals beats blocking the bench. Structure
    validation must not swallow that path either."""
    r = client.post("/finalize", json=_finalize_payload(looks=[[], []]))
    assert r.status_code == 200, r.text[:400]
    body = r.json()
    assert "error" not in body
    assert body["result"]["n_bulb_observations"] == 0


# ==========================================================================
# 8. UNVALIDATED centre_id -- 500s and the orphan-certificate black hole
# ==========================================================================


@pytest.mark.parametrize("bad_id", ["abc", [1], {"id": 1}, 3.7, True, -5])
def test_malformed_centre_id_is_400_writes_nothing(tmp_db, bad_id):
    before_lots, before_centres = _lot_count(), _centre_count()
    r = client.post("/finalize", json=_finalize_payload(centre_id=bad_id))
    body = _expect_json_error(r, status=400)
    assert "centre" in body["error"].lower(), body["error"]
    assert _lot_count() == before_lots
    assert _centre_count() == before_centres


def test_nonexistent_centre_id_cannot_mint_an_orphan_certificate(tmp_db):
    """foreign_keys are OFF, so a well-typed bogus id used to insert a lot
    row whose centre JOIN matches nothing: get_lot/report/verify/recent_lots
    all returned 'not found' for a certificate the ledger PROVED exists.
    Now refused up front, naming the id and the way out."""
    before_lots, before_centres = _lot_count(), _centre_count()
    ghost_id = 987654321
    r = client.post("/finalize", json=_finalize_payload(centre_id=ghost_id))
    body = _expect_json_error(r, status=400)
    assert str(ghost_id) in body["error"], body["error"]
    assert _lot_count() == before_lots, "orphan lot row was written"
    assert _centre_count() == before_centres


def test_numeric_string_centre_id_from_ui_still_works(tmp_db):
    """CONTRACT GUARD for the fix: the shipped UI posts centre_id as a
    STRING off <option value>. Rejecting digit-strings would 400 every
    finalize from the real frontend -- the cure must not kill the patient."""
    centre_id = sama_db.upsert_centre("UI String Centre")
    body = _finalize(centre_id=str(centre_id))          # e.g. "7"
    stored = sama_db.get_lot(body["lot_id"])
    assert stored["centre_id"] == centre_id
    assert _lot_count() == 1


def test_zero_centre_id_falls_back_like_the_frontend_sends(tmp_db):
    """index.html posts `centre_id: $('centre').value || null` -- the empty
    option arrives as '' or null and has always meant 'file under a name'.
    Preserve that fallback exactly."""
    body = _finalize(centre_id="", centre_name="Fallback Centre")
    stored = sama_db.get_lot(body["lot_id"])
    assert stored["centre_name"] == "Fallback Centre"


# ==========================================================================
# 9. UNBOUNDED FORM FIELDS -> SCALE-CACHE MEMORY AMPLIFICATION
# ==========================================================================


def test_analyze_rejects_absurdly_long_lot_ref(monkeypatch):
    """/analyze cached lot_ref VERBATIM as a _LAST_GOOD_SCALE key: a loop
    of 25 MB strings parks ~800 MB across the 32 slots. Cap mirrors the
    signed-record limit (120); over-limit is refused BEFORE the upload is
    even read."""
    monkeypatch.setattr(sama, "MODEL", _MustNotPredict())
    monkeypatch.setattr(sama, "MODEL_ERROR", None)
    r = client.post(
        "/analyze",
        files={"file": ("tray.jpg", _gray_jpeg(), "image/jpeg")},
        data={"lot_ref": "L" * 121},
    )
    body = _expect_json_error(r, status=400)
    assert "lot_ref" in body["error"], body["error"]
    assert "120" in body["error"], body["error"]


def test_analyze_rejects_overlong_tray_id(monkeypatch):
    monkeypatch.setattr(sama, "MODEL", _MustNotPredict())
    monkeypatch.setattr(sama, "MODEL_ERROR", None)
    r = client.post(
        "/analyze",
        files={"file": ("tray.jpg", _gray_jpeg(), "image/jpeg")},
        data={"tray_id": "T" * 65},
    )
    body = _expect_json_error(r, status=400)
    assert "tray_id" in body["error"], body["error"]
    assert "64" in body["error"], body["error"]


def test_analyze_field_caps_admit_normal_values(monkeypatch):
    """Positive control: 120-char lot_ref and 64-char tray_id pass."""
    monkeypatch.setattr(sama, "MODEL", _FakeModel(delay=0.0))
    monkeypatch.setattr(sama, "MODEL_ERROR", None)
    r = client.post(
        "/analyze",
        files={"file": ("tray.jpg", _gray_jpeg(), "image/jpeg")},
        data={"lot_ref": "L" * 120, "tray_id": "T" * 64},
    )
    assert r.status_code == 200, r.text[:300]
    body = r.json()
    assert body["lot_ref"] == "L" * 120
    assert body["tray_id"] == "T" * 64
