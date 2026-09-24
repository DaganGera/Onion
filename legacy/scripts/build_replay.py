"""Pre-compute /analyze responses so the demo survives with no network.

Gate T11 is the most important gate of Day 3. Venue wifi fails, tunnels drop,
GPUs get claimed by another team. Replay mode makes the whole flow -- capture,
shake, results, sign-off, certificate -- work from cached JSON with no model
call and no network, and the audience cannot tell the difference.

    python scripts/build_replay.py
    # then open  http://localhost:8000/?replay=1
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

CACHE = ROOT / "app" / "cache"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--images", type=Path, nargs="*",
                    help="tray photos in capture order: "
                         "tray1 look1, tray1 look2, tray2 look1, ...")
    ap.add_argument("--data", type=Path, default=ROOT / "data")
    ap.add_argument("--pairs", type=int, default=3, help="tray pairs to cache")
    ap.add_argument("--weights", type=Path, default=ROOT / "weights" / "best.pt")
    args = ap.parse_args()

    if not args.weights.exists():
        print(f"No {args.weights}. Train first.")
        return 1

    images = list(args.images or [])
    if not images:
        # whole Two-Look pairs, so the shake step has something to show
        trays = sorted((args.data / "dataset" / "test" / "images").glob("*_look0.jpg"))
        for look0 in trays[:args.pairs]:
            look1 = look0.with_name(look0.name.replace("_look0", "_look1"))
            if look1.exists():
                images += [look0, look1]
        if not images:
            images = sorted((args.data / "holdout" / "images").glob("*.jpg"))[:args.pairs * 2]

    if not images:
        print("No images to cache.")
        return 1

    from app import grading
    from app.main import _annotate
    from ultralytics import YOLO

    model = YOLO(str(args.weights))
    CACHE.mkdir(parents=True, exist_ok=True)
    for old in CACHE.glob("replay_*.json"):
        old.unlink()

    for index, path in enumerate(images):
        image = cv2.imread(str(path))
        if image is None:
            print(f"  skip {path.name} (unreadable)")
            continue

        scale = grading.detect_scale(image)
        result = model.predict(image, conf=0.25, verbose=False, max_det=300)[0]

        bulbs = []
        if result.boxes is not None:
            for bbox, cls, conf in zip(result.boxes.xyxy.cpu().numpy(),
                                       result.boxes.cls.cpu().numpy(),
                                       result.boxes.conf.cpu().numpy()):
                cls_idx = int(cls)
                diameter = grading.bulb_diameter_mm(bbox, scale)
                bulbs.append({
                    "bbox": [float(v) for v in bbox],
                    "cls": cls_idx,
                    "cls_name": grading.CLASS_NAMES[cls_idx],
                    "confidence": round(float(conf), 4),
                    "diameter_mm": round(diameter, 1) if diameter else None,
                    "size_grade": grading.size_grade(diameter),
                    "decision": grading.decide(float(conf)),
                    "tray_id": f"T{index // 2 + 1}",
                })

        payload = {
            "lot_ref": "REPLAY",
            "look_index": index % 2,
            "tray_id": f"T{index // 2 + 1}",
            "bulbs": bulbs,
            "n_bulbs": len(bulbs),
            "scale": scale.to_dict(),
            "annotated": _annotate(image, bulbs),
            "elapsed_ms": 240.0,
            "replay_source": path.name,
        }

        out = CACHE / f"replay_{index}.json"
        out.write_text(json.dumps(payload), encoding="utf-8")
        print(f"  replay_{index}.json  <- {path.name:<28} "
              f"{len(bulbs):>3} bulbs  {out.stat().st_size / 1024:6.0f} KB")

    print(f"\nCached {len(list(CACHE.glob('replay_*.json')))} responses in {CACHE}")
    print("\nGATE T11: unplug ethernet, turn off wifi, kill the tunnel, then open")
    print("  http://localhost:8000/?replay=1")
    print("and run the full flow through to the certificate.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
