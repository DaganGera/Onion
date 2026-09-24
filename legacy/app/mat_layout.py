"""Canonical calibration-mat geometry.

ONE definition, imported by the mat generator, the scale detector and the
synthetic renderer. If these three ever disagree about where a marker sits,
every size measurement is silently wrong and nothing raises.

WHY EIGHT MARKERS
-----------------
The first design had two markers in opposite corners. Onions are dumped onto
the mat and roll. When a bulb covers a marker, ArUco does not degrade -- it
fails completely, because detection needs the whole black square plus its
border. Two markers meant two single points of failure for the entire
product output.

Eight markers ring the perimeter. Losing four still leaves a usable
homography, and losing all eight is close to impossible unless the mat is
buried, which the operator can see and fix.
"""

from __future__ import annotations

# A4 landscape. The mat is printed at exactly this size.
MAT_W_MM = 297.0
MAT_H_MM = 210.0

MARKER_MM = 40.0          # printed side of the black square, all eight
QUIET_MM = 6.0            # white margin each side, needed for detection
INSET_MM = 6.0            # gap from the paper edge

# Top-left corner of each marker, in mat millimetres.
# Perimeter ring: four corners plus four edge midpoints. The centre is left
# clear for the size-reference circles and for the onions themselves.
_x_left = INSET_MM + QUIET_MM
_x_right = MAT_W_MM - INSET_MM - QUIET_MM - MARKER_MM
_x_mid = (MAT_W_MM - MARKER_MM) / 2.0
_y_top = INSET_MM + QUIET_MM
_y_bottom = MAT_H_MM - INSET_MM - QUIET_MM - MARKER_MM
_y_mid = (MAT_H_MM - MARKER_MM) / 2.0

MARKER_ORIGINS_MM: dict[int, tuple[float, float]] = {
    0: (_x_left,  _y_top),
    1: (_x_mid,   _y_top),
    2: (_x_right, _y_top),
    3: (_x_left,  _y_mid),
    4: (_x_right, _y_mid),
    5: (_x_left,  _y_bottom),
    6: (_x_mid,   _y_bottom),
    7: (_x_right, _y_bottom),
}

N_MARKERS = len(MARKER_ORIGINS_MM)


def marker_corners_mm(marker_id: int) -> list[tuple[float, float]]:
    """The marker's four corners in mat millimetres.

    Order matches cv2.aruco's corner output: top-left, top-right,
    bottom-right, bottom-left. Getting this order wrong produces a homography
    that is subtly rotated and sizes that are plausible but incorrect.
    """
    x, y = MARKER_ORIGINS_MM[marker_id]
    s = MARKER_MM
    return [(x, y), (x + s, y), (x + s, y + s), (x, y + s)]


MAT_CORNERS_MM: list[tuple[float, float]] = [
    (0.0, 0.0), (MAT_W_MM, 0.0), (MAT_W_MM, MAT_H_MM), (0.0, MAT_H_MM),
]
