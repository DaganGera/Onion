"""Pre-label a folder of photos so humans only correct, never redraw.

Drawing 5,000 boxes by hand is where a 3-day project dies. Running a rough
model first and letting people fix its output cuts labelling roughly in half.

Every box is written as class 0 (sound) ON PURPOSE. Humans are fast at
reclassifying and slow at drawing, and a confidently wrong class suggestion
biases the labeller -- they accept it without looking.

    python scripts/bootstrap_label.py --images data/raw --weights weights/best.pt
"""

from __future__ import annotations

import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--images", type=Path, required=True)
    ap.add_argument("--weights", type=Path, default=ROOT / "weights" / "best.pt")
    ap.add_argument("--conf", type=float, default=0.25,
                    help="low on purpose: a missed box costs more than a spare one")
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--keep-classes", action="store_true",
                    help="write predicted classes instead of all-sound")
    args = ap.parse_args()

    if not args.weights.exists():
        print(f"No {args.weights}. Train a throwaway model first.")
        return 1
    if not args.images.is_dir():
        print(f"{args.images} is not a directory.")
        return 1

    out = args.out or (args.images.parent / "labels")
    out.mkdir(parents=True, exist_ok=True)

    from ultralytics import YOLO
    model = YOLO(str(args.weights))

    images = sorted([p for p in args.images.iterdir()
                     if p.suffix.lower() in {".jpg", ".jpeg", ".png"}])
    if not images:
        print(f"No images in {args.images}")
        return 1

    total = 0
    for path in images:
        result = model.predict(str(path), conf=args.conf, verbose=False, max_det=300)[0]
        lines = []
        if result.boxes is not None:
            for box, cls in zip(result.boxes.xywhn.cpu().numpy(),
                                result.boxes.cls.cpu().numpy()):
                index = int(cls) if args.keep_classes else 0
                lines.append(f"{index} {box[0]:.6f} {box[1]:.6f} {box[2]:.6f} {box[3]:.6f}")

        (out / f"{path.stem}.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
        total += len(lines)
        print(f"  {path.name:<40} {len(lines):>3} boxes")

    print(f"\n{len(images)} images, {total} boxes -> {out}")
    print(f"mean {total / len(images):.1f} boxes per image")
    if not args.keep_classes:
        print("\nAll boxes written as class 0 (sound).")
        print("In Roboflow: correct the CLASS only. Do not redraw boxes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
