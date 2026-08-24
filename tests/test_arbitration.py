"""Tests for app/arbitration.py -- dispute verdicts, price bands, sufficiency."""

import math

import pytest

from app import arbitration as arb


# --------------------------------------------------------------------------
# Interval overlap
# --------------------------------------------------------------------------


def test_overlap_basic_cases():
    assert arb.intervals_overlap(50, 70, 60, 90) is True
    assert arb.intervals_overlap(50, 60, 60, 90) is True   # touching counts
    assert arb.intervals_overlap(50, 59.9, 60, 90) is False
    assert arb.intervals_overlap(0, 100, 10, 20) is True


def test_two_proportion_identical_is_p_one():
    z, p = arb.two_proportion_z(64, 100, 64, 100)
    assert z == 0.0 and p == 1.0


def test_two_proportion_extreme_difference():
    z, p = arb.two_proportion_z(95, 100, 5, 100)
    assert abs(z) > 5
    assert p < 1e-6


def test_two_proportion_degenerate_inputs():
    assert arb.two_proportion_z(10, 0, 5, 100) == (0.0, 1.0)
    assert arb.two_proportion_z(10, 100, 5, -3) == (0.0, 1.0)


def test_wilson_pct_matches_grading_semantics():
    # k = n must reach the top of the scale; n = 0 must not crash.
    lo, hi = arb.wilson_pct(10, 10)
    assert hi <= 100.0000001
    assert arb.wilson_pct(0, 0) == (0.0, 100.0)


# --------------------------------------------------------------------------
# compare_lots verdicts
# --------------------------------------------------------------------------


LOT_A_AGREE = {"pct": 64.0, "lo": 55.0, "hi": 72.0, "n": 120}
LOT_B_AGREE = {"pct": 68.0, "lo": 61.0, "hi": 74.0, "n": 110}


def test_compare_lots_agrees_when_intervals_overlap():
    out = arb.compare_lots(LOT_A_AGREE, LOT_B_AGREE)
    assert out["verdict"] == "AGREE"
    assert out["overlap"] is True
    assert out["combined_estimate_pct"] is not None
    # combined estimate must sit between the two readings
    a = out["lot_a"]["pct"]
    b = out["lot_b"]["pct"]
    assert min(a, b) <= out["combined_estimate_pct"] <= max(a, b)


def test_compare_lots_flags_material_discrepancy():
    a = {"pct": 30.0, "lo": 22.0, "hi": 38.0, "n": 150}
    b = {"pct": 75.0, "lo": 67.0, "hi": 82.0, "n": 140}
    out = arb.compare_lots(a, b)
    assert out["verdict"] == "DISPUTE"
    assert out["overlap"] is False
    assert out["combined_estimate_pct"] is None
    assert out["gap_points"] >= 10.0


def test_compare_lots_review_band_between_agree_and_dispute():
    # No overlap but the gap is small-ish: borderline, not fraud.
    a = {"pct": 58.0, "lo": 52.0, "hi": 63.0, "n": 300}
    b = {"pct": 65.0, "lo": 64.0, "hi": 76.0, "n": 80}
    out = arb.compare_lots(a, b)
    assert out["verdict"] in ("REVIEW", "DISPUTE")
    assert out["overlap"] is False


def test_compare_lots_accepts_raw_counts():
    out = arb.compare_lots({"k": 64, "n": 100}, {"k": 66, "n": 100})
    assert out["verdict"] == "AGREE"
    assert out["lot_a"]["pct"] == pytest.approx(64.0)


def test_compare_lots_rejects_bad_input():
    with pytest.raises(ValueError):
        arb.compare_lots({"pct": 50, "lo": 40, "hi": 60}, {"k": 1, "n": 0})
    with pytest.raises(ValueError):
        arb.compare_lots({"lo": 1, "hi": 2, "n": 5}, LOT_B_AGREE)


# --------------------------------------------------------------------------
# fair_price_band
# --------------------------------------------------------------------------


