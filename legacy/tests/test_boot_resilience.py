"""Task B-002 fix 2 regression tests: boot survives a broken OpenCV.

RT-001 D-1 found the most likely live-demo crash: app/scale.py built its
ArUco detector at module level, so a machine with plain opencv-python (no
cv2.aruco submodule) died with AttributeError before uvicorn even bound --
taking pages, replay, dashboard and verify down with capture.

The contract now:

    1. Importing app.scale never raises, whatever cv2 looks like.
    2. get_detector() returns None instead of raising when aruco is missing.
    3. detect_scale() keeps its "never raises" promise and simply skips the
       marker rungs of the ladder in that environment.
    4. POST /analyze alone degrades, loudly, with a JSON error naming the
       calibration module; pages / replay / health keep answering.
    5. /api/health reports aruco_available so a venue box can be diagnosed
       from the browser, not the console.

The subprocess test is the real guarantee for (1): it deletes the
cv2.aruco attribute -- exactly what plain opencv-python lacks -- and then
imports app.scale and app.grading fresh.

Run:
    C:/Users/ADMIN/AppData/Local/Programs/Python/Python311/python.exe -m pytest tests/test_boot_resilience.py -q
"""

import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import main as sama        # noqa: E402
from app import scale as scale_mod  # noqa: E402

client = TestClient(sama.app, raise_server_exceptions=False)
ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def no_aruco(monkeypatch):
    """Simulate plain opencv-python on the already-imported module."""
    monkeypatch.setattr(scale_mod, "_DETECTOR", None)
    monkeypatch.setattr(scale_mod, "_DETECTOR_BROKEN", False)
    monkeypatch.setattr(scale_mod, "ARUCO_AVAILABLE", False)


# --------------------------------------------------------------------------
# Healthy environment: the lazy detector still works and is cached
# --------------------------------------------------------------------------


def test_healthy_env_builds_and_caches_detector():
    # This repo pins opencv-contrib-python, so the dev/demo machine has
    # aruco. If this assert fires here, the guard broke the normal path.
    assert scale_mod.ARUCO_AVAILABLE is True
    det = scale_mod.get_detector()
    assert det is not None
    assert scale_mod.get_detector() is det, "detector must be built once"


def test_scale_result_to_dict_survives_missing_aruco(no_aruco):
    result = scale_mod.detect_scale(np.zeros((240, 320, 3), np.uint8))
    payload = result.to_dict()          # must be JSON-safe without markers
    assert payload["calibrated"] is False
    assert payload["marker_ids"] == []


# --------------------------------------------------------------------------
# Missing cv2.aruco: nothing raises, the ladder just loses its marker rungs
# --------------------------------------------------------------------------


def test_get_detector_returns_none_when_aruco_missing(no_aruco):
    assert scale_mod.get_detector() is None


def test_detect_scale_never_raises_when_aruco_missing(no_aruco):
    result = scale_mod.detect_scale(np.zeros((64, 64, 3), np.uint8))
    assert isinstance(result, scale_mod.ScaleResult)
    assert result.marker_ids == []      # marker rungs skipped, not crashed
    assert result.calibrated is False   # featureless frame: honest "none"
    assert result.source == "none"


def test_import_survives_missing_cv2_aruco_subprocess():
    """The actual RT-001 D-1 scenario, end to end.

    Plain opencv-python ships without the cv2.aruco submodule. Delete the
    attribute to simulate it, then import app.scale and app.grading fresh
    in a clean interpreter: neither may raise, and detect_scale must work.
    """
    code = (
        "import sys\n"
        f"sys.path.insert(0, {str(ROOT)!r})\n"
        "import cv2\n"
        "if hasattr(cv2, 'aruco'):\n"
        "    del cv2.aruco            # simulate plain opencv-python\n"
        "assert not hasattr(cv2, 'aruco')\n"
        "import numpy as np\n"
        "import app.scale as s\n"
        "assert s.ARUCO_AVAILABLE is False, 'guard missed missing aruco'\n"
        "assert s.get_detector() is None, 'detector built without aruco'\n"
        "r = s.detect_scale(np.zeros((64, 64, 3), np.uint8))\n"
        "assert r.calibrated is False and r.marker_ids == []\n"
        "import app.grading as g     # grading imports scale too\n"
        "g.detect_scale(np.zeros((32, 32, 3), np.uint8))\n"
        "print('BOOT-OK')\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(ROOT), capture_output=True, text=True, timeout=300,
    )
    assert proc.returncode == 0, (
        f"import-time crash still present:\nstdout={proc.stdout!r}\n"
        f"stderr={proc.stderr[-2000:]!r}"
    )
    assert "BOOT-OK" in proc.stdout


# --------------------------------------------------------------------------
# The one degraded route: POST /analyze says exactly what broke
# --------------------------------------------------------------------------


class _MustNotPredict:
    def predict(self, *args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("predict() ran although calibration is missing")


def _jpeg_bytes(width=32, height=32) -> bytes:
    import cv2
    import io as _io
    ok, buf = cv2.imencode(".jpg", np.zeros((height, width, 3), np.uint8))
    assert ok
    return buf.tobytes()


def test_analyze_without_calibration_module_is_json_503(no_aruco, monkeypatch):
    monkeypatch.setattr(sama, "MODEL", _MustNotPredict())
    monkeypatch.setattr(sama, "MODEL_ERROR", None)
    r = client.post(
        "/analyze",
        files={"file": ("tray.jpg", _jpeg_bytes(), "image/jpeg")},
        data={"lot_ref": "QA"},
    )
    assert r.status_code == 503, r.text[:400]
    body = r.json()
    assert set(body.keys()) == {"error"}
    assert "calibration module unavailable" in body["error"]
    assert "Traceback" not in r.text


# --------------------------------------------------------------------------
# Everything else keeps serving while calibration is unavailable
# --------------------------------------------------------------------------


def test_pages_serve_without_calibration_module(no_aruco):
    for path in ("/", "/dashboard"):
        r = client.get(path)
        assert r.status_code == 200, (path, r.status_code)
        assert r.headers["content-type"].startswith("text/html")
        assert "Traceback" not in r.text


def test_replay_serves_without_calibration_module(no_aruco, tmp_path,
                                                  monkeypatch):
    (tmp_path / "replay_0.json").write_text('{"lot_ref": "DEMO"}',
                                            encoding="utf-8")
    monkeypatch.setattr(sama, "CACHE", tmp_path)
    r = client.get("/api/replay/0")
    assert r.status_code == 200
    assert r.json()["lot_ref"] == "DEMO"


def test_health_reports_aruco_state(no_aruco):
    body = client.get("/api/health").json()
    assert body["aruco_available"] is False


def test_health_reports_aruco_available_on_healthy_machine():
    body = client.get("/api/health").json()
    assert body["aruco_available"] is True
