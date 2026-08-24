"""Check a photo of a PRINTED calibration mat.

Print scaling is silent and fatal: "Fit to page" shrinks A4 by about 6%, so
every onion reads 6% small and the Grade A percentage is wrong all day.
Photograph a printed mat next to a ruler and run this before shooting.

    python scripts/verify_mat.py photo_of_printed_mat.jpg
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.mat_layout import MARKER_MM
from app.scale import _DETECTOR, _mean_side_px, detect_scale


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("image", type=Path)
    args = ap.parse_args()

    image = cv2.imread(str(args.image))
    if image is None:
        print(f"Could not read {args.image}")
        return 1

    scale = detect_scale(image)
    print(f"image        : {args.image.name}  {image.shape[1]}x{image.shape[0]}")
    print(f"markers found: {len(scale.marker_ids)}/8  {scale.marker_ids}")
    print(f"scale source : {scale.source}  (confidence {scale.confidence:.2f})")

    if not scale.calibrated:
        print("FAIL - no usable reference found.")
        print("  Is the whole mat in frame? In focus? Too dark?")
        return 1

    grey = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    corners, ids, _ = _DETECTOR.detectMarkers(grey)
    if ids is not None:
        print()
        for corner, marker_id in zip(corners, ids.ravel()):
            side_px = _mean_side_px(corner.reshape(4, 2))
            print(f"  ID {int(marker_id)}: {side_px:7.2f} px  ->  "
                  f"{MARKER_MM / side_px:.5f} mm/px")

    print(f"mm per pixel : {scale.mm_per_px:.5f}")
    if scale.perspective_skew:
        print("WARNING - markers differ in apparent size by more than 8%.")
        print("  The phone was tilted. Hold it flat, directly above the mat.")
    if scale.warning:
        print(scale.warning)

    missing = 8 - len(scale.marker_ids)
    if missing:
        print(f"{missing} marker(s) not visible. Still usable, but clear the")
        print("mat border for the best sizing.")

    print(f"Now caliper a printed marker square: it must read "
          f"{MARKER_MM:.1f} +/- 0.3 mm.")
    print("If not, reprint at ACTUAL SIZE / 100%.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
