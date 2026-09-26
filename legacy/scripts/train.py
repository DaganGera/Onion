"""Train the YOLO26 defect detector and evaluate it on the holdout set.

    python scripts/train.py --model yolo26s.pt --imgsz 1024 --batch 12 --epochs 120

Evaluates BOTH inference modes -- end2end=True (NMS-free) and end2end=False
(NMS path) -- because YOLO26's one-to-one head trades roughly 0.5 mAP for
speed. Which one we ship is a measurement, not an assumption.

Reproducibility: the run is seeded (--seed, default 0) and trained with
deterministic=True, and runs/report/<name>/config.json echoes the full run
configuration -- git commit, library versions, seed, every hyperparameter.
Same commit + same data + same config -> comparable numbers.

Prints a one-screen PASS/FAIL summary. You should never need TensorBoard.
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.grading import CLASS_NAMES  # noqa: E402
from scripts.run_config import echo_config  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]

# Gate T4 thresholds, from the project plan.
GATE_SOUND_MAP50 = 0.60
GATE_DEFECT_MAP50 = 0.45
GATE_DEFECT_COUNT = 3


def _holdout_yaml(holdout: Path, out: Path) -> Path:
    """Point a data.yaml at the holdout set so model.val() can score it."""
    names = "\n".join(f"  {i}: {n}" for i, n in enumerate(CLASS_NAMES))
    yaml_path = out / "holdout.yaml"
    yaml_path.write_text(
        f"path: {holdout.resolve().as_posix()}\n"
        "train: images\n"
        "val: images\n"
        f"nc: {len(CLASS_NAMES)}\n"
        f"names:\n{names}\n",
        encoding="utf-8",
    )
    return yaml_path


def _per_class_rows(metrics, mode: str) -> list[dict]:
    rows = []
    box = metrics.box
    for idx, cls_idx in enumerate(box.ap_class_index):
        name = CLASS_NAMES[int(cls_idx)] if int(cls_idx) < len(CLASS_NAMES) else str(cls_idx)
        rows.append({
            "mode": mode,
            "class": name,
            "precision": round(float(box.p[idx]), 4),
            "recall": round(float(box.r[idx]), 4),
            "mAP50": round(float(box.ap50[idx]), 4),
            "mAP50_95": round(float(box.ap[idx]), 4),
        })
    rows.append({
        "mode": mode,
        "class": "ALL",
        "precision": round(float(box.mp), 4),
        "recall": round(float(box.mr), 4),
        "mAP50": round(float(box.map50), 4),
        "mAP50_95": round(float(box.map), 4),
    })
    return rows


def _reliability(model, holdout: Path, report: Path, e2e: bool) -> float:
    """Predicted confidence vs observed precision, in 10 bins.

    Tells us whether the 0.75 ACCEPT threshold means anything. A detector
    that says 0.9 and is right 60% of the time makes the REFER band a lie.
    Returns the fraction of predictions landing below the ACCEPT threshold.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    images = sorted((holdout / "images").glob("*.jpg"))
    confs: list[float] = []
    correct: list[int] = []

    for img_path in images:
        label_path = holdout / "labels" / f"{img_path.stem}.txt"
        truth = []
        if label_path.exists():
            for line in label_path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    parts = line.split()
                    truth.append((int(parts[0]), float(parts[1]), float(parts[2])))

        result = model.predict(str(img_path), conf=0.05, verbose=False,
                               end2end=e2e, max_det=300)[0]
        if result.boxes is None:
            continue

        h, w = result.orig_shape
        for box, cls, conf in zip(result.boxes.xywhn.cpu().numpy(),
                                  result.boxes.cls.cpu().numpy(),
                                  result.boxes.conf.cpu().numpy()):
            # nearest ground-truth box by centre, then check the class matched
            best, best_d = None, 1e9
            for t_cls, t_cx, t_cy in truth:
                d = (box[0] - t_cx) ** 2 + (box[1] - t_cy) ** 2
                if d < best_d:
                    best, best_d = t_cls, d
            hit = best is not None and best == int(cls) and best_d < 0.0015
            confs.append(float(conf))
            correct.append(1 if hit else 0)

    if not confs:
        return 0.0

    confs_arr = np.array(confs)
    correct_arr = np.array(correct)

    edges = np.linspace(0, 1, 11)
    centres, observed = [], []
    for lo, hi in zip(edges[:-1], edges[1:]):
        sel = (confs_arr >= lo) & (confs_arr < hi)
        if sel.sum() >= 5:
            centres.append((lo + hi) / 2)
            observed.append(correct_arr[sel].mean())

    fig, ax = plt.subplots(figsize=(5, 5))
    ax.plot([0, 1], [0, 1], "--", color="#888", label="perfect calibration")
    ax.plot(centres, observed, "o-", color="#166534", label="observed")
    ax.axvline(0.75, color="#b45309", ls=":", label="ACCEPT threshold")
    ax.set_xlabel("predicted confidence")
    ax.set_ylabel("observed accuracy")
    ax.set_title(f"Reliability (end2end={e2e})")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(report / f"reliability_e2e{int(e2e)}.png", dpi=130)
    plt.close(fig)

    return float((confs_arr < 0.75).mean())


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model", default="yolo26s.pt")
    ap.add_argument("--imgsz", type=int, default=1024)
    ap.add_argument("--epochs", type=int, default=120)
    ap.add_argument("--batch", type=int, default=12)
    ap.add_argument("--name", default="s1024")
    ap.add_argument("--data", type=Path, default=ROOT / "data/dataset/data.yaml")
    ap.add_argument("--holdout", type=Path, default=ROOT / "data/holdout")
    ap.add_argument("--device", default="0")
    ap.add_argument("--seed", type=int, default=0,
                    help="training seed; echoed into the run config")
    args = ap.parse_args()

    if "yolo11" in args.model or "yolov8" in args.model:
        print(f"WARNING: --model is {args.model}. This project is YOLO26. "
              "See the YOLO26 rules in CLAUDE.md.")

    # YOLO26 rule guards. Advisory (an experiment may override on purpose),
    # but the defaults are the protocol: 1024 because a black-smut speck is
    # ~12 px at 640 and ~22 px at 1024; batch 12, or 8 under VRAM pressure --
    # never a lower resolution.
    if args.imgsz != 1024:
        print(f"WARNING: --imgsz {args.imgsz} breaks protocol. Small defects "
              "need 1024; if VRAM is short drop --batch to 8 instead.")
    if args.batch not in (8, 12):
        print(f"NOTE: --batch {args.batch} is off-protocol "
              "(12 standard, 8 when VRAM-bound).")

    from ultralytics import YOLO

    report = ROOT / "runs" / "report" / args.name
    report.mkdir(parents=True, exist_ok=True)

    # Config echo BEFORE training starts: a run that dies at epoch 3 still
    # leaves behind what it was trying to be.
    cfg = echo_config(
        report / "config.json",
        script="train.py", model=args.model, imgsz=args.imgsz,
        batch=args.batch, epochs=args.epochs, seed=args.seed,
        deterministic=True, patience=30, data=str(args.data),
        holdout=str(args.holdout), device=args.device,
        project=str(ROOT / "runs" / "detect"), run_name=args.name,
    )

    model = YOLO(args.model)
    model.train(
        data=str(args.data),
        imgsz=args.imgsz,
        epochs=args.epochs,
        batch=args.batch,
        patience=30,
        device=args.device,
        name=args.name,
        project=str(ROOT / "runs" / "detect"),
        seed=args.seed,
        deterministic=True,
        # Tuned for phone-camera and outdoor-light variance, not COCO.
        hsv_h=0.02, hsv_s=0.8, hsv_v=0.5,
        degrees=15, translate=0.1, scale=0.4,
        fliplr=0.5, mosaic=0.8, close_mosaic=15,
        verbose=True,
    )

    best = Path(model.trainer.best)
    weights_dir = ROOT / "weights"
    weights_dir.mkdir(exist_ok=True)
    shutil.copy(best, weights_dir / "best.pt")
    print(f"\nCopied {best} -> weights/best.pt")

    # --- evaluate on the holdout, both inference modes --------------------
    holdout_yaml = _holdout_yaml(args.holdout, report)
    scored = YOLO(str(weights_dir / "best.pt"))

    rows: list[dict] = []
    refer_rates: dict[str, float] = {}
    summary: dict[str, dict] = {}

    for e2e in (False, True):
        label = f"end2end={e2e}"
        print(f"\n--- holdout evaluation, {label} ---")
        metrics = scored.val(data=str(holdout_yaml), imgsz=args.imgsz,
                             device=args.device, end2end=e2e, max_det=300,
                             project=str(report), name=f"val_e2e{int(e2e)}",
                             exist_ok=True, plots=True, verbose=False)
        rows += _per_class_rows(metrics, label)
        summary[label] = {
            r["class"]: r["mAP50"] for r in rows if r["mode"] == label
        }
        refer_rates[label] = _reliability(scored, args.holdout, report, e2e)

    with open(report / "metrics.csv", "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    (report / "refer_rate.txt").write_text(
        "\n".join(f"{k}: {v:.4f} of predictions below the 0.75 ACCEPT threshold"
                  for k, v in refer_rates.items()),
        encoding="utf-8",
    )

    # --- one-screen summary -----------------------------------------------
    print("\n" + "=" * 66)
    print(f"HOLDOUT RESULTS  ({args.name}, {args.model} @ {args.imgsz})")
    print("=" * 66)
    header = f"{'class':<15}" + "".join(f"{m:>22}" for m in summary)
    print(header)
    for name in CLASS_NAMES + ["ALL"]:
        line = f"{name:<15}"
        for mode in summary:
            value = summary[mode].get(name)
            line += f"{'  -' if value is None else f'{value:>22.3f}'}"
        print(line)

    print("\nrefer rate (below 0.75):")
    for mode, rate in refer_rates.items():
        print(f"  {mode:<16} {rate * 100:5.1f}%")

    # Gate T4 is judged on the accuracy-first NMS path.
    gate_mode = "end2end=False"
    gate = summary.get(gate_mode, {})
    sound = gate.get("sound", 0.0) or 0.0
    defects = [gate.get(c, 0.0) or 0.0 for c in CLASS_NAMES if c != "sound"]
    n_defect_ok = sum(1 for v in defects if v >= GATE_DEFECT_MAP50)

    sound_ok = sound >= GATE_SOUND_MAP50
    passed = sound_ok and n_defect_ok >= GATE_DEFECT_COUNT

    print("\n" + "-" * 66)
    print(f"GATE T4  (judged on {gate_mode})")
    print(f"  sound mAP50 >= {GATE_SOUND_MAP50}       : "
          f"{sound:.3f}  {'PASS' if sound_ok else 'FAIL'}")
    print(f"  >= {GATE_DEFECT_MAP50} on >= {GATE_DEFECT_COUNT} defect classes : "
          f"{n_defect_ok} of {len(defects)}  "
          f"{'PASS' if n_defect_ok >= GATE_DEFECT_COUNT else 'FAIL'}")
    print(f"\n  GATE T4: {'PASS' if passed else 'FAIL'}")
    if not passed:
        print("\n  The fix is MORE DATA of the failing class, not more epochs.")
    print("-" * 66)
    print(f"\nReport written to {report}")

    (report / "summary.json").write_text(
        json.dumps({"config": cfg, "summary": summary, "refer_rates": refer_rates,
                    "gate_t4_pass": passed}, indent=2),
        encoding="utf-8",
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
