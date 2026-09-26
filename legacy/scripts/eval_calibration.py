"""Measure whether detector confidence tells the truth -- then feed the
REFER threshold with what it says.

    python scripts/eval_calibration.py [--split valid] [--write-threshold]

The ACCEPT/REFER policy promises that a call at or above the threshold is a
machine call you do not need to double-check. This script measures whether
the promise holds: it runs the DEPLOYED inference path over hand-labelled
trays, matches every detection against ground truth (same class, IoU >= 0.5,
greedy highest-confidence-first), and treats each detection as one
(confidence, was-it-right) sample. From those pairs it reports:

  - a reliability diagram (predicted confidence vs observed accuracy),
  - ECE / MCE -- how far, on average and at worst, stated confidence sits
    from observed accuracy,
  - a RECOMMENDED accept threshold: the smallest cut whose top slice is
    right at least --target of the time with >= --min-support samples,
  - a binary temperature-scaling fit that would de-bias the confidences.

Reporting is honest by construction:
  - everything here is MEASURED on labelled data, never simulated;
  - an unmeetable target returns NO recommendation rather than a quietly
    lowered bar;
  - --write-threshold is OPT-IN and refuses cuts outside [0.30, 0.95]:
    moving a signed-certificate threshold is a human decision, this script
    only earns the right to propose one.

Inference mode is PINNED: end2end from app/constants.json, imgsz 1024,
max_det 300 -- identical to deployment, so the calibration transfers.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import calibration as cal          # noqa: E402
from app import grading                     # noqa: E402
from scripts.run_config import (            # noqa: E402
    echo_config, resolve_e2e_mode, yolo26_inference_kwargs,
)

ROOT = Path(__file__).resolve().parents[1]
CONSTANTS_PATH = ROOT / "app" / "constants.json"
SPLITS = ("valid", "test", "train", "holdout")

# A proposed certificate threshold must stay inside human sense. Outside
# this band something is wrong with the DATA, and writing it anyway would
# launder a measurement bug into a signed policy.
SAFE_THRESHOLD_BAND = (0.30, 0.95)

ASSUMPTIONS = [
    "correctness = same-class match at IoU >= threshold, greedy "
    "highest-confidence-first (standard detection protocol)",
    "unmatched ground-truth boxes lower recall but contribute no "
    "(confidence, correctness) pair -- they carry no predicted confidence",
    "confidence is treated as P(this call is correct); calibration error "
    "is measured against that definition, not against class-posterior "
    "semantics",
]


def _load_gt_boxes(label_path: Path, w: int, h: int) -> list[tuple[int, float, float, float, float]]:
    """YOLO normalised cx,cy,w,h lines -> pixel xyxy + class."""
    out = []
    if not label_path.exists():
        return out
    for line in label_path.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) < 5:
            continue
        cls, cx, cy, bw, bh = (int(parts[0]), *(float(x) for x in parts[1:5]))
        x0, y0 = (cx - bw / 2) * w, (cy - bh / 2) * h
        x1, y1 = (cx + bw / 2) * w, (cy + bh / 2) * h
        out.append((cls, x0, y0, x1, y1))
    return out


def _iou_matrix(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """a: [n,4] xyxy, b: [m,4] xyxy -> [n,m] IoU."""
    if len(a) == 0 or len(b) == 0:
        return np.zeros((len(a), len(b)))
    lt = np.maximum(a[:, None, :2], b[None, :, :2])
    rb = np.minimum(a[:, None, 2:], b[None, :, 2:])
    wh = np.clip(rb - lt, 0, None)
    inter = wh[..., 0] * wh[..., 1]
    area_a = (a[:, 2] - a[:, 0]) * (a[:, 3] - a[:, 1])
    area_b = (b[:, 2] - b[:, 0]) * (b[:, 3] - b[:, 1])
    union = area_a[:, None] + area_b[None, :] - inter
    return np.where(union > 0, inter / union, 0.0)


def collect_pairs(model, image_paths: list[Path], labels_dir: Path,
                  conf_floor: float, iou_thresh: float,
                  predict_kwargs: dict) -> dict:
    """Run the deployed inference path; return (conf, correct) pairs plus
    raw counts for precision/recall accounting."""
    confs: list[float] = []
    correct: list[int] = []
    n_gt_total = 0

    for img_path in sorted(image_paths):
        img = cv2.imread(str(img_path))
        if img is None:
            continue
        h, w = img.shape[:2]
        gt = _load_gt_boxes(labels_dir / f"{img_path.stem}.txt", w, h)
        n_gt_total += len(gt)
        result = model.predict(img, conf=conf_floor, verbose=False,
                               **predict_kwargs)[0]
        if result.boxes is None or len(result.boxes) == 0:
            continue

        boxes = result.boxes.xyxy.cpu().numpy()
        clss = result.boxes.cls.cpu().numpy().astype(int)
        scores = result.boxes.conf.cpu().numpy()

        order = np.argsort(-scores, kind="stable")   # greedy: best first
        gt_matched = np.zeros(len(gt), dtype=bool)
        gt_cls = np.array([g[0] for g in gt]) if gt else np.zeros(0, dtype=int)
        gt_xyxy = np.array([g[1:] for g in gt]) if gt else np.zeros((0, 4))
        ious = _iou_matrix(boxes[order], gt_xyxy) if len(gt) else \
            np.zeros((len(order), 0))

        for i_row, p_idx in enumerate(order):
            hit = False
            if len(gt):
                cand = np.where(~gt_matched &
                                (gt_cls == int(clss[p_idx])))[0]
                if len(cand):
                    best = cand[np.argmax(ious[i_row, cand])]
                    if ious[i_row, best] >= iou_thresh:
                        gt_matched[best] = True
                        hit = True
            confs.append(float(scores[p_idx]))
            correct.append(1 if hit else 0)

    return {
        "confs": np.array(confs, dtype=float),
        "correct": np.array(correct, dtype=float),
        "n_ground_truths": n_gt_total,
    }


def _prf(pairs: dict, threshold: float) -> dict | None:
    """Precision / recall / F1 among detections at or above a cut."""
    confs, corr = pairs["confs"], pairs["correct"]
    sel = confs >= threshold
    tp = int(corr[sel].sum())
    called = int(sel.sum())
    if called == 0 or pairs["n_ground_truths"] == 0:
        return None
    precision = tp / called
    recall = tp / pairs["n_ground_truths"]
    f1 = 2 * precision * recall / (precision + recall) \
        if (precision + recall) > 0 else 0.0
    return {
        "threshold": round(float(threshold), 4),
        "called": called,
        "true_positives": tp,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
    }


def _diagram(rel: dict, current_t: float, rec_t: float | None, out: Path,
             title: str) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(5.5, 5.5))
    ax.plot([0, 1], [0, 1], "--", color="#888", lw=1,
            label="perfectly calibrated")
    xs = [b["mean_conf"] for b in rel["bins"] if b["count"]]
    ys = [b["accuracy"] for b in rel["bins"] if b["count"]]
    ax.plot(xs, ys, "o-", color="#166534", label="observed accuracy")
    ax.axvline(current_t, color="#b45309", ls=":",
               label=f"ACCEPT threshold {current_t:.2f}")
    if rec_t is not None:
        ax.axvline(rec_t, color="#1d4ed8", ls="-.",
                   label=f"recommended {rec_t:.2f}")
    ax.set_xlabel("stated confidence")
    ax.set_ylabel("observed accuracy")
    ax.set_title(title)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.legend(fontsize=8, loc="upper left")
    fig.tight_layout()
    fig.savefig(out, dpi=130)
    plt.close(fig)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dataset", type=Path, default=ROOT / "data" / "dataset")
    ap.add_argument("--split", choices=SPLITS + ("all",), default="valid")
    ap.add_argument("--weights", type=Path, default=ROOT / "weights" / "best.pt")
    ap.add_argument("--imgsz", type=int, default=1024,
                    help="inference resolution; protocol pins this at 1024")
    ap.add_argument("--conf-floor", type=float, default=0.05,
                    help="lowest confidence scored; low floor widens the "
                         "curve below the operating point")
    ap.add_argument("--iou", type=float, default=0.5)
    ap.add_argument("--target", type=float, default=0.95,
                    help="accuracy the ACCEPT band must demonstrate")
    ap.add_argument("--min-support", type=int, default=30)
    ap.add_argument("--write-threshold", action="store_true",
                    help="OPT-IN: write the recommended cut into "
                         "app/constants.json as accept_threshold")
    ap.add_argument("--out", type=Path, default=ROOT / "runs" / "report")
    args = ap.parse_args()

    if args.imgsz != 1024:
        print(f"WARNING: --imgsz {args.imgsz} breaks protocol; calibration "
              "is only valid at the deployed resolution.")

    if not args.weights.exists():
        print(f"No {args.weights}. Train first.")
        return 1

    if args.split == "all":
        image_paths: list[Path] = []
        for s in SPLITS:
            d = args.dataset / s
            image_paths.extend(
                sorted(p for p in (d / "images").glob("*")
                       if p.suffix.lower() in (".jpg", ".jpeg", ".png")))
    else:
        split_dir = args.dataset / args.split
        if not (split_dir / "images").exists():
            print(f"No image dir at {split_dir / 'images'}.")
            return 1
        image_paths = sorted([p for p in (split_dir / "images").glob("*")
                              if p.suffix.lower() in (".jpg", ".jpeg", ".png")])
    if not image_paths:
        print("No labelled images found for that split.")
        return 1

    e2e_mode = resolve_e2e_mode()
    predict_kwargs = yolo26_inference_kwargs(args.imgsz)
    print(f"inference mode: end2end={e2e_mode} (app/constants.json), "
          f"imgsz={args.imgsz}, max_det=300, conf>={args.conf_floor}, "
          f"IoU>={args.iou}")

    from ultralytics import YOLO
    model = YOLO(str(args.weights))

    # Per-image label dirs: 'all' spans splits, so resolve per stem.
    def labels_for(stem: str) -> Path | None:
        for s in SPLITS:
            cand = args.dataset / s / "labels" / f"{stem}.txt"
            if cand.exists():
                return cand.parent
        return None

    # Group images by their label directory once, then measure.
    by_labels: dict[Path, list[Path]] = {}
    for p in image_paths:
        lab = labels_for(p.stem)
        if lab is None:
            continue
        by_labels.setdefault(lab, []).append(p)
    if not by_labels:
        print("No matching label files for any image.")
        return 1

    pairs = {"confs": np.zeros(0), "correct": np.zeros(0),
             "n_ground_truths": 0}
    for lab_dir, imgs in by_labels.items():
        chunk = collect_pairs(model, imgs, lab_dir, args.conf_floor,
                              args.iou, predict_kwargs)
        pairs["confs"] = np.concatenate([pairs["confs"], chunk["confs"]])
        pairs["correct"] = np.concatenate([pairs["correct"], chunk["correct"]])
        pairs["n_ground_truths"] += chunk["n_ground_truths"]

    n_det = int(pairs["confs"].size)
    if n_det == 0:
        print("No detections at all -- nothing to calibrate.")
        return 1

    current_t = float(grading.CONSTANTS.get("accept_threshold", 0.75))

    rel = cal.reliability(pairs["confs"], pairs["correct"], n_bins=10,
                          min_bin_count=5)
    fit = cal.fit_temperature(pairs["confs"], pairs["correct"])
    rec = cal.recommend_threshold(pairs["confs"], pairs["correct"],
                                  target_accuracy=args.target,
                                  min_support=args.min_support)

    print(f"\ndetections scored : {n_det}   "
          f"ground-truth boxes: {pairs['n_ground_truths']}")
    print(f"ECE               : {rel['ece']:.4f}   "
          f"(mean |stated confidence - observed accuracy|)")
    print(f"MCE               : {rel['mce']:.4f}   (worst bin)")
    print(f"\n{'band':<14}{'n':>7}{'mean conf':>11}{'observed':>10}")
    for b in rel["bins"]:
        if b["mean_conf"] is not None:
            print(f"[{b['lo']:.1f}-{b['hi']:.1f})  {b['count']:>7}"
                  f"{b['mean_conf']:>11.3f}{b['accuracy']:>10.3f}")
        elif b["count"]:
            print(f"[{b['lo']:.1f}-{b['hi']:.1f})  {b['count']:>7}"
                  f"   too few samples")
        else:
            print(f"[{b['lo']:.1f}-{b['hi']:.1f})        0      no evidence")

    print(f"\ntemperature fit   : T={fit['temperature']}  "
          f"ECE {fit['ece_before']:.4f} -> {fit['ece_after']:.4f}")
    m_now = _prf(pairs, current_t)
    if m_now:
        print(f"at current ACCEPT >= {current_t:.2f}: "
              f"precision {m_now['precision']:.3f}  "
              f"recall {m_now['recall']:.3f}  "
              f"F1 {m_now['f1']:.3f}  ({m_now['called']} called)")

    if rec is None:
        print(f"\nRECOMMENDATION: none -- no reachable cut reaches "
              f"{args.target:.0%} accuracy with >= {args.min_support} "
              f"samples. Current threshold stands; retrain before trusting "
              f"the band, not after.")
    else:
        print(f"\nRECOMMENDATION: smallest trustworthy cut = "
              f"{rec['threshold']:.2f} "
              f"(right {rec['achieved_accuracy']:.1%} of "
              f"{rec['support']} calls; {rec['referred']} calls would move "
              f"to REFER)")

    wrote = False
    if args.write_threshold:
        if rec is None:
            print("--write-threshold refused: no qualifying recommendation.")
        elif not (SAFE_THRESHOLD_BAND[0] <= rec["threshold"]
                  <= SAFE_THRESHOLD_BAND[1]):
            print(f"--write-threshold refused: {rec['threshold']:.2f} outside "
                  f"safe band {SAFE_THRESHOLD_BAND}.")
        elif abs(rec["threshold"] - current_t) < 1e-9:
            print(f"--write-threshold: recommended cut equals the current "
                  f"one ({current_t}); constants.json untouched.")
        else:
            constants = {}
            if CONSTANTS_PATH.exists():
                constants = json.loads(
                    CONSTANTS_PATH.read_text(encoding="utf-8"))
            constants["accept_threshold"] = round(rec["threshold"], 4)
            CONSTANTS_PATH.write_text(json.dumps(constants, indent=2),
                                      encoding="utf-8")
            wrote = True
            print(f"Wrote accept_threshold {current_t} -> "
                  f"{constants['accept_threshold']} to {CONSTANTS_PATH}")

    args.out.mkdir(parents=True, exist_ok=True)
    report = {
        "kind": "detection_calibration",
        "labels": {"reliability": "measured", "recommendation": "measured",
                   "temperature_fit": "fitted on measured pairs"},
        "split": args.split,
        "n_images": len(image_paths),
        "n_detections": n_det,
        "n_ground_truths": pairs["n_ground_truths"],
        "iou_match": args.iou,
        "confidence_floor": args.conf_floor,
        "current_threshold": current_t,
        "reliability": rel,
        "recommendation": rec,
        "temperature_fit": fit,
        "detection_metrics": {"at_current_threshold": m_now},
        "assumptions": ASSUMPTIONS,
    }
    report.update(echo_config(
        out_path=None,
        script="eval_calibration.py", weights=str(args.weights),
        imgsz=args.imgsz, max_det=300, e2e_mode=e2e_mode,
        target_accuracy=args.target, min_support=args.min_support,
        wrote_threshold=wrote,
    ))
    (args.out / "calibration.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8")

    rec_t = rec["threshold"] if rec else None
    _diagram(rel, current_t, rec_t, args.out / "reliability_diagram.png",
             f"Reliability, {args.split} (ECE {rel['ece']:.3f})")
    echo_config(
        args.out / "calibration_run_config.json",
        script="eval_calibration.py", split=args.split,
        detections=n_det, ece=rel["ece"], mce=rel["mce"],
        recommended_threshold=rec_t, wrote_threshold=wrote,
    )

    if rec is not None:
        print(f"\nPITCH NUMBER: detector confidence within "
              f"{rel['ece'] * 100:.1f} points of its true accuracy "
              f"(ECE, n={n_det}); trustworthy auto-accept cut measured at "
              f"{rec['threshold']:.2f}.")
    else:
        print(f"\nPITCH NUMBER: detector confidence within "
              f"{rel['ece'] * 100:.1f} points of its true accuracy "
              f"(ECE, n={n_det}).")
    print(f"Wrote {args.out / 'calibration.json'}, "
          f"reliability_diagram.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
