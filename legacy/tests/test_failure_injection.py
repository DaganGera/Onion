"""QA task Q-001 -- deliberate garbage in, readable JSON out. Never a crash.

Every case here is something that WILL happen at a mandi bench on demo day:
an officer taps upload before the camera finishes, a phone sends a truncated
photo over bad wifi, someone pokes the API with curl to see what happens.
The contract under test:

    1. The response body parses as JSON, always.
    2. It carries an "error" key whose value is a non-empty string a human
       can act on -- never a blank screen, never a raw stack trace.
    3. The status code is sane (4xx for caller mistakes, 5xx only when the
       server genuinely cannot proceed).

Covered matrix (task Q-001):
    POST /analyze   : empty body, zero-byte file, text bytes, fake PNG magic,
                      truncated JPEG, ~10 MB random bytes, bad form field type
                      and the model-unavailable degradation
    GET /api/replay/999      -> missing replay
    GET /api/replay/abc      -> non-numeric id
    GET /api/verify/nonexistent-lot -> non-numeric id
    GET /api/verify/<huge missing int> -> numeric but absent certificate
    GET /api/arbitrate       -> missing params (none given / half given)
    POST /finalize           -> malformed JSON (broken syntax, no body,
                                wrong top-level type x2, type-confused looks)

app/main.py is exercised exactly as shipped; nothing here patches grading
math. The YOLO model object itself is stubbed so these tests stay hermetic
and fast: every injected payload below is rejected BEFORE inference would
run, so a stub that raises if predict() is ever reached doubles as proof the
rejection happened for the right reason.

Run:
    C:/Users/ADMIN/AppData/Local/Programs/Python/Python311/python.exe -m pytest tests/test_failure_injection.py -q
"""

import sys
from pathlib import Path

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import main as sama  # noqa: E402

# raise_server_exceptions=False: we want to see what a phone on market wifi
# would see, not have pytest re-raise the server-side exception at us.
client = TestClient(sama.app, raise_server_exceptions=False)


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def _expect_json_error(response, status=None):
    """The one contract every failure path must satisfy.

    Returns the parsed body so tests can assert on the message content.
    """
    if status is not None:
        assert response.status_code == status, (
            f"expected HTTP {status}, got {response.status_code}: "
            f"{response.text[:400]!r}"
        )
    else:
        assert 400 <= response.status_code < 600, (
            f"expected a client/server error code, got "
            f"{response.status_code}: {response.text[:400]!r}"
        )
        # 500 is legal only where state is genuinely unrecoverable; the
        # specific expectations per test say which code each case earns.
    assert response.headers["content-type"].startswith("application/json"), (
        f"failure must be JSON, got content-type "
        f"{response.headers.get('content-type')!r}: {response.text[:400]!r}"
    )
    body = response.json()
    assert isinstance(body, dict), f"error body should be an object: {body!r}"
    assert "error" in body, f"missing 'error' key: {body!r}"
    message = body["error"]
    assert isinstance(message, str), f"'error' must be a string: {body!r}"
    assert message.strip(), "'error' must not be empty"
    assert "Traceback" not in response.text, "stack trace leaked to client"
    return body


