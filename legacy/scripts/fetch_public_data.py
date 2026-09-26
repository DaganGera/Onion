"""Pull public onion datasets to supplement your own photos.

WHAT THESE ARE GOOD FOR
-----------------------
Extra examples of what rot, sprouting and black smut LOOK like. That is real
value early, when your own defect photos number in the dozens.

WHAT THEY CANNOT DO
-------------------
None of them carry a calibration mat, so no bulb in them can be sized in mm.
None are shot as procurement trays, so they teach nothing about occlusion or
lot composition. And their class definitions are not yours -- one public set
uses 22 classes including combinations like "blacksmut-rotten".

So: use them to pretrain or to pad rare defect classes. Do NOT put them in
your holdout, and do NOT quote a metric measured on them. Your own trays are
the only honest evaluation.

    set ROBOFLOW_API_KEY=your_key
    python scripts/fetch_public_data.py --list
    python scripts/fetch_public_data.py --download kryotech-onion
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "data" / "public"


def to_yolo_bbox(cls_idx: int, coords: list[float]) -> str:
    """Return a 'class xc yc w h' row.

    Public sets mix plain bboxes (4 values) with polygon annotations (>4,
    pairs of x,y). Ultralytics detection training and this repo's
    measure_bbox_mm both need a box, not a mask, so polygons collapse to
    their tightest enclosing box -- a deterministic min/max, not a guess.
    """
    if len(coords) == 4:
        xc, yc, w, h = coords
    else:
        xs, ys = coords[0::2], coords[1::2]
        x0, x1 = min(xs), max(xs)
        y0, y1 = min(ys), max(ys)
        xc, yc = (x0 + x1) / 2, (y0 + y1) / 2
        w, h = x1 - x0, y1 - y0
    return f"{cls_idx} {xc:.6f} {yc:.6f} {w:.6f} {h:.6f}"

# Verified to exist on Roboflow Universe. Counts are what the listings state;
# re-check before relying on them, public datasets get edited.
SOURCES = {
    "kryotech-onion": {
        "workspace": "kryotech",
        "project": "onion-detection",
        "version": 1,
        "images": 261,
        "classes": ["rotten", "sprout"],
        "url": "https://universe.roboflow.com/kryotech/onion-detection",
        "note": "Closest match to our task. Only 2 defect classes, no mat, "
                "no tray context. Published mAP@50 is low (~24%), so treat the "
                "IMAGES as the asset, not the labels.",
    },
    "kadiri-onion-disease": {
        "workspace": "anas-kadiri-ffnxr",
        "project": "onion-disease",
        "version": 2,
        "images": 125,
        "classes": ["22 compound classes e.g. 'sprouted-blacksmutinfected', "
                    "inconsistent capitalization -- verified live via API, "
                    "grew from 53 to 125 images since first checked"],
        "url": "https://universe.roboflow.com/anas-kadiri-ffnxr/onion-disease",
        "note": "Covers black smut, our rarest class and the hardest to collect. "
                "CC BY 4.0. A workspace called onion-detection-system/onion-disease-rdezg "
                "is a fork of this exact data -- do not add both.",
    },
    "onion-spoilage": {
        "workspace": "onionspoilagedetection",
        "project": "onion_spoilage_detection-chyfl",
        "version": 6,
        "images": None,
        "classes": ["healthy", "mold", "rotten", "sprouted"],
        "url": "https://universe.roboflow.com/onionspoilagedetection/onion_spoilage_detection-chyfl",
        "note": "Verified live via API: box counts mold=109 rotten=1465 healthy=433 "
                "sprouted=218. CC BY 4.0. 'mold' is mapped to black_smut below -- "
                "that's an assumption (fungal skin growth, same family), not a "
                "certainty. Spot-check a sample after download before trusting it.",
    },
    "onion-sorting": {
        "workspace": "imagelabelling",
        "project": "onion-sorting-cghvq",
        "version": 1,
        "images": 1616,
        "classes": ["Good Onion", "Rotten Onion", "onion"],
        "url": "https://universe.roboflow.com/imagelabelling/onion-sorting-cghvq",
        "note": "Verified live via API -- 1616 images, largest source available. "
                "CC BY 4.0 (confirmed from the downloaded data.yaml). "
                "No mat/tray context.",
    },
}

# How public labels map onto our six classes. Anything unmapped is dropped
# rather than guessed -- a wrong label is worse than a missing one.
CLASS_REMAP = {
    "rotten": "rotten",
    "rot": "rotten",
    "sprout": "sprouted",
    "sprouted": "sprouted",
    "blacksmut": "black_smut",
    "blacksmutinfected": "black_smut",
    "black_smut": "black_smut",
    "damaged": "damaged_skin",
    "discoloured": "damaged_skin",
    "good": "sound",
    "healthy": "sound",
    "onion": "sound",
    "mold": "black_smut",
}


def show_sources() -> None:
    print("Public onion datasets\n")
    for key, meta in SOURCES.items():
        print(f"  {key}")
        print(f"    {meta['url']}")
        print(f"    {meta['images']} images | classes: {', '.join(meta['classes'])}")
        print(f"    {meta['note']}")
        print()
    print("Roboflow downloads need an API key (free account):")
    print("  1. sign in at https://roboflow.com")
    print("  2. Settings -> API keys -> copy the private key")
    print("  3. set ROBOFLOW_API_KEY=xxxxx")
    print("  4. python scripts/fetch_public_data.py --download kryotech-onion")
    print()
    print("Class remapping applied on import:")
    for source, target in CLASS_REMAP.items():
        print(f"  {source:<20} -> {target}")
    print("\nAnything not in that table is DROPPED, not guessed.")


def download(key: str) -> int:
    meta = SOURCES.get(key)
    if meta is None:
        print(f"Unknown source '{key}'. Options: {', '.join(SOURCES)}")
        return 1

    api_key = os.environ.get("ROBOFLOW_API_KEY", "").strip()
    if not api_key:
        print("ROBOFLOW_API_KEY is not set.\n")
        print("  PowerShell:  $env:ROBOFLOW_API_KEY = 'your_key'")
        print("  cmd:         set ROBOFLOW_API_KEY=your_key")
        print(f"\nOr download manually from {meta['url']} in YOLOv8 format")
        print(f"and unzip into {PUBLIC / key}")
        return 1

    try:
        from roboflow import Roboflow
    except ImportError:
        print("The roboflow package is not installed.")
        print("  pip install roboflow")
        return 1

    PUBLIC.mkdir(parents=True, exist_ok=True)
    target = PUBLIC / key
    print(f"Downloading {key} -> {target}")

    try:
        rf = Roboflow(api_key=api_key)
        project = rf.workspace(meta["workspace"]).project(meta["project"])
        project.version(meta["version"]).download("yolov8", location=str(target))
    except Exception as exc:  # noqa: BLE001
        print(f"Download failed: {type(exc).__name__}: {exc}")
        print(f"\nFall back to a manual download from {meta['url']}")
        return 1

    print("\nDone. Now remap classes before training on it:")
    print(f"  python scripts/fetch_public_data.py --remap {key}")
    return 0


def remap(key: str) -> int:
    """Rewrite a downloaded dataset's labels into our 6-class scheme."""
    sys.path.insert(0, str(ROOT))
    from app.grading import CLASS_NAMES

    target = PUBLIC / key
    if not target.exists():
        print(f"{target} does not exist. Download it first.")
        return 1

    yaml_files = list(target.rglob("data.yaml"))
    if not yaml_files:
        print(f"No data.yaml under {target}")
        return 1

    import yaml
    text = yaml_files[0].read_text(encoding="utf-8")
    parsed = yaml.safe_load(text) or {}
    names = parsed.get("names")
    if isinstance(names, dict):
        # old numbered-dict export: {0: 'healthy', 1: 'mold', ...}
        source_names = [names[i] for i in sorted(names, key=int)]
    elif isinstance(names, list):
        # inline list or YAML block-list export -- both parse to a list
        source_names = list(names)
    else:
        source_names = []

    print(f"source classes: {source_names}")
    if not source_names:
        print("Could not read any class names from data.yaml -- refusing to "
              "touch labels rather than silently writing empty files.")
        return 1

    index_map: dict[int, int] = {}
    for i, name in enumerate(source_names):
        clean = name.lower().replace("-", "").replace(" ", "").replace("_", "")
        mapped = None
        for source, dest in CLASS_REMAP.items():
            if source.replace("_", "") in clean:
                mapped = dest
                break
        if mapped:
            index_map[i] = CLASS_NAMES.index(mapped)
            print(f"  {name:<28} -> {mapped}")
        else:
            print(f"  {name:<28} -> DROPPED (no confident mapping)")

    # Write into a sibling labels_sama6/ next to each original labels/ dir --
    # never overwrite the raw download. A parsing bug here must not be able
    # to silently destroy source data, the way an earlier version of this
    # script did.
    changed = dropped = 0
    for label_path in target.rglob("labels/*.txt"):
        out_dir = label_path.parent.parent / "labels_sama6"
        out_dir.mkdir(exist_ok=True)
        out_lines = []
        for line in label_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            parts = line.split()
            src = int(parts[0])
            if src in index_map:
                coords = [float(v) for v in parts[1:]]
                out_lines.append(to_yolo_bbox(index_map[src], coords))
                changed += 1
            else:
                dropped += 1
        (out_dir / label_path.name).write_text(
            "\n".join(out_lines) + "\n", encoding="utf-8")

    print(f"\nremapped {changed} boxes, dropped {dropped}")
    print(f"\nWritten to labels_sama6/ next to each split's images/ under {target} "
          "-- originals in labels/ are untouched.")
    print("Merge images/ + labels_sama6/ into training with care -- "
          "keep these OUT of data/holdout/.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--download", metavar="SOURCE")
    ap.add_argument("--remap", metavar="SOURCE")
    args = ap.parse_args()

    if args.download:
        return download(args.download)
    if args.remap:
        return remap(args.remap)
    show_sources()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
