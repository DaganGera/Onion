"""LOOP-A2223 regression tests: every request has a deadline + one retry.

On rural 3G any of the app's requests could stall forever: no AbortController
deadline existed anywhere, so one wedged request hung the busy overlay until
the operator killed the page and lost the capture flow. index.html now routes
ALL traffic through saFetch() -- 15 s deadline for JSON endpoints, 60 s for
photo/finalize uploads -- retries exactly ONCE and only when the server never
answered (a real HTTP answer is never blindly repeated), and throws a typed
NetError so callers can print WHY in Hindi or English.

When even that fails on /analyze, the compressed photo and its exact prepared
FormData stay on the phone behind an explicit Retry/Discard bar: the officer
never re-photographs a perfectly good tray because of a network hiccup.

The static-contract style matches tests/test_upload_downscale.py because the
logic lives in browser JS (no npm, no build step by project rule).

Run:
    C:/Users/ADMIN/AppData/Local/Programs/Python/Python311/python.exe -m pytest tests/test_network_resilience.py -q
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
INDEX_HTML = (ROOT / "app" / "static" / "index.html").read_text(encoding="utf-8")
MAIN_PY = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
DB_PY = (ROOT / "app" / "db.py").read_text(encoding="utf-8")


def _block(header_pattern: str) -> str:
    """Return the source text of the { ... } block following a regex match."""
    m = re.search(header_pattern, INDEX_HTML)
    assert m, f"block not found: {header_pattern}"
    depth = 1
    i = m.end()
    while depth and i < len(INDEX_HTML):
        if INDEX_HTML[i] == "{":
            depth += 1
        elif INDEX_HTML[i] == "}":
            depth -= 1
        i += 1
    return INDEX_HTML[m.end():i]


def _i18n_block(lang: str) -> str:
    return _block(rf"\b{lang}: \{{")


# --------------------------------------------------------------------------
# The wrapper itself: deadline, exactly-one retry, typed error
# --------------------------------------------------------------------------


def test_deadline_constants_exist_and_ordered():
    net = re.search(r"NET_TIMEOUT_MS\s*=\s*(\d+)", INDEX_HTML)
    up = re.search(r"ANALYZE_TIMEOUT_MS\s*=\s*(\d+)", INDEX_HTML)
    back = re.search(r"RETRY_BACKOFF_MS\s*=\s*(\d+)", INDEX_HTML)
    assert net and up and back, "timeout constants missing"
    assert int(net.group(1)) == 15000, "JSON endpoints get 15 s"
    assert int(up.group(1)) == 60000, "photo/finalize uploads get 60 s"
    assert 0 < int(back.group(1)) <= 5000, "backoff must be short but real"


def test_abortcontroller_deadline_is_actually_wired():
    body = _block(r"async function saFetch\(")
    assert "new AbortController()" in body
    assert re.search(
        r"setTimeout\(\(\) => ctl\.abort\(\),\s*timeoutMs\)", body), (
        "the deadline must abort the real request, not just be declared")
    assert "clearTimeout(timer)" in body, "timer must not leak past completion"
    # Graceful degradation: ancient engines lose only the deadline.
    assert "typeof AbortController === 'undefined'" in body


def test_retries_exactly_once_and_only_for_silent_failures():
    body = _block(r"async function saFetch\(")
    assert body.count("return await once();") == 2, "retry-once means once"
    first = body.index("return await once();")
    second = body.rindex("return await once();")
    assert "RETRY_BACKOFF_MS" in body[first:second], (
        "second attempt must wait out a backoff")
    # Both attempts sit inside try/catch: a retry fires only for exceptions
    # (server never answered), never after a real HTTP response.
    assert "catch (first)" in body and "catch (second)" in body


def test_typed_error_distinguishes_timeout_from_unreachable():
    body = _block(r"async function saFetch\(")
    assert re.search(
        r"second\.name === 'AbortError' \? 'timeout' : 'unreachable'", body), (
        "our own deadline must be reported as a timeout, not bad luck")
    assert "class NetError extends Error" in INDEX_HTML
    assert "this.netKind = kind" in INDEX_HTML


def test_wrapper_sits_above_the_first_immediate_request():
    # saFetch's default parameter reads NET_TIMEOUT_MS at CALL time, and
    # /api/centres fires during initial script evaluation. A const declared
    # below that call would TDZ-throw and kill the whole script (the exact
    # accident class LOOP-F2217 documented at the top of index.html).
    wrapper_pos = INDEX_HTML.index("const NET_TIMEOUT_MS")
    centres_pos = INDEX_HTML.index("saFetch('/api/centres')")
    assert wrapper_pos < centres_pos, (
        "saFetch constants must precede the immediately-invoked centres call")


# --------------------------------------------------------------------------
# Routing: nothing bypasses the wrapper
# --------------------------------------------------------------------------

ALL_ENDPOINTS = [
    "'/api/centres'",
    "'/api/replay/'",
    "'/analyze'",
    "'/finalize'",
    "`/api/sufficiency/${lotId}`",
    "`/api/price-band/${lotId}`",
    "'/dispute/'",
]


@pytest.mark.parametrize("endpoint", ALL_ENDPOINTS)
def test_every_endpoint_routed_through_sa_fetch(endpoint):
    assert f"saFetch({endpoint}" in INDEX_HTML, (
        f"{endpoint} bypasses saFetch -- it would have no deadline, no retry")


def test_no_bare_fetch_call_survives_anywhere_else():
    wrapper = _block(r"async function saFetch\(")
    rest = INDEX_HTML.replace(wrapper, "")
    stray = re.findall(r"\bfetch\(", rest)   # lowercase only; saFetch has no match
    assert not stray, (
        f"{len(stray)} request(s) bypass saFetch -- find them and wrap them")


def test_finalize_gets_the_upload_deadline_too():
    # Its payload carries per-look base64 thumbnails (~1 MB): at rural-3G
    # uplink speeds the default 15 s JSON deadline would abort a healthy,
    # merely slow upload -- twice.
    start = INDEX_HTML.index("saFetch('/finalize'")
    end = INDEX_HTML.index("await r.json()", start)
    assert "ANALYZE_TIMEOUT_MS" in INDEX_HTML[start:end]


# --------------------------------------------------------------------------
# Retry safety is guaranteed server-side, not just hoped for client-side
# --------------------------------------------------------------------------


def test_analyze_retry_cannot_double_write():
    # /analyze returns detections only; bulb rows are written by /finalize.
    start = MAIN_PY.index('@app.post("/analyze")')
    nxt = MAIN_PY.index("@app.", start + 10)
    analyze_src = MAIN_PY[start:nxt]
    assert "insert_lot" not in analyze_src
    assert "INSERT INTO" not in analyze_src


def test_finalize_retry_is_server_deduped():
    assert "dedupe=True" in MAIN_PY, (
        "/finalize must dedupe so a timeout-retry cannot mint two certificates")


def test_dispute_retry_is_a_boolean_update():
    assert "UPDATE bulbs SET disputed = 1" in DB_PY, (
        "/dispute must stay idempotent under automatic retries")


# --------------------------------------------------------------------------
# Save-and-retry: failed uploads wait on the phone with a one-tap resend
# --------------------------------------------------------------------------


def test_postanalyze_shared_by_capture_and_retry_button():
    post = _block(r"async function postAnalyze\(fd\) \{")
    assert "saFetch('/analyze'" in post and "ANALYZE_TIMEOUT_MS" in post
    assert "if (data.error) throw new Error(data.error)" in post, (
        "a real HTTP error stays final and readable even inside the wrapper")
    submit_body = _block(r"async function submit\(blob\) \{")
    assert "postAnalyze(fd)" in submit_body
    retry = _block(r"\$\('pendingRetry'\)\.onclick = async \(\) => \{")
    assert "postAnalyze(p.fd)" in retry, (
        "resend must reuse the EXACT prepared request, byte-for-byte")


def test_one_success_path_for_both_capture_and_resend():
    submit_body = _block(r"async function submit\(blob\) \{")
    retry = _block(r"\$\('pendingRetry'\)\.onclick = async \(\) => \{")
    assert "acceptLook(data);" in submit_body
    assert "acceptLook(data);" in retry
    accept = _block(r"function acceptLook\(data\) \{")
    for must_live_there in ("state.looks.push", "busy(false)", "saveSession();"):
        assert must_live_there in accept
    # Drift guard: recording and checkpointing exist in exactly ONE place.
    # (busy(false) may appear twice in submit -- success goes through
    # acceptLook, but the FAILURE path must clear its own overlay too.)
    assert "state.looks.push" not in submit_body
    assert "saveSession();" not in submit_body


def test_failed_capture_keeps_exact_request_and_reports_why():
    submit_body = _block(r"async function submit\(blob\) \{")
    m = re.search(
        r"state\.pending = \{ fd, origKB: prep\.origKB, sentKB: prep\.sentKB,"
        r"\s*kind: netKey\(e\) \};", submit_body)
    assert m, "failed upload must be kept together with its KB ledger"


def test_pending_bar_ui_elements_and_touch_targets():
    assert 'id="pendingBar"' in INDEX_HTML
    for btn in ("pendingRetry", "pendingDiscard"):
        m = re.search(rf'id="{btn}"[^>]*class="([^"]*)"', INDEX_HTML)
        assert m, f"{btn} button missing"
        assert "min-h-[48px]" in m.group(1), (
            f"{btn} must meet the >=48 px touch-target rule")


def test_discard_clears_and_says_so():
    discard = _block(r"\$\('pendingDiscard'\)\.onclick = \(\) => \{")
    assert "state.pending = null" in discard
    assert "t('pendingDiscarded')" in discard


def test_success_supersedes_any_stale_pending_upload():
    submit_body = _block(r"async function submit\(blob\) \{")
    tail = submit_body.split("acceptLook(data);")[1]
    assert "state.pending = null;" in tail and "hidePending();" in tail


# --------------------------------------------------------------------------
# Bilingual completeness + language-switch survival
# --------------------------------------------------------------------------


@pytest.mark.parametrize("key", ["netFailTitle", "netTimeout", "netUnreachable",
                                 "pendingSaved", "retryUpload", "discardShot",
                                 "pendingDiscarded"])
def test_new_strings_present_in_en(key):
    assert key in _i18n_block("en"), f"I18N.en.{key} missing"


@pytest.mark.parametrize("key", ["netFailTitle", "netTimeout", "netUnreachable",
                                 "pendingSaved", "retryUpload", "discardShot",
                                 "pendingDiscarded"])
def test_new_strings_present_in_hi(key):
    assert key in _i18n_block("hi"), f"I18N.hi.{key} missing"


def test_pending_bar_survives_language_switch():
    apply_lang = _block(r"function applyLang\(\) \{")
    assert "renderPending()" in apply_lang, (
        "the save-and-retry bar must re-render when the officer switches "
        "between Hindi and English")


# --------------------------------------------------------------------------
# Neighbouring guarantees that must survive this pass untouched
# --------------------------------------------------------------------------


def test_replay_failures_keep_the_honest_banner_path():
    # Replay mode never produces a pending upload (prep stays null); its
    # failures keep the original fault+way-forward banner wording.
    submit_body = _block(r"async function submit\(blob\) \{")
    assert "captureFailHint" in submit_body


def test_manual_finalize_fallback_wording_intact():
    assert "finaliseFailHint" in INDEX_HTML