class _MustNotPredict:
    """Sentinel 'model'. If any rejected upload reaches inference, this
    blows up server-side and the test fails loudly instead of passing by
    accident."""

    def predict(self, *args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("predict() ran on a payload that should have "
                             "been rejected before inference")


@pytest.fixture()
def model_ready(monkeypatch):
    """Force the app into 'weights loaded' mode regardless of the machine.

    All bad-upload rejections happen between the MODEL check and MODEL.predict,
    so the stub never runs -- but its presence lets these tests pass on a
    laptop with no weights at all, which is exactly the replay-mode venue box.
    """
    monkeypatch.setattr(sama, "MODEL", _MustNotPredict())
    monkeypatch.setattr(sama, "MODEL_ERROR", None)


@pytest.fixture()
def empty_cache(tmp_path, monkeypatch):
    """Point the replay cache at an isolated dir so 'available replays'
    messages are deterministic whatever the demo machine has cached."""
    monkeypatch.setattr(sama, "CACHE", tmp_path)
    return tmp_path


def _jpeg_bytes(width=32, height=32) -> bytes:
    import io as _io  # local alias to keep module imports boring
    img = np.zeros((height, width, 3), dtype=np.uint8)
    ok, buf = cv2.imencode(".jpg", img)
    assert ok, "test fixture could not encode a plain JPEG"
    return buf.tobytes()


def _imdecodes(data: bytes) -> bool:
    return cv2.imdecode(np.frombuffer(data, dtype=np.uint8),
                        cv2.IMREAD_COLOR) is not None


# --------------------------------------------------------------------------
# POST /analyze -- empty body
# --------------------------------------------------------------------------


def test_analyze_no_fields_at_all_is_json_422(model_ready):
    # A bare POST with no multipart fields: FastAPI's validation fires, and
    # the custom handler must convert it to the {"error": ...} shape the
    # frontend reads (Starlette's default uses "detail").
    r = client.post("/analyze")
    _expect_json_error(r, status=422)


def test_analyze_zero_byte_file_is_readable_400(model_ready):
    # The tap-too-soon case: the browser sends the field but the photo has
    # no bytes yet. Must be a gentle retry hint, not a crash.
    r = client.post(
        "/analyze",
        files={"file": ("tray.jpg", b"", "image/jpeg")},
        data={"lot_ref": "QA", "look_index": "0"},
    )
    body = _expect_json_error(r, status=400)
    assert "empty" in body["error"].lower()


# --------------------------------------------------------------------------
# POST /analyze -- bytes that are not decodable images
# --------------------------------------------------------------------------


def test_analyze_plain_text_bytes_is_400(model_ready):
    r = client.post(
        "/analyze",
        files={"file": ("notes.txt", b"this is definitely not an image",
                        "text/plain")},
    )
    body = _expect_json_error(r, status=400)
    assert "image" in body["error"].lower()


def test_analyze_fake_png_magic_with_junk_is_400(model_ready):
    # Guards against a regression to signature-sniffing: the PNG magic
    # followed by garbage must not be treated as a decodable image.
    payload = b"\x89PNG\r\n\x1a\n" + b"\x00garbage-not-really-a-png" * 8
    assert not _imdecodes(payload), "fixture accidentally became a valid image"
    r = client.post(
        "/analyze",
        files={"file": ("fake.png", payload, "image/png")},
    )
    _expect_json_error(r, status=400)


def test_analyze_truncated_jpeg_is_400(model_ready):
    # Bad-wifi case: the phone's upload dies mid-transfer. Keep only the
    # SOI + header of a real JPEG -- well below the smallest decodable
    # JPEG (~a few hundred bytes), so OpenCV must refuse it.
    full = _jpeg_bytes()
    truncated = full[:48]
    assert len(truncated) < len(full)
    assert not _imdecodes(truncated), (
        "48-byte truncation decoded anyway; tighten the fixture before "
        "letting this test claim coverage"
    )
    r = client.post(
        "/analyze",
        files={"file": ("cut.jpg", truncated, "image/jpeg")},
    )
    body = _expect_json_error(r, status=400)
    assert "image" in body["error"].lower()


def test_analyze_huge_random_blob_is_400(model_ready):
    # ~10 MiB of noise: oversized AND undecodable. Seeded so failures
    # reproduce byte-for-byte.
    blob = np.random.default_rng(12345).bytes(10 * 1024 * 1024)
    assert not _imdecodes(blob), "random fixture decoded; pick new seed"
    r = client.post(
        "/analyze",
        files={"file": ("noise.bin", blob, "application/octet-stream")},
    )
    _expect_json_error(r, status=400)


def test_analyze_bad_form_field_type_is_json_422(model_ready):
    # look_index must be an int; "soon" is not. Field coercion failures go
    # through the same validation handler as missing fields.
    r = client.post(
        "/analyze",
        files={"file": ("tray.jpg", _jpeg_bytes(), "image/jpeg")},
        data={"lot_ref": "QA", "look_index": "soon"},
    )
    _expect_json_error(r, status=422)


# --------------------------------------------------------------------------
# POST /analyze -- model unavailable degradation (backend-down path)
# --------------------------------------------------------------------------


def test_analyze_without_model_points_to_replay_mode(monkeypatch):
    # No weights on this machine (venue laptop / GPU dead): /analyze must
    # say so and name the offline path forward, not hang or 500.
    monkeypatch.setattr(sama, "MODEL", None)
    monkeypatch.setattr(sama, "MODEL_ERROR", "weights not found (test)")
    r = client.post(
        "/analyze",
        files={"file": ("tray.jpg", _jpeg_bytes(), "image/jpeg")},
    )
    body = _expect_json_error(r, status=503)
    assert "replay" in body["error"].lower()
    assert "503" not in body["error"]  # no bare codes without explanation


# --------------------------------------------------------------------------
# GET /api/replay/{n}
# --------------------------------------------------------------------------


def test_replay_missing_999_is_json_404(empty_cache):
    r = client.get("/api/replay/999")
    body = _expect_json_error(r, status=404)
    # Readable means actionable: say WHICH number was asked for.
    assert "999" in body["error"]


def test_replay_missing_lists_available_ids(empty_cache):
    (empty_cache / "replay_2.json").write_text("{}", encoding="utf-8")
    r = client.get("/api/replay/999")
    body = _expect_json_error(r, status=404)
    assert "[2]" in body["error"], (
        f"officer should be told replay 2 exists: {body['error']!r}"
    )


def test_replay_non_numeric_id_is_json_422():
    # "abc" can never be a replay number: validation error, still JSON.
    r = client.get("/api/replay/abc")
    body = _expect_json_error(r, status=422)
    assert "detail" not in body, "raw FastAPI validation shape leaked through"


# --------------------------------------------------------------------------
# GET /api/verify/{lot_id} -- the public trust surface
# --------------------------------------------------------------------------


def test_verify_nonexistent_lot_slug_is_json_422():
    r = client.get("/api/verify/nonexistent-lot")
    body = _expect_json_error(r, status=422)
    assert "detail" not in body


def test_verify_numeric_but_absent_lot_is_json_404():
    # Far beyond any real row id, so this stays valid even if the demo DB
    # accumulates certificates.
    r = client.get("/api/verify/987654321")
    body = _expect_json_error(r, status=404)
    assert "certificate" in body["error"].lower()


# --------------------------------------------------------------------------
# GET /api/arbitrate -- missing parameters
# --------------------------------------------------------------------------


def test_arbitrate_with_no_params_is_json_422():
    r = client.get("/api/arbitrate")
    _expect_json_error(r, status=422)


def test_arbitrate_with_only_a_is_json_422():
    # Half a request is still a broken request; both missing params must be
    # reported in the {"error": ...} shape.
    r = client.get("/api/arbitrate", params={"a": "1"})
    body = _expect_json_error(r, status=422)
    assert "detail" not in body


def test_arbitrate_both_certificates_absent_is_json_404():
    # Params present but pointing at certificates that do not exist. The
    # shipped contract names the failing SLOTS ("A", "B") -- same terseness
    # as /api/verify's "No such certificate." -- so lock that, not an
    # id-echoing format the app never promised.
    r = client.get(
        "/api/arbitrate", params={"a": "987654321", "b": "987654322"}
    )
    body = _expect_json_error(r, status=404)
    assert "A" in body["error"] and "B" in body["error"]


def test_arbitrate_names_only_the_missing_side(monkeypatch):
    # Lot A resolves, lot B does not: the verdict must be refused with the
    # B slot named and A untouched -- an officer on a dispute call has to be
    # able to tell WHICH certificate failed to resolve.
    stub = {
        "id": 987654321, "lot_ref": "QA-ONE-SIDED", "centre_name": "QA",
        "farmer_name": "", "officer_name": "", "created_at": "2026-01-01T00:00:00+00:00",
        "grade_a_pct": 60.0, "ci_low": 50.0, "ci_high": 70.0,
        "n_bulbs": 100, "result": {"grade_a_pct": 60.0},
    }
    monkeypatch.setattr(
        sama.db, "get_lot",
        lambda lot_id: stub if lot_id == 987654321 else None,
    )
    r = client.get(
        "/api/arbitrate", params={"a": "987654321", "b": "987654322"}
    )
    body = _expect_json_error(r, status=404)
    # Message reads "Certificate(s) not found: B". Capital "A" appears
    # nowhere else in it, so these two lines pin the slot list to {B}.
    assert "B" in body["error"], body["error"]
    assert "A" not in body["error"], (
        f"healthy side must not be blamed: {body['error']!r}"
    )


# --------------------------------------------------------------------------
# POST /finalize -- malformed JSON bodies
# --------------------------------------------------------------------------


def test_finalize_syntactically_broken_json_is_json_422():
    r = client.post(
        "/finalize", content="{not json at all",
        headers={"Content-Type": "application/json"},
    )
    body = _expect_json_error(r, status=422)
    assert "detail" not in body


def test_finalize_no_body_at_all_is_json_error():
    r = client.post("/finalize")
    body = _expect_json_error(r)
    assert r.status_code in (400, 422)


def test_finalize_json_array_body_is_json_422():
    # Valid JSON, wrong top-level shape: endpoint declares dict.
    r = client.post(
        "/finalize", content="[1, 2, 3]",
        headers={"Content-Type": "application/json"},
    )
    _expect_json_error(r, status=422)


def test_finalize_json_string_body_is_json_422():
    r = client.post(
        "/finalize", content='"just a string"',
        headers={"Content-Type": "application/json"},
    )
    _expect_json_error(r, status=422)


def test_finalize_empty_object_gets_actionable_400():
    # Parses fine but has nothing in it: guidance, not a crash.
    r = client.post(
        "/finalize", content="{}", headers={"Content-Type": "application/json"},
    )
    body = _expect_json_error(r, status=400)
    assert "looks" in body["error"].lower()


def test_finalize_type_confused_looks_never_crashes_raw():
    # Valid JSON dict, but "looks" is a string. Whatever happens inside,
    # the client must receive the standard JSON error shape.
    r = client.post(
        "/finalize", content='{"looks": "junk"}',
        headers={"Content-Type": "application/json"},
    )
    _expect_json_error(r)
    assert r.status_code in (400, 422, 500)
