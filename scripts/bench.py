"""Latency benchmark. Run this on the laptop you carry to the venue.

The 16 GB training machine is not the machine that demos. Benchmark the one
that does, and benchmark both YOLO26 inference modes -- the NMS-free path is
markedly faster on CPU, which is the fallback if the venue GPU is unavailable.

    python scripts/bench.py
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
BUDGET_MS = 400.0


def bench(model, images, e2e: bool, device: str, warmup: int = 3) -> dict:
    """Timed predict loop. Warm-up runs are discarded -- the first call pays
    for CUDA context creation and would dominate a 20-image average."""
    for path in images[:warmup]:
        model.predict(str(path), verbose=False, end2end=e2e,
                      device=device, max_det=300)

    times = []
    for path in images:
        start = time.perf_counter()
        model.predict(str(path), verbose=False, end2end=e2e,
                      device=device, max_det=300)
        times.append((time.perf_counter() - start) * 1000)

    arr = np.array(times)
    return {
        "mean_ms": round(float(arr.mean()), 1),
        "p50_ms": round(float(np.percentile(arr, 50)), 1),
        "p95_ms": round(float(np.percentile(arr, 95)), 1),
        "max_ms": round(float(arr.max()), 1),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--weights", type=Path, default=ROOT / "weights" / "best.pt")
    ap.add_argument("--images", type=Path, default=ROOT / "data" / "holdout" / "images")
    ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--device", default=None, help="cpu, 0, ... (default: both)")
    args = ap.parse_args()

    if not args.weights.exists():
        print(f"No {args.weights}.")
        return 1

    images = sorted(args.images.glob("*.jpg"))[:args.n]
    if not images:
        print(f"No images in {args.images}")
        return 1

    import torch
    from ultralytics import YOLO

    devices = [args.device] if args.device else (
        ["0", "cpu"] if torch.cuda.is_available() else ["cpu"])

    print(f"benchmarking {len(images)} images from {args.images.name}")
    if torch.cuda.is_available():
        prop = torch.cuda.get_device_properties(0)
        print(f"GPU: {prop.name}  {prop.total_memory / 1024 ** 3:.1f} GB")
    print()

    model = YOLO(str(args.weights))
    results: dict[str, dict] = {}

    print(f"{'device':<8}{'mode':<16}{'mean':>9}{'p50':>9}{'p95':>9}{'max':>9}{'':>13}")
    print("-" * 73)
    for device in devices:
        for e2e in (False, True):
            key = f"{device}/end2end={e2e}"
            try:
                stats = bench(model, images, e2e, device)
            except Exception as exc:  # noqa: BLE001
                print(f"{device:<8}{f'end2end={e2e}':<16}  failed: {type(exc).__name__}")
                continue
            results[key] = stats
            verdict = "PASS" if stats["p95_ms"] < BUDGET_MS else "OVER BUDGET"
            print(f"{device:<8}{f'end2end={e2e}':<16}"
                  f"{stats['mean_ms']:>9.1f}{stats['p50_ms']:>9.1f}"
                  f"{stats['p95_ms']:>9.1f}{stats['max_ms']:>9.1f}{verdict:>13}")

    if torch.cuda.is_available():
        print(f"\npeak GPU memory: {torch.cuda.max_memory_allocated() / 1024 ** 2:.0f} MB")

    passing = {k: v for k, v in results.items() if v["p95_ms"] < BUDGET_MS}
    print("\n" + "-" * 73)
    if passing:
        best = min(passing.items(), key=lambda kv: kv[1]["p95_ms"])
        print(f"GATE T12: PASS -- {len(passing)} of {len(results)} configurations "
              f"under the {BUDGET_MS:.0f} ms p95 budget.")
        print(f"  fastest: {best[0]} at {best[1]['p95_ms']:.0f} ms p95")

        nms = results.get("cpu/end2end=False")
        e2e = results.get("cpu/end2end=True")
        if nms and e2e and e2e["p95_ms"] < nms["p95_ms"]:
            gain = (1 - e2e["p95_ms"] / nms["p95_ms"]) * 100
            print(f"  NMS-free is {gain:.0f}% faster on CPU. If you demo on CPU, set")
            print('  "e2e_mode": true in app/constants.json.')
    else:
        print(f"GATE T12: FAIL -- nothing under {BUDGET_MS:.0f} ms p95.")
        print("  Try yolo26n instead of yolo26s, or drop inference imgsz to 640.")

    out = ROOT / "runs" / "report" / "bench.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\nWrote {out}")
    return 0 if passing else 1


if __name__ == "__main__":
    raise SystemExit(main())
