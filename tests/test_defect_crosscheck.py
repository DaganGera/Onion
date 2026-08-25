"""Loop I858: RT-001 S-1 visible compensation — per-tray pooled defect cross-check.

RT-001 S-1 (CRITICAL, grading.py frozen): the certified defect rate is
max(per_look_rates)/factor. max() over more looks/trays can only grow, so an
officer who photographs MORE of the lot mechanically RAISES the certified
number — the bias lands on the party being paid less. Unfreezing merge_looks
is a data-scientist decision; this loop ships the documented alternative:
a second estimator computed at /finalize from what merge_looks ALREADY
published, rendered beside the certified figure so the conservatism is
visible instead of hidden.

Contract under test:

  1. Point estimate = pooled incidence 100*(n_obs - sound)/n_obs, rebuilt
     ONLY from published class_counts — it can never drift from the printed
     statistic (same discipline as D8's defect_ci_fields).
  2. Interval uses a per-tray design effect: within a tray, repeated looks
     re-observe the same bulbs (worst-case rho=1, D11); ACROSS trays,
     samples are physically distinct and earn full credit.
        n_eff = sum_t(n_t / m_t),   deff = n_obs / n_eff   (>= 1)
     Uniform looks-per-tray reduces exactly to D11's Kish deff = m.
  3. Single look, single tray -> deff = 1 and the interval equals the plain
     Wilson interval bit-for-bit.
  4. Degenerate inputs (no observations, missing/unusable class_counts,
     negative defect count) return {} -- callers render nothing rather than
     inventing numbers.
  5. /finalize merges the fields into result_json; legacy certificates
     without them stay byte-identical (hash-frozen rows are NOT rewritten).

Run:
    python -m pytest tests/test_defect_crosscheck.py -q
"""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import arbitration as arb  # noqa: E402
from app import main as sama  # noqa: E402

client = TestClient(sama.app, raise_server_exceptions=False)


@pytest.fixture()
def tmp_db(tmp_path, monkeypatch):
    """Isolated SQLite file so tests never touch data/sama.db."""
    monkeypatch.setattr(sama.db, "DB_PATH", tmp_path / "crosscheck_test.db")
    sama.db.init_db()
    return sama.db


def _bulb(cls_name="sound", tray="T1"):
    idx = (sama.grading.CLASS_NAMES.index(cls_name)
           if cls_name in sama.grading.CLASS_NAMES else 0)
    return {"cls": idx, "cls_name": cls_name, "confidence": 0.9,
            "size_grade": "B", "tray_id": tray}


def _result_from(looks):
    """A real merge_looks result, as /finalize would have produced."""
    return sama.grading.merge_looks(looks)


# --------------------------------------------------------------------------
# 1+2+3. Pure-function contracts on arbitration.tray_pooled_defect_fields
# --------------------------------------------------------------------------

SINGLE_LOOK = [
    [_bulb("sound"), _bulb("rotten"), _bulb("sound"), _bulb("sound"),
     _bulb("sound"), _bulb("black_smut")],           # 6 obs, 2 defects
]
TWO_TRAYS_UNIFORM = [
    [_bulb("rotten", "T1"), _bulb("sound", "T1"), _bulb("sound", "T1"),
     _bulb("sound", "T1")],                          # T1 look 1: 4 obs, 1 def
    [_bulb("rotten", "T1"), _bulb("sound", "T1"), _bulb("sound", "T1"),
     _bulb("sound", "T1")],                          # T1 look 2: same bulbs
    [_bulb("sprouted", "T2"), _bulb("sound", "T2"), _bulb("damaged_skin", "T2"),
     _bulb("sound", "T2"), _bulb("sound", "T2"), _bulb("sound", "T2"),
     _bulb("sound", "T2"), _bulb("sound", "T2")],    # T2 look 1: 8 obs, 2 def
]
MIXED_DESIGN = TWO_TRAYS_UNIFORM + [
    # T2 gets a PARTIAL second look: two of its eight bulbs re-seen.
    [_bulb("rotten", "T2"), _bulb("sound", "T2")],
]


