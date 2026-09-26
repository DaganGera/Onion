"""The metric that actually matters: lot-percentage error.

SAMA's job is not classifying individual onions. It is telling a procurement
officer and a farmer what percentage of THIS LOT is Grade A, accurately
enough that both sign the certificate. mAP does not measure that. This does.

    python scripts/eval_lot.py

Compares predicted Grade-A and defect percentages against hand-sorted tray
counts, for 1-look and 2-look inputs separately, and prints the headline
sentence for the pitch.

Reporting is three layers:
  - the aggregate table (MAE / p95 / bias per metric),
  - runs/report/lot_per_tray.csv -- EVERY tray's true vs predicted values
    with signed and absolute errors. An aggregate MAE hides the two trays
    that are off by 15 points; this file makes them un-hideable,
  - a histogram of absolute errors plus the worst offenders of whichever
    report becomes the pitch number.

Inference mode is PINNED: end2end from app/constants.json (the mode the app
actually ships), imgsz 1024, max_det 300 -- identical to deployment, so an
eval number is transferable to the demo.
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
from scripts.run_config import (  # noqa: E402
    echo_config, resolve_e2e_mode, yolo26_inference_kwargs,
)

ROOT = Path(__file__).resolve().parents[1]
DEFECT_COLUMNS = ["n_rotten", "n_sprouted", "n_smut", "n_damaged", "n_doubles"]

# Report display name -> (predicted column, abs-error column) in per-tray rows.
REPORT_COLUMNS = {
    "Grade A %, 1 look": ("pred_grade_a_1look", "abs_err_grade_a_1look"),
    "Grade A %, 2 looks": ("pred_grade_a_2look", "abs_err_grade_a_2look"),
    "Defect %, 1 look": ("pred_defect_1look", "abs_err_defect_1look"),
    "Defect %, 2 looks": ("pred_defect_2look", "abs_err_defect_2look"),
}


def _find(data_dir: Path, name: str) -> Path | None:
    for candidate in data_dir.rglob(name):
        return candidate
    return None


def _analyse(model, image_path: Path, conf: float, predict_kwargs: dict) -> list[dict]:
    """Run the real inference path and return per-bulb records."""
    img = cv2.imread(str(image_path))
    if img is None:
        return []
    scale = detect_scale(img)
    result = model.predict(img, conf=conf, verbose=False, **predict_kwargs)[0]
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


def _per_tray_row(tray_id: str, true_a: float, true_d: float,
                  pred_a_1: float, pred_d_1: float,
                  pred_a_2: float | None, pred_d_2: float | None) -> dict:
    """One tray's error record -- the unit the aggregate table averages over.

    Signed errors keep the direction (over-predicting Grade A flatters the
    farmer, under-predicting it flatters the buyer; both matter). Absolute
    errors feed MAE/p95. When only one photo exists, the 2-look columns
    carry the 1-look estimate and n_looks_used=1 flags the degraded case --
    that mixed population was previously invisible.
    """
    row = {
        "tray_id": tray_id,
        "true_grade_a_pct": true_a,
        "true_defect_pct": true_d,
        "pred_grade_a_1look": pred_a_1,
        "err_grade_a_1look": pred_a_1 - true_a,
        "abs_err_grade_a_1look": abs(pred_a_1 - true_a),
        "pred_defect_1look": pred_d_1,
        "err_defect_1look": pred_d_1 - true_d,
        "abs_err_defect_1look": abs(pred_d_1 - true_d),
    }
    if pred_a_2 is None or pred_d_2 is None:
        row["n_looks_used"] = 1
        row["pred_grade_a_2look"] = pred_a_1
        row["err_grade_a_2look"] = pred_a_1 - true_a
        row["abs_err_grade_a_2look"] = abs(pred_a_1 - true_a)
        row["pred_defect_2look"] = pred_d_1
        row["err_defect_2look"] = pred_d_1 - true_d
        row["abs_err_defect_2look"] = abs(pred_d_1 - true_d)
    else:
        row["n_looks_used"] = 2
        row["pred_grade_a_2look"] = pred_a_2
        row["err_grade_a_2look"] = pred_a_2 - true_a
        row["abs_err_grade_a_2look"] = abs(pred_a_2 - true_a)
        row["pred_defect_2look"] = pred_d_2
        row["err_defect_2look"] = pred_d_2 - true_d
        row["abs_err_defect_2look"] = abs(pred_d_2 - true_d)
    return row


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


def _error_histogram(rows: list[dict], out: Path) -> None:
    """Where does the error LIVE? One bad tray under a smooth average is
    exactly what a signed certificate must not hide."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    one = [r["abs_err_grade_a_1look"] for r in rows]
    two = [r["abs_err_grade_a_2look"] for r in rows]
    hi = max(one + two + [1.0]) * 1.05

    fig, ax = plt.subplots(figsize=(7, 4.5))
    bins = np.linspace(0, hi, 21)
    ax.hist(one, bins=bins, alpha=0.65, label="Grade A %, 1 look", color="#b45309")
    ax.hist(two, bins=bins, alpha=0.65, label="Grade A %, 2 looks", color="#166534")
    ax.set_xlabel("|predicted − hand-sorted| (percentage points)")
    ax.set_ylabel("trays")
    ax.set_title("Per-lot Grade-A error distribution")
    ax.legend()
    fig.tight_layout()
    fig.savefig(out, dpi=130)
    plt.close(fig)


