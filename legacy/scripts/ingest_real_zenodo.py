#!/usr/bin/env python
"""Extract real onion-bulb images from the Zenodo dataset and remap to SAMA-6.

Source: "Image Dataset of Red and White Onion Bulbs and Leaves"
Zenodo record 20254934 (DOI 10.5281/zenodo.20254933), Pune market photos,
Motorola 50 Ultra, 1024x768. CC-licensed public dataset.

Mapping to SAMA-6 (0 sound, 1 rotten, 2 sprouted, 3 black_smut, 4 damaged_skin,
5 doubles):
    healthy   -> 0 sound
    unhealthy -> 1 rotten (dominant spoilage mode in the set; spot-checks show
                 mold/rot lesions. Some unhealthy samples are damaged skin or
                 sprout — the bootstrap auto-labeler reassigns by pixel heuristics
                 and every image keeps provenance `real-zenodo` + original label
                 so relabeling is lossless.)

Images are extracted to data/real/bulbs/{sound,rotten}/ as JPEG. Detection
boxes are produced by a center-weighted auto-boxer (bulb fills most of frame
for single shots) and for 'multiple' shots a classical segmentation finds
connected bulb regions. These are BOOTSTRAP labels: scripts/bootstrap_label.py
philosophy applies — humans correct classes later if precision matters.

Usage:
    python scripts/ingest_real_zenodo.py --zip data/real/OnionImageDataset.zip
"""
import argparse
import csv
import io
import json
import zipfile
from collections import Counter
from pathlib import Path

import cv2
import numpy as np

SOUND, ROTTEN = 0, 1


def auto_boxes(img: np.ndarray, multiple: bool):
    """Find bulb regions. Single: one generous center box. Multiple: watershed-ish
    connected components on a saturation+value foreground mask."""
    h, w = img.shape[:2]
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    # bulbs are warm (hue 0-30 or 160-180) and not background cloth
    m1 = cv2.inRange(hsv, (0, 60, 60), (30, 255, 255))
    m2 = cv2.inRange(hsv, (150, 40, 60), (180, 255, 255))
    mask = cv2.morphologyEx(m1 | m2, cv2.MORPH_CLOSE,
                            np.ones((25, 25), np.uint8))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((15, 15), np.uint8))
    if not multiple:
        ys, xs = np.where(mask > 0)
        if len(xs) < 0.02 * w * h:  # fallback: generous center box
            return [(0.18, 0.18, 0.64, 0.64)]
        x0, x1 = xs.min(), xs.max()
        y0, y1 = ys.min(), ys.max()
        # square-ish expansion
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        side = max(x1 - x0, y1 - y0) * 1.08
        return [(max(0, (cx - side / 2)) / w, max(0, (cy - side / 2)) / h,
                 min(w, side) / w, min(h, side) / h)]
    n, lab, stats, _ = cv2.connectedComponentsWithStats(mask)
    boxes = []
    for i in range(1, n):
        x, y, bw, bh, area = stats[i]
        if area < 0.01 * w * h or bw > 0.95 * w:  # skip specks and full-frame
            continue
        boxes.append((x / w, y / h, bw / w, bh / h))
    return boxes or [(0.18, 0.18, 0.64, 0.64)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--zip", default="data/real/OnionImageDataset.zip")
    ap.add_argument("--out", default="data/real/bulbs")
    ap.add_argument("--max-per-class", type=int, default=1200,
                    help="cap per (health, variety) group to keep training sane")
    ap.add_argument("--holdout-frac", type=float, default=0.10)
    args = ap.parse_args()

    out = Path(args.out)
    for sub in ("train", "holdout"):
        (out / sub / "images").mkdir(parents=True, exist_ok=True)
        (out / sub / "labels").mkdir(parents=True, exist_ok=True)

    z = zipfile.ZipFile(args.zip)
    manifest = []
    counts = Counter()
    holdout_names = set()

    bulbs = [n for n in z.namelist()
             if "/2. Bulb/" in n and n.lower().endswith(".jpg")]
    for name in sorted(bulbs):
        parts = name.split("/")
        healthy = "1. Healthy" in name
        variety = "red" if "Red" in name else "white"
        multiple = "2. Multiple" in name
        group = (healthy, variety)
        if counts[group] >= args.max_per_class:
            continue
        counts[group] += 1

        cls = SOUND if healthy else ROTTEN
        rng = hash(name) & 0xFFFFFFFF
        is_holdout = (rng % 100) < args.holdout_frac * 100
        split = "holdout" if is_holdout else "train"
        stem = Path(name).stem

        img_bytes = z.read(name)
        img = cv2.imdecode(np.frombuffer(img_bytes, np.uint8),
                           cv2.IMREAD_COLOR)
        if img is None:
            continue
        h, w = img.shape[:2]
        boxes = auto_boxes(img, multiple)

        img_name = f"zen_{stem}.jpg"
        cv2.imwrite(str(out / split / "images" / img_name), img,
                    [cv2.IMWRITE_JPEG_QUALITY, 90])
        with open(out / split / "labels" / f"zen_{stem}.txt", "w") as f:
            for bx in boxes:
                cx = (bx[0] + bx[2] / 2)
                cy = (bx[1] + bx[3] / 2)
                f.write(f"{cls} {cx:.6f} {cy:.6f} {bx[2]:.6f} {bx[3]:.6f}\n")
        manifest.append({"image": img_name, "split": split, "class": cls,
                         "source": "zenodo-20254934", "variety": variety,
                         "original_label": "healthy" if healthy else "unhealthy",
                         "n_bulbs": len(boxes)})

    with open(out / "PROVENANCE.csv", "w", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=list(manifest[0].keys()))
        wr.writeheader()
        wr.writerows(manifest)

    summary = {
        "total": len(manifest),
        "by_split": Counter(m["split"] for m in manifest),
        "by_class": Counter(m["class"] for m in manifest),
        "source": "Zenodo 20254934 (Pune market onion bulbs, real photos)",
        "note": "bootstrap boxes; unhealthy->rotten mapping approximate, "
                "provenance kept for relabeling",
    }
    (out / "SUMMARY.json").write_text(json.dumps(summary, indent=2,
                                                 default=lambda c: dict(c)))
    print(json.dumps(summary, indent=2, default=lambda c: dict(c)))


if __name__ == "__main__":
    main()
