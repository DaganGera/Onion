"""Gate T0 -- prove the machine can actually run this project.

    python scripts/check_env.py

Prints a pass/fail table. Anything red comes with the exact command to fix it.
"""

from __future__ import annotations

import json
import platform
import sys
from pathlib import Path

CHECKS: list[tuple[str, str]] = []


def record(name: str, ok: bool, detail: str, fix: str = "") -> bool:
    CHECKS.append((name, "PASS" if ok else "FAIL", detail, "" if ok else fix))
    return ok


def check_python() -> bool:
    v = sys.version_info
    return record(
        "Python 3.11.x",
        (v.major, v.minor) == (3, 11),
        f"{v.major}.{v.minor}.{v.micro} on {platform.system()}",
        "Install Python 3.11 and rebuild the venv: py -3.11 -m venv .venv",
    )


def check_torch() -> bool:
    try:
        import torch
    except ImportError:
        return record("PyTorch + CUDA", False, "torch not installed",
                      "pip install torch torchvision "
                      "--index-url https://download.pytorch.org/whl/cu121")

    if not torch.cuda.is_available():
        return record("PyTorch + CUDA", False,
                      f"torch {torch.__version__}, CUDA NOT available",
                      "Reinstall the CUDA build: pip install --force-reinstall torch "
                      "torchvision --index-url https://download.pytorch.org/whl/cu121")

    prop = torch.cuda.get_device_properties(0)
    vram = prop.total_memory / 1024 ** 3
    detail = f"torch {torch.__version__} | {prop.name} | {vram:.1f} GB VRAM"
    ok = record("PyTorch + CUDA", True, detail)

    # Advisory only -- a smaller card still works, it just changes the config.
    # YOLO26 rule: resolution stays 1024; VRAM pressure is relieved by batch.
    if vram < 7:
        print(f"  NOTE: {vram:.1f} GB VRAM. Keep imgsz 1024, drop batch to 8.")
    elif vram < 12:
        print(f"  NOTE: {vram:.1f} GB VRAM. yolo26s at 1024/batch 12 should fit;"
              " drop batch to 8 if it OOMs. Never drop the resolution.")
    return ok


def check_opencv() -> bool:
    try:
        import cv2
    except ImportError:
        return record("OpenCV + ArUco", False, "cv2 not installed",
                      "pip install opencv-contrib-python")

    version = cv2.__version__
    major, minor = (int(p) for p in version.split(".")[:2])
    if (major, minor) < (4, 7):
        return record("OpenCV + ArUco", False, f"cv2 {version} is too old",
                      "pip install -U opencv-contrib-python")

    # The class API only exists in opencv-contrib. Plain opencv-python has no
    # cv2.aruco at all, and that failure shows up two days later.
    has_aruco = hasattr(cv2, "aruco") and hasattr(cv2.aruco, "ArucoDetector")
    return record("OpenCV + ArUco", has_aruco,
                  f"cv2 {version}, ArucoDetector={'yes' if has_aruco else 'NO'}",
                  "pip uninstall -y opencv-python && pip install opencv-contrib-python")


def check_yolo26() -> bool:
    try:
        import ultralytics
    except ImportError:
        return record("Ultralytics YOLO26", False, "ultralytics not installed",
                      "pip install -U ultralytics")

    try:
        from ultralytics import YOLO
        model = YOLO("yolo26s.pt")
        params = sum(p.numel() for p in model.model.parameters()) / 1e6
        return record("Ultralytics YOLO26", True,
                      f"ultralytics {ultralytics.__version__}, "
                      f"yolo26s.pt loaded ({params:.1f}M params)")
    except Exception as exc:  # noqa: BLE001
        return record("Ultralytics YOLO26", False,
                      f"ultralytics {ultralytics.__version__} cannot load yolo26s.pt: "
                      f"{type(exc).__name__}",
                      "pip install -U ultralytics   "
                      "(if it still fails, fall back to yolo11s.pt and move on)")


