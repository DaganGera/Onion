"""India-access pass A2212 regression tests: photos are shrunk BEFORE upload.

The single most expensive step of a grading lot on a rupees-8k phone on rural
3G used to be the raw camera upload: 3-8 MB per frame at stock JPEG quality,
40-120 s per look on ~0.5 Mbps uplink. index.html now re-encodes every live
capture client-side (canvas long edge <= 1600 px, JPEG q80) BEFORE POSTing to
/analyze, and shows both KB numbers honestly in the UI -- including the
"sent as-is" case when compression saved nothing.

The model letterboxes to 1024 px internally either way, so this loses nothing
that matters for detection while cutting upload time ~10-20x. These tests are
static contracts on app/static/index.html because the logic lives in browser
JS (no npm, no build step by project rule); they pin the constants, the
wiring order, the honesty guard, and Hindi/English completeness so the
optimisation cannot silently regress or go monolingual.

Run:
    C:/Users/ADMIN/AppData/Local/Programs/Python/Python311/python.exe -m pytest tests/test_upload_downscale.py -q
"""

import re
import sys
from pathlib import Path

import pytest

INDEX_HTML = (Path(__file__).resolve().parents[1]
              / "app" / "static" / "index.html").read_text(encoding="utf-8")


def _i18n_block(lang: str) -> str:
    """Return the source text of I18N.<lang> = { ... }."""
    m = re.search(rf"\b{lang}: \{{", INDEX_HTML)
    assert m, f"I18N.{lang} block not found"
    start = m.end()
    depth = 1
    i = start
    while depth and i < len(INDEX_HTML):
        if INDEX_HTML[i] == "{":
            depth += 1
        elif INDEX_HTML[i] == "}":
            depth -= 1
        i += 1
    return INDEX_HTML[start:i]


def _submit_body() -> str:
    """Return the source text of async function submit(blob) { ... }."""
    m = re.search(r"async function submit\(blob\) \{", INDEX_HTML)
    assert m, "submit() not found"
    start = m.end()
    depth = 1
    i = start
    while depth and i < len(INDEX_HTML):
        if INDEX_HTML[i] == "{":
            depth += 1
        elif INDEX_HTML[i] == "}":
            depth -= 1
        i += 1
    return INDEX_HTML[start:i]


# --------------------------------------------------------------------------
# Constants: the resize budget itself
# --------------------------------------------------------------------------


def test_upload_max_edge_is_1600():
    m = re.search(r"UPLOAD_MAX_EDGE\s*=\s*(\d+)", INDEX_HTML)
    assert m, "UPLOAD_MAX_EDGE constant missing"
    assert int(m.group(1)) == 1600


def test_upload_jpeg_quality_is_080():
    m = re.search(r"UPLOAD_JPEG_QUALITY\s*=\s*([\d.]+)", INDEX_HTML)
    assert m, "UPLOAD_JPEG_QUALITY constant missing"
    assert abs(float(m.group(1)) - 0.80) < 1e-9
    # ...and actually passed to the encoder, not just declared.
    assert re.search(
        r"toBlob\([^)]*'image/jpeg',\s*UPLOAD_JPEG_QUALITY\)", INDEX_HTML)


# --------------------------------------------------------------------------
# Wiring: shrink happens inside submit(), before the FormData leaves
# --------------------------------------------------------------------------


def test_submit_downscales_before_formdata_append():
    body = _submit_body()
    prep = re.search(r"await downscaleForUpload\(blob\)", body)
    append = re.search(r"fd\.append\('file',\s*blob,\s*'tray\.jpg'\)", body)
    assert prep, "submit() never calls downscaleForUpload(blob)"
    assert append, "FormData file append missing"
    # The prepared blob must be assigned back before the append that sends it.
    assign = re.search(r"blob\s*=\s*prep\.blob", body)
    assert assign, "downscaled blob never replaces the original"
    assert prep.start() < assign.start() < append.start(), (
        "downscale must run BEFORE the upload payload is built")


def test_downscale_sends_whichever_blob_is_smaller_honest_guard():
    # If canvas re-encode came out bigger than the original (tiny or already
    # well-compressed photo), the original must ship instead -- no fake
    # savings shown to the operator.
    assert re.search(r"out\.size\s*<\s*blob\.size", INDEX_HTML), (
        "honesty guard (keep original when re-encode is larger) missing")
    assert "resized: false" in INDEX_HTML, "as-is result path missing"


def test_replay_branch_never_touches_the_canvas_pipeline():
    # ?replay=1 is the zero-network judge demo; its cached payloads must not
    # be routed through any decode/resize machinery.
    body = _submit_body()
    m = re.search(r"if \(REPLAY\) \{.*?\} else \{", body, flags=re.S)
    assert m, "replay/live branching not found in submit()"
    assert "downscale" not in m.group(0), (
        "replay branch must stay free of the downscale pipeline")


# --------------------------------------------------------------------------
# Honest UI: per-look line, session total, language-switch survival
# --------------------------------------------------------------------------


def test_dataline_element_exists_in_capture_screen():
    assert 'id="dataLine"' in INDEX_HTML


def test_renderdataline_called_from_applylang():
    apply_lang = re.search(
        r"function applyLang\(\) \{.*?\n\}", INDEX_HTML, flags=re.S)
    assert apply_lang, "applyLang() not found"
    assert "renderDataLine()" in apply_lang.group(0), (
        "data line must survive a Hindi/English switch")


def test_session_ledger_accumulates_real_savings_only():
    # savedKB may only grow when the resized blob actually went out smaller;
    # otherwise the session total would advertise savings that never happened.
    m = re.search(
        r"if \(prep\.resized && prep\.sentKB < prep\.origKB\) \{\s*"
        r"state\.savedKB \+= prep\.origKB - prep\.sentKB;", INDEX_HTML)
    assert m, "session ledger must add only verified savings"


def test_per_look_kb_note_on_results_screen():
    assert "uploadLog[i]" in INDEX_HTML, (
        "results screen should show each look's actual upload size")


# --------------------------------------------------------------------------
# Bilingual completeness: every new string exists in BOTH languages
# --------------------------------------------------------------------------


@pytest.mark.parametrize("key", ["photoOptimised", "photoAsIs", "sessionSaved"])
def test_new_strings_present_in_en(key):
    assert key in _i18n_block("en"), f"I18N.en.{key} missing"


@pytest.mark.parametrize("key", ["photoOptimised", "photoAsIs", "sessionSaved"])
def test_new_strings_present_in_hi(key):
    assert key in _i18n_block("hi"), f"I18N.hi.{key} missing"
