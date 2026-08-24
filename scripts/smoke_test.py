"""End-to-end smoke test against a running server.

Exercises the exact path a phone takes: two looks through /analyze, then
/finalize, then the rendered certificate. Catches the integration failures
that unit tests cannot -- wrong field names, unsubstituted placeholders,
oversized payloads.

    uvicorn app.main:app --port 8000
    python scripts/smoke_test.py --port 8000
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import urllib.request
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def post_multipart(url: str, image: Path, fields: dict) -> dict:
    boundary = uuid.uuid4().hex
    body = bytearray()
    for key, value in fields.items():
        body += (f"--{boundary}\r\n"
                 f'Content-Disposition: form-data; name="{key}"\r\n\r\n'
                 f"{value}\r\n").encode()
    mime = mimetypes.guess_type(image.name)[0] or "image/jpeg"
    body += (f"--{boundary}\r\n"
             f'Content-Disposition: form-data; name="file"; filename="{image.name}"\r\n'
             f"Content-Type: {mime}\r\n\r\n").encode()
    body += image.read_bytes()
    body += f"\r\n--{boundary}--\r\n".encode()

    req = urllib.request.Request(
        url, data=bytes(body),
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    return json.loads(urllib.request.urlopen(req, timeout=120).read())


def post_json(url: str, payload: dict) -> dict:
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=60).read())


def get(url: str) -> str:
    return urllib.request.urlopen(url, timeout=60).read().decode("utf-8", "replace")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--host", default="127.0.0.1")
    args = ap.parse_args()

    base = f"http://{args.host}:{args.port}"
    failures: list[str] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}{'  ' + detail if detail else ''}")
        if not ok:
            failures.append(name)

    print(f"SAMA smoke test against {base}\n")

    # --- health ----------------------------------------------------------
    health = json.loads(get(f"{base}/api/health"))
    check("server responds", True)
    check("model loaded", health["model_loaded"], str(health.get("model_error") or ""))

    # --- find a Two-Look pair --------------------------------------------
    pairs = sorted((ROOT / "data/dataset/test/images").glob("*_look0.jpg"))
    pair = None
    for look0 in pairs:
        look1 = look0.with_name(look0.name.replace("_look0", "_look1"))
        if look1.exists():
            pair = (look0, look1)
            break
    if pair is None:
        print("\nNo Two-Look pair found. Run make_synthetic.py first.")
        return 1
    print(f"\n  using {pair[0].name} + {pair[1].name}")

    # --- analyze ----------------------------------------------------------
    looks = []
    for index, image in enumerate(pair):
        data = post_multipart(f"{base}/analyze", image, {
            "lot_ref": "SMOKE-01", "look_index": index, "tray_id": "T1"})
        if "error" in data:
            check(f"/analyze look {index}", False, data["error"])
            return 1

        annotated_kb = len(data["annotated"]) / 1024
        diameters = [b["diameter_mm"] for b in data["bulbs"] if b["diameter_mm"]]
        check(f"/analyze look {index}", data["n_bulbs"] > 0,
              f"{data['n_bulbs']} bulbs, {annotated_kb:.0f} KB annotated")
        sc = data["scale"]
        # Not "all 8 markers visible" -- onions bury markers routinely and
        # that is the whole point of the fallback ladder. What must hold is
        # that the scale is good enough to certify a grade.
        check(f"  scale certified (look {index})",
              sc.get("grades_certified") is True,
              f"{sc['markers_found']}/{sc['markers_expected']} markers, "
              f"{sc['source']}, confidence {sc['confidence']}")
        check(f"  diameters plausible (look {index})",
              bool(diameters) and 20 <= min(diameters) and max(diameters) <= 120,
              f"{min(diameters):.0f}-{max(diameters):.0f} mm" if diameters else "none")
        check(f"  annotated payload under 600 KB (look {index})",
              annotated_kb < 600, f"{annotated_kb:.0f} KB")
        looks.append(data["bulbs"])

    # --- finalize ---------------------------------------------------------
    final = post_json(f"{base}/finalize", {
        "looks": looks, "lot_ref": "SMOKE-01",
        "farmer_name": "R. Kannan", "officer_name": "Insp. D. Kumar",
        "centre_name": "Chennai-11", "lat": 13.08, "lon": 80.27, "calibrated": True})
    if "error" in final:
        check("/finalize", False, final["error"])
        return 1

    result = final["result"]
    check("/finalize", True, f"lot {final['lot_id']}")
    check("  row_hash is sha256", len(final["row_hash"]) == 64)
    check("  Grade A within 0-100", 0 <= result["grade_a_pct"] <= 100,
          f"{result['grade_a_pct']:.1f}%")
    check("  CI brackets the estimate",
          result["grade_a_ci_low"] <= result["grade_a_pct"] <= result["grade_a_ci_high"],
          f"{result['grade_a_ci_low']:.1f}-{result['grade_a_ci_high']:.1f}%")
    check("  pooled both looks", result["n_looks"] == 2,
          f"{result['n_bulb_observations']} observations")

    per_look = result.get("defect_rate_per_look", [])
    check("  defect rate = best look, not average",
          bool(per_look) and abs(result["defect_rate_raw"] - max(per_look)) < 0.01,
          f"{per_look} -> {result['defect_rate_raw']:.1f}%")

    # --- certificate -------------------------------------------------------
    html = get(f"{base}/report/{final['lot_id']}")
    check("/report renders", "__LOT_DATA__" not in html, f"{len(html) // 1024} KB")
    for probe in ("SMOKE-01", "R. Kannan", "Insp. D. Kumar", "Chennai-11"):
        check(f"  certificate contains {probe!r}", probe in html)

    # --- dashboard ---------------------------------------------------------
    # a degraded scale must never be silently presented as certified
    from app.scale import GRADING_FLOOR, SOURCE_CONFIDENCE
    check("  mat_edge rung is below the grading floor",
          SOURCE_CONFIDENCE["mat_edge"] < GRADING_FLOOR,
          f"{SOURCE_CONFIDENCE['mat_edge']} < {GRADING_FLOOR}")
    check("  carried outranks mat_edge",
          SOURCE_CONFIDENCE["carried"] > SOURCE_CONFIDENCE["mat_edge"])

    drift = json.loads(get(f"{base}/api/drift"))
    flagged = [c["name"] for c in drift["centres"] if c["status"] == "RECALIBRATE"]
    check("/api/drift", "centres" in drift, f"{len(drift['centres'])} centres")
    check("  a centre is flagged for recalibration", bool(flagged), ", ".join(flagged))
    check("  all hash chains intact",
          all(c.get("chain_intact") for c in drift["centres"]))
    check("/dashboard renders", "SAMA" in get(f"{base}/dashboard"))
    check("/ renders", "SHAKE THE TRAY" in get(base))

    # --- graceful failure ---------------------------------------------------
    try:
        urllib.request.urlopen(f"{base}/api/replay/999", timeout=20)
        check("missing replay returns an error, not a crash", False)
    except urllib.error.HTTPError as exc:
        body = json.loads(exc.read())
        check("missing replay returns JSON error, not a stack trace",
              "error" in body, body.get("error", "")[:60])

    print()
    if failures:
        print(f"{len(failures)} CHECK(S) FAILED:")
        for name in failures:
            print(f"  - {name}")
        return 1
    print("ALL SMOKE CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