def check_imports() -> bool:
    missing = []
    for module, package in [
        ("fastapi", "fastapi"), ("uvicorn", "uvicorn[standard]"),
        ("multipart", "python-multipart"), ("PIL", "pillow"),
        ("numpy", "numpy"), ("scipy", "scipy"), ("matplotlib", "matplotlib"),
    ]:
        try:
            __import__(module)
        except ImportError:
            missing.append(package)

    return record("App dependencies", not missing,
                  "all present" if not missing else f"missing: {', '.join(missing)}",
                  f"pip install {' '.join(missing)}" if missing else "")


def check_grading() -> bool:
    """The one project-specific check: our own math module must import."""
    try:
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from app import grading
        return record("app/grading.py", True,
                      f"{len(grading.CLASS_NAMES)} classes, "
                      f"marker={grading.MARKER_MM} mm")
    except Exception as exc:  # noqa: BLE001
        return record("app/grading.py", False, f"{type(exc).__name__}: {exc}",
                      "Run from the repo root: python scripts/check_env.py")


def check_constants() -> bool:
    """constants.json must be parseable, known-keyed, and in sane ranges.

    A typo'd key is the silent killer: grading._load_constants() merges
    whatever it reads over its defaults and IGNORES unknown keys -- so
    "height_corrrection": 0.94 would quietly fall back to 1.0 and every
    bulb on the certificate reads oversized.
    """
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from app.grading import _DEFAULTS
    except Exception as exc:  # noqa: BLE001
        return record("app/constants.json", False,
                      f"cannot import grading defaults: {type(exc).__name__}: {exc}",
                      "Run from the repo root: python scripts/check_env.py")

    path = Path(__file__).resolve().parents[1] / "app" / "constants.json"
    if not path.exists():
        # Absent file is legal -- every default applies -- but say so.
        return record("app/constants.json", True,
                      "absent; all defaults apply (height_correction=1.0, "
                      "e2e_mode=False)")

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return record("app/constants.json", False,
                      f"unparseable: {exc}",
                      "Fix the JSON syntax; app falls back to ALL defaults "
                      "while this file is broken.")

    if not isinstance(raw, dict):
        return record("app/constants.json", False,
                      f"expected a JSON object, got {type(raw).__name__}")

    unknown = sorted(set(raw) - set(_DEFAULTS))
    if unknown:
        return record("app/constants.json", False,
                      f"unknown key(s) {unknown} -- silently ignored by "
                      "grading.py, which keeps the default value instead",
                      "Fix the typo or delete the key. Known keys: "
                      f"{sorted(_DEFAULTS)}")

    ranges = {
        "height_correction": (0.0, 2.0),
        "occlusion_correction_1look": (0.0, 2.0),
        "occlusion_correction_2look": (0.0, 2.0),
        "accept_threshold": (0.0, 1.0),
    }
    for key, (lo, hi) in ranges.items():
        if key in raw:
            value = raw[key]
            if not isinstance(value, (int, float)) or not (lo < value <= hi):
                return record("app/constants.json", False,
                              f"{key}={value!r} outside sane range ({lo}, {hi}]",
                              f"Re-fit with calibrate_size.py / measure_occlusion.py")
    if "e2e_mode" in raw and not isinstance(raw["e2e_mode"], bool):
        return record("app/constants.json", False,
                      f"e2e_mode={raw['e2e_mode']!r} is not a boolean",
                      'Use true or false (false = NMS path, the default).')

    detail = ", ".join(f"{k}={raw[k]}" for k in sorted(raw)) or "empty object"
    return record("app/constants.json", True, detail)


def main() -> int:
    print("SAMA environment check\n")

    [
        check_python(),
        check_torch(),
        check_opencv(),
        check_yolo26(),
        check_imports(),
        check_grading(),
        check_constants(),
    ]

    width = max(len(name) for name, *_ in CHECKS)
    print()
    for name, status, detail, _ in CHECKS:
        print(f"  [{status}] {name:<{width}}  {detail}")

    failures = [(n, f) for n, s, _, f in CHECKS if s == "FAIL"]
    print()
    if not failures:
        print("ALL CHECKS PASSED")
        print("\nNEXT: python scripts/make_mat.py   (Gate T1)")
        return 0

    print(f"{len(failures)} CHECK(S) FAILED\n")
    for name, fix in failures:
        print(f"  {name}")
        print(f"    fix: {fix}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
