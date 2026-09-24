"""Emit golden vectors from the legacy Python grading math for TS parity tests.

Stubs app.scale (needs OpenCV) since wilson_interval and merge_looks don't use it.
Run: python tools/make_golden.py > packages/core/test/golden/legacy_grading.json
"""
import json, sys, types, random
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "legacy"))
stub = types.ModuleType("app.scale")
stub.ARUCO_DICT = None; stub.SKEW_TOLERANCE = 0.1
class ScaleResult: pass
stub.ScaleResult = ScaleResult
stub.measure_bbox_mm = lambda *a, **k: None
stub.detect_scale = lambda *a, **k: None
sys.modules["app.scale"] = stub
from app import grading as g  # noqa: E402

g.CONSTANTS.update({"occlusion_correction_1look": 0.8, "occlusion_correction_2look": 0.9})
out = {"constants": {k: g.CONSTANTS[k] for k in ("occlusion_correction_1look", "occlusion_correction_2look")},
       "wilson": [], "merge_looks": []}
for n in [0, 1, 2, 5, 10, 35, 60, 100, 250]:
    for k in sorted({0, 1, n // 3, n // 2, n - 1, n} & set(range(n + 1))):
        lo, hi = g.wilson_interval(k, n)
        out["wilson"].append({"k": k, "n": n, "lo": lo, "hi": hi})
rng = random.Random(26031)
names = g.CLASS_NAMES
for case in range(40):
    looks = []
    for _ in range(rng.choice([1, 2, 2, 3])):
        look = []
        for _ in range(rng.randint(0, 45)):
            look.append({"cls": rng.choice(names) if rng.random() < .5 else rng.randrange(len(names)),
                         "size_grade": rng.choice(["A", "B", "C", "UNDERSIZED", "UNKNOWN"]),
                         "decision": rng.choice(["ACCEPT", "REFER"]),
                         "tray_id": rng.choice([1, 2, 3])})
        looks.append(look)
    out["merge_looks"].append({"looks": looks, "result": g.merge_looks(looks)})
json.dump(out, sys.stdout)
