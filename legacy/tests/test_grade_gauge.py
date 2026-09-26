"""LOOP-W2224 -- the Grade-A gauge with its Wilson CI whiskers.

The one number this product exists to produce must be glanceable AND honest.
The gauge is drawn only from the stored Wilson interval on each surface that
shows it: the live result screen (index.html #s3, right after grading) and
the certificate everyone else reads (report.html -- projector, print, QR).

Static contracts on the HTML because the logic lives in browser JS (no npm /
build step by project rule). What is pinned here:

- the strip exists on BOTH result surfaces, inside the sheet that prints;
- it reads ONLY res.grade_a_ci_low / res.grade_a_ci_high / grade_a_pct --
  no default interval, no invented endpoints anywhere in the drawing code;
- an absent or impossible interval HIDES the strip instead of guessing;
- values enter through setAttribute/textContent only, never innerHTML;
- numbers render in Indian digit grouping with a plain-toFixed fallback;
- bilingual labels ship on the printed certificate and via the app toggle.

Run:
    C:/Users/ADMIN/AppData/Local/Programs/Python/Python311/python.exe -m pytest tests/test_grade_gauge.py -q
"""

from __future__ import annotations

import re
from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / "app" / "static"
REPORT_HTML = (STATIC / "report.html").read_text(encoding="utf-8")
INDEX_HTML = (STATIC / "index.html").read_text(encoding="utf-8")

GAUGE_MARK = '<script id="sama-gauge-js">'


def _gauge_js(source: str) -> str:
    """Source of the shared gauge script block."""
    start = source.index(GAUGE_MARK) + len(GAUGE_MARK)
    end = source.index("</script>", start)
    return source[start:end]


def _i18n_block(lang: str) -> str:
    m = re.search(rf"\b{lang}: \{{", INDEX_HTML)
    assert m, f"{lang} i18n dict missing"
    depth, i = 1, m.end()
    while depth and i < len(INDEX_HTML):
        if INDEX_HTML[i] == "{":
            depth += 1
        elif INDEX_HTML[i] == "}":
            depth -= 1
        i += 1
    return INDEX_HTML[m.end():i]


# ---- presence and placement -------------------------------------------------


def test_gauge_on_certificate():
    assert 'id="ggSvg"' in REPORT_HTML


def test_gauge_inside_the_printed_sheet():
    """It must live before the no-print footer, or A4 print loses the
    picture and keeps only the buttons nobody prints."""
    assert REPORT_HTML.index('id="ggWrap"') < REPORT_HTML.index('class="no-print')


def test_gauge_sits_with_the_headline_number():
    """Same card as the big number -- one glance, not a hunt."""
    card = REPORT_HTML.index("Grade A proportion")
    assert card < REPORT_HTML.index('id="gradeA"') < REPORT_HTML.index('id="ggWrap"')
    assert REPORT_HTML.index('id="ggWrap"') < REPORT_HTML.index('id="sampleLine"')


def test_gauge_on_live_result_screen():
    """The phone that graded the lot shows the same picture immediately."""
    s3 = INDEX_HTML.index('<section id="s3"')
    assert INDEX_HTML.index('id="ggSvg"', s3) < INDEX_HTML.index('id="suffCard"', s3)


def test_svg_scales_to_any_phone_width():
    for src in (REPORT_HTML, INDEX_HTML):
        assert re.search(r'<svg id="ggSvg"[^>]*viewBox="0 0 1000 104"', src), \
            "gauge svg lost its responsive viewBox"


# ---- honesty: the whisker is only ever the stored Wilson interval -----------


def test_whisker_reads_only_real_ci_fields():
    """The draw call must pass the stored interval fields -- the gauge has
    no other legitimate source for its endpoints."""
    for src in (REPORT_HTML, INDEX_HTML):
        m = re.search(r"samaGauge\('ggSvg'[^)]*\)", src)
        assert m, "gauge draw call missing"
        call = m.group(0)
        assert "grade_a_pct" in call
        assert "grade_a_ci_low" in call
        assert "grade_a_ci_high" in call


def test_no_invented_interval_anywhere_in_the_drawing_code():
    """If these literals appear as fallbacks, the gauge could draw an
    interval nobody measured. That is the exact failure a signed
    certificate may never have."""
    for src in (REPORT_HTML, INDEX_HTML):
        js = _gauge_js(src)
        for bad in ("?? 50", "?? 100", "|| 50", "|| 100", "[0, 100]", "= 50;"):
            assert bad not in js, f"gauge contains invented-interval fallback {bad!r}"


def test_impossible_interval_hides_the_strip():
    """NaN / inverted / out-of-range inputs must hide the whisker row --
    degrade to the plain number, never draw a guess."""
    for src in (REPORT_HTML, INDEX_HTML):
        js = _gauge_js(src)
        assert "Number.isFinite" in js
        assert "wrap.hidden = true" in js


# ---- safety and formatting ---------------------------------------------------


def test_gauge_never_uses_innerhtml():
    """Certificate fields reach the gauge; markup must not be able to."""
    for src in (REPORT_HTML, INDEX_HTML):
        assert ".innerHTML" not in _gauge_js(src)


def test_indian_number_format_with_fallback():
    for src in (REPORT_HTML, INDEX_HTML):
        js = _gauge_js(src)
        assert "'en-IN'" in js
        assert "toFixed" in js, "missing non-Intl fallback"


def test_counts_also_render_indian_format():
    """Bulb-observation counts use the same locale grouping."""
    assert "fmtIN(res.n_bulb_observations ?? 0, 0)" in REPORT_HTML
    assert "fmtIN(res.n_bulb_observations, 0)" in INDEX_HTML


def test_bilingual_labels_on_certificate_and_app():
    assert "ग्रेड A हिस्सा" in REPORT_HTML          # printed subtitle
    assert "विश्वास अंतराल" in REPORT_HTML          # printed CI caption
    assert "ciLabel:" in _i18n_block("en")
    assert "ciLabel:" in _i18n_block("hi")
