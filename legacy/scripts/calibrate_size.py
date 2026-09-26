"""Fit height_correction: the factor that turns pixel sizes into real mm.

An onion sits ON the mat, so it is nearer the camera than the marker and
images slightly LARGER than its true size. Left uncorrected, every bulb reads
oversized and the Grade A percentage is inflated -- the single number the
whole product reports.

    python scripts/calibrate_size.py [--no-write]

Writes height_correction into app/constants.json and prints the error before
and after, which is one of the five numbers quoted to judges. --no-write
fits and reports WITHOUT touching constants.json (a dry run). The full fit
-- pairs, factor, errors, config echo -- lands in runs/report/calibrate_size.json.

Inference is pinned to the shipped mode (end2end from app/constants.json),
imgsz 1024, max_det 300.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.grading import detect_scale  # noqa: E402
from app.scale import measure_bbox_mm  # noqa: E402
from scripts.run_config import echo_config, yolo26_inference_kwargs  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
CONSTANTS = ROOT / "app" / "constants.json"


def _raw_diameter_mm(bbox, scale) -> float | None:
    """Uncorrected diameter, perspective-corrected but WITHOUT height_correction.

    Deliberately does not call grading.bulb_diameter_mm -- that already
    applies height_correction, and fitting a factor on top of itself would
    silently converge to 1.0 and hide the real bias.
    """
    return measure_bbox_mm(bbox, scale)


def _load_caliper(data_dir: Path) -> list[dict]:
    path = data_dir / "caliper.csv"
    if not path.exists():
        print(f"No {path}. Hand-measure 40 bulbs with a vernier caliper and "
              "record onion_id,tray_id,caliper_mm,image,bbox_x0,bbox_y0,bbox_x1,bbox_y1")
        return []
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _find_image(data_dir: Path, filename: str) -> Path | None:
    for candidate in data_dir.rglob(filename):
        return candidate
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data", type=Path, default=ROOT / "data")
    ap.add_argument("--weights", type=Path, default=ROOT / "weights" / "best.pt")
    ap.add_argument("--imgsz", type=int, default=1024,
                    help="inference resolution; protocol pins this at 1024")
    ap.add_argument("--write", action=argparse.BooleanOptionalAction, default=True,
                    help="--no-write fits and reports without touching "
                         "constants.json")
    ap.add_argument("--out", type=Path, default=ROOT / "runs" / "report")
    args = ap.parse_args()

    if args.imgsz != 1024:
        print(f"WARNING: --imgsz {args.imgsz} breaks protocol; the correction "
              "factor is only valid at the resolution it was fitted on.")

    rows = _load_caliper(args.data)
    if not rows:
        return 1

    use_model = args.weights.exists()
    model = None
    predict_kwargs = {}
    if use_model:
        from ultralytics import YOLO
        model = YOLO(str(args.weights))
        predict_kwargs = yolo26_inference_kwargs(args.imgsz)
        print(f"Matching detections from {args.weights} "
              f"(end2end={predict_kwargs.get('end2end')}, imgsz={args.imgsz})")
    else:
        print(f"No {args.weights} yet -- measuring the recorded boxes directly.")

    pairs: list[tuple[float, float]] = []
    unmatched = 0
    image_cache: dict[str, tuple[np.ndarray, dict]] = {}

    for row in rows:
        filename = row.get("image", "")
        if filename not in image_cache:
            path = _find_image(args.data, filename)
            if path is None:
                continue
            img = cv2.imread(str(path))
            image_cache[filename] = (img, detect_scale(img))
        img, scale = image_cache[filename]

        if img is None or not scale.calibrated:
            continue

        truth_bbox = (float(row["bbox_x0"]), float(row["bbox_y0"]),
                      float(row["bbox_x1"]), float(row["bbox_y1"]))
        caliper_mm = float(row["caliper_mm"])

        bbox = truth_bbox
        if model is not None:
            # nearest detection centre to the measured bulb
            result = model.predict(img, conf=0.25, verbose=False,
                                   **predict_kwargs)[0]
            if result.boxes is None or len(result.boxes) == 0:
                unmatched += 1
                continue
            tcx = (truth_bbox[0] + truth_bbox[2]) / 2
            tcy = (truth_bbox[1] + truth_bbox[3]) / 2
            boxes = result.boxes.xyxy.cpu().numpy()
            centres = np.stack([(boxes[:, 0] + boxes[:, 2]) / 2,
                                (boxes[:, 1] + boxes[:, 3]) / 2], axis=1)
            dists = np.hypot(centres[:, 0] - tcx, centres[:, 1] - tcy)
            best = int(np.argmin(dists))
            # reject a match further away than half a bulb -- that is a
            # different onion, and a wrong pair poisons the fit
            if dists[best] > 0.5 * (truth_bbox[2] - truth_bbox[0]):
                unmatched += 1
                continue
            bbox = tuple(boxes[best])

        predicted = _raw_diameter_mm(bbox, scale)
        if predicted and predicted > 0:
            pairs.append((caliper_mm, predicted))

    if not pairs:
        print("No usable caliper/detection pairs. Cannot fit.")
        return 1

    truth = np.array([p[0] for p in pairs])
    raw = np.array([p[1] for p in pairs])
    factor = float(np.mean(truth / raw))

    err_before = np.abs(raw - truth)
    err_after = np.abs(raw * factor - truth)

    print(f"\nmatched pairs        : {len(pairs)}  (unmatched {unmatched})")
    print(f"height_correction    : {factor:.4f}")
    print()
    print(f"  MAE before         : {err_before.mean():6.2f} mm")
    print(f"  MAE after          : {err_after.mean():6.2f} mm")
    print(f"  p95 before         : {np.percentile(err_before, 95):6.2f} mm")
    print(f"  p95 after          : {np.percentile(err_after, 95):6.2f} mm")

    if args.write:
        constants = {}
        if CONSTANTS.exists():
            constants = json.loads(CONSTANTS.read_text(encoding="utf-8"))
        # Preserve any keys we do not own (e2e_mode, accept_threshold, ...).
        constants["height_correction"] = round(factor, 4)
        CONSTANTS.write_text(json.dumps(constants, indent=2), encoding="utf-8")
        print(f"\nWrote height_correction to {CONSTANTS}")
    else:
        print("\n--no-write: constants.json left untouched (dry run).")

    echo_config(
        args.out / "calibrate_size.json",
        script="calibrate_size.py", weights=str(args.weights) if use_model else None,
        imgsz=args.imgsz, matched_pairs=len(pairs), unmatched=unmatched,
        height_correction=round(factor, 4),
        mae_before_mm=round(float(err_before.mean()), 3),
        mae_after_mm=round(float(err_after.mean()), 3),
        p95_before_mm=round(float(np.percentile(err_before, 95)), 3),
        p95_after_mm=round(float(np.percentile(err_after, 95)), 3),
        wrote_constants=bool(args.write),
    )

    print(f"\nPITCH NUMBER: size estimate within +/- {err_after.mean():.1f} mm "
          f"of caliper (n={len(pairs)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
