"""Recovering millimetres from a photo, and degrading honestly when we can't.

THE PROBLEM THIS SOLVES
-----------------------
Onions are tipped onto the mat and roll. A bulb that covers an ArUco marker
does not make detection worse -- it makes it fail outright, because the
decoder needs the entire black square plus its quiet border. With two
markers, two unlucky onions removed every size measurement in the lot.

THE LADDER
----------
Each rung is strictly worse than the one above but strictly better than
nothing, and every result says which rung it landed on so the certificate
can state its own limits.

  HOMOGRAPHY  >=3 markers   perspective-correct, per-bulb local scale
  HOMOGRAPHY  2 markers     same maths, weaker geometry
  SINGLE      1 marker      one global mm/px, no perspective correction
  CARRIED     0 markers     scale reused from an earlier look of this lot
  MAT_EDGE    0 markers     the mat's own A4 outline -- PROVISIONAL ONLY

On a clean bench MAT_EDGE looks excellent (0.1-3 mm error on a 100 mm span,
per scripts/occlusion_stress.py). On real cluttered trays it is not: measured
against caliper ground truth it came out at 16.9 mm MAE, versus 0.5-0.7 mm for
every marker-based rung. A 17 mm error on a 60 mm bulb moves it two grade
bands, so this rung is confidently wrong rather than usefully approximate --
the worst kind of failure on a signed document.

It is kept only because some scale beats none for a relative size picture, and
it sits BELOW carried: a homography measured thirty seconds ago on the same
bench is far more trustworthy than a bright quadrilateral that could be a
tray, a cloth, or a sheet of paper. Anything at or below GRADING_FLOOR is
flagged provisional and must not be presented as a certified grade.

  NONE        nothing       uncalibrated; sizes withheld, not guessed

The last rung matters as much as the first. A number invented without a
reference would be indistinguishable from a real one on the certificate.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import cv2
import numpy as np

from app.mat_layout import (
    MARKER_MM, MAT_CORNERS_MM, MAT_H_MM, MAT_W_MM, marker_corners_mm,
)

# Guarded at import (RT-001 D-1): plain opencv-python has no cv2.aruco
# submodule at all. A bare `cv2.aruco.DICT_4X4_50` here used to raise
# AttributeError before uvicorn even bound -- killing pages, replay,
# dashboard and verify along with capture. Import must never raise; only
# /analyze is allowed to degrade for this.
try:
    ARUCO_DICT = cv2.aruco.DICT_4X4_50
except AttributeError:
    ARUCO_DICT = None

ARUCO_AVAILABLE = ARUCO_DICT is not None

SKEW_TOLERANCE = 0.08

# Confidence attached to each rung. Used to decide whether to warn the
# operator, not to scale any measurement.
SOURCE_CONFIDENCE = {
    "homography": 1.00,
    "homography_weak": 0.85,
    "single_marker": 0.70,
    "carried": 0.40,
    "mat_edge": 0.25,   # measured at 16.9 mm MAE on cluttered trays
    "none": 0.0,
}

# At or below this, sizes are provisional: usable as a relative picture,
# not as a certified ICAR-DOGR grade.
GRADING_FLOOR = 0.35

_DETECTOR = None          # built lazily by get_detector(); never at import
_DETECTOR_BROKEN = False  # set once if construction fails; stops retrying


def get_detector():
    """Build the ArUco detector on first use instead of at import time.

    Returns None when cv2.aruco is unavailable so callers can degrade
    explicitly (main.py /analyze answers with a clear JSON error). Never
    raises. The built detector is cached for the life of the process.
    """
    global _DETECTOR, _DETECTOR_BROKEN
    if _DETECTOR is not None:
        return _DETECTOR
    if _DETECTOR_BROKEN or not ARUCO_AVAILABLE:
        return None
    try:
        _DETECTOR = cv2.aruco.ArucoDetector(
            cv2.aruco.getPredefinedDictionary(ARUCO_DICT),
            cv2.aruco.DetectorParameters(),
        )
    except Exception as exc:  # noqa: BLE001 -- construction must never raise
        _DETECTOR_BROKEN = True
        print(f"WARNING: ArUco detector unavailable -- "
              f"{type(exc).__name__}: {exc}")
    return _DETECTOR


@dataclass
class ScaleResult:
    """How to convert this image's pixels into millimetres, and how much to
    trust the conversion."""

    calibrated: bool = False
    source: str = "none"
    mm_per_px: float | None = None          # representative, for display
    homography: np.ndarray | None = None    # image px -> mat mm
    marker_ids: list[int] = field(default_factory=list)
    markers_expected: int = 8
    perspective_skew: bool = False
    confidence: float = 0.0
    warning: str = ""

    @property
    def grades_certified(self) -> bool:
        """Whether these sizes may be presented as an ICAR-DOGR grade."""
        return self.calibrated and self.confidence > GRADING_FLOOR

    def to_dict(self) -> dict:
        """JSON-safe. The homography is dropped -- the client never needs it,
        and a 3x3 float matrix in every response is noise."""
        return {
            "calibrated": self.calibrated,
            "source": self.source,
            "mm_per_px": self.mm_per_px,
            "marker_ids": self.marker_ids,
            "markers_found": len(self.marker_ids),
            "markers_expected": self.markers_expected,
            "perspective_skew": self.perspective_skew,
            "confidence": round(self.confidence, 2),
            "warning": self.warning,
            "grades_certified": self.grades_certified,
        }


def _mean_side_px(corner_set: np.ndarray) -> float:
    pts = corner_set.reshape(4, 2).astype(float)
    return float(np.mean([
        np.linalg.norm(pts[i] - pts[(i + 1) % 4]) for i in range(4)
    ]))


def _mm_per_px_from_homography(H: np.ndarray, width: int, height: int) -> float:
    """Representative scale at the image centre.

    Under perspective the scale genuinely varies across the frame, so this is
    only for display. Actual sizing uses the homography per bulb.
    """
    cx, cy = width / 2.0, height / 2.0
    pts = np.array([[[cx, cy]], [[cx + 10.0, cy]]], dtype=np.float32)
    mapped = cv2.perspectiveTransform(pts, H).reshape(2, 2)
    return float(np.linalg.norm(mapped[1] - mapped[0]) / 10.0)


def _find_mat_quad(image_bgr: np.ndarray) -> np.ndarray | None:
    """Locate the mat's own white A4 rectangle.

    Last resort when every marker is buried. The mat is the brightest large
    convex quadrilateral in frame. This can be fooled by a white tray or a
    sheet of paper, which is exactly why it is reported as a distinct,
    low-confidence source rather than folded in silently.
    """
    grey = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)

    # A featureless frame -- a blank wall, a lens cap, an overexposed shot --
    # thresholds into one full-frame blob that passes every shape test below
    # and yields confident, meaningless millimetres. Otsu always splits
    # something, so the contrast check has to happen before it runs.
    if float(grey.std()) < 12.0:
        return None

    grey = cv2.GaussianBlur(grey, (5, 5), 0)
    _, mask = cv2.threshold(grey, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE,
                            cv2.getStructuringElement(cv2.MORPH_RECT, (25, 25)))

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None

    frame_area = image_bgr.shape[0] * image_bgr.shape[1]
    # Upper bound as well as lower: a blob filling the frame edge-to-edge is
    # not a sheet lying on a bench, it is the absence of one. A genuine mat
    # photo has background visible around it -- and if the mat really did
    # fill the frame, its markers would be visible and we would never reach
    # this rung.
    candidates = [c for c in contours
                  if 0.12 * frame_area <= cv2.contourArea(c) <= 0.90 * frame_area]
    if not candidates:
        return None

    contour = max(candidates, key=cv2.contourArea)

    # Onions sitting over the mat's edge bite notches out of its outline, so
    # the raw contour is neither convex nor four-sided. The convex hull
    # bridges those bites and recovers the sheet the notches were cut from.
    hull = cv2.convexHull(contour)

    best = None
    perimeter = cv2.arcLength(hull, True)
    for epsilon in (0.01, 0.02, 0.03, 0.05, 0.08):
        approx = cv2.approxPolyDP(hull, epsilon * perimeter, True)
        if len(approx) == 4:
            best = approx.reshape(4, 2).astype(np.float32)
            break

    if best is None:
        # Still not a clean quadrilateral. A rotated bounding box is a
        # cruder fit -- it cannot represent perspective -- but for a mat
        # photographed near-flat it is far better than refusing to size.
        best = cv2.boxPoints(cv2.minAreaRect(hull)).astype(np.float32)

    # Sanity: an A4 sheet has a known aspect ratio. Anything wildly off is a
    # white tray or a tablecloth, not our mat, and using it would invent
    # confident millimetres from the wrong object.
    side_a = np.linalg.norm(best[1] - best[0])
    side_b = np.linalg.norm(best[2] - best[1])
    if min(side_a, side_b) <= 0:
        return None
    aspect = max(side_a, side_b) / min(side_a, side_b)
    expected = max(MAT_W_MM, MAT_H_MM) / min(MAT_W_MM, MAT_H_MM)
    if not (0.65 * expected <= aspect <= 1.5 * expected):
        return None

    # order corners TL, TR, BR, BL so they match MAT_CORNERS_MM
    summed = best.sum(axis=1)
    diffed = np.diff(best, axis=1).ravel()
    return np.array([
        best[np.argmin(summed)],   # top-left  has the smallest x+y
        best[np.argmin(diffed)],   # top-right has the smallest y-x
        best[np.argmax(summed)],   # bottom-right
        best[np.argmax(diffed)],   # bottom-left
    ], dtype=np.float32)


def detect_scale(image_bgr, carried: ScaleResult | None = None) -> ScaleResult:
    """Work down the ladder until something gives us millimetres.

    Never raises. `carried` is a scale recovered from an earlier look of the
    same lot -- the mat and phone have not moved much between two photos of
    one tray, so reusing it beats reporting nothing.
    """
    result = ScaleResult()

    if image_bgr is None or getattr(image_bgr, "size", 0) == 0:
        result.warning = "No image."
        return result

    height, width = image_bgr.shape[:2]

    detector = get_detector()
    if detector is None:
        # No cv2.aruco on this machine: skip the marker rungs entirely. The
        # ladder still walks (carried / mat_edge / none), so detect_scale
        # keeps its "never raises" contract even in a broken environment.
        corners, ids = [], None
    else:
        try:
            grey = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
            corners, ids, _ = detector.detectMarkers(grey)
        except cv2.error:
            corners, ids = [], None

    found: list[tuple[int, np.ndarray]] = []
    if ids is not None:
        for corner, marker_id in zip(corners, ids.ravel()):
            marker_id = int(marker_id)
            if marker_id in {k for k in range(8)}:
                found.append((marker_id, corner.reshape(4, 2).astype(np.float32)))

    result.marker_ids = sorted(m for m, _ in found)

    # --- rungs 1 and 2: homography from two or more markers ---------------
    if len(found) >= 2:
        image_pts, mat_pts = [], []
        for marker_id, quad in found:
            image_pts.extend(quad.tolist())
            mat_pts.extend(marker_corners_mm(marker_id))

        H, _ = cv2.findHomography(
            np.array(image_pts, np.float32), np.array(mat_pts, np.float32),
            cv2.RANSAC, 3.0)

        if H is not None:
            result.calibrated = True
            result.homography = H
            result.mm_per_px = _mm_per_px_from_homography(H, width, height)
            strong = len(found) >= 3
            result.source = "homography" if strong else "homography_weak"
            result.confidence = SOURCE_CONFIDENCE[result.source]

            sides = [_mean_side_px(q) for _, q in found]
            if len(sides) >= 2 and min(sides) > 0:
                result.perspective_skew = abs(max(sides) / min(sides) - 1.0) > SKEW_TOLERANCE

            missing = 8 - len(found)
            if missing >= 4:
                result.warning = (f"{missing} of 8 markers hidden. "
                                  "Clear onions off the mat border.")
            elif not strong:
                result.warning = "Only 2 markers visible. Sizes are usable but less certain."
            return result

    # --- rung 3: a single marker ------------------------------------------
    if len(found) == 1:
        side_px = _mean_side_px(found[0][1])
        if side_px > 0:
            result.calibrated = True
            result.source = "single_marker"
            result.mm_per_px = MARKER_MM / side_px
            result.confidence = SOURCE_CONFIDENCE["single_marker"]
            result.warning = ("Only 1 marker visible. No tilt correction -- "
                              "hold the phone flat and clear the mat border.")
            return result

    # --- rung 4: reuse a scale from an earlier look of this lot ------------
    if carried is not None and carried.calibrated:
        result.calibrated = True
        result.source = "carried"
        result.mm_per_px = carried.mm_per_px
        result.homography = carried.homography
        result.confidence = SOURCE_CONFIDENCE["carried"]
        result.warning = ("No reference in this photo. Reusing the scale from an "
                          "earlier look -- valid only if the phone has not moved.")
        return result

    # --- rung 5: the mat's own outline ------------------------------------
    quad = _find_mat_quad(image_bgr)
    if quad is not None:
        H, _ = cv2.findHomography(quad, np.array(MAT_CORNERS_MM, np.float32))
        if H is not None:
            result.calibrated = True
            result.source = "mat_edge"
            result.homography = H
            result.mm_per_px = _mm_per_px_from_homography(H, width, height)
            result.confidence = SOURCE_CONFIDENCE["mat_edge"]
            result.warning = ("No marker visible. Scale taken from the mat outline -- "
                              "sizes are PROVISIONAL, not a certified grade. Reshoot with the mat clear.")
            return result

    # --- floor: refuse to invent a number ----------------------------------
    result.warning = ("Calibration mat not detected. Sizes cannot be measured. "
                      "Clear the mat border and photograph the tray again.")
    return result


def measure_bbox_mm(bbox_xyxy, scale: ScaleResult) -> float | None:
    """Bulb diameter in millimetres, perspective-corrected where possible.

    With a homography the box corners are mapped into the mat plane and
    measured there, so a bulb at the edge of a tilted frame is not reported
    larger than the same bulb at the centre. Without one, falls back to a
    single global mm/px.

    Returns the SHORTER side: onions in a tray are wider than tall, and the
    short side is the more stable estimate of true bulb diameter.
    """
    if scale is None or not scale.calibrated:
        return None

    x0, y0, x1, y1 = (float(v) for v in bbox_xyxy)

    if scale.homography is not None:
        quad = np.array([[[x0, y0]], [[x1, y0]], [[x1, y1]], [[x0, y1]]], np.float32)
        mapped = cv2.perspectiveTransform(quad, scale.homography).reshape(4, 2)
        width_mm = (np.linalg.norm(mapped[1] - mapped[0])
                    + np.linalg.norm(mapped[2] - mapped[3])) / 2.0
        height_mm = (np.linalg.norm(mapped[3] - mapped[0])
                     + np.linalg.norm(mapped[2] - mapped[1])) / 2.0
        return float(min(width_mm, height_mm))

    if scale.mm_per_px is None:
        return None
    return float(min(abs(x1 - x0), abs(y1 - y0)) * scale.mm_per_px)