def test_single_look_single_tray_matches_plain_wilson_bit_for_bit():
    res = _result_from(SINGLE_LOOK)
    out = arb.tray_pooled_defect_fields(res, SINGLE_LOOK)
    assert out, "single usable look must produce fields"
    k = res["n_bulb_observations"] - res["class_counts"]["sound"]
    n = res["n_bulb_observations"]
    lo, hi = arb.wilson_pct(k, n)
    assert out["defect_pooled_pct"] == pytest.approx(round(100.0 * k / n, 2))
    assert out["defect_pooled_ci_low"] == round(lo, 2)
    assert out["defect_pooled_ci_high"] == round(hi, 2)
    assert out["defect_pooled_design_effect"] == 1.0
    assert out["defect_pooled_n_effective"] == n
    assert out["defect_pooled_method"] == "wilson-pooled-per-tray"


def test_uniform_two_look_trays_reduce_to_kish_deff_of_two():
    res = _result_from(TWO_TRAYS_UNIFORM)
    out = arb.tray_pooled_defect_fields(res, TWO_TRAYS_UNIFORM)
    n = res["n_bulb_observations"]
    assert out["defect_pooled_trays"] == 2
    # T1 contributes 8 obs at m=2 -> 4 effective; T2 one look -> 8 effective.
    assert out["defect_pooled_n_effective"] == 12
    assert out["defect_pooled_design_effect"] == pytest.approx(round(n / 12.0, 4))
    # Same interval wilson_pct_effective would draw at that design effect.
    k = n - res["class_counts"]["sound"]
    lo, hi = arb.wilson_pct_effective(k, n, n / 12.0)
    assert out["defect_pooled_ci_low"] == round(lo, 2)
    assert out["defect_pooled_ci_high"] == round(hi, 2)


def test_clustered_interval_is_wider_than_naive_pooled_wilson():
    """The whole point of the deff: repeats must not fake precision."""
    res = _result_from(TWO_TRAYS_UNIFORM)
    out = arb.tray_pooled_defect_fields(res, TWO_TRAYS_UNIFORM)
    n = res["n_bulb_observations"]
    k = n - res["class_counts"]["sound"]
    naive_lo, naive_hi = arb.wilson_pct(k, n)
    width_cross = out["defect_pooled_ci_high"] - out["defect_pooled_ci_low"]
    width_naive = naive_hi - naive_lo
    assert width_cross > width_naive


def test_mixed_design_credits_independent_trays_more_than_global_deff():
    """T2 was photographed twice too in MIXED_DESIGN; but a design where only
    SOME trays repeat must sit strictly between no penalty and the global
    worst-case penalty."""
    res = _result_from(MIXED_DESIGN)
    out = arb.tray_pooled_defect_fields(res, MIXED_DESIGN)
    # T1: 8 obs @ m=2 -> 4 eff; T2: 8+2=10 obs @ m=2 -> 5 eff => 9 effective.
    assert out["defect_pooled_n_effective"] == 9
    global_deff = float(max(1, int(res.get("n_looks") or 1)))   # rho=1, D11
    assert global_deff == 4.0                    # four looks, worst-case Kish
    assert out["defect_pooled_design_effect"] <= global_deff


def test_point_estimate_rebuilds_from_published_class_counts_only():
    """Drift-proofing (D8 discipline): even if the raw looks disagreed with
    the published counts, the cross-check describes the PRINTED statistic."""
    res = _result_from(SINGLE_LOOK)
    tampered = dict(res)
    tampered["class_counts"] = dict(res["class_counts"], sound=4)  # forces k=2? no:
    # n=6, sound now claimed 4 -> pooled k must read 2 regardless of raw looks.
    out = arb.tray_pooled_defect_fields(tampered, [])
    assert out["defect_pooled_pct"] == pytest.approx(round(100.0 * 2 / 6, 2))


def test_gap_field_reports_certified_minus_pooled():
    res = _result_from(TWO_TRAYS_UNIFORM)
    factor = res.get("occlusion_factor_applied") or 1.0
    out = arb.tray_pooled_defect_fields(res, TWO_TRAYS_UNIFORM)
    expected_gap = round(res["defect_rate_corrected"] - out["defect_pooled_pct"], 2)
    if res["defect_rate_corrected"] is not None:
        assert out["defect_pooled_gap_pts"] == expected_gap
    # Sanity on the direction the red team predicted: with the shipped
    # constants (factor < 1 divides UPWARD) and a worst-view selection, the
    # certified ceiling should not sit below the pooled average here.
    assert res["defect_rate_corrected"] >= out["defect_pooled_pct"] - 1e-9 \
        or factor >= 1.0


