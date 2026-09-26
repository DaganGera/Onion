"""Loop I2211: the capture-quality gate for frames nobody can grade.

Field condition nobody had tested: procurement continues after dusk and in
closed godowns. A near-black (or flash-blown) frame decodes as a valid image,
passes every upstream check, and used to reach the detector -- which emits
confident-looking boxes on noise -- landing guesses on a signed certificate.

Contract under test:
  1. assess_capture_quality() blocks only genuinely unusable frames
     (mean luma < 40 or > 246), warns on dim/blurry, and never raises.
  2. /analyze refuses a blocked frame with a JSON 422 whose message says
     what to do -- BEFORE the model runs (the stub below proves it).
  3. A usable frame passes through and carries a `quality` block so the UI
     can advise without blocking.

Run:
    python -m pytest tests/test_capture_quality.py -q
"""

import sys
from pathlib import Path

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import capture_quality as cq  # noqa: E402
from app import main as sama  # noqa: E402

client = TestClient(sama.app, raise_server_exceptions=False)


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def _frame(mean: float = 128.0, width: int = 640, height: int = 480,
           noise: float = 0.0, seed: int = 7) -> np.ndarray:
    """BGR test frame with a target mean luma and optional texture."""
    rng = np.random.default_rng(seed)
    base = np.full((height, width, 3), mean, dtype=np.float64)
    if noise > 0:
        base += rng.normal(0, noise, base.shape)
    return np.clip(base, 0, 255).astype(np.uint8)


def _jpeg_bytes(image: np.ndarray) -> bytes:
    ok, buf = cv2.imencode(".jpg", image)
    assert ok, "fixture failed to encode JPEG"
    return buf.tobytes()


class _MustNotPredict:
    """Sentinel: if predict() runs, an earlier gate failed to fire."""

    def predict(self, *args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("MODEL.predict ran on a frame that should "
                             "have been refused by the quality gate")


@pytest.fixture()
def model_ready(monkeypatch):
    monkeypatch.setattr(sama, "MODEL", _MustNotPredict())
    monkeypatch.setattr(sama, "MODEL_ERROR", None)


# --------------------------------------------------------------------------
# Pure function: assess_capture_quality
# --------------------------------------------------------------------------


def test_pitch_black_frame_is_blocked_as_dark():
    q = cq.assess_capture_quality(_frame(mean=8))
    assert q["checked"] is True
    assert q["blocked"] is True
    assert q["reason"] == "dark"


def test_flash_blown_frame_is_blocked_as_overexposed():
    q = cq.assess_capture_quality(_frame(mean=252))
    assert q["blocked"] is True
    assert q["reason"] == "overexposed"


def test_normal_indoor_frame_passes_with_no_warnings():
    # Mid-grey plus heavy sensor noise: plenty of luminance, plenty of
    # high-frequency detail (noise drives Laplacian variance up).
    q = cq.assess_capture_quality(_frame(mean=120, noise=18))
    assert q["blocked"] is False
    assert q["reason"] is None
    assert q["warnings"] == []
    assert 100 <= q["brightness"] <= 140


def test_dim_but_usable_frame_warns_without_blocking():
    q = cq.assess_capture_quality(_frame(mean=55, noise=15))
    assert q["blocked"] is False
    assert "dim" in q["warnings"]
    assert q["brightness"] < cq.DIM_WARN_MEAN


def test_blurry_checkerboard_warns_and_sharp_one_does_not():
    # Checkerboard at a realistic capture width; then the same board after a
    # strong Gaussian blur. Same brightness, wildly different sharpness --
    # which is exactly the discrimination the warning must make.
    sq = 16
    ii, jj = np.indices((480, 640))
    board = ((((ii // sq) + (jj // sq)) % 2) * 255).astype(np.uint8)
    sharp = cv2.cvtColor(board, cv2.COLOR_GRAY2BGR)
    blurry = cv2.GaussianBlur(sharp, (41, 41), 12)

    q_sharp = cq.assess_capture_quality(sharp)
    q_blur = cq.assess_capture_quality(blurry)

    assert q_sharp["checked"] and not q_sharp["blocked"]
    assert "blurry" not in q_sharp["warnings"], q_sharp
    assert q_blur["sharpness"] < cq.BLUR_WARN_VAR <= q_sharp["sharpness"]
    assert "blurry" in q_blur["warnings"]
    assert q_blur["blocked"] is False


def test_sharpness_estimate_is_resolution_independent():
    # The gate's promise is a stable VERDICT across phone megapixels: the
    # same scene at two resolutions must land on the same side of the blur
    # threshold. (Raw variance still drifts -- area downsampling attenuates
    # pure sensor noise -- which is why the threshold is set an order of
    # magnitude below textured-scene values and only ever WARNS.)
    small = _frame(mean=120, width=480, height=360, noise=18)
    big = _frame(mean=120, width=960, height=720, noise=18)
    q_small = cq.assess_capture_quality(small)
    q_big = cq.assess_capture_quality(big)
    assert "blurry" not in q_small["warnings"]
    assert "blurry" not in q_big["warnings"]
    assert min(q_small["sharpness"], q_big["sharpness"]) > cq.BLUR_WARN_VAR


def test_broken_input_never_raises_and_never_blocks():
    for junk in (None, np.zeros((0, 0, 3), dtype=np.uint8), "not an image"):
        q = cq.assess_capture_quality(junk)
        assert q["checked"] is False
        assert q["blocked"] is False   # degrade to old behaviour, not refuse


def test_rejection_message_names_the_fix():
    dark = cq.rejection_message({"blocked": True, "reason": "dark",
                                 "brightness": 12.4})
    washed = cq.rejection_message({"blocked": True, "reason": "overexposed"})
    assert "too dark" in dark and "daylight" in dark and "12.4" in dark
    assert "flash" in washed.lower()
    assert cq.rejection_message({"blocked": False}) is None


# --------------------------------------------------------------------------
# API: /analyze refuses unusable frames before the model runs
# --------------------------------------------------------------------------


def _post_analyze(payload: bytes, filename="tray.jpg"):
    return client.post(
        "/analyze",
        files={"file": (filename, payload, "image/jpeg")},
        data={"lot_ref": "QA-DARK", "look_index": "0", "tray_id": "T1"},
    )


def test_analyze_refuses_black_frame_with_json_422(model_ready):
    r = _post_analyze(_jpeg_bytes(_frame(mean=5)))
    assert r.status_code == 422, r.text[:300]
    body = r.json()
    assert set(body.keys()) == {"error"}
    assert "too dark" in body["error"]
    assert "daylight" in body["error"]      # actionable, not just a refusal
    assert "Traceback" not in r.text


def test_analyze_refuses_washed_out_frame_with_json_422(model_ready):
    r = _post_analyze(_jpeg_bytes(_frame(mean=253)))
    assert r.status_code == 422
    assert "washed out" in r.json()["error"]


def test_analyze_usable_frame_passes_and_carries_quality_block(monkeypatch):
    class _FakeModel:
        def predict(self, *args, **kwargs):  # noqa: ANN002, ANN003
            class _R:
                boxes = None   # no detections needed; we are testing plumbing
            return [_R()]

    monkeypatch.setattr(sama, "MODEL", _FakeModel())
    r = _post_analyze(_jpeg_bytes(_frame(mean=130, noise=16)))
    assert r.status_code == 200, r.text[:300]
    body = r.json()
    assert "error" not in body, body
    assert body["quality"]["checked"] is True
    assert body["quality"]["blocked"] is False
    assert body["n_bulbs"] == 0
