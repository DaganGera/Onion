"""Fill the database with a believable procurement network.

An empty dashboard proves nothing to a judge. This seeds six centres with
30 days of reference runs, five holding steady and one visibly degrading, so
the drift monitor has something real to catch the moment the page loads.

    python scripts/seed_demo.py
"""

from __future__ import annotations

import argparse
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import db  # noqa: E402
from app.grading import CLASS_NAMES, merge_looks, size_grade  # noqa: E402

CENTRES = [
    ("Nashik-04", "Nashik"),
    ("Chennai-11", "Chennai"),
    ("Kurnool-02", "Kurnool"),        # the one that drifts
    ("Lasalgaon-07", "Nashik"),
    ("Pimpalgaon-01", "Nashik"),
    ("Solapur-03", "Solapur"),
]

DRIFTING = "Kurnool-02"
DAYS = 30
DRIFT_STARTS_DAYS_AGO = 4

FARMERS = ["R. Kannan", "S. Meena", "A. Patil", "V. Reddy", "M. Sharma",
           "K. Devi", "T. Nair", "B. Yadav", "P. Kaur", "G. Rao"]
OFFICERS = ["Insp. D. Kumar", "Insp. L. Fernandes", "Insp. N. Joshi"]


def _reference_score(centre: str, days_ago: int, rng: random.Random) -> float:
    """Score of a sealed reference tray re-graded at that centre."""
    if centre == DRIFTING and days_ago <= DRIFT_STARTS_DAYS_AGO:
        # a worn mat degrading over the last few days
        progress = (DRIFT_STARTS_DAYS_AGO - days_ago) / max(DRIFT_STARTS_DAYS_AGO, 1)
        return round(98.0 - 9.0 * progress + rng.uniform(-0.5, 0.5), 2)
    return round(rng.uniform(96.0, 99.0), 2)


def _fake_lot(rng: random.Random) -> tuple[dict, list[list[dict]]]:
    """A plausible lot, built through the real merge_looks path so the
    dashboard numbers are consistent with what the app would produce."""
    n = rng.randint(24, 40)
    looks = []
    for _ in range(2):
        bulbs = []
        for _ in range(n):
            roll = rng.random()
            cls = ("sound" if roll < 0.72 else
                   "rotten" if roll < 0.80 else
                   "sprouted" if roll < 0.87 else
                   "black_smut" if roll < 0.92 else
                   "damaged_skin" if roll < 0.98 else "doubles")
            diameter = max(26.0, rng.gauss(62, 15))
            conf = rng.uniform(0.55, 0.98)
            bulbs.append({
                "cls": CLASS_NAMES.index(cls),
                "cls_name": cls,
                "confidence": round(conf, 3),
                "diameter_mm": round(diameter, 1),
                "size_grade": size_grade(diameter),
                "decision": "ACCEPT" if conf >= 0.75 else "REFER",
                "bbox": [0, 0, 10, 10],
                "tray_id": "T1",
            })
        looks.append(bulbs)
    return merge_looks(looks), looks


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--lots", type=int, default=40)
    ap.add_argument("--seed", type=int, default=2026)
    ap.add_argument("--reset", action="store_true",
                    help="delete the existing database first")
    args = ap.parse_args()

    if args.reset and db.DB_PATH.exists():
        db.DB_PATH.unlink()
        for suffix in ("-wal", "-shm"):
            extra = db.DB_PATH.with_name(db.DB_PATH.name + suffix)
            if extra.exists():
                extra.unlink()
        print(f"Deleted {db.DB_PATH}")

    db.init_db()
    rng = random.Random(args.seed)

    centre_ids: dict[str, int] = {}
    for name, district in CENTRES:
        centre_ids[name] = db.upsert_centre(name, district)
    print(f"{len(centre_ids)} centres")

    now = datetime.now(timezone.utc)
    runs = 0
    for name, centre_id in centre_ids.items():
        for days_ago in range(DAYS, -1, -1):
            run_at = (now - timedelta(days=days_ago)).isoformat(timespec="seconds")
            db.insert_reference_run(centre_id, _reference_score(name, days_ago, rng), run_at)
            runs += 1
    print(f"{runs} reference runs over {DAYS} days")

    names = list(centre_ids)
    for i in range(args.lots):
        centre_name = names[i % len(names)]
        result, looks = _fake_lot(rng)
        created = (now - timedelta(days=rng.randint(0, DAYS),
                                   hours=rng.randint(0, 23))).isoformat(timespec="seconds")
        db.insert_lot(
            centre_id=centre_ids[centre_name],
            lot_ref=f"LOT-2026-{1000 + i}",
            result=result,
            meta={
                "farmer_name": rng.choice(FARMERS),
                "officer_name": rng.choice(OFFICERS),
                "created_at": created,
                "lat": round(rng.uniform(11.0, 20.5), 5),
                "lon": round(rng.uniform(74.0, 80.5), 5),
                "calibrated": True,
                "looks": looks,
            },
        )
    print(f"{args.lots} historical lots")

    print("\nchain verification:")
    for name, centre_id in centre_ids.items():
        intact, count = db.verify_chain(centre_id)
        print(f"  {name:<16} {'OK ' if intact else 'BROKEN'}  {count} records")

    print("\ndrift report:")
    for row in db.drift_report():
        flag = "  <-- flagged" if row["status"] == "RECALIBRATE" else ""
        print(f"  {row['name']:<16} latest {row['latest']:5.1f}%  "
              f"drift {row['drift']:+6.2f}  {row['status']}{flag}")

    print("\nOpen http://localhost:8000/dashboard")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
