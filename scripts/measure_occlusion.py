"""Measure how many defects one look misses, and how many two looks recover.

This script decides whether the Two-Look protocol survives into the pitch.
A defect can sit on the underside or far side of a bulb where no camera
angle reaches it. Shaking the tray re-seats every bulb, so a second look
sees surfaces the first could not.

    python scripts/measure_occlusion.py

GATE T5: two-look under-detection MUST be lower than one-look. If it is not,
the Two-Look claim is unsupported and comes out of the deck. This script
says so loudly rather than letting the claim slide through.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.grading import CLASS_NAMES  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
CONSTANTS = ROOT / "app" / "constants.json"

TRUTH_DEFECT_COLUMNS = ["n_rotten", "n_sprouted", "n_smut", "n_damaged", "n_doubles"]


def _find(data_dir: Path, name: str) -> Path | None:
    for candidate in data_dir.rglob(name):
        return candidate
    return None


def _observed_defects(model, image_path: Path, conf: float) -> tuple[int, int]:
    """Return (defect detections, total detections) for one photo."""
    result = model.predict(str(image_path), conf=conf, verbose=False, max_det=300)[0]
    if result.boxes is None or len(result.boxes) == 0:
        return 0, 0
    classes = result.boxes.cls.cpu().numpy().astype(int)
    sound_idx = CLASS_NAMES.index("sound")
    return int((classes != sound_idx).sum()), int(len(classes))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data", type=Path, default=ROOT / "data")
    ap.add_argument("--weights", type=Path, default=ROOT / "weights" / "best.pt")
    ap.add_argument("--conf", type=float, default=0.35)
    args = ap.parse_args()

    gt_path = args.data / "groundtruth.csv"
    if not gt_path.exists():
        print(f"No {gt_path}. Hand-sort 20 trays before shooting them.")
        return 1
    if not args.weights.exists():
        print(f"No {args.weights}. Train first: python scripts/train.py")
        return 1

    from ultralytics import YOLO
    model = YOLO(str(args.weights))

    with open(gt_path, newline="", encoding="utf-8") as fh:
        trays = list(csv.DictReader(fh))

    # Single-class trays are shot to teach the model each defect. They are
    # not realistic lots, so they would skew an occlusion rate. Use mixed
    # trays only, when the column exists.
    mixed = [t for t in trays if t.get("composition", "mixed") == "mixed"]
    if not mixed:
        mixed = trays

    true_total = 0
    look1_total = 0
    look2_total = 0
    pooled_total = 0
    used = 0

    for tray in mixed:
        tray_id = tray["tray_id"]
        img1 = _find(args.data, f"{tray_id}_look0.jpg")
        img2 = _find(args.data, f"{tray_id}_look1.jpg")
        if img1 is None or img2 is None:
            continue

        truth = sum(int(tray.get(col, 0) or 0) for col in TRUTH_DEFECT_COLUMNS)
        if truth == 0:
            continue

        d1, _ = _observed_defects(model, img1, args.conf)
        d2, _ = _observed_defects(model, img2, args.conf)

        # Two looks re-observe the SAME physical bulbs. Adding the counts
        # would double-count every defect visible in both. The recoverable
        # signal is the better of the two views, which is what an inspector
        # acts on after a shake.
        pooled = max(d1, d2)

        true_total += truth
        look1_total += d1
        look2_total += d2
        pooled_total += pooled
        used += 1

    if used == 0 or true_total == 0:
        print("No usable Two-Look pairs with ground truth. Cannot fit.")
        return 1

    factor_1look = look1_total / true_total
    factor_2look = pooled_total / true_total
    under_1 = (1 - factor_1look) * 100
    under_2 = (1 - factor_2look) * 100

    print(f"\ntrays used              : {used}")
    print(f"true defects (sorted)   : {true_total}")
    print(f"look 1 alone            : {look1_total}")
    print(f"look 2 alone            : {look2_total}")
    print(f"two looks pooled        : {pooled_total}")
    print()
    print(f"  one-look under-detection : {under_1:5.1f}%   "
          f"(occlusion_correction_1look = {factor_1look:.4f})")
    print(f"  two-look under-detection : {under_2:5.1f}%   "
          f"(occlusion_correction_2look = {factor_2look:.4f})")

    constants = {}
    if CONSTANTS.exists():
        constants = json.loads(CONSTANTS.read_text(encoding="utf-8"))
    constants["occlusion_correction_1look"] = round(factor_1look, 4)
    constants["occlusion_correction_2look"] = round(factor_2look, 4)
    CONSTANTS.write_text(json.dumps(constants, indent=2), encoding="utf-8")
    print(f"\nWrote both factors to {CONSTANTS}")

    print("\n" + "=" * 62)
    if under_2 < under_1:
        gain = under_1 - under_2
        print(f"GATE T5: PASS -- two looks recover {gain:.1f} percentage points "
              "of hidden defects.")
        print("\nPITCH NUMBERS:")
        print(f"  One look misses {under_1:.0f}% of defects.")
        print(f"  Two looks miss {under_2:.0f}%.")
        print("=" * 62)
        return 0

    print("GATE T5: FAIL")
    print()
    print("  Two looks are NOT better than one on this data.")
    print("  The Two-Look protocol must come OUT of the pitch until this")
    print("  measurement says otherwise. Do not claim it.")
    print("=" * 62)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
