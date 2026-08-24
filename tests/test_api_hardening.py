"""QA audit B-001 regression tests: every failure path stays readable.

Covers:
- global exception handler -> _error() JSON shape, never a raw 500
- unmatched routes / bad params -> JSON errors, not Starlette plain text
- /api/health survives stray or malformed filenames in app/cache
- /api/replay/{n} read failures come back as JSON
- page routes fail to a minimal readable HTML stub, never a traceback

app/grading.py is untouched by all of this; these tests only exercise
app/main.py failure paths.
"""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import main as sama  # noqa: E402

# raise_server_exceptions=False so tests see exactly what a phone on wifi
# would see, instead of pytest re-raising the server-side error.
client = TestClient(sama.app, raise_server_exceptions=False)


@pytest.fixture()
def cache_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(sama, "CACHE", tmp_path)
    return tmp_path


@pytest.fixture()
def static_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(sama, "STATIC", tmp_path)
    return tmp_path


# --------------------------------------------------------------------------
# Global exception handlers -- nothing escapes as a raw 500
# --------------------------------------------------------------------------


def test_unhandled_exception_returns_error_json(monkeypatch):
    def boom(name):
        raise RuntimeError("demo explosion")

    monkeypatch.setattr(sama, "_serve", boom)
    r = client.get("/dashboard")
    assert r.status_code == 500
    body = r.json()
    assert set(body.keys()) == {"error"}
    assert "Traceback" not in r.text
    # exception internals must not leak to the client
    assert "demo explosion" not in body["error"]


def test_unknown_route_returns_json_error():
    r = client.get("/definitely-not-a-route")
    assert r.status_code == 404
    assert set(r.json().keys()) == {"error"}


def test_bad_query_params_return_error_shape():
    # /api/arbitrate needs ints; letters force FastAPI validation to fire,
    # which must come back in the {"error": ...} shape the frontend reads.
    r = client.get("/api/arbitrate", params={"a": "x", "b": "y"})
    assert r.status_code == 422
    assert "error" in r.json()


# --------------------------------------------------------------------------
# /api/health vs a messy cache dir
# --------------------------------------------------------------------------


def test_health_skips_malformed_cache_filenames(cache_dir):
    (cache_dir / "replay_2.json").write_text("{}", encoding="utf-8")
    (cache_dir / "replay_10.json").write_text("{}", encoding="utf-8")
    (cache_dir / "replay_.json").write_text("{}", encoding="utf-8")        # int("")
    (cache_dir / "replay_notes.json").write_text("{}", encoding="utf-8")   # int("notes")
    (cache_dir / "notes.txt").write_text("x", encoding="utf-8")            # not a replay

    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/json")
    assert r.json()["replays_available"] == [2, 10]


def test_health_collapses_duplicate_replay_numbers(cache_dir):
    (cache_dir / "replay_5.json").write_text("{}", encoding="utf-8")
    (cache_dir / "replay_05.json").write_text("{}", encoding="utf-8")

    r = client.get("/api/health")
    assert r.json()["replays_available"] == [5]


def test_health_survives_an_exploding_cache_scan(monkeypatch):
    class ExplodingCache:
        def glob(self, pattern):
            raise RuntimeError("fs gone")

    monkeypatch.setattr(sama, "CACHE", ExplodingCache())
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["replays_available"] == []


# --------------------------------------------------------------------------
# /api/replay/{n} -- every read failure is JSON
# --------------------------------------------------------------------------


def test_replay_happy_path_still_works(cache_dir):
    (cache_dir / "replay_3.json").write_text('{"lot_ref": "DEMO"}',
                                             encoding="utf-8")
    r = client.get("/api/replay/3")
    assert r.status_code == 200
    assert r.json()["lot_ref"] == "DEMO"


def test_replay_missing_file_is_json_404(cache_dir):
    r = client.get("/api/replay/42")
    assert r.status_code == 404
    assert "No cached replay 42" in r.json()["error"]


def test_replay_corrupt_json_is_json_error(cache_dir):
    (cache_dir / "replay_4.json").write_text("{not json at all",
                                             encoding="utf-8")
    r = client.get("/api/replay/4")
    assert r.status_code == 500
    assert "corrupt" in r.json()["error"]


def test_replay_invalid_utf8_is_json_error(cache_dir):
    (cache_dir / "replay_6.json").write_bytes(b"\xff\xfe\x00binary junk")
    r = client.get("/api/replay/6")
    assert r.status_code == 500
    assert set(r.json().keys()) == {"error"}


def test_replay_unreadable_file_is_json_error(cache_dir):
    # A directory sitting where the file should be makes read_text raise an
    # OSError (IsADirectoryError on Linux, PermissionError on Windows).
    (cache_dir / "replay_9.json").mkdir()
    r = client.get("/api/replay/9")
    assert r.status_code == 500
    assert set(r.json().keys()) == {"error"}


def test_replay_missing_lists_only_parseable_ids(cache_dir):
    (cache_dir / "replay_1.json").write_text("{}", encoding="utf-8")
    (cache_dir / "replay_junk.json").write_text("{}", encoding="utf-8")

    r = client.get("/api/replay/7")
    error = r.json()["error"]
    assert "[1]" in error               # real option shown...
    assert "junk" not in error          # ...unparseable name filtered out


# --------------------------------------------------------------------------
# Page routes fail to a readable stub, never a traceback
# --------------------------------------------------------------------------


def test_missing_static_file_gives_readable_404(static_dir):
    r = client.get("/dashboard")
    assert r.status_code == 404
    assert "dashboard.html" in r.text
    assert "Traceback" not in r.text


def test_unreadable_static_file_gives_readable_stub(static_dir):
    # A directory where the page should be -> read_text raises OSError.
    (static_dir / "dashboard.html").mkdir()
    r = client.get("/dashboard")
    assert r.status_code == 503
    assert "SAMA" in r.text
    assert "Could not load" in r.text
    assert "Traceback" not in r.text


def test_report_template_failure_gives_readable_stub(static_dir, monkeypatch):
    monkeypatch.setattr(
        sama.db, "get_lot", lambda lot_id: {"id": lot_id, "lot_ref": "X"})
    (static_dir / "report.html").mkdir()   # unreadable on purpose

    r = client.get("/report/1")
    assert r.status_code == 503
    assert "certificate page" in r.text
    assert "Traceback" not in r.text


def test_report_missing_template_gives_readable_404(static_dir, monkeypatch):
    monkeypatch.setattr(
        sama.db, "get_lot", lambda lot_id: {"id": lot_id, "lot_ref": "X"})

    r = client.get("/report/1")
    assert r.status_code == 404
    assert "report.html" in r.text


def test_verify_template_failure_gives_readable_stub(static_dir, monkeypatch):
    monkeypatch.setattr(
        sama, "_lot_verification",
        lambda lot_id: {"lot": {}, "chain": {}})
    (static_dir / "verify.html").mkdir()   # unreadable on purpose

    r = client.get("/verify/1")
    assert r.status_code == 503
    assert "verification page" in r.text
    assert "Traceback" not in r.text