def _print_worst(rows: list[dict], report_name: str, k: int = 5) -> None:
    _, abs_col = REPORT_COLUMNS[report_name]
    worst = sorted(rows, key=lambda r: r[abs_col], reverse=True)[:k]
    print(f"\nworst trays ({report_name}):")
    print(f"{'tray_id':<16}{'|err|':>8}{'signed':>9}{'looks':>7}")
    for r in worst:
        signed_col = abs_col.replace("abs_", "", 1)
        print(f"{str(r['tray_id']):<16}{r[abs_col]:>8.2f}"
              f"{r[signed_col]:>+9.2f}{r['n_looks_used']:>7d}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data", type=Path, default=ROOT / "data")
    ap.add_argument("--weights", type=Path, default=ROOT / "weights" / "best.pt")
    ap.add_argument("--conf", type=float, default=0.35)
    ap.add_argument("--imgsz", type=int, default=1024,
                    help="inference resolution; protocol pins this at 1024")
    ap.add_argument("--out", type=Path, default=ROOT / "runs" / "report")
    args = ap.parse_args()

    gt_path = args.data / "groundtruth.csv"
    if not gt_path.exists():
        print(f"No {gt_path}.")
        return 1
    if not args.weights.exists():
        print(f"No {args.weights}. Train first.")
        return 1
    if args.imgsz != 1024:
        print(f"WARNING: --imgsz {args.imgsz} breaks protocol; small defects "
              "need 1024.")

    # Same inference mode as the deployed app -- read once, pass explicitly.
    # Before this, predict() silently used Ultralytics' own default mode,
    # so eval numbers were measured on a different detector than we ship.
    e2e_mode = resolve_e2e_mode()
    predict_kwargs = yolo26_inference_kwargs(args.imgsz)
    print(f"inference mode: end2end={e2e_mode} (app/constants.json), "
          f"imgsz={args.imgsz}, max_det=300")

    from ultralytics import YOLO
    model = YOLO(str(args.weights))

    with open(gt_path, newline="", encoding="utf-8") as fh:
        trays = list(csv.DictReader(fh))
    mixed = [t for t in trays if t.get("composition", "mixed") == "mixed"] or trays

    rows: list[dict] = []
    skipped_no_truth = skipped_no_photo = skipped_no_detections = 0

    for tray in mixed:
        truth = _truth_percentages(tray)
        if truth is None:
            skipped_no_truth += 1
            continue
        true_a, true_d = truth

        img1 = _find(args.data, f"{tray['tray_id']}_look0.jpg")
        img2 = _find(args.data, f"{tray['tray_id']}_look1.jpg")
        if img1 is None:
            skipped_no_photo += 1
            continue

        look1 = _analyse(model, img1, args.conf, predict_kwargs)
        if not look1:
            skipped_no_detections += 1
            continue
        one = merge_looks([look1])

        pred_a_2 = pred_d_2 = None
        if img2 is not None:
            look2 = _analyse(model, img2, args.conf, predict_kwargs)
            two = merge_looks([look1, look2])
            pred_a_2 = two["grade_a_pct"]
            pred_d_2 = two["defect_rate_corrected"]

        rows.append(_per_tray_row(
            tray["tray_id"], true_a, true_d,
            one["grade_a_pct"], one["defect_rate_corrected"],
            pred_a_2, pred_d_2))

    if not rows:
        print("No usable trays.")
        return 1

    def col(name: str) -> list[float]:
        pred_col, _ = REPORT_COLUMNS[name]
        return [r[pred_col] for r in rows]

    def truth(which: str) -> list[float]:
        key = "true_grade_a_pct" if which.startswith("Grade") else "true_defect_pct"
        return [r[key] for r in rows]

    reports = [
        _report("Grade A %, 1 look", col("Grade A %, 1 look"), truth("Grade A")),
        _report("Grade A %, 2 looks", col("Grade A %, 2 looks"), truth("Grade A")),
        _report("Defect %, 1 look", col("Defect %, 1 look"), truth("Defect")),
        _report("Defect %, 2 looks", col("Defect %, 2 looks"), truth("Defect")),
    ]

    n_single_photo = sum(1 for r in rows if r["n_looks_used"] == 1)
    print(f"\ntrays scored: {len(rows)}   "
          f"(skipped: {skipped_no_truth} no ground truth, "
          f"{skipped_no_photo} no photo, "
          f"{skipped_no_detections} no detections; "
          f"{n_single_photo} of the scored trays had only one photo)")

    print(f"\n{'metric':<22}{'n':>5}{'MAE':>9}{'p95':>9}{'bias':>9}")
    print("-" * 54)
    for r in reports:
        print(f"{r['name']:<22}{r['n']:>5}{r['mae']:>9.2f}{r['p95']:>9.2f}{r['bias']:>+9.2f}")

    args.out.mkdir(parents=True, exist_ok=True)

    fieldnames = ["tray_id", "n_looks_used",
                  "true_grade_a_pct", "true_defect_pct",
                  "pred_grade_a_1look", "err_grade_a_1look", "abs_err_grade_a_1look",
                  "pred_defect_1look", "err_defect_1look", "abs_err_defect_1look",
                  "pred_grade_a_2look", "err_grade_a_2look", "abs_err_grade_a_2look",
                  "pred_defect_2look", "err_defect_2look", "abs_err_defect_2look"]
    with open(args.out / "lot_per_tray.csv", "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    with open(args.out / "lot_metrics.csv", "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(reports[0]))
        writer.writeheader()
        writer.writerows(reports)

    _scatter({"Grade A %, 1 look": (col("Grade A %, 1 look"), truth("Grade A")),
              "Grade A %, 2 looks": (col("Grade A %, 2 looks"), truth("Grade A"))},
             args.out / "lot_scatter.png")
    _error_histogram(rows, args.out / "lot_error_hist.png")

    best = min(reports[:2], key=lambda r: r["mae"])
    print("\nPITCH NUMBER:")
    print(f'  "Lot Grade-A percentage estimated within {best["mae"]:.1f} points '
          f'on average (n={best["n"]} trays)."')
    _print_worst(rows, best["name"])
    print(f"\nWrote {args.out / 'lot_metrics.csv'}, lot_per_tray.csv, "
          "lot_scatter.png and lot_error_hist.png")

    echo_config(
        args.out / "lot_run_config.json",
        script="eval_lot.py", weights=str(args.weights), conf=args.conf,
        imgsz=args.imgsz, max_det=300, e2e_mode=e2e_mode,
        data=str(args.data), trays_scored=len(rows),
        trays_skipped_no_truth=skipped_no_truth,
        trays_skipped_no_photo=skipped_no_photo,
        trays_skipped_no_detections=skipped_no_detections,
        single_photo_trays=n_single_photo,
        pitch_metric=best["name"], pitch_mae=round(best["mae"], 4),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
