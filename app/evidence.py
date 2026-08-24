"""Persisted photographic evidence for certificates (RT-001 T-7).

THE PROBLEM
-----------
/analyze returns an annotated JPEG for every look, but only into client
memory. Nothing persisted it, so report.html's evidence section (#shots)
stayed empty forever: the printed certificate carried numbers with no
photographs, which is weak for an arbitration document.

THE CONTRACT
------------
The capture page sends one shot entry per look at finalize time:

    {"annotated": "data:image/jpeg;base64,...", "tray_id": "T1"}

save_lot_evidence() decodes each JPEG, writes it under
data/evidence/lot_<id>/look_<i>.jpg and returns a manifest row per stored
file: {look_index, path, sha256, bytes}. The manifest goes into
lots.evidence_json; the report route turns it back into displayable data
URIs.

WHAT THIS IS NOT
----------------
Thumbnails sit OUTSIDE the hash chain, exactly like result_json and the
bulbs rows. They are supporting evidence for humans, not signed fields -- a
person with write access could swap the image file without detection. Say
so plainly if asked; the certificate's own evidence note does.

FAILURE POSTURE
---------------
Evidence must never be load-bearing for the certificate itself:
    * a malformed/oversized/garbage shot is skipped and counted;
    * a disk failure while saving degrades to a note on a SUCCESSFUL
      certificate (finalize still returns 200);
    * a missing/unreadable file at render time drops out of the gallery;
      the rest of the page is untouched.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_DIR = ROOT / "data" / "evidence"

DATA_URI_PREFIX = "data:image/jpeg;base64,"

# A tray look annotated at <=1280 px wide / q82 lands around 100-250 KB.
# 512 KB decoded accepts any honest capture with head room and still caps
# a hostile payload well below anything that could hurt the disk.
MAX_SHOT_BYTES = 512 * 1024
# Twelve looks covers every real session many times over; the cap exists so
# a crafted finalize body cannot write unbounded files.
MAX_SHOTS_PER_LOT = 12


def extract_shots(raw_shots) -> tuple[list[dict], int]:
    """Validate client-supplied shot entries.

    Returns (valid_shots, n_skipped). Each valid shot is
    {look_index: int, tray_id: str, jpeg: bytes}. Anything malformed --
    wrong type, wrong prefix, bad base64, over the size cap -- is skipped,
    not fatal: photographs may not block a certificate from existing.
    """
    if not isinstance(raw_shots, list):
        return [], 0
    valid: list[dict] = []
    skipped = 0
    for position, entry in enumerate(raw_shots[: MAX_SHOTS_PER_LOT]):
        try:
            if not isinstance(entry, dict):
                raise ValueError("not an object")
            uri = entry.get("annotated")
            if not isinstance(uri, str) or not uri.startswith(DATA_URI_PREFIX):
                raise ValueError("not an annotated jpeg")
            b64 = uri[len(DATA_URI_PREFIX):]
            jpeg = base64.b64decode(b64, validate=True)
            if not jpeg:
                raise ValueError("empty image")
            if len(jpeg) > MAX_SHOT_BYTES:
                raise ValueError("oversized")
        except (ValueError, binascii.Error, TypeError):
            skipped += 1
            continue
        valid.append({
            "look_index": position,
            "tray_id": str(entry.get("tray_id") or ""),
            "jpeg": jpeg,
        })
    return valid, skipped


def save_lot_evidence(lot_id: int, shots: list[dict]) -> list[dict]:
    """Write one JPEG per look and return the manifest rows.

    Directory layout: EVIDENCE_DIR / lot_<id> / look_<i>.jpg. Deterministic
    names make a deduped retry overwrite identical content rather than pile
    up copies. Per-file failures skip that look; a directory-level failure
    raises so the caller can degrade loudly.
    """
    lot_dir = EVIDENCE_DIR / f"lot_{int(lot_id)}"
    try:
        lot_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        raise
    manifest: list[dict] = []
    for shot in shots:
        name = f"look_{shot['look_index']}.jpg"
        target = lot_dir / name
        try:
            target.write_bytes(shot["jpeg"])
        except OSError as exc:
            print(f"WARNING: evidence write failed for lot {lot_id} "
                  f"{name} -- {type(exc).__name__}: {exc}")
            continue
        manifest.append({
            "look_index": shot["look_index"],
            "tray_id": shot["tray_id"],
            # Relative, portable across machines (Windows <-> Linux).
            "path": f"lot_{int(lot_id)}/{name}",
            "sha256": hashlib.sha256(shot["jpeg"]).hexdigest(),
            "bytes": len(shot["jpeg"]),
        })
    return manifest


def parse_manifest(raw) -> list[dict]:
    """evidence_json -> manifest list, tolerating NULL/corrupt cells."""
    import json
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except (ValueError, TypeError):
        return []
    if not isinstance(parsed, list):
        return []
    return [row for row in parsed if isinstance(row, dict)]


def page_views(manifest: list[dict], *, total_cap_bytes: int = 8 * 1024 * 1024) -> list[dict]:
    """Manifest -> render-ready views with fresh data URIs.

    Reads each stored file back at page build time so the certificate shows
    what is actually on this machine's disk right now. A missing or
    unreadable file silently drops out of the gallery -- an old certificate
    whose images were archived renders fine with zero photos.
    """
    views: list[dict] = []
    budget = total_cap_bytes
    for row in sorted(manifest, key=lambda r: r.get("look_index", 0)):
        if budget <= 0:
            break
        rel = row.get("path")
        if not isinstance(rel, str) or not rel:
            continue
        path = EVIDENCE_DIR / rel
        # Defence in depth: a tampered manifest row must not escape the
        # evidence directory.
        try:
            resolved = path.resolve()
            resolved.relative_to(EVIDENCE_DIR.resolve())
        except (ValueError, OSError):
            continue
        try:
            jpeg = path.read_bytes()
        except OSError:
            continue
        if not jpeg or len(jpeg) > budget:
            continue
        budget -= len(jpeg)
        views.append({
            "look_index": row.get("look_index"),
            "tray_id": row.get("tray_id") or "",
            "sha256": row.get("sha256") or "",
            "bytes": len(jpeg),
            "data_uri": DATA_URI_PREFIX + base64.b64encode(jpeg).decode("ascii"),
        })
    return views
