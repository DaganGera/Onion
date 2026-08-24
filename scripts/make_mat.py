"""Generate the printable A4 calibration mat.

The mat is what turns a phone photo into millimetres. Everything downstream
-- size grades, the caliper correction factor, the whole Grade A/B/C split --
depends on the printed markers being EXACTLY the designed size.

Eight markers ring the perimeter. Onions get tipped onto the mat and roll,
and a bulb covering a marker kills that marker outright rather than degrading
it. Eight means losing half still leaves a usable homography.

Print with "Actual size" / 100%, never "Fit to page", then caliper a printed
marker square. If it does not read 40.0 mm, the printer scaled the page and
every size measurement will be wrong by that same factor -- reprint.

    python scripts/make_mat.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.mat_layout import (  # noqa: E402
    MARKER_MM, MARKER_ORIGINS_MM, MAT_H_MM, MAT_W_MM, QUIET_MM,
)
from app.scale import ARUCO_DICT, detect_scale  # noqa: E402

DPI = 300
PX_PER_MM = DPI / 25.4
RULER_MM = 50.0     # all the gap between perimeter markers allows
GREY_PATCH_MM = 14.0

OUT_PDF = Path("calibration_mat.pdf")
OUT_PNG = Path("calibration_mat.png")


def mm(value: float) -> int:
    return int(round(value * PX_PER_MM))


def _font(size_px: int) -> ImageFont.FreeTypeFont:
    for name in ("arialbd.ttf", "arial.ttf", "DejaVuSans-Bold.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size_px)
        except OSError:
            continue
    return ImageFont.load_default()


def build_mat() -> Image.Image:
    canvas = Image.new("L", (mm(MAT_W_MM), mm(MAT_H_MM)), 255)
    draw = ImageDraw.Draw(canvas)

    f_tiny = _font(mm(2.6))
    f_small = _font(mm(3.4))
    f_med = _font(mm(4.6))
    f_large = _font(mm(6.5))

    dictionary = cv2.aruco.getPredefinedDictionary(ARUCO_DICT)
    side_px = mm(MARKER_MM)

    # --- the eight perimeter markers --------------------------------------
    # Positions come from app/mat_layout.py so the printed sheet and the
    # detector can never disagree about where a marker is.
    for marker_id, (x_mm, y_mm) in MARKER_ORIGINS_MM.items():
        marker = cv2.aruco.generateImageMarker(dictionary, marker_id, side_px)
        # white quiet zone around the square, required for reliable decoding
        tile = np.full((side_px + 2 * mm(QUIET_MM), side_px + 2 * mm(QUIET_MM)),
                       255, np.uint8)
        tile[mm(QUIET_MM):mm(QUIET_MM) + side_px,
             mm(QUIET_MM):mm(QUIET_MM) + side_px] = marker
        canvas.paste(Image.fromarray(tile).convert("L"),
                     (mm(x_mm - QUIET_MM), mm(y_mm - QUIET_MM)))
        draw.text((mm(x_mm), mm(y_mm + MARKER_MM + 1)), f"{marker_id}",
                  font=f_tiny, fill=0)

    # --- everything below must stay inside the SAFE BOX -------------------
    # The eight markers plus their quiet zones occupy the whole perimeter.
    # Anything drawn on top of a marker stops it decoding -- that is exactly
    # how marker 6 was lost on the first attempt. make_mat.py re-detects its
    # own output and fails the build if any marker is covered.
    #   safe box: x in [58, 239], y in [58, 152]
    #   top gaps: x in [58, 122] and [174, 239], y in [12, 52]
    #   bottom gap: x in [58, 122], y in [158, 198]

    # --- title -------------------------------------------------------------
    draw.text((mm(62), mm(60)), "SAMA", font=f_large, fill=0)
    draw.text((mm(62), mm(70)), "Calibration Mat", font=f_small, fill=0)
    draw.text((mm(62), mm(76)), "ICAR-DOGR grading standard", font=f_tiny, fill=0)

    # --- size reference circles, inside the safe box -----------------------
    circles = [(80.0, "A", 105.0), (50.0, "B", 172.0), (30.0, "C", 216.0)]
    cy = 108.0
    for diameter, label, cx in circles:
        r = diameter / 2.0
        draw.ellipse([mm(cx - r), mm(cy - r), mm(cx + r), mm(cy + r)],
                     outline=0, width=mm(0.5))
        draw.text((mm(cx - 2.5), mm(cy - 3.5)), label, font=f_med, fill=0)

    draw.text((mm(62), mm(147)), "A  > 80 mm      B  50-80 mm      C  30-50 mm",
              font=f_small, fill=0)

    # --- greyscale strip, top-left gap -------------------------------------
    draw.text((mm(62), mm(16)), "White balance", font=f_tiny, fill=0)
    for i, level in enumerate((255, 128, 0)):
        gx = 62.0 + i * (GREY_PATCH_MM + 2.0)
        draw.rectangle([mm(gx), mm(21), mm(gx + GREY_PATCH_MM), mm(21 + GREY_PATCH_MM)],
                       fill=level, outline=0, width=mm(0.3))

    # --- verification ruler, top-right gap ---------------------------------
    # 50 mm, not 100 -- that is all the gap between markers allows. The
    # markers themselves are the better check: caliper one black square,
    # it must read exactly 40.0 mm.
    rx, ry = 178.0, 30.0
    draw.text((mm(rx), mm(ry - 8)), "MEASURE: must be 50.0 mm", font=f_tiny, fill=0)
    draw.line([mm(rx), mm(ry), mm(rx + 50.0), mm(ry)], fill=0, width=mm(0.4))
    for tick in range(0, 51, 10):
        h = 3.5 if tick % 50 == 0 else 2.2
        draw.line([mm(rx + tick), mm(ry), mm(rx + tick), mm(ry + h)], fill=0, width=mm(0.4))
        draw.text((mm(rx + tick - 1.5), mm(ry + h + 0.4)), str(tick), font=f_tiny, fill=0)

    # --- instructions, bottom-left gap -------------------------------------
    draw.text((mm(62), mm(163)), "Print at ACTUAL SIZE / 100%.", font=f_small, fill=0)
    draw.text((mm(62), mm(169)), "Not 'Fit to page'.", font=f_tiny, fill=0)
    draw.text((mm(62), mm(176)), f"Each marker square = {MARKER_MM:.1f} mm.",
              font=f_tiny, fill=0)
    draw.text((mm(62), mm(181)), "Caliper one to verify the print.", font=f_tiny, fill=0)
    draw.text((mm(62), mm(188)), "Keep onions OFF the marker border.", font=f_tiny, fill=0)

    return canvas


def main() -> int:
    mat = build_mat()
    mat.save(OUT_PNG, dpi=(DPI, DPI))
    mat.convert("RGB").save(OUT_PDF, "PDF", resolution=DPI)

    bgr = cv2.cvtColor(np.array(mat), cv2.COLOR_GRAY2BGR)
    scale = detect_scale(bgr)

    print(f"Wrote {OUT_PDF}  ({MAT_W_MM} x {MAT_H_MM} mm at {DPI} DPI)")
    print(f"Wrote {OUT_PNG}\n")
    print(f"  markers detected : {len(scale.marker_ids)}/8  {scale.marker_ids}")
    print(f"  scale source     : {scale.source}")
    print(f"  mm per pixel     : {scale.mm_per_px:.6f}  "
          f"(expected {1.0 / PX_PER_MM:.6f})")

    if len(scale.marker_ids) != 8:
        print("\nFAIL - all eight markers must decode in the generated sheet.")
        return 1

    # Round-trip a known length through the homography. This catches a
    # mat_layout / renderer disagreement, which would otherwise show up as
    # plausible-but-wrong millimetres in the field.
    probe = np.array([[[mm(50.0), mm(100.0)]], [[mm(150.0), mm(100.0)]]], np.float32)
    mapped = cv2.perspectiveTransform(probe, scale.homography).reshape(2, 2)
    measured = float(np.linalg.norm(mapped[1] - mapped[0]))
    error_pct = abs(measured - 100.0) / 100.0 * 100

    print(f"  100 mm round-trip: {measured:.3f} mm  ({error_pct:.3f}% error)")
    if error_pct > 1.0:
        print("\nFAIL - homography does not reproduce a known distance.")
        return 1

    print("\nNEXT: print 5 copies at ACTUAL SIZE, then caliper the printed sheet.")
    print(f"      A marker square must read {MARKER_MM:.1f} +/- 0.3 mm, and the ruler")
    print("      50.0 +/- 0.3 mm. That is Gate T1.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
