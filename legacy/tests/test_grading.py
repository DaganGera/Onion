"""Tests for app/grading.py. Gate T2: all of these must pass, then the
module is frozen."""

import sys
from pathlib import Path

import cv2
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import grading  # noqa: E402


# --------------------------------------------------------------------------
# Scale detection -- the fallback ladder
# --------------------------------------------------------------------------


def _blank(w=1200, h=900, level=255):
    return np.full((h, w, 3), level, np.uint8)


def _paste_marker(canvas, marker_id, side_px, x, y):
    dictionary = cv2.aruco.getPredefinedDictionary(grading.ARUCO_DICT)
    marker = cv2.aruco.generateImageMarker(dictionary, marker_id, side_px)
    canvas[y:y + side_px, x:x + side_px] = cv2.cvtColor(marker, cv2.COLOR_GRAY2BGR)
    return canvas


def _mat_photo(px_per_mm=4.0, hide=()):
    """Render the real printed mat, optionally burying some markers."""
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    from make_mat import build_mat
    from app.mat_layout import MARKER_MM, MARKER_ORIGINS_MM, MAT_H_MM, MAT_W_MM

    mat = np.array(build_mat())
    w = int(MAT_W_MM * px_per_mm)
    h = int(MAT_H_MM * px_per_mm)
    mat = cv2.resize(mat, (w, h), interpolation=cv2.INTER_AREA)
    scene = np.full((h + 120, w + 120, 3), 170, np.uint8)
    scene[60:60 + h, 60:60 + w] = cv2.cvtColor(mat, cv2.COLOR_GRAY2BGR)

    for marker_id in hide:
        x_mm, y_mm = MARKER_ORIGINS_MM[marker_id]
        cx = int(60 + (x_mm + MARKER_MM / 2) * px_per_mm)
        cy = int(60 + (y_mm + MARKER_MM / 2) * px_per_mm)
        cv2.circle(scene, (cx, cy), int(30 * px_per_mm), (60, 110, 160), -1)
    return scene


def test_full_mat_uses_homography():
    scale = grading.detect_scale(_mat_photo())
    assert scale.calibrated is True
    assert scale.source == "homography"
    assert len(scale.marker_ids) == 8
    assert scale.homography is not None
    assert scale.confidence == pytest.approx(1.0)


def test_homography_recovers_a_known_distance():
    """The whole point: 100 mm on the mat must measure 100 mm."""
    px_per_mm = 4.0
    scale = grading.detect_scale(_mat_photo(px_per_mm))
    x0 = 60 + 70.0 * px_per_mm
    x1 = 60 + 170.0 * px_per_mm
    y = 60 + 105.0 * px_per_mm
    pts = np.array([[[x0, y]], [[x1, y]]], np.float32)
    mapped = cv2.perspectiveTransform(pts, scale.homography).reshape(2, 2)
    assert float(np.linalg.norm(mapped[1] - mapped[0])) == pytest.approx(100.0, abs=1.5)


def test_three_markers_still_strong_homography():
    scale = grading.detect_scale(_mat_photo(hide=(0, 1, 2, 3, 4)))
    assert scale.calibrated is True
    assert scale.source == "homography"
    assert len(scale.marker_ids) == 3


def test_two_markers_degrade_to_weak_homography():
    scale = grading.detect_scale(_mat_photo(hide=(0, 1, 2, 3, 4, 5)))
    assert scale.calibrated is True
    assert scale.source == "homography_weak"
    assert scale.confidence < 1.0
    assert scale.warning


def test_one_marker_degrades_to_single_marker():
    scale = grading.detect_scale(_mat_photo(hide=(0, 1, 2, 3, 4, 5, 6)))
    assert scale.calibrated is True
    assert scale.source == "single_marker"
    assert scale.mm_per_px is not None
    assert "1 marker" in scale.warning


def test_all_markers_buried_falls_back_to_mat_outline():
    """Every marker gone and a scale is still recovered -- but marked
    provisional, because on cluttered trays this rung measured 16.9 mm MAE."""
    scale = grading.detect_scale(_mat_photo(hide=tuple(range(8))))
    assert scale.calibrated is True
    assert scale.source == "mat_edge"
    assert scale.grades_certified is False
    assert "PROVISIONAL" in scale.warning


def test_carried_outranks_mat_outline():
    """A homography from thirty seconds ago beats a guessed rectangle."""
    good = grading.detect_scale(_mat_photo())
    buried = grading.detect_scale(_mat_photo(hide=tuple(range(8))), carried=good)
    assert buried.source == "carried"
    assert buried.grades_certified is True


def test_marker_rungs_are_all_certified():
    for hide in ((), (0, 1, 2), (0, 1, 2, 3, 4, 5), (0, 1, 2, 3, 4, 5, 6)):
        scale = grading.detect_scale(_mat_photo(hide=hide))
        assert scale.grades_certified is True, scale.source


