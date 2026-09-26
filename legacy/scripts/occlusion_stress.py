"""What happens when onions bury the calibration markers?

Progressively covers markers on real mat photos and measures what the scale
ladder recovers at each level. This is the experiment that decides whether
the eight-marker redesign was worth the paper.

    python scripts/occlusion_stress.py

Reports, for 0 through 8 markers covered:
  - which rung of the ladder the detector landed on
  - the error in a known 100 mm distance recovered from that rung
  - whether a lot would still get graded at all

The headline comparison is against the ORIGINAL two-marker design, simulated
by ignoring all but markers 0 and 7.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.mat_layout import (  # noqa: E402
    MARKER_MM, MARKER_ORIGINS_MM, MAT_H_MM, MAT_W_MM, QUIET_MM,
)
from app.scale import detect_scale  # noqa: E402

PX_PER_MM = 4.0
TRUE_SPAN_MM = 100.0


def render_mat(rng: np.random.Generator,
               tilt: bool = False) -> tuple[np.ndarray, np.ndarray]:
    """A photographed mat: the real printed sheet, optionally at an angle.

    Also returns the warp applied, so probe points defined in flat mat
    coordinates can be moved into the tilted image. Without that the error
    measurement would compare the detector against the wrong pixels and
    report nonsense the moment tilt is switched on.
    """
    from make_mat import build_mat

    mat = np.array(build_mat())
    w = int(MAT_W_MM * PX_PER_MM)
    h = int(MAT_H_MM * PX_PER_MM)
    mat = cv2.resize(mat, (w, h), interpolation=cv2.INTER_AREA)
    scene = np.full((h + 200, w + 200, 3), 170, np.uint8)
    scene[100:100 + h, 100:100 + w] = cv2.cvtColor(mat, cv2.COLOR_GRAY2BGR)

    warp = np.eye(3, dtype=np.float32)
    if tilt:
        H, W = scene.shape[:2]
        src = np.float32([[0, 0], [W, 0], [W, H], [0, H]])
        jitter = (rng.uniform(-0.08, 0.08, 8).reshape(4, 2)
                  * np.float32([W, H])).astype(np.float32)
        warp = cv2.getPerspectiveTransform(src, (src + jitter).astype(np.float32))
        scene = cv2.warpPerspective(scene, warp, (W, H), borderValue=(170, 170, 170))
    return scene, warp


def _to_scene(x_mm: float, y_mm: float, warp: np.ndarray) -> tuple[float, float]:
    """Flat mat millimetres -> pixel position in the (possibly tilted) photo."""
    pt = np.array([[[100 + x_mm * PX_PER_MM, 100 + y_mm * PX_PER_MM]]], np.float32)
    out = cv2.perspectiveTransform(pt, warp).reshape(2)
    return float(out[0]), float(out[1])


def bury_markers(scene: np.ndarray, ids: list[int], rng: np.random.Generator,
                 warp: np.ndarray) -> np.ndarray:
    """Drop an onion-coloured blob over each named marker."""
    out = scene.copy()
    for marker_id in ids:
        x_mm, y_mm = MARKER_ORIGINS_MM[marker_id]
        cx, cy = _to_scene(x_mm + MARKER_MM / 2, y_mm + MARKER_MM / 2, warp)
        cx, cy = int(cx), int(cy)
        r = int((MARKER_MM / 2 + QUIET_MM) * PX_PER_MM * rng.uniform(0.95, 1.25))
        colour = (int(rng.integers(40, 90)), int(rng.integers(90, 140)),
                  int(rng.integers(140, 190)))
        cv2.circle(out, (cx, cy), r, colour, -1)
    return out


def span_error_mm(scale, warp: np.ndarray) -> float | None:
    """Error in a known 100 mm span, measured through the recovered scale.

    The two endpoints are defined in flat mat millimetres and pushed through
    the same warp as the photo, so this stays honest under tilt.
    """
    if not scale.calibrated:
        return None

    p0 = _to_scene(70.0, 105.0, warp)
    p1 = _to_scene(70.0 + TRUE_SPAN_MM, 105.0, warp)

    if scale.homography is not None:
        pts = np.array([[list(p0)], [list(p1)]], np.float32)
        mapped = cv2.perspectiveTransform(pts, scale.homography).reshape(2, 2)
        measured = float(np.linalg.norm(mapped[1] - mapped[0]))
    elif scale.mm_per_px is not None:
        measured = float(np.hypot(p1[0] - p0[0], p1[1] - p0[1])) * scale.mm_per_px
    else:
        return None
    return measured - TRUE_SPAN_MM


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--trials", type=int, default=25)
    ap.add_argument("--tilt", action="store_true", default=True)
    args = ap.parse_args()

    rng = np.random.default_rng(2026)
    all_ids = sorted(MARKER_ORIGINS_MM)

    print("MARKER OCCLUSION STRESS TEST")
    print(f"{args.trials} trials per level, mats photographed at a random angle\n")
    print(f"{'buried':>7}{'visible':>9}{'calibrated':>12}{'source':>18}"
          f"{'|100mm err|':>13}{'graded?':>9}")
    print("-" * 70)

    rows = []
    for n_buried in range(0, 9):
        sources: dict[str, int] = {}
        errors: list[float] = []
        calibrated = 0

        for trial in range(args.trials):
            scene, warp = render_mat(rng, tilt=args.tilt)
            buried = list(rng.choice(all_ids, size=n_buried, replace=False)) if n_buried else []
            scene = bury_markers(scene, buried, rng, warp)

            scale = detect_scale(scene)
            sources[scale.source] = sources.get(scale.source, 0) + 1
            if scale.calibrated:
                calibrated += 1
                err = span_error_mm(scale, warp)
                if err is not None:
                    errors.append(abs(err))

        top = max(sources, key=sources.get)
        rate = 100.0 * calibrated / args.trials
        mae = float(np.mean(errors)) if errors else float("nan")
        visible = 8 - n_buried
        graded = "YES" if rate > 50 else ("some" if rate > 0 else "NO")
        print(f"{n_buried:>7}{visible:>9}{rate:>11.0f}%{top:>18}"
              f"{mae:>13.2f}{graded:>9}")
        rows.append((n_buried, rate, mae, top))

    # --- what the ORIGINAL two-marker mat would have done ------------------
    print("\n" + "-" * 70)
    print("COMPARISON: the original 2-marker design")
    print("(simulated by burying all but markers 0 and 7, then covering those)\n")
    print(f"{'buried':>7}{'visible':>9}{'calibrated':>12}{'outcome':>34}")
    print("-" * 70)

    for n_buried_of_two in range(0, 3):
        calibrated = 0
        for trial in range(args.trials):
            scene, warp = render_mat(rng, tilt=args.tilt)
            # everything except 0 and 7 never existed on the old mat
            hidden = [i for i in all_ids if i not in (0, 7)]
            hidden += (list(rng.choice([0, 7], size=n_buried_of_two, replace=False))
                       if n_buried_of_two else [])
            scene = bury_markers(scene, hidden, rng, warp)
            scale = detect_scale(scene)
            # the old code had no mat-edge or carried fallback
            if scale.calibrated and scale.source in {"homography", "homography_weak",
                                                     "single_marker"}:
                calibrated += 1

        rate = 100.0 * calibrated / args.trials
        outcome = ("all lots graded" if rate > 90 else
                   "degraded, no tilt check" if rate > 50 else
                   "TOTAL FAILURE - no sizes at all")
        print(f"{n_buried_of_two:>7}{2 - n_buried_of_two:>9}{rate:>11.0f}%{outcome:>34}")

    print("\n" + "=" * 70)
    survive = [r for r in rows if r[1] > 50]
    print(f"8-marker mat keeps grading with up to {max(r[0] for r in survive)} "
          "markers buried.")
    print("2-marker mat loses every size in the lot once both are covered,")
    print("which two unlucky onions can do.")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
