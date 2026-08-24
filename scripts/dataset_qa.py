"""Audit a YOLO dataset before training on it.

Six people uploading photos to Roboflow will create duplicates, mislabel
boxes, and forget the calibration mat. The model learns all of it faithfully.
This catches what a human would not notice across 5,000 boxes.

    python scripts/dataset_qa.py

Writes a scannable report to runs/dataset_qa.txt. Written for a
non-technical reader -- anything it flags is an instruction, not a hint.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter, defaultdict
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.grading import CLASS_NAMES, detect_scale  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]

MIN_INSTANCES_PER_CLASS = 150
MIN_BOX_AREA_FRAC = 0.001      # below this is probably a mis-click
MAX_BOX_AREA_FRAC = 0.20       # above this is probably the whole tray
MIN_BOXES = 5
MAX_BOXES = 60
NEAR_DUPLICATE_DISTANCE = 5    # Hamming distance between dhashes

lines: list[str] = []


def say(text: str = "") -> None:
    print(text)
    lines.append(text)


def dhash(image: np.ndarray, size: int = 8) -> int:
    """Perceptual hash. Survives resizing and recompression, unlike md5."""
    grey = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    small = cv2.resize(grey, (size + 1, size), interpolation=cv2.INTER_AREA)
    bits = small[:, 1:] > small[:, :-1]
    value = 0
    for bit in bits.flatten():
        value = (value << 1) | int(bit)
    return value


def _iter_images(root: Path):
    for split_dir in sorted(root.glob("*")):
        images = split_dir / "images"
        if images.is_dir():
            for path in sorted(images.glob("*.jpg")) + sorted(images.glob("*.png")):
                yield split_dir.name, path


def _labels_for(image_path: Path) -> Path:
    return image_path.parent.parent / "labels" / f"{image_path.stem}.txt"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dataset", type=Path, default=ROOT / "data" / "dataset")
    ap.add_argument("--holdout", type=Path, default=ROOT / "data" / "holdout")
    ap.add_argument("--check-mat", action="store_true", default=True,
                    help="run ArUco detection on every image (slow but worth it)")
    ap.add_argument("--out", type=Path, default=ROOT / "runs" / "dataset_qa.txt")
    args = ap.parse_args()

    entries: list[tuple[str, Path]] = list(_iter_images(args.dataset))
    if (args.holdout / "images").is_dir():
        entries += [("holdout", p)
                    for p in sorted((args.holdout / "images").glob("*.jpg"))]

    if not entries:
        print(f"No images under {args.dataset}")
        return 1

    say("=" * 64)
    say("SAMA DATASET QA")
    say("=" * 64)
    say(f"images found: {len(entries)}")
    say()

    hashes: dict[int, list[tuple[str, Path]]] = defaultdict(list)
    class_counts: Counter = Counter()
    split_class: dict[str, Counter] = defaultdict(Counter)
    tiny_boxes: list[str] = []
    huge_boxes: list[str] = []
    box_count_outliers: list[str] = []
    no_mat: list[str] = []
    unlabelled: list[str] = []

    for split, image_path in entries:
        image = cv2.imread(str(image_path))
        if image is None:
            continue

        hashes[dhash(image)].append((split, image_path))

        label_path = _labels_for(image_path)
        if not label_path.exists():
            unlabelled.append(f"{split}/{image_path.name}")
            continue

        rows = [r for r in label_path.read_text(encoding="utf-8").splitlines() if r.strip()]
        if len(rows) < MIN_BOXES or len(rows) > MAX_BOXES:
            box_count_outliers.append(f"{split}/{image_path.name}: {len(rows)} boxes")

        for row in rows:
            parts = row.split()
            if len(parts) < 5:
                continue
            cls = int(parts[0])
            name = CLASS_NAMES[cls] if cls < len(CLASS_NAMES) else f"UNKNOWN_{cls}"
            class_counts[name] += 1
            split_class[split][name] += 1

            area = float(parts[3]) * float(parts[4])
            if area < MIN_BOX_AREA_FRAC:
                tiny_boxes.append(f"{split}/{image_path.name}: {area * 100:.3f}% of image")
            elif area > MAX_BOX_AREA_FRAC:
                huge_boxes.append(f"{split}/{image_path.name}: {area * 100:.1f}% of image")

        if args.check_mat and not detect_scale(image).calibrated:
            no_mat.append(f"{split}/{image_path.name}")

    # --- 1. leakage ------------------------------------------------------
    say("1. LEAKAGE BETWEEN SPLITS")
    exact = {h: v for h, v in hashes.items() if len(v) > 1}
    cross_split = {h: v for h, v in exact.items() if len({s for s, _ in v}) > 1}
    if cross_split:
        say(f"   PROBLEM: {len(cross_split)} image(s) appear in more than one split.")
        say("   The same photo in train and valid makes your scores meaningless.")
        for group in list(cross_split.values())[:10]:
            say("     " + " | ".join(f"{s}/{p.name}" for s, p in group))
    else:
        say("   OK - no identical image appears in two splits.")

    keys = list(hashes)
    near = 0
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            if bin(keys[i] ^ keys[j]).count("1") <= NEAR_DUPLICATE_DISTANCE:
                near += 1
    say(f"   near-duplicate pairs (Hamming <= {NEAR_DUPLICATE_DISTANCE}): {near}")
    if near:
        say("   Near-duplicates inflate your validation score. Review them.")
    say()

    # --- 2. class balance -------------------------------------------------
    say("2. CLASS BALANCE")
    total = sum(class_counts.values())
    say(f"   {total} boxes across {len(class_counts)} classes")
    for name in CLASS_NAMES:
        count = class_counts.get(name, 0)
        share = 100 * count / total if total else 0
        flag = "  <-- UNDER-REPRESENTED" if count < MIN_INSTANCES_PER_CLASS else ""
        say(f"     {name:<15} {count:>6}  ({share:4.1f}%){flag}")
    unknown = [n for n in class_counts if n.startswith("UNKNOWN_")]
    if unknown:
        say(f"   PROBLEM: labels reference classes outside our 6: {unknown}")
        say("   Someone added a class in Roboflow. Remove it.")
    say()

    # --- 3. box sanity ----------------------------------------------------
    say("3. BOX SANITY")
    say(f"   suspiciously tiny boxes (< {MIN_BOX_AREA_FRAC * 100}% of image): {len(tiny_boxes)}")
    for entry in tiny_boxes[:5]:
        say(f"     {entry}")
    say(f"   suspiciously huge boxes (> {MAX_BOX_AREA_FRAC * 100}% of image): {len(huge_boxes)}")
    for entry in huge_boxes[:5]:
        say(f"     {entry}")
    if huge_boxes:
        say("   A huge box usually means someone boxed the whole tray.")
    say()

    # --- 4. calibration mat ------------------------------------------------
    say("4. CALIBRATION MAT")
    if args.check_mat:
        say(f"   images with NO detectable marker: {len(no_mat)} of {len(entries)}")
        for entry in no_mat[:10]:
            say(f"     {entry}")
        if no_mat:
            say("   These cannot be sized in mm. Reshoot or exclude them.")
    else:
        say("   skipped (--check-mat off)")
    say()

    # --- 5. label completeness --------------------------------------------
    say("5. LABEL COMPLETENESS")
    say(f"   images with no label file: {len(unlabelled)}")
    for entry in unlabelled[:10]:
        say(f"     {entry}")
    say(f"   images with < {MIN_BOXES} or > {MAX_BOXES} boxes: {len(box_count_outliers)}")
    for entry in box_count_outliers[:10]:
        say(f"     {entry}")
    if box_count_outliers:
        say("   Usually means labelling was left half-finished.")
    say()

    # --- verdict -----------------------------------------------------------
    blockers = len(cross_split) + len(unknown) + len(unlabelled)
    say("=" * 64)
    if blockers == 0:
        say("VERDICT: no blocking problems found. Safe to train.")
    else:
        say(f"VERDICT: {blockers} blocking problem(s). Fix before training.")
    say("=" * 64)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nWrote {args.out}")
    return 0 if blockers == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