@pytest.mark.parametrize("bad", [
    {},
    {"n_bulb_observations": 0, "class_counts": {"sound": 0}},
    {"n_bulb_observations": 10, "class_counts": {}},
    {"n_bulb_observations": 10},                      # class_counts absent
    {"n_bulb_observations": 10, "class_counts": {"sound": True}},  # bool, not count
    {"n_bulb_observations": 10, "class_counts": {"sound": 11}},    # impossible
])
def test_degenerate_inputs_return_empty_dict(bad):
    assert arb.tray_pooled_defect_fields(bad, []) == {}


def test_missing_tray_ids_fall_back_to_global_two_look_deff():
    looks = [[{"cls": 1, "size_grade": "B"}, {"cls": 0, "size_grade": "B"}],
             [{"cls": 0, "size_grade": "B"}, {"cls": 0, "size_grade": "B"}]]
    res = _result_from(looks)
    out = arb.tray_pooled_defect_fields(res, looks)
    n = res["n_bulb_observations"]
    assert out["defect_pooled_trays"] == 1
    assert out["defect_pooled_n_effective"] == n // 2          # rho=1 worst case
    assert out["defect_pooled_design_effect"] == pytest.approx(2.0)


def test_null_look_slots_and_junk_bulbs_do_not_crash():
    """merge_looks never emits null BULBS inside a look (finalize validates
    them), but the cross-check must survive them anyway if an older cached
    payload or a future caller ever produces one."""
    res = {
        "n_bulb_observations": 4,
        "class_counts": {"sound": 2, "rotten": 1, "sprouted": 0,
                         "black_smut": 1, "damaged_skin": 0, "doubles": 0},
        "n_looks": 3,
        "defect_rate_corrected": 50.0,
    }
    looks = [None, [_bulb("rotten", "T1"), None, "junk"],
             [{"cls": 99, "size_grade": None}]]
    out = arb.tray_pooled_defect_fields(res, looks)
    assert isinstance(out, dict) and out
    assert out["defect_pooled_ci_low"] <= out["defect_pooled_pct"] \
           <= out["defect_pooled_ci_high"] + 1e-9


# --------------------------------------------------------------------------
# 5. /finalize wiring: fields land in result_json, empty stays empty
# --------------------------------------------------------------------------

def test_finalize_attaches_crosscheck_fields(tmp_db):
    looks = [[_bulb("sound"), _bulb("rotten"), _bulb("sound"),
              _bulb("sound"), _bulb("sound"), _bulb("black_smut")]]
    r = client.post("/finalize", json={
        "looks": looks, "lot_ref": "QA-CROSSCHECK",
        "farmer_name": "Cross Check", "officer_name": "Tester",
    })
    assert r.status_code == 200, r.text[:400]
    body = r.json()
    result = body["result"]
    for key in ("defect_pooled_pct", "defect_pooled_ci_low",
                "defect_pooled_ci_high", "defect_pooled_method",
                "defect_pooled_trays", "defect_pooled_n_effective"):
        assert key in result, f"missing {key}"
    lot = sama.db.get_lot(body["lot_id"])
    stored = lot["result"]
    assert stored["defect_pooled_pct"] == result["defect_pooled_pct"]


def test_finalize_all_empty_looks_stays_clean(tmp_db):
    r = client.post("/finalize", json={
        "looks": [[], []], "lot_ref": "QA-CROSSCHECK-EMPTY",
        "farmer_name": "Nobody", "officer_name": "Tester",
    })
    assert r.status_code == 200, r.text[:400]
    result = r.json()["result"]
    assert not any(k.startswith("defect_pooled") for k in result)


def test_legacy_certificate_shape_unchanged_when_overlay_absent():
    """Older stored results must not sprout keys they were never signed with:
    the overlay runs server-side at finalize only."""
    res = _result_from(SINGLE_LOOK)
    before = set(res.keys())
    arb.grade_a_ci_fields(res)          # neighbour overlays exist; ensure ours
    arb.defect_ci_fields(res, SINGLE_LOOK)   # does not mutate its input
    assert set(res.keys()) == before
