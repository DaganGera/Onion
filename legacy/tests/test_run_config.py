"""Tests for the run-config plumbing added in pass 2220.

Covers the arithmetic and the contract that keeps scripts and the app on
the SAME inference mode:
  - resolve_e2e_mode reads constants.json through grading.CONSTANTS,
  - yolo26_inference_kwargs pins imgsz 1024 / max_det 300 / end2end,
  - echo_config produces a self-describing record for every run output,
  - eval_lot._per_tray_row error math (the unit MAE averages over).
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import grading  # noqa: E402
from scripts.run_config import (  # noqa: E402
    echo_config, git_commit, resolve_e2e_mode, yolo26_inference_kwargs,
)
from scripts.eval_lot import _per_tray_row  # noqa: E402


# --------------------------------------------------------------------------
# e2e mode -- one reader, from constants.json
# --------------------------------------------------------------------------

def test_e2e_mode_defaults_false_when_key_absent(monkeypatch):
    monkeypatch.setattr(grading, "CONSTANTS", {"height_correction": 0.945})
    assert resolve_e2e_mode() is False


def test_e2e_mode_follows_constants_json(monkeypatch):
    monkeypatch.setattr(grading, "CONSTANTS", {"e2e_mode": True})
    assert resolve_e2e_mode() is True
    monkeypatch.setattr(grading, "CONSTANTS", {"e2e_mode": False})
    assert resolve_e2e_mode() is False


def test_shipped_constants_json_declares_the_mode():
    """The file itself must state the mode -- no invisible defaults."""
    raw = json.loads(
        (Path(__file__).resolve().parents[1] / "app" / "constants.json")
        .read_text(encoding="utf-8"))
    assert isinstance(raw.get("e2e_mode"), bool)


# --------------------------------------------------------------------------
# inference kwargs -- the YOLO26 rules pinned in one place
# --------------------------------------------------------------------------

def test_inference_kwargs_pin_max_det_and_imgsz():
    kw = yolo26_inference_kwargs()
    assert kw["imgsz"] == 1024
    assert kw["max_det"] == 300


def test_inference_kwargs_end2end_matches_constants(monkeypatch):
    monkeypatch.setattr(grading, "CONSTANTS", {"e2e_mode": True})
    assert yolo26_inference_kwargs()["end2end"] is True
    monkeypatch.setattr(grading, "CONSTANTS", {})
    assert yolo26_inference_kwargs()["end2end"] is False


def test_inference_kwargs_rejects_non_default_imgsz_only_by_request():
    assert yolo26_inference_kwargs(imgsz=640)["imgsz"] == 640


# --------------------------------------------------------------------------
# config echo -- every run output carries its own configuration
# --------------------------------------------------------------------------

def test_echo_config_writes_self_describing_json(tmp_path):
    out = tmp_path / "sub" / "config.json"
    cfg = echo_config(out, script="unit-test.py", imgsz=1024, seed=0)
    on_disk = json.loads(out.read_text(encoding="utf-8"))
    assert cfg == on_disk
    for key in ("timestamp_utc", "git_commit", "python", "platform",
                "opencv", "numpy", "torch", "ultralytics"):
        assert key in cfg, f"config echo missing {key}"
    assert cfg["script"] == "unit-test.py"
    assert cfg["imgsz"] == 1024
    assert cfg["seed"] == 0


def test_echo_config_survives_unwritable_path(tmp_path):
    # A directory where the file should be -- must not raise.
    blocker = tmp_path / "blocked"
    blocker.mkdir()
    cfg = echo_config(blocker, script="x")  # path exists as dir -> OSError path
    assert cfg["script"] == "x"


def test_git_commit_is_a_string():
    commit = git_commit()
    assert isinstance(commit, str) and commit
    if not commit.startswith("unknown"):
        assert len(commit) == 12


# --------------------------------------------------------------------------
# per-tray error rows -- the arithmetic the aggregate table hides behind
# --------------------------------------------------------------------------

def _two_look_row():
    return _per_tray_row("T1", true_a=50.0, true_d=10.0,
                         pred_a_1=55.0, pred_d_1=8.0,
                         pred_a_2=52.0, pred_d_2=9.0)


def test_per_tray_row_signed_errors_keep_direction():
    row = _two_look_row()
    assert row["err_grade_a_1look"] == 5.0      # over-predicts Grade A
    assert row["err_defect_1look"] == -2.0      # under-predicts defects
    assert row["err_grade_a_2look"] == 2.0
    assert row["n_looks_used"] == 2


def test_per_tray_row_abs_errors_feed_mae():
    row = _per_tray_row("T2", true_a=50.0, true_d=10.0,
                        pred_a_1=45.0, pred_d_1=13.0,
                        pred_a_2=None, pred_d_2=None)
    assert row["abs_err_grade_a_1look"] == 5.0
    assert row["abs_err_defect_1look"] == 3.0


def test_per_tray_row_single_photo_degrades_and_flags():
    row = _per_tray_row("T3", true_a=50.0, true_d=10.0,
                        pred_a_1=51.0, pred_d_1=9.0,
                        pred_a_2=None, pred_d_2=None)
    assert row["n_looks_used"] == 1
    # 2-look columns mirror the 1-look estimate so aggregate populations
    # stay comparable, but the flag exposes the mixture.
    assert row["pred_grade_a_2look"] == row["pred_grade_a_1look"]
    assert row["abs_err_grade_a_2look"] == row["abs_err_grade_a_1look"]


def test_per_tray_row_aggregates_match_legacy_report_math():
    """The per-tray rows must reproduce exactly what _report computes."""
    import numpy as np
    from scripts.eval_lot import _report

    cases = [("A", 50.0, 52.0), ("B", 30.0, 25.5), ("C", 80.0, 79.0)]
    preds = [c[2] for c in cases]
    trues = [c[1] for c in cases]

    rows = [_per_tray_row(tid, ta, 5.0, pa, 5.0, None, None)
            for tid, ta, pa in cases]
    legacy = _report("Grade A %, 1 look", preds, trues)
    from_rows = _report("Grade A %, 1 look",
                        [r["pred_grade_a_1look"] for r in rows],
                        [r["true_grade_a_pct"] for r in rows])
    assert np.isclose(from_rows["mae"], legacy["mae"])
    assert np.isclose(from_rows["bias"], legacy["bias"])
    assert from_rows["n"] == legacy["n"] == len(rows)


def test_report_columns_map_covers_every_report_name():
    from scripts.eval_lot import REPORT_COLUMNS
    for name in ("Grade A %, 1 look", "Grade A %, 2 looks",
                 "Defect %, 1 look", "Defect %, 2 looks"):
        pred_col, abs_col = REPORT_COLUMNS[name]
        assert abs_col.startswith("abs_err_")
        assert abs_col.endswith(pred_col.replace("pred_", ""))
