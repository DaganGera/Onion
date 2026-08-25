"""LOOP-I858 -- static contracts for the three UI surfaces touched.

1. report.html renders the per-tray pooled defect cross-check ONLY when
   result_json carries it (legacy hash-frozen certificates stay unchanged),
   and fills it via textContent.
2. index.html carries the bilingual pooledCrosscheck strings and the same
   presence guard on the officer's result screen.
3. verify.html carries the one-sentence story line, filled via textContent
   from the injected verification payload (judge touchpoint: a QR scan
   should tell the whole story in five seconds).

Static checks because this UI is plain HTML + vanilla JS by project rule
(no build step, no npm). The JS itself is syntax-checked separately with
node --check; these tests pin the CONTRACTS that must survive refactors.

Run:
    C:/Users/ADMIN/AppData/Local/Programs/Python/Python311/python.exe -m pytest tests/test_i858_ui_contracts.py -q
"""

from __future__ import annotations

import re
from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / "app" / "static"
REPORT_HTML = (STATIC / "report.html").read_text(encoding="utf-8")
INDEX_HTML = (STATIC / "index.html").read_text(encoding="utf-8")
VERIFY_HTML = (STATIC / "verify.html").read_text(encoding="utf-8")


# --------------------------------------------------------------------------
# report.html -- pooled cross-check on the certificate
# --------------------------------------------------------------------------

def test_report_has_pooled_container():
    assert 'id="defectPooled"' in REPORT_HTML


def test_report_render_is_gated_on_field_presence():
    m = re.search(r"const pooled = \$\('defectPooled'\);(.*?)pooled\.", REPORT_HTML, re.S)
    assert m, "guarded pooled block not found"
    assert "res.defect_pooled_pct != null" in m.group(1)


def test_report_fills_via_textcontent():
    assert "$('defectPooled');" in REPORT_HTML
    assert "pooled.textContent = line;" in REPORT_HTML


def test_report_states_the_conservative_direction():
    # The gap sentence must say WHICH WAY the estimator errs and why,
    # otherwise a hostile reader supplies their own explanation.
    assert "errs high on purpose" in REPORT_HTML


# --------------------------------------------------------------------------
# index.html -- officer's result screen, bilingual
# --------------------------------------------------------------------------

def test_index_has_bilingual_pooled_strings():
    for lang_anchor in ("en: {", "hi: {"):
        start = INDEX_HTML.index(lang_anchor)
        block = INDEX_HTML[start:INDEX_HTML.index("},", start)]
        assert "pooledCrosscheck:" in block, f"{lang_anchor} missing pooled string"


def test_index_renders_only_when_fields_exist():
    assert "res.defect_pooled_pct != null" in INDEX_HTML


def test_index_pooled_line_names_trays_and_distinct_bulbs():
    m = re.search(r"pooledCrosscheck: \(pct, trays, nEff\) =>", INDEX_HTML)
    assert m, "pooledCrosscheck signature changed"
    en = INDEX_HTML[m.start():INDEX_HTML.index("},", m.start())]
    assert "tray(s)" in en or "${trays}" in en
    assert "distinct bulbs" in en


# --------------------------------------------------------------------------
# verify.html -- the five-second story for anyone who scans the QR
# --------------------------------------------------------------------------

def test_verify_story_line_exists_and_uses_textcontent():
    assert 'id="storyLine"' in VERIFY_HTML
    assert "$('storyLine').textContent =" in VERIFY_HTML


def test_verify_story_carries_the_load_bearing_facts():
    m = re.search(r"\$\('storyLine'\)\.textContent =(.*?);", VERIFY_HTML, re.S)
    js = m.group(1)
    for token in ("Grade A", "95% confidence", "visible defects",
                  "bulb-observations", "look"):
        assert token in js, f"story line omits {token!r}"


def test_verify_story_reads_injected_payload_only():
    m = re.search(r"\$\('storyLine'\)\.textContent =(.*?);", VERIFY_HTML, re.S)
    js = m.group(1)
    assert "lot." in js
    assert "document.cookie" not in js and "localStorage" not in js
