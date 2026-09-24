"""LOOP-I2222 -- the certificate's five-second read.

A judge, farmer or trader scanning a paper certificate in the first 90
seconds lands on the headline strip before any table. It must exist, be
filled from the same result_json as every other figure (no second source of
truth), and be written via textContent so no field value can inject markup.
Static contracts on app/static/report.html because the logic lives in
browser JS (no npm / build step by project rule).

Run:
    C:/Users/ADMIN/AppData/Local/Programs/Python/Python311/python.exe -m pytest tests/test_certificate_headline.py -q
"""

from __future__ import annotations

import re
from pathlib import Path

REPORT_HTML = (Path(__file__).resolve().parents[1]
               / "app" / "static" / "report.html").read_text(encoding="utf-8")


def test_strip_exists_above_the_numbers():
    m = re.search(r'id="headlineStrip"', REPORT_HTML)
    assert m, "headline strip div missing"
    # It must sit BEFORE the big-number grid: first thing the eye finds.
    assert m.start() < REPORT_HTML.index('id="gradeA"')


def test_filled_via_textcontent_not_innerhtml():
    assert "$('headlineText').textContent =" in REPORT_HTML


def test_sentence_carries_the_four_load_bearing_facts():
    m = re.search(r"\$\('headlineText'\)\.textContent =(.*?);", REPORT_HTML, re.S)
    assert m, "headline assignment not found"
    js = m.group(1)
    for token in ("Grade A", "95% CI", "visible surface defects",
                  "bulb-observations", "look"):
        assert token in js, f"headline omits {token!r}"


def test_all_interpolations_guarded():
    m = re.search(r"\$\('headlineText'\)\.textContent =(.*?);", REPORT_HTML, re.S)
    js = m.group(1)
    # Every res.* read uses the ?? fallback; LOT.lot_ref and created_at are
    # guarded too, so a legacy/partial record degrades to dashes, not a
    # half-rendered certificate.
    assert js.count("??") >= 5
    assert "LOT.created_at ?" in js