def test_no_reference_at_all_refuses_to_guess():
    """A number invented without a reference is indistinguishable from a
    real one on the certificate. Withhold it instead."""
    scale = grading.detect_scale(_blank(400, 300, level=128))
    assert scale.calibrated is False
    assert scale.source == "none"
    assert scale.mm_per_px is None
    assert grading.bulb_diameter_mm((0, 0, 100, 80), scale) is None


def test_carried_scale_rescues_a_second_look():
    good = grading.detect_scale(_mat_photo())
    blank = grading.detect_scale(_blank(400, 300, level=128), carried=good)
    assert blank.calibrated is True
    assert blank.source == "carried"
    assert blank.mm_per_px == good.mm_per_px
    assert "not moved" in blank.warning


def test_carried_scale_is_not_used_when_markers_are_visible():
    good = grading.detect_scale(_mat_photo())
    fresh = grading.detect_scale(_mat_photo(), carried=good)
    assert fresh.source == "homography"


def test_carrying_an_uncalibrated_scale_does_not_calibrate():
    empty = grading.detect_scale(_blank(400, 300, level=128))
    again = grading.detect_scale(_blank(400, 300, level=128), carried=empty)
    assert again.calibrated is False


def test_detect_scale_handles_none_and_empty():
    assert grading.detect_scale(None).calibrated is False
    assert grading.detect_scale(np.zeros((0, 0, 3), np.uint8)).calibrated is False


def test_scale_result_is_json_safe():
    payload = grading.detect_scale(_mat_photo()).to_dict()
    import json
    json.dumps(payload)
    assert payload["markers_found"] == 8
    assert payload["markers_expected"] == 8
    assert "homography" not in payload   # a 3x3 matrix in every response is noise


# --------------------------------------------------------------------------
# Sizing
# --------------------------------------------------------------------------


def test_bulb_diameter_uses_short_side():
    # 120 px wide, 80 px tall. Short side is 80. At 0.5 mm/px that is 40 mm,
    # then scaled by whatever height_correction calibrate_size.py last fitted.
    # Asserting a bare 40.0 would break every time the factor is re-fitted.
    expected = 40.0 * grading.CONSTANTS["height_correction"]
    assert grading.bulb_diameter_mm((0, 0, 120, 80), 0.5) == pytest.approx(expected)


def test_bulb_diameter_applies_height_correction(monkeypatch):
    monkeypatch.setitem(grading.CONSTANTS, "height_correction", 0.5)
    # short side 80 px * 0.5 mm/px * 0.5 correction = 20 mm
    assert grading.bulb_diameter_mm((0, 0, 120, 80), 0.5) == pytest.approx(20.0)


def test_bulb_diameter_without_scale_is_none():
    assert grading.bulb_diameter_mm((0, 0, 120, 80), None) is None


# --------------------------------------------------------------------------
# Grade boundaries -- lower edge inclusive
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "diameter,expected",
    [
        (95.0, "A"),
        (80.0, "A"),      # boundary
        (79.9, "B"),
        (50.0, "B"),      # boundary
        (49.9, "C"),
        (30.0, "C"),      # boundary
        (29.9, "UNDERSIZED"),
        (0.0, "UNDERSIZED"),
    ],
)
def test_size_grade_boundaries(diameter, expected):
    assert grading.size_grade(diameter) == expected


def test_size_grade_unknown_without_diameter():
    assert grading.size_grade(None) == "UNKNOWN"


# --------------------------------------------------------------------------
# Wilson interval
# --------------------------------------------------------------------------


def test_wilson_at_zero_n_does_not_divide_by_zero():
    assert grading.wilson_interval(0, 0) == (0.0, 1.0)


def test_wilson_at_k_equals_n_has_upper_bound_one():
    lo, hi = grading.wilson_interval(20, 20)
    assert hi == pytest.approx(1.0)
    assert 0.0 < lo < 1.0


def test_wilson_at_k_zero_has_lower_bound_zero():
    lo, hi = grading.wilson_interval(0, 20)
    assert lo == pytest.approx(0.0)
    assert 0.0 < hi < 1.0


def test_wilson_brackets_the_point_estimate():
    lo, hi = grading.wilson_interval(15, 40)
    assert lo < 15 / 40 < hi


def test_wilson_narrows_as_n_grows():
    _, hi_small = grading.wilson_interval(5, 10)
    lo_small, _ = grading.wilson_interval(5, 10)
    lo_big, hi_big = grading.wilson_interval(500, 1000)
    assert (hi_big - lo_big) < (hi_small - lo_small)


# --------------------------------------------------------------------------
# decide()
# --------------------------------------------------------------------------


def test_decide_thresholds():
    threshold = grading.CONSTANTS["accept_threshold"]
    assert grading.decide(threshold) == "ACCEPT"
    assert grading.decide(threshold + 0.1) == "ACCEPT"
    assert grading.decide(threshold - 0.01) == "REFER"


# --------------------------------------------------------------------------
# merge_looks
# --------------------------------------------------------------------------


def _bulb(cls, grade="B", decision="ACCEPT", tray_id="T1"):
    return {"cls": cls, "size_grade": grade, "decision": decision, "tray_id": tray_id}