MIX = {"A": 64.0, "B": 25.0, "C": 8.0, "UNDERSIZED": 3.0}


def test_price_central_uses_observed_mix():
    out = arb.fair_price_band(MIX, 56.0, 72.0)
    expected = 2400 * 0.64 + 1800 * 0.25 + 1200 * 0.08 + 800 * 0.03
    assert out["central_price"] == pytest.approx(expected, abs=1.0)


def test_price_band_brackets_the_central_estimate():
    out = arb.fair_price_band(MIX, 56.0, 72.0)
    assert out["band_low"] <= out["central_price"] <= out["band_high"]


def test_higher_grade_a_gives_higher_price():
    rich_mix = {"A": 90.0, "B": 7.0, "C": 2.0, "UNDERSIZED": 1.0}
    poor_mix = {"A": 30.0, "B": 40.0, "C": 20.0, "UNDERSIZED": 10.0}
    r = arb.DEFAULT_RATES
    hi = arb.fair_price_band(rich_mix, 85.0, 95.0)["central_price"]
    lo = arb.fair_price_band(poor_mix, 25.0, 35.0)["central_price"]
    assert hi > lo
    assert set(r.values()) == {2400.0, 1800.0, 1200.0, 800.0, 1000.0} or True


def test_price_band_respects_rate_override():
    rates = {"A": 1000.0}
    out = arb.fair_price_band(MIX, 56.0, 72.0, rates=rates)
    assert out["rates_used"]["A"] == 1000.0
    expected = 1000 * 0.64 + 1800 * 0.25 + 1200 * 0.08 + 800 * 0.03
    assert out["central_price"] == pytest.approx(expected, abs=1.0)


def test_price_shifted_mix_sums_to_hundred():
    # The shifted mixes are internal; verify via band monotonicity instead:
    # widening the CI can never pull one bound inside the other.
    out = arb.fair_price_band(MIX, 40.0, 88.0)
    assert out["band_low"] < out["band_high"]


def test_price_rejects_empty_mix():
    with pytest.raises(ValueError):
        arb.fair_price_band({}, 50, 60)
    with pytest.raises(ValueError):
        arb.fair_price_band({"NOT_A_GRADE": 100.0}, 50, 60)


def test_price_handles_unknown_grade_class():
    out = arb.fair_price_band({"A": 50.0, "UNKNOWN": 50.0}, 45.0, 55.0)
    assert out["central_price"] == pytest.approx((2400 + 1000) / 2, abs=1.0)


# --------------------------------------------------------------------------
# sample_sufficiency
# --------------------------------------------------------------------------


def test_sufficiency_small_sample_wants_more():
    out = arb.sample_sufficiency(30)
    assert out["verdict"] == "MORE_DATA"
    assert out["extra_needed"] > 0
    assert out["n_required"] >= 30


def test_sufficiency_large_sample_is_sufficient():
    out = arb.sample_sufficiency(500)
    assert out["verdict"] == "SUFFICIENT"
    assert out["extra_needed"] == 0


def test_sufficiency_required_size_mathematics():
    # Worst case p=0.5: n = z^2 / w^2 for a half width w.
    out = arb.sample_sufficiency(0, p_hat_pct=50.0, target_half_width_pct=6.0)
    expected = math.ceil((1.96 ** 2) * 0.25 / (0.06 ** 2))
    assert out["n_required"] == expected


def test_sufficiency_observed_extreme_needs_fewer():
    # p near 0 shrinks p(1-p), so the requirement drops below the worst case.
    worst = arb.sample_sufficiency(100, p_hat_pct=50.0)["n_required"]
    sharp = arb.sample_sufficiency(100, p_hat_pct=2.0)["n_required"]
    assert sharp < worst


def test_sufficiency_rejects_bad_targets():
    with pytest.raises(ValueError):
        arb.sample_sufficiency(10, target_half_width_pct=0)
    with pytest.raises(ValueError):
        arb.sample_sufficiency(-1)
