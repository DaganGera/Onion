"""The metric that actually matters: lot-percentage error.

SAMA's job is not classifying individual onions. It is telling a procurement
officer and a farmer what percentage of THIS LOT is Grade A, accurately
enough that both sign the certificate. mAP does not measure that. This does.

    python scripts/eval_lot.py

Compares predicted Grade-A and defect percentages against hand-sorted tray
counts, for 1-look and 2-look inputs separately, and prints the headline
sentence for the pitch.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.grading import (  # noqa: E402
    bulb_diameter_mm, decide, detect_scale, merge_looks, size_grade,
)

ROOT = Path(__file__).resolve().parents[1]
DEFECT_COLUMNS = ["n_rotten", "n_sprouted", "n_smut", "n_damaged", "n_doubles"]


def _find(data_dir: Path, name: str) -> Path | None:
    for candidate in data_dir.rglob(name):
        return candidate
    return None


def _analyse(model, image_path: Path, conf: float) -> list[dict]:
    """Run the real inference path and return per-bulb records."""
    img = cv2.imread(str(image_path))
    if img is None:
        return []
    scale = detect_scale(img)
    result = model.predict(img, conf=conf, verbose=False, max_det=300)[0]
    if result.boxes is None or len(result.boxes) == 0:
        return []

    bulbs = []
    for bbox, cls, cf in zip(result.boxes.xyxy.cpu().numpy(),
                             result.boxes.cls.cpu().numpy(),
                             result.boxes.conf.cpu().numpy()):
        diameter = bulb_diameter_mm(bbox, scale)
        bulbs.append({
            "cls": int(cls),
            "confidence": float(cf),
            "diameter_mm": diameter,
            "size_grade": size_grade(diameter),
            "decision": decide(float(cf)),
        })
    return bulbs


def _truth_percentages(tray: dict) -> tuple[float, float] | None:
    total = int(tray.get("n_total", 0) or 0)
    if total <= 0:
        return None
    grade_a = int(tray.get("n_grade_A", 0) or 0)
    defects = sum(int(tray.get(c, 0) or 0) for c in DEFECT_COLUMNS)
    return 100.0 * grade_a / total, 100.0 * defects / total


def _report(name: str, pred: list[float], true: list[float]) -> dict:
    errors = np.abs(np.array(pred) - np.array(true))
    return {
        "name": name,
        "n": len(pred),
        "mae": float(errors.mean()) if len(errors) else float("nan"),
        "p95": float(np.percentile(errors, 95)) if len(errors) else float("nan"),
        "bias": float((np.array(pred) - np.array(true)).mean()) if len(errors) else 0.0,
    }


def _scatter(pairs: dict[str, tuple[list[float], list[float]]], out: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, len(pairs), figsize=(5 * len(pairs), 5), squeeze=False)
    for ax, (title, (pred, true)) in zip(axes[0], pairs.items()):
        ax.plot([0, 100], [0, 100], "--", color="#888", lw=1)
        ax.scatter(true, pred, s=26, alpha=0.75, color="#166534")
        ax.set_xlabel("hand-sorted %")
        ax.set_ylabel("predicted %")
        ax.set_title(title)
        ax.set_xlim(0, 100)
        ax.set_ylim(0, 100)
    fig.tight_layout()
    fig.savefig(out, dpi=130)
    plt.close(fig)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data", type=Path, default=ROOT / "data")
    ap.add_argument("--weights", type=Path, default=ROOT / "weights" / "best.pt")
    ap.add_argument("--conf", type=float, default=0.35)
    ap.add_argument("--out", type=Path, default=ROOT / "runs" / "report")
    args = ap.parse_args()

    gt_path = args.data / "groundtruth.csv"
    if not gt_path.exists():
        print(f"No {gt_path}.")
        return 1
    if not args.weights.exists():
        print(f"No {args.weights}. Train first.")
        return 1

    from ultralytics import YOLO
    model = YOLO(str(args.weights))

    with open(gt_path, newline="", encoding="utf-8") as fh:
        trays = list(csv.DictReader(fh))
    mixed = [t for t in trays if t.get("composition", "mixed") == "mixed"] or trays

    a_pred_1, a_pred_2, a_true = [], [], []
    d_pred_1, d_pred_2, d_true = [], [], []

    for tray in mixed:
        truth = _truth_percentages(tray)
        if truth is None:
            continue
        true_a, true_d = truth

        img1 = _find(args.data, f"{tray['tray_id']}_look0.jpg")
        img2 = _find(args.data, f"{tray['tray_id']}_look1.jpg")
        if img1 is None:
            continue

        look1 = _analyse(model, img1, args.conf)
        if not look1:
            continue
        one = merge_looks([look1])
        a_pred_1.append(one["grade_a_pct"])
        d_pred_1.append(one["defect_rate_corrected"])

        if img2 is not None:
            look2 = _analyse(model, img2, args.conf)
            two = merge_looks([look1, look2])
            a_pred_2.append(two["grade_a_pct"])
            d_pred_2.append(two["defect_rate_corrected"])
        else:
            a_pred_2.append(one["grade_a_pct"])
            d_pred_2.append(one["defect_rate_corrected"])

        a_true.append(true_a)
        d_true.append(true_d)

    if not a_true:
        print("No usable trays.")
        return 1

    reports = [
        _report("Grade A %, 1 look", a_pred_1, a_true),
        _report("Grade A %, 2 looks", a_pred_2, a_true),
        _report("Defect %, 1 look", d_pred_1, d_true),
        _report("Defect %, 2 looks", d_pred_2, d_true),
    ]

    print(f"\n{'metric':<22}{'n':>5}{'MAE':>9}{'p95':>9}{'bias':>9}")
    print("-" * 54)
    for r in reports:
        print(f"{r['name']:<22}{r['n']:>5}{r['mae']:>9.2f}{r['p95']:>9.2f}{r['bias']:>+9.2f}")

    args.out.mkdir(parents=True, exist_ok=True)
    with open(args.out / "lot_metrics.csv", "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(reports[0]))
        writer.writeheader()
        writer.writerows(reports)

    _scatter({"Grade A %, 1 look": (a_pred_1, a_true),
              "Grade A %, 2 looks": (a_pred_2, a_true)},
             args.out / "lot_scatter.png")

    best = min(reports[:2], key=lambda r: r["mae"])
    print("\nPITCH NUMBER:")
    print(f'  "Lot Grade-A percentage estimated within {best["mae"]:.1f} points '
          f'on average (n={best["n"]} trays)."')
    print(f"\nWrote {args.out / 'lot_metrics.csv'} and lot_scatter.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