def test_merge_two_empty_looks_does_not_crash():
    out = grading.merge_looks([[], []])
    assert out["n_bulb_observations"] == 0
    assert out["n_looks"] == 2
    assert out["grade_a_pct"] == 0.0
    assert out["grade_a_ci_low"] == 0.0
    assert out["grade_a_ci_high"] == 100.0


def test_merge_pools_across_looks():
    look1 = [_bulb("sound", "A"), _bulb("rotten", "B")]
    look2 = [_bulb("sound", "A"), _bulb("sprouted", "C")]
    out = grading.merge_looks([look1, look2])
    assert out["n_bulb_observations"] == 4
    assert out["n_looks"] == 2
    assert out["n_trays"] == 1
    assert out["class_counts"]["sound"] == 2
    assert out["class_counts"]["rotten"] == 1
    assert out["grade_counts"]["A"] == 2
    assert out["grade_a_pct"] == pytest.approx(50.0)


def test_merge_accepts_integer_class_indices():
    out = grading.merge_looks([[_bulb(0), _bulb(1), _bulb(3)]])
    assert out["class_counts"]["sound"] == 1
    assert out["class_counts"]["rotten"] == 1
    assert out["class_counts"]["black_smut"] == 1


def test_merge_counts_referred_bulbs():
    look = [_bulb("sound", decision="REFER"), _bulb("sound"), _bulb("rotten", decision="REFER")]
    assert grading.merge_looks([look])["n_referred"] == 2


def test_merge_reports_raw_and_corrected_separately():
    look = [_bulb("sound"), _bulb("sound"), _bulb("rotten"), _bulb("rotten")]
    out = grading.merge_looks([look])
    assert out["defect_rate_raw"] == pytest.approx(50.0)
    assert "defect_rate_corrected" in out
    # raw must survive untouched even when a correction is applied
    assert out["defect_rate_raw"] == pytest.approx(50.0)


def test_one_look_and_two_looks_apply_different_occlusion_factors(monkeypatch):
    monkeypatch.setitem(grading.CONSTANTS, "occlusion_correction_1look", 0.5)
    monkeypatch.setitem(grading.CONSTANTS, "occlusion_correction_2look", 0.8)

    bulbs = [_bulb("sound"), _bulb("rotten")]
    one = grading.merge_looks([bulbs])
    two = grading.merge_looks([bulbs, []])

    assert one["occlusion_factor_applied"] == 0.5
    assert two["occlusion_factor_applied"] == 0.8
    # A worse 1-look factor must inflate the corrected rate more.
    assert one["defect_rate_corrected"] > two["defect_rate_corrected"]


def test_corrected_defect_rate_is_capped_at_100():
    monkeypatch_value = 0.1
    original = grading.CONSTANTS["occlusion_correction_1look"]
    grading.CONSTANTS["occlusion_correction_1look"] = monkeypatch_value
    try:
        out = grading.merge_looks([[_bulb("rotten"), _bulb("rotten")]])
        assert out["defect_rate_corrected"] == pytest.approx(100.0)
    finally:
        grading.CONSTANTS["occlusion_correction_1look"] = original


def test_merge_counts_distinct_trays():
    look = [_bulb("sound", tray_id="T1"), _bulb("sound", tray_id="T2")]
    assert grading.merge_looks([look])["n_trays"] == 2


# --------------------------------------------------------------------------
# Defect pooling semantics -- two looks re-observe the SAME bulbs
# --------------------------------------------------------------------------


def test_defect_rate_takes_best_look_not_the_average():
    """A defect hidden in look 1 and visible in look 2 is still a defect.

    Averaging the two looks would report 25% for a tray that is really 50%
    defective, which is the exact bias the Two-Look protocol exists to remove.
    """
    look1 = [_bulb("sound"), _bulb("sound"), _bulb("sound"), _bulb("sound")]
    look2 = [_bulb("rotten"), _bulb("rotten"), _bulb("sound"), _bulb("sound")]
    out = grading.merge_looks([look1, look2])

    assert out["defect_rate_per_look"] == [0.0, 50.0]
    assert out["defect_rate_raw"] == pytest.approx(50.0)   # best view, not 25%


def test_defect_rate_ignores_empty_looks():
    look = [_bulb("rotten"), _bulb("sound")]
    out = grading.merge_looks([look, []])
    assert out["defect_rate_raw"] == pytest.approx(50.0)


def test_grade_a_still_pools_every_observation():
    """Size does not hide on a shake, so pooling is right for grades."""
    look1 = [_bulb("sound", "A"), _bulb("sound", "B")]
    look2 = [_bulb("sound", "A"), _bulb("sound", "B")]
    out = grading.merge_looks([look1, look2])
    assert out["n_bulb_observations"] == 4
    assert out["grade_counts"]["A"] == 2
    assert out["grade_a_pct"] == pytest.approx(50.0)
    # more observations must tighten the interval
    one = grading.merge_looks([look1])
    assert (out["grade_a_ci_high"] - out["grade_a_ci_low"]) <            (one["grade_a_ci_high"] - one["grade_a_ci_low"])
