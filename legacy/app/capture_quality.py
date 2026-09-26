"""Capture-quality gate: refuse the photos nobody can grade.

THE FIELD CONDITION NOBODY TESTED
---------------------------------
Procurement does not stop at sunset. A tray photographed inside a closed
storage godown, or with the phone's flash blowing out the near bulb, decodes
as a perfectly valid image -- so every guard upstream of the model passes --
and then one of two things happens:

  * ArUco finds nothing, sizes fall off the ladder, and the detector still
    emits confident-looking boxes on noise. The officer sees bulbs drawn on
    a black rectangle and signs a certificate built from that.
  * The frame is so dark (or so washed out) that class labels are guesses.

Either way the failure is SILENT: no crash, no banner, just numbers that
should never have existed. This module measures the two properties a human
checks without thinking -- is it bright enough, is it sharp enough -- and
answers in JSON the API can act on:

  blocked=True   -> /analyze refuses the capture with an actionable message
                    (retake in daylight). Grading an unusable frame would
                    print guesses on a signed document.
  warnings=[...] -> capture proceeds (a dim-but-usable or slightly soft
                    photo still carries information) but the UI says so
                    before the next look, not after the certificate.

Thresholds are deliberately conservative: only frames a person would
immediately retake get blocked. Pure functions over a numpy image -- no
model, no I/O -- so they run in microseconds and test without torch.
"""

from __future__ import annotations

import cv2
import numpy as np

# Mean luma (0-255) below which the frame cannot be graded at all. A dim but
# workable indoor shot sits around 70-110; a godown-after-dusk frame lands
# under 40, where even humans squint. Between 40 and 70 we warn, not block.
DARK_BLOCK_MEAN = 40.0
DIM_WARN_MEAN = 70.0

# Mean luma above which the frame is effectively blown out (direct flash on
# the near bulbs, or the lens covered by a finger in sunlight).
BRIGHT_BLOCK_MEAN = 246.0

# Laplacian variance below which the frame warns as blurry. Computed after
# downsampling to a FIXED width so phone megapixels do not change the answer:
# raw variance scales with resolution, and a 48 MP phone would never warn
# while a 5 MP workhorse always would.
SHARPNESS_SAMPLE_WIDTH = 480
BLUR_WARN_VAR = 20.0


def _sharpness(gray: np.ndarray) -> float:
    """Resolution-independent blur estimate: variance of the Laplacian."""
    h, w = gray.shape[:2]
    if w <= 0 or h <= 0:
        return 0.0
    if w > SHARPNESS_SAMPLE_WIDTH:
        scale = SHARPNESS_SAMPLE_WIDTH / float(w)
        gray = cv2.resize(gray, None, fx=scale, fy=scale,
                          interpolation=cv2.INTER_AREA)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def assess_capture_quality(image_bgr: np.ndarray) -> dict:
    """Brightness/blur verdict for one decoded frame.

    Returns a JSON-safe dict:
      checked      False only if the frame was too broken to measure at all
                   (callers then behave exactly as before this module existed)
      brightness   mean luma 0-255, rounded
      sharpness    Laplacian variance at a fixed sampling width
      blocked      True when the frame must not be graded
      reason       "dark" | "overexposed" | None
      warnings     subset of ["dim", "blurry"]
    """
    try:
        if image_bgr is None or not hasattr(image_bgr, "shape") \
                or image_bgr.size == 0:
            raise ValueError("no image to assess")
        gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
        brightness = float(np.mean(gray))
        sharpness = _sharpness(gray)
    except Exception:  # noqa: BLE001 -- measurement must never break capture
        return {"checked": False, "brightness": None, "sharpness": None,
                "blocked": False, "reason": None, "warnings": []}

    reason = None
    if brightness < DARK_BLOCK_MEAN:
        reason = "dark"
    elif brightness > BRIGHT_BLOCK_MEAN:
        reason = "overexposed"

    warnings: list[str] = []
    if reason is None:
        if brightness < DIM_WARN_MEAN:
            warnings.append("dim")
        if sharpness < BLUR_WARN_VAR:
            warnings.append("blurry")

    return {
        "checked": True,
        "brightness": round(brightness, 1),
        "sharpness": round(sharpness, 1),
        "blocked": reason is not None,
        "reason": reason,
        "warnings": warnings,
    }


def rejection_message(quality: dict) -> str | None:
    """The exact operator-facing reason a blocked frame was refused."""
    if not quality.get("blocked"):
        return None
    if quality.get("reason") == "overexposed":
        return ("Photo washed out — flash glare or direct sun. Step back, "
                "turn off the flash, shade the tray, and retake.")
    measured = quality.get("brightness")
    detail = f" (measured brightness {measured}/255)" if measured is not None else ""
    return ("Photo too dark to grade" + detail + ". Move to daylight or "
            "switch on the godown lights and retake — grading a frame this "
            "dark would print guesses on the certificate.")
