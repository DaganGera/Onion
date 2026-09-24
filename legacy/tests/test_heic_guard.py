"""Loop I858 edge-case hunt: iPhone/HEIC uploads get an actionable refusal.

THE FIELD CONDITION NOBODY TESTED
---------------------------------
iPhones default to HEVC/HEIC ("High Efficiency") stills; some Androids ship
HEIF too. OpenCV has no HEIF decoder, so cv2.imdecode returns None and
/analyze answered "Could not read that image. Try again." -- advice that can
NEVER work, because every retake saves the same format. An officer with a
perfectly good tray photo hits a dead end mid-dispute.

Contract under test:

  1. Pure sniffer: ISO-BMFF files whose ftyp box carries a HEIF/HEIC/AVIF
     brand are named; JPEG/PNG/short garbage return None.
  2. /analyze refuses such uploads BEFORE decoding with a 400-class JSON
     error that names the format AND the fix (camera setting / export as
     JPEG), and explicitly warns that retrying the same file cannot work.
  3. A normal JPEG is NOT intercepted by the guard (it proceeds to the
     ordinary decode path).

Run:
    python -m pytest tests/test_heic_guard.py -q
"""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import main as sama  # noqa: E402

client = TestClient(sama.app, raise_server_exceptions=False)


def _ftyp(major: bytes, compat: list[bytes]) -> bytes:
    """A minimal-but-honest ISO-BMFF header like a real phone emits."""
    brands = b"".join(compat)
    size = 16 + len(brands)
    return (size.to_bytes(4, "big") + b"ftyp" + major
            + (0).to_bytes(2, "big") + b"mif1herp"[:2] + brands)


HEIC = _ftyp(b"heic", [b"mif1", b"heic"])
MIF1 = _ftyp(b"mif1", [b"heic"])          # iPhones often declare mif1 major
AVIF = _ftyp(b"avif", [b"avis", b"avif"])
# A real JPEG: SOI + APP0/JFIF marker.
JPEG = (b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
        b"\xff\xd9")
PNG = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
       b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00")


# --------------------------------------------------------------------------
# 1. Pure sniffer
# --------------------------------------------------------------------------

@pytest.mark.parametrize("blob,label", [
    (HEIC, "HEIC"), (MIF1, "HEIF"), (AVIF, "AVIF"),
])
def test_heif_brands_are_named(blob, label):
    assert sama.rejected_container_brand(blob) == label


@pytest.mark.parametrize("blob", [
    JPEG, PNG, b"", b"\x00\x00\x00\x18ftyp", b"\x00\x00\x00\x18ftypi",
    b"\x00\x00\x00\x18ftypisom" + b"\x00" * 8,      # plain MP4 family brand
])
def test_non_heif_blobs_pass_through(blob):
    assert sama.rejected_container_brand(blob) is None


# --------------------------------------------------------------------------
# 2+3. /analyze behaviour
# --------------------------------------------------------------------------

def test_analyze_refuses_heic_with_actionable_message():
    r = client.post("/analyze", files={"file": ("tray.heic", HEIC,
                                                 "image/heic")},
                    data={"lot_ref": "QA-HEIC", "look_index": "0"})
    assert r.status_code == 400, r.text[:300]
    msg = r.json().get("error", "")
    assert "HEIC" in msg or "HEIF" in msg
    assert "JPEG" in msg                       # names the fix
    assert "retry" in msg.lower()              # warns retrying cannot work


def test_analyze_refuses_mif1_container_too():
    r = client.post("/analyze", files={"file": ("tray.jpg", MIF1,
                                                 "image/jpeg")},
                    data={"lot_ref": "QA-MIF1"})
    assert r.status_code == 400
    assert "cannot decode" in r.json().get("error", "")


def test_normal_jpeg_is_not_intercepted_by_the_format_guard():
    r = client.post("/analyze", files={"file": ("tray.jpg", JPEG,
                                                 "image/jpeg")},
                    data={"lot_ref": "QA-JPEG"})
    body = r.json()
    # Truncated JPEG decodes to None -> the ORDINARY unreadable-image path,
    # proving the format guard did not claim it.
    assert body.get("error") == "Could not read that image. Try again."
