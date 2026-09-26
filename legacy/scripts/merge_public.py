"""Merge the remapped public datasets into the training split.

    python scripts/merge_public.py            # pad with defaults
    python scripts/merge_public.py --clean    # remove previously merged files first

WHY
---
The model trains on synthetic trays, whose defect classes are uneven
(doubles 1.7%). Two real Roboflow sets -- onion-spoilage (772 images) and
onion-sorting (1,616 images) -- were downloaded and class-remapped into the
SAMA-6 schema by fetch_public_data.py. Their labels live in labels_sama6/
next to each split's images/. This script copies a capped, class-balanced
selection of them into data/dataset/train/ so the detector sees REAL rot,
sprout and smut texture before demo day.

RULES THIS SCRIPT ENFORCES
--------------------------
- Train split ONLY. valid/, test/ and holdout/ are never touched: public
  images must never be able to flatter a reported metric.
- Filenames are prefixed pub_ so re-runs and --clean are unambiguous.
- Per-class caps stop 2,500 real rotten close-ups from swamping the tray
  domain the app actually operates in.
- Images with no label file, or no boxes in a wanted class, are skipped.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PUBLIC_DIRS = [
    ROOT / "data" / "public" / "onion-spoilage",
    ROOT / "data" / "public" / "onion-sorting",
]
TRAIN = ROOT / "data" / "dataset" / "train"
PREFIX = "pub_"

# class index -> how many IMAGES containing it may be merged. Chosen to pad
# the defect classes without drowning ~182 synthetic train trays.
DEFAULT_CAPS = {1: 600, 2: 400, 3: 250, 0: 500}
IMAGE_EXTS = {".jpg", ".jpeg", ".png"}


def _find_image(split_dir: Path, stem: str) -> Path | None:
    for ext in IMAGE_EXTS:
        candidate = split_dir / "images" / f"{stem}{ext}"
        if candidate.exists():
            return candidate
    return None


def collect_wanted(caps: dict[int, int]) -> list[tuple[Path, Path]]:
    """Pick (image, label) pairs up to each per-class image cap.

    Greedy in two passes: first every image that contains an under-capped
    DEFECT box (those are the point of this exercise), then sound-only
    images if their cap still has room.
    """
    candidates: list[tuple[frozenset, Path, Path]] = []
    for public in PUBLIC_DIRS:
        for split in ("train", "valid", "test"):
            label_dir = public / split / "labels_sama6"
            if not label_dir.exists():
                continue
            for label_path in sorted(label_dir.glob("*.txt")):
                image_path = _find_image(public / split, label_path.stem)
                if image_path is None:
                    continue
                classes = set()
                try:
                    for line in label_path.read_text(encoding="utf-8").splitlines():
                        if line.strip():
                            classes.add(int(line.split()[0]))
                except (ValueError, IndexError):
                    continue
                classes &= set(caps)
                if classes:
                    candidates.append((frozenset(classes), image_path, label_path))

    used = {k: 0 for k in caps}
    chosen: list[tuple[Path, Path]] = []

    # pass 1: images that contain at least one wanted defect class
    for classes, image_path, label_path in sorted(
        candidates, key=lambda c: -len(c[0] & {1, 2, 3})
    ):
        wants = [c for c in classes if c != 0 and used[c] < caps[c]]
        if not wants:
            continue
        chosen.append((image_path, label_path))
        for c in classes:
            used[c] += 1

    # pass 2: pure-sound images for background balance
    for classes, image_path, label_path in candidates:
        if classes == frozenset({0}) and used[0] < caps[0]:
            chosen.append((image_path, label_path))
            used[0] += 1

    return chosen


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--caps", type=int, nargs=4, default=None, metavar=("ROT", "SPR", "SMUT", "SND"),
                    help="per-class image caps: rotten sprouted black_smut sound")
    ap.add_argument("--clean", action="store_true",
                    help="remove every pub_ file from the train split before merging")
    args = ap.parse_args()

    caps = dict(zip((1, 2, 3, 0), args.caps)) if args.caps else DEFAULT_CAPS

    img_out = TRAIN / "images"
    lbl_out = TRAIN / "labels"
    img_out.mkdir(parents=True, exist_ok=True)
    lbl_out.mkdir(parents=True, exist_ok=True)

    if args.clean:
        removed = 0
        for pattern_dir in (img_out, lbl_out):
            for old in pattern_dir.glob(f"{PREFIX}*"):
                old.unlink()
                removed += 1
        print(f"removed {removed} previously merged pub_ files")

    pairs = collect_wanted(caps)
    copied = skipped = 0
    per_class = {k: 0 for k in caps}

    for image_path, label_path in pairs:
        dst_img = img_out / f"{PREFIX}{image_path.name}"
        dst_lbl = lbl_out / f"{PREFIX}{label_path.stem}.txt"
        if dst_img.exists() and dst_lbl.exists():
            skipped += 1
            continue
        shutil.copy2(image_path, dst_img)
        shutil.copy2(label_path, dst_lbl)
        copied += 1
        try:
            for line in label_path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    c = int(line.split()[0])
                    if c in per_class:
                        per_class[c] += 1
        except (ValueError, IndexError):
            pass

    print(f"\nmerged {copied} new images ({skipped} already present)")
    print("boxes added per class:")
    names = {0: "sound", 1: "rotten", 2: "sprouted", 3: "black_smut"}
    for k in sorted(per_class):
        print(f"  {names[k]:<12} {per_class[k]:>5}")
    total = len(list(img_out.glob('*')))
    print(f"\ntrain split now holds {total} images")
    print("valid/, test/ and holdout/ untouched by design.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
