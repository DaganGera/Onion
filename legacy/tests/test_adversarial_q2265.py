"""QA task LOOP-Q2265 -- adversarial pass 2265, NEW failure modes.

Prior coverage this pass builds on (and deliberately does not repeat):
    test_failure_injection.py   garbage uploads / malformed bodies (Q-001)
    test_adversarial_q2216.py   chain forks, XSS, surrogates, disk-full at
                                COMMIT, upload cap, pixel bombs
    test_adversarial_q2260.py   racing identical finalizes, concurrent
                                analyze w/ STUBBED scales, clock-skew types
                                and the 24 h window, disk-full AFTER commit,
                                cap boundary ('>' not '>='), field caps

The six seams attacked HERE, each named for the gap it closes:

    1. NON-FINITE COORDINATES   json.loads ACCEPTS NaN / Infinity literals
                                (and 1e999 overflows to inf). lat/lon/
                                scale_confidence were bound straight into
                                REAL columns; Starlette serialises with
                                allow_nan=False, so ONE poisoned row made
                                GET /api/lots raise ValueError while
                                RENDERING -- outside every endpoint's
                                try/except -- and the dashboard listing
                                died for ALL lots until manual surgery.
    2. NFC/NFD DOUBLE CERT      visually identical Devanagari lot refs
                                (precomposed U+0958 vs U+0915+U+093C) were
                                byte-different, so a retried finalize typed
                                on another keyboard MISSED dedupe and
                                minted a SECOND signed certificate for the
                                same physical lot.
    3. BIDI CONTROL SPOOFING    U+202E in farmer_name survived into the
                                signed record and reorders neighbouring
                                text on the PUBLIC verify/report pages.
    4. UNBOUNDED REQUEST BODY   /analyze capped only its FILE field;
                                /finalize had NO cap at all -- a 40 MB junk
                                JSON body parsed fine AND MINTED A
                                CERTIFICATE, and spare multipart fields
                                could spool to temp disk without bound.
    5. DISK FULL, EARLIER       Q2216 killed COMMIT, Q2260 killed evidence
        PHASES + DISPUTE       writes. Not covered: ENOSPC during the
                                centres INSERT (before insert_lot), during
                                the BULB inserts (mid-transaction), and on
                                POST /dispute -- which answered a generic
                                500 with no free-space guidance.
    6. CONCURRENT ANALYZE,      Q2216/Q2260 stubbed grading.detect_scale,
        REAL DETECTOR PATH      so cv2.aruco never ran under contention and
                                blocked/unusable frames never mixed with
                                successes mid-storm.
    7. CLOCK SKEW, REMAINING    malformed UTC OFFSETS ("+99:00", impossible
        SHAPES                  dates) and the 'Z' suffix within-window pin.

Contract unchanged from Q-001: failures answer JSON {"error": <non-empty>,
sane status, no traceback, path forward; caller mistakes are 4xx. grading.py
stays untouched; db.py stays untouched.

Run:
    C:/Users/ADMIN/AppData/Local/Programs/Python/Python311/python.exe -m pytest tests/test_adversarial_q2265.py -q
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
    else:
        assert 400 <= response.status_code < 600, (
            f"expected an error status, got {response.status_code}: "
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


def _strict_json(response):
    """Parse demanding RFC 8259 compliance: NaN/Infinity tokens explode."""

    def _boom(token):
        raise AssertionError(
            f"response contains non-strict JSON token {token!r}: "
            f"{response.text[:200]!r}"
        )

    return json.loads(response.text, parse_constant=_boom)


@pytest.fixture()
def tmp_db(tmp_path, monkeypatch):
    """Isolated SQLite file so tests never touch data/sama.db."""
    monkeypatch.setattr(sama_db, "DB_PATH", tmp_path / "q2265_test.db")
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
        "lot_ref": "QA-2265",
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


def _bulb_count() -> int:
    conn = sama_db.connect()
    try:
        return conn.execute("SELECT COUNT(*) AS n FROM bulbs").fetchone()["n"]
    finally:
        conn.close()


def _centre_count() -> int:
    conn = sama_db.connect()
    try:
        return conn.execute("SELECT COUNT(*) AS n FROM centres").fetchone()["n"]
    finally:
        conn.close()


def _gray_jpeg(width=64, height=48, level=127) -> bytes:
    """Decodable, mid-gray JPEG: passes quality gates, finds no markers."""
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


# Raw-JSON posting: Python's json.loads accepts the non-strict literals
# NaN / Infinity / 1e999 that httpx's json= encoder refuses to SEND. These
# helpers smuggle them onto the wire the way curl does.
_RAW_LITERALS = (('"@nan@"', "NaN"),
                 ('"@inf@"', "Infinity"),
                 ('"@neginf@"', "-Infinity"),
                 ('"@huge@"', "1e999"))


def _post_raw_json(payload: dict):
    text = json.dumps(payload)
    for token, literal in _RAW_LITERALS:
        text = text.replace(token, literal)
    return client.post("/finalize", content=text.encode("utf-8"),
                       headers={"Content-Type": "application/json"})


# ==========================================================================
# 1. NON-FINITE lat / lon / scale_confidence MUST NOT POISON THE LEDGER
# ==========================================================================


@pytest.mark.parametrize("field,token,literal", [
    ("lat", "@huge@", "1e999"),
    ("lat", "@inf@", "Infinity"),
    ("lon", "@nan@", "NaN"),
    ("lon", "@inf@", "Infinity"),
    ("scale_confidence", "@nan@", "NaN"),
    ("scale_confidence", "@inf@", "Infinity"),
])
def test_nonfinite_number_is_rejected_and_poisons_nothing(tmp_db, field,
                                                          token, literal):
    """One inf/NaN row used to kill GET /api/lots for EVERY lot: rendering
    raised ValueError outside any try/except (allow_nan=False). Now the
    finalize itself refuses, naming the field, writing nothing."""
    before = _lot_count()
    payload = _finalize_payload(lot_ref=f"INF-{field}")
    payload[field] = token
    r = _post_raw_json(payload)
    body = _expect_json_error(r, status=400)
    assert field in body["error"], (
        f"rejection must name the offending field: {body['error']!r}"
    )
    assert _lot_count() == before, "rejected payload must write nothing"

    # The listing survives, and strictly: no Infinity/NaN tokens anywhere.
    listing = client.get("/api/lots")
    assert listing.status_code == 200, listing.text[:300]
    _strict_json(listing)


@pytest.mark.parametrize("bad", [True, [12.9], {"lat": 12.9}])
def test_wrongly_typed_coordinates_are_400_not_stored(tmp_db, bad):
    before = _lot_count()
    r = client.post("/finalize", json=_finalize_payload(lat=bad))
    body = _expect_json_error(r, status=400)
    assert "lat" in body["error"]
    assert _lot_count() == before


def test_numeric_string_coordinates_are_accepted(tmp_db):
    """Older UI builds posted coordinates as strings; '' means absent.
    Keep both working while the garbage door stays shut."""
    body = _finalize(lat="12.9719", lon="77.5937",
                     scale_confidence="0.93")
    stored = sama_db.get_lot(body["lot_id"])
    assert stored["lat"] == pytest.approx(12.9719)
    assert stored["lon"] == pytest.approx(77.5937)
    assert stored["scale_conf"] == pytest.approx(0.93)


def test_listing_strict_parses_after_mixed_traffic(tmp_db):
    """End-to-end: normal certificates plus a refused poison attempt leave
    /api/lots parseable by a STRICT parser (what every browser runs)."""
    _finalize(lot_ref="GOOD-A", lat=12.97, lon=77.59)
    payload = _finalize_payload(lot_ref="BAD-B")
    payload["lon"] = "@nan@"
    _expect_json_error(_post_raw_json(payload), status=400)
    _finalize(lot_ref="GOOD-C")

    listing = client.get("/api/lots")
    assert listing.status_code == 200
    data = _strict_json(listing)
    refs = {row["lot_ref"] for row in data["lots"]}
    assert {"GOOD-A", "GOOD-C"} <= refs
    assert "BAD-B" not in refs


# ==========================================================================
# 2. NFC/NFD -- CANONICAL-EQUIVALENT LOT REFS MUST DEDUPE
# ==========================================================================

# Precomposed DEVANAGARI LETTER KA WITH NUKTA vs the spelling every Android
# Gboard actually emits (KA + combining NUKTA). Canonical equivalents;
# byte-different strings.
_REF_A = "\u0958\u0930\u0940\u0926-\U0001F945-\u0030\u0030\u0031"
_REF_B = "\u0915\u093c\u0930\u0940\u0926-\U0001F945-\u0030\u0030\u0031"


def test_canonically_equivalent_lot_refs_dedupe(tmp_db):
    """Same physical lot, two keyboards: the retry must land on the FIRST
    certificate, not mint a second signed record beside it."""
    import unicodedata

    first = _finalize(lot_ref=_REF_A)
    second = _finalize(lot_ref=_REF_B)
    assert second.get("duplicate") is True, (
        "canonical-equivalent lot refs must dedupe after NFC normalisation"
    )
    assert second["lot_id"] == first["lot_id"]
    assert second["row_hash"] == first["row_hash"]
    assert _lot_count() == 1
    # Both spellings collapse to one stored form.
    stored = sama_db.get_lot(first["lot_id"])
    assert stored["lot_ref"] == unicodedata.normalize("NFC", _REF_A)


def test_farmer_name_stored_nfc_normalized(tmp_db):
    import unicodedata

    decomposed = unicodedata.normalize("NFD", "caf\u00e9 S\u00edntesis")
    assert decomposed != "caf\u00e9 S\u00edntesis"  # fixture really differs
    body = _finalize(farmer_name=decomposed)
    stored = sama_db.get_lot(body["lot_id"])
    assert stored["farmer_name"] == "caf\u00e9 S\u00edntesis"


def test_plain_ascii_lot_ref_dedupe_unaffected(tmp_db):
    """Positive control: the fix must not disturb the ASCII path."""
    first = _finalize(lot_ref="PLAIN-ASCII")
    second = _finalize(lot_ref="PLAIN-ASCII")
    assert second.get("duplicate") is True
    assert second["lot_id"] == first["lot_id"]
    assert _lot_count() == 1


def test_look_order_swapped_is_the_same_certificate(tmp_db):
    """Duplicate-lot semantics pin: the SAME two looks submitted in the
    other order pool to identical certified numbers (grade mix, Wilson
    bounds, worst-look defect rate), so a retried session that replayed its
    photos shuffled must dedupe rather than double-certify."""
    b1, b2, b3 = _bulb(), _bulb("rotten", grade="B", dia=65.0), _bulb()
    first = _finalize(lot_ref="ORDER-SWAP", looks=[[b1, b2], [b3]])
    second = _finalize(lot_ref="ORDER-SWAP", looks=[[b3], [b1, b2]])
    assert second.get("duplicate") is True
    assert second["lot_id"] == first["lot_id"]
    assert _lot_count() == 1
    assert _bulb_count() == 3, "dedupe must not write fresh bulb rows"


# ==========================================================================
# 3. BIDI CONTROLS CANNOT RIDE INTO A SIGNED NAME
# ==========================================================================


@pytest.mark.parametrize("field", ["farmer_name", "officer_name"])
@pytest.mark.parametrize("control", ["\u202e", "\u202d", "\u2066", "\u2069"])
def test_bidi_controls_stripped_from_names(tmp_db, field, control):
    """RLO/LRI-style controls carry no name content -- only reordering.
    'Rames<U+202E>Kumar' displayed as something else on the public pages."""
    sneaky = f"Rames{control}Kumar"
    body = _finalize(**{field: sneaky})
    stored = sama_db.get_lot(body["lot_id"])
    got = stored[field]
    assert all(ord(ch) < 0x202A or ord(ch) > 0x202E for ch in got), repr(got)
    assert all(ord(ch) < 0x2066 or ord(ch) > 0x2069 for ch in got), repr(got)
    assert "RamesKumar".replace(" ", "") in got.replace(" ", "")


def test_name_without_bidi_is_untouched(tmp_db):
    """Positive control: ordinary names (including RTL-script ones, which
    render correctly WITHOUT embedding controls) store byte-intact."""
    body = _finalize(farmer_name="\u0930\u093e\u092e\u0947\u0936 \u0915\u0941\u092e\u093e\u0930")
    stored = sama_db.get_lot(body["lot_id"])
    assert stored["farmer_name"] == "\u0930\u093e\u092e\u0947\u0936 \u0915\u0941\u092e\u093e\u0930"


# ==========================================================================
# 4. WHOLE-REQUEST BODY CAPS (/finalize had none; /analyze only its file)
# ==========================================================================


def test_finalize_giant_junk_body_is_413_writes_nothing(tmp_db):
    """40 MB of junk JSON used to parse cleanly AND MINT A CERTIFICATE.
    Now the door shuts before parsing: readable 413, zero rows."""
    before = _lot_count()
    pad = b"P" * (34 * 1024 * 1024)
    body_bytes = b'{"looks": [[]], "pad": "' + pad + b'"}'
    r = client.post("/finalize", content=body_bytes,
                    headers={"Content-Type": "application/json"})
    del body_bytes, pad
    resp_body = _expect_json_error(r, status=413)
    lowered = resp_body["error"].lower()
    assert "limit" in lowered or "mb" in lowered, resp_body["error"]
    assert "photo" in lowered or "send" in lowered or "retry" in lowered, (
        "path forward required"
    )
    assert _lot_count() == before


def test_finalize_large_but_under_cap_body_still_parsed(tmp_db):
    """The cap must not swallow legitimate big payloads: ~20 MB of real
    JSON shape reaches the endpoint and gets judged on its merits."""
    payload = _finalize_payload(lot_ref="BIG-BUT-LEGAL")
    payload["pad"] = "P" * (20 * 1024 * 1024)
    r = client.post("/finalize", json=payload)
    assert r.status_code != 413, "under-cap payload must not be capped"
    assert r.status_code == 200, r.text[:300]
    assert "error" not in r.json()


def test_finalize_normal_size_unaffected(tmp_db):
    body = _finalize(lot_ref="NORMAL-SIZE")
    assert body["lot_id"] > 0


def test_analyze_giant_spare_fields_capped_before_model(monkeypatch, tmp_path):
    """The FILE field was bounded (Q2216) but spare multipart fields could
    spool to temp disk unbounded. A body past the analyze ceiling dies at
    the door, before the model, with the same 413 contract."""
    monkeypatch.setattr(sama, "MODEL", _MustNotPredict())
    monkeypatch.setattr(sama, "MODEL_ERROR", None)
    # 16 MB of raw junk hex-encodes to a 32 MB form field -- comfortably
    # past the analyze ceiling, without moving huge blobs through CI RAM.
    big_junk = b"\x00" * (16 * 1024 * 1024)
    r = client.post(
        "/analyze",
        files={"file": ("tray.jpg", _gray_jpeg(), "image/jpeg")},
        data={"lot_ref": "L" * 120, "junk": big_junk.hex()},
    )
    del big_junk
    resp_body = _expect_json_error(r, status=413)
    assert "limit" in resp_body["error"].lower()


def test_analyze_normal_photo_still_processed(monkeypatch):
    """Positive control: honest phones sail under the ceiling."""
    monkeypatch.setattr(sama, "MODEL", _FakeModel(delay=0.0))
    monkeypatch.setattr(sama, "MODEL_ERROR", None)
    r = client.post(
        "/analyze",
        files={"file": ("tray.jpg", _gray_jpeg(), "image/jpeg")},
        data={"lot_ref": "QA-NORMAL"},
    )
    assert r.status_code == 200, r.text[:300]
    assert "error" not in r.json()


# ==========================================================================
# 5. DISK FULL -- EARLIER PHASES AND THE DISPUTED-BULB WRITE
# ==========================================================================


class _FailOnConnection:
    """Delegating sqlite connection that raises SQLITE_FULL on chosen SQL.

    Generalises Q2216's COMMIT-killing proxy: the matcher decides WHICH
    statements die, so a test can drop the disk out from under one phase
    (centres INSERT / bulb INSERTs) and leave everything else honest."""

    def __init__(self, conn: sqlite3.Connection, matcher):
        object.__setattr__(self, "_conn", conn)
        object.__setattr__(self, "_matcher", matcher)

    def __getattr__(self, name):
        return getattr(self._conn, name)

    def __setattr__(self, name, value):
        setattr(self._conn, name, value)

    def execute(self, sql, *args, **kwargs):
        if self._matcher(sql):
            raise sqlite3.OperationalError("database or disk is full")
        return self._conn.execute(sql, *args, **kwargs)


def _with_full_disk_during(monkeypatch, fragment: str):
    """Patch db.connect to a proxy failing on SQL containing `fragment`.
    Returns the real connect for the caller to restore (targeted undo --
    a blanket monkeypatch.undo() would also drop tmp_db's DB_PATH patch)."""
    real_connect = sama_db.connect

    def full_connect():
        return _FailOnConnection(real_connect(),
                                 lambda sql: fragment in sql.upper())

    monkeypatch.setattr(sama_db, "connect", full_connect)
    return real_connect


def test_disk_full_during_centre_insert_is_actionable(tmp_db, monkeypatch):
    """ENOSPC can strike at the very FIRST write (centre upsert), before
    insert_lot ever runs. Contract: 503, storage named, and the 'nothing
    was written' promise holds for centres too."""
    before_lots, before_centres = _lot_count(), _centre_count()
    real_connect = _with_full_disk_during(monkeypatch, "INSERT INTO CENTRES")

    r = client.post("/finalize", json=_finalize_payload())
    monkeypatch.setattr(sama_db, "connect", real_connect)

    resp_body = _expect_json_error(r, status=503)
    lowered = resp_body["error"].lower()
    assert "disk" in lowered or "space" in lowered or "storage" in lowered
    assert _lot_count() == before_lots
    assert _centre_count() == before_centres, "centre row leaked"


def test_disk_full_mid_bulb_inserts_leaves_zero_partial_rows(
        tmp_db, monkeypatch):
    """The certificate row INSERT succeeds, then the volume fills during
    bulb writes. The explicit ROLLBACK must leave NO lot row and NO bulbs
    -- and the server must take a healthy finalize immediately after."""
    centre_id = sama_db.upsert_centre("Mid Bulb Failure Centre")
    before_lots, before_bulbs = _lot_count(), _bulb_count()
    real_connect = _with_full_disk_during(monkeypatch, "INSERT INTO BULBS")

    r = client.post("/finalize",
                    json=_finalize_payload(centre_id=str(centre_id)))
    monkeypatch.setattr(sama_db, "connect", real_connect)

    _expect_json_error(r, status=503)
    assert _lot_count() == before_lots, "half a certificate survived"
    assert _bulb_count() == before_bulbs, "partial bulb rows survived"
    intact, _, _ = sama_db.audit_chain(centre_id)
    assert intact is True

    recovered = _finalize(lot_ref="POST-RECOVERY", centre_id=str(centre_id))
    assert recovered.get("duplicate") is False
    assert _lot_count() == before_lots + 1
    intact, _, n = sama_db.audit_chain(centre_id)
    assert intact is True and n >= 1


def test_dispute_during_disk_full_is_actionable(tmp_db, monkeypatch):
    """Contesting a bulb on a full box answered a bare
    500 'Could not log dispute: OperationalError'. Contract: 503 naming
    storage, saying the dispute was NOT recorded, with the retry path."""
    body = _finalize(lot_ref="DISPUTE-DISKFULL")
    bulb_ids = body["bulb_ids"]
    target = bulb_ids[0][0]

    def full_mark(bulb_id):
        raise sqlite3.OperationalError("database or disk is full")

    # Targeted restore (NOT monkeypatch.undo(), which would also drop
    # tmp_db's DB_PATH patch and point the assertions below at the real
    # demo database -- the same trap Q2216 documented).
    real_mark = sama.db.mark_disputed
    monkeypatch.setattr(sama.db, "mark_disputed", full_mark)
    r = client.post(f"/dispute/{target}")
    monkeypatch.setattr(sama.db, "mark_disputed", real_mark)

    resp_body = _expect_json_error(r, status=503)
    lowered = resp_body["error"].lower()
    assert "disk" in lowered or "space" in lowered
    assert "not recorded" in lowered
    # Nothing half-flipped.
    conn = sama_db.connect()
    try:
        row = conn.execute("SELECT disputed FROM bulbs WHERE id = ?",
                           (target,)).fetchone()
    finally:
        conn.close()
    assert row["disputed"] == 0


def test_dispute_other_db_failure_still_readable(tmp_db, monkeypatch):
    body = _finalize(lot_ref="DISPUTE-OTHER")
    target = body["bulb_ids"][0][0]

    def broken_mark(bulb_id):
        raise sqlite3.OperationalError("unable to open database file")

    real_mark = sama.db.mark_disputed
    monkeypatch.setattr(sama.db, "mark_disputed", broken_mark)
    r = client.post(f"/dispute/{target}")
    monkeypatch.setattr(sama.db, "mark_disputed", real_mark)

    resp_body = _expect_json_error(r, status=500)
    assert "dispute" in resp_body["error"].lower()


# ==========================================================================
# 6. CONCURRENT ANALYZE THROUGH THE REAL DETECTOR PATH
# ==========================================================================


def test_concurrent_analyze_real_scale_path_never_cross_talks(monkeypatch):
    """Q2260's storm stubbed grading.detect_scale, so cv2.aruco and the
    capture-quality gate never ran under contention. Here only the MODEL is
    fake: marker detection, the calibration ladder and quality assessment
    all execute concurrently. Every response must belong to its own
    request, and the shared cache must stay empty (flat gray finds no
    markers worth carrying)."""
    monkeypatch.setattr(sama, "_LAST_GOOD_SCALE", {})
    fake = _FakeModel(delay=0.0)
    monkeypatch.setattr(sama, "MODEL", fake)
    monkeypatch.setattr(sama, "MODEL_ERROR", None)

    jpeg = _gray_jpeg()

    def upload(i: int) -> dict:
        r = client.post(
            "/analyze",
            files={"file": (f"tray{i}.jpg", jpeg, "image/jpeg")},
            data={"lot_ref": f"QA-REAL-{i}", "look_index": str(i)},
        )
        assert r.status_code == 200, r.text[:300]
        return r.json()

    with ThreadPoolExecutor(max_workers=12) as pool:
        bodies = list(pool.map(upload, range(12)))

    assert fake.calls == 12
    for i, body in enumerate(bodies):
        assert body["lot_ref"] == f"QA-REAL-{i}", "cross-talk between requests"
        assert body["look_index"] == i
        assert body["scale"]["calibrated"] is False  # flat gray: no markers
    assert len(sama._LAST_GOOD_SCALE) <= sama._MAX_REMEMBERED_LOTS


def test_concurrent_mixed_good_and_garbage_uploads_stay_sorted(monkeypatch):
    """Half the bench uploads decodable trays while half fat-fingers text
    files. Successes and 400s must sort EXACTLY by input -- a failure must
    never bleed into a neighbour's success -- while health polls continue."""
    monkeypatch.setattr(sama, "MODEL", _FakeModel(delay=0.0))
    monkeypatch.setattr(sama, "MODEL_ERROR", None)

    good = _gray_jpeg()
    bad = b"this is definitely not an image"
    lock = threading.Lock()
    outcomes: dict[int, tuple[int, str]] = {}

    def upload(i: int) -> None:
        is_good = i % 2 == 0
        payload_bytes = good if is_good else bad
        r = client.post(
            "/analyze",
            files={"file": (f"t{i}.jpg", payload_bytes, "image/jpeg")},
            data={"lot_ref": f"QA-MIX-{i}"},
        )
        with lock:
            outcomes[i] = (r.status_code,
                           (r.json() or {}).get("error", ""))

    def poll_health(_n: int) -> None:
        r = client.get("/api/health")
        assert r.status_code == 200

    with ThreadPoolExecutor(max_workers=16) as pool:
        futures = [pool.submit(upload, i) for i in range(12)]
        health = [pool.submit(poll_health, n) for n in range(6)]
        for f in futures + health:
            f.result(timeout=60)

    assert len(outcomes) == 12
    for i, (status, err) in sorted(outcomes.items()):
        if i % 2 == 0:
            assert status == 200, (i, status, err)
        else:
            assert status == 400, (i, status, err)
            assert "image" in err.lower()


# ==========================================================================
# 7. CLOCK SKEW -- REMAINING SHAPES
# ==========================================================================


@pytest.mark.parametrize("bad_offset", [
    "2026-08-25T10:00:00+99:00",          # impossible hour offset
    "2026-08-25T10:00:00+05:7",           # truncated offset component
    "2026-02-30T10:00:00",                # impossible calendar date
    "2026-08-25T10:00:00+00:00 extra",    # trailing junk after a real ts
])
def test_malformed_timezone_shapes_get_server_time_with_note(tmp_db,
                                                             bad_offset):
    """Q2260 covered unusable TYPES; these are well-typed strings whose
    OFFSETS/dates cannot parse. Each must fall back to server time WITH an
    honest note -- never a crash, never a silent rewrite."""
    before = _lot_count()
    r = client.post("/finalize",
                    json=_finalize_payload(created_at=bad_offset))
    assert r.status_code == 200, r.text[:400]
    body = r.json()
    assert "error" not in body
    assert body.get("server_timestamp_used") is True, bad_offset
    note = body.get("timestamp_note")
    assert isinstance(note, str) and note.strip()
    stored = sama_db.get_lot(body["lot_id"])
    stored_dt = datetime.fromisoformat(stored["created_at"])
    if stored_dt.tzinfo is None:
        stored_dt = stored_dt.replace(tzinfo=timezone.utc)
    assert abs(stored_dt - datetime.now(timezone.utc)) < timedelta(minutes=10)
    assert _lot_count() == before + 1


def test_leniently_parsed_offset_is_judged_on_skew_alone(tmp_db):
    """DOCUMENTATION pin, not a failure case: CPython's fromisoformat
    accepts '+05:70' (as +06:10) where browsers see an invalid RFC 3339
    offset. The app deliberately does NOT second-guess the parser: once a
    string parses, its fate is decided ONLY by the +/-24 h skew window --
    here 'today with a weird offset' is plausible and stays verbatim,
    exactly like any other in-window client clock."""
    lenient = ((datetime.now(timezone.utc) - timedelta(hours=1))
               .strftime("%Y-%m-%dT%H:%M:%S") + "+05:70")
    assert "+05:70" in lenient  # fixture really is the lenient shape
    body = _finalize(created_at=lenient)
    assert not body.get("server_timestamp_used"), body
    stored = sama_db.get_lot(body["lot_id"])
    assert stored["created_at"] == lenient


def test_z_suffix_timestamp_inside_window_kept_verbatim(tmp_db):
    """Pin: ISO-8601 'Z' (what JS Date.toISOString emits) parses on
    Python 3.11 and, inside the window, stores VERBATIM -- the frontend's
    own format must keep its clock vote."""
    plausible = (datetime.now(timezone.utc)
                 - timedelta(hours=1)).isoformat().replace("+00:00", "Z")
    body = _finalize(created_at=plausible)
    assert not body.get("server_timestamp_used"), body
    stored = sama_db.get_lot(body["lot_id"])
    assert stored["created_at"] == plausible
