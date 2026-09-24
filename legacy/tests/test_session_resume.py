"""LOOP-I2222 regression tests: an unfinished lot survives tab discard.

The untested field condition: a rupees-8k Android phone running Chrome
discards background tabs under memory pressure WITHOUT asking. An officer
who captured three trays, walked to the next shed, and came back used to
find an empty form -- every look re-photographed, ~2 minutes per look of
physical handling repeated for nothing. index.html now checkpoints the
analysis data to localStorage after each successful capture and offers it
back on the next load ("sama_session_v1").

Contracts pinned here (static, because the logic lives in browser JS -- no
npm / build step by project rule):
  1. a checkpoint is saved only AFTER a look is truly captured, never before;
  2. replay mode never checkpoints (offline demo stays deterministic);
  3. a full storage quota degrades to metadata-only (numbers survive,
     photos honestly flagged lost) and storage failure never blocks capture;
  4. finalize clears the checkpoint (a certified lot needs no rescue copy);
  5. restore fills form fields via .value/.textContent, never innerHTML;
  6. every new UI string exists in BOTH English and Hindi.

Run:
    C:/Users/ADMIN/AppData/Local/Programs/Python/Python311/python.exe -m pytest tests/test_session_resume.py -q
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

INDEX_HTML_PATH = (Path(__file__).resolve().parents[1]
                   / "app" / "static" / "index.html")
INDEX_HTML = INDEX_HTML_PATH.read_text(encoding="utf-8")


def _block(source: str, header_pattern: str) -> str:
    """Return the source text of the { ... } block following a header."""
    m = re.search(header_pattern, source)
    assert m, f"block not found: {header_pattern}"
    start = m.end()
    depth = 1
    i = start
    while depth and i < len(source):
        if source[i] == "{":
            depth += 1
        elif source[i] == "}":
            depth -= 1
        i += 1
    return source[start:i]


def _fn_body(name: str) -> str:
    return _block(INDEX_HTML, rf"function {name}\(\) \{{")


def _submit_body() -> str:
    return _block(INDEX_HTML, r"async function submit\(blob\) \{")


def _resume_block() -> str:
    return _block(INDEX_HTML, r"\(function offerResume\(\) \{")


def _i18n_keys(lang: str) -> set[str]:
    body = _block(INDEX_HTML, rf"\b{lang}: \{{")
    return set(re.findall(r"^\s{4}([A-Za-z_][A-Za-z0-9_]*):", body, re.M))


# --------------------------------------------------------------------------
# The checkpoint itself
# --------------------------------------------------------------------------


def test_session_key_is_versioned():
    assert "const SESSION_KEY = 'sama_session_v1'" in INDEX_HTML
    assert "v: 1," in INDEX_HTML


def test_save_happens_after_capture_success():
    # LOOP-A2223 moved the success tail into acceptLook(), shared by the
    # first capture AND the pending-resend button. The invariant is the
    # same and now stronger: the checkpoint runs only after a look is fully
    # recorded (tally marks it), and NO other path can call saveSession()
    # directly -- so an unsent or failed upload can never be resurrected
    # as if it had been analysed.
    accept = _block(INDEX_HTML, r"function acceptLook\(data\) \{")
    assert accept.index("tally();") < accept.index("saveSession();")
    submit_body = _submit_body()
    retry = _block(INDEX_HTML, r"\$\('pendingRetry'\)\.onclick = async \(\) => \{")
    assert "saveSession();" not in submit_body
    assert "saveSession();" not in retry


def test_replay_never_checkpoints():
    assert re.search(r"if \(REPLAY \|\| state\.lotId\) return;", _fn_body("saveSession"))


def test_quota_fallback_keeps_numbers_drops_photos():
    body = _fn_body("saveSession")
    m = re.search(r"catch \(quotaErr\) \{", body)
    assert m, "quota-exceeded branch missing"
    tail = body[m.end():]
    assert "sessionCheckpoint(false)" in tail, \
        "quota fallback must retry without images"
    assert "images_dropped = true" in tail, \
        "the photo loss must be flagged so the UI can say so"


def test_storage_failure_cannot_block_capture():
    # Outer guard: even reading localStorage can throw (private mode).
    body = _fn_body("saveSession")
    assert re.search(r"catch \(e\) \{\s*/\* storage unavailable", body)


def test_finalize_clears_checkpoint():
    finish = _block(INDEX_HTML, r"\$\('finishBtn'\)\.onclick = async \(\) => \{")
    assert "clearSession();" in finish


def test_clear_is_defensive_too():
    assert re.search(r"try \{ localStorage\.removeItem\(SESSION_KEY\); \}"
                     r" catch \(e\) \{\}", _fn_body("clearSession"))


# --------------------------------------------------------------------------
# The restore path
# --------------------------------------------------------------------------


def test_restore_offered_on_boot_and_skipped_in_replay():
    body = _resume_block()
    assert "if (REPLAY) return;" in body
    assert "$('resumeCard').classList.remove('hidden')" in body


def test_restore_uses_safe_dom_only():
    body = _resume_block()
    assert "innerHTML" not in body, (
        "restored localStorage strings must never hit innerHTML")
    assert ".value = saved.lotRef" in body
    assert ".textContent = t('resumeBody')" in body


def test_corrupt_checkpoint_cannot_brick_the_flow():
    body = _resume_block()
    assert re.search(r"catch \(e\) \{[^}]*clearSession\(\);", body, re.S), (
        "restore errors must discard the bad checkpoint and continue")


def test_centre_restored_only_if_still_listed():
    body = _resume_block()
    assert "some(o => o.value === want)" in body, (
        "a centre deleted while we were away must not break restore")


def test_shots_rebuilt_from_looks_for_inspect_and_finalize():
    body = _resume_block()
    # annotated goes back onto each shot; bulbs geometry comes from looks
    assert "annotated: (s && typeof s.annotated === 'string') ? s.annotated : ''" in body
    assert "bulbs: state.looks[i] || []" in body


# --------------------------------------------------------------------------
# Bilingual completeness
# --------------------------------------------------------------------------

RESUME_KEYS = {"resumeTitle", "resumeBody", "resumeBtn", "freshStart",
               "resumeImagesLost", "resumeRestored"}


def test_resume_strings_exist_in_english():
    missing = RESUME_KEYS - _i18n_keys("en")
    assert not missing, f"missing EN keys: {sorted(missing)}"


def test_resume_strings_exist_in_hindi():
    missing = RESUME_KEYS - _i18n_keys("hi")
    assert not missing, f"missing HI keys: {sorted(missing)}"
