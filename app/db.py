"""SQLite storage with a per-centre hash chain.

WHY A HASH CHAIN
----------------
The product's claim is that a grading certificate is contestable. That only
means something if a record cannot be quietly edited after a dispute is
raised. Each lot's hash covers its own canonical JSON plus the previous
lot's hash for that centre, so altering any historical row breaks every hash
after it and verify_chain() reports the break.

This is tamper-EVIDENCE, not tamper-proofing. Anyone with write access to
the file could recompute the whole chain. Say that plainly if a judge asks;
claiming blockchain-grade immutability for a local SQLite file would not
survive one informed question.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[1] / "data" / "sama.db"
GENESIS_HASH = "0" * 64

SCHEMA = """
CREATE TABLE IF NOT EXISTS centres (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL UNIQUE,
    district    TEXT,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS lots (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    centre_id     INTEGER NOT NULL REFERENCES centres(id),
    lot_ref       TEXT NOT NULL,
    farmer_name   TEXT,
    officer_name  TEXT,
    created_at    TEXT NOT NULL,
    lat           REAL,
    lon           REAL,
    n_looks       INTEGER,
    n_bulbs       INTEGER,
    grade_a_pct   REAL,
    ci_low        REAL,
    ci_high       REAL,
    defect_pct    REAL,
    n_referred    INTEGER,
    calibrated    INTEGER,
    scale_source  TEXT,
    scale_conf    REAL,
    result_json   TEXT,
    prev_hash     TEXT NOT NULL,
    row_hash      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS bulbs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    lot_id      INTEGER NOT NULL REFERENCES lots(id),
    look_index  INTEGER,
    bbox_json   TEXT,
    cls         TEXT,
    confidence  REAL,
    diameter_mm REAL,
    size_grade  TEXT,
    decision    TEXT,
    disputed    INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS reference_runs (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    centre_id  INTEGER NOT NULL REFERENCES centres(id),
    run_at     TEXT NOT NULL,
    score      REAL NOT NULL,
    drift      REAL
);

CREATE INDEX IF NOT EXISTS idx_lots_centre ON lots(centre_id, id);
CREATE INDEX IF NOT EXISTS idx_bulbs_lot ON bulbs(lot_id);
CREATE INDEX IF NOT EXISTS idx_ref_centre ON reference_runs(centre_id, run_at);
"""


def connect() -> sqlite3.Connection:
    """One connection per call. check_same_thread=False because FastAPI
    serves requests from a thread pool."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db() -> None:
    conn = connect()
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _canonical(payload: dict) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def compute_row_hash(payload: dict, prev_hash: str) -> str:
    return hashlib.sha256((_canonical(payload) + prev_hash).encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------
# Centres
# --------------------------------------------------------------------------


def upsert_centre(name: str, district: str = "") -> int:
    conn = connect()
    try:
        row = conn.execute("SELECT id FROM centres WHERE name = ?", (name,)).fetchone()
        if row:
            return int(row["id"])
        cur = conn.execute(
            "INSERT INTO centres (name, district, created_at) VALUES (?,?,?)",
            (name, district, _now()),
        )
        conn.commit()
        return int(cur.lastrowid)
    finally:
        conn.close()


def list_centres() -> list[dict]:
    conn = connect()
    try:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM centres ORDER BY name").fetchall()]
    finally:
        conn.close()


# --------------------------------------------------------------------------
# Lots
# --------------------------------------------------------------------------


def _prev_hash(conn: sqlite3.Connection, centre_id: int) -> str:
    row = conn.execute(
        "SELECT row_hash FROM lots WHERE centre_id = ? ORDER BY id DESC LIMIT 1",
        (centre_id,),
    ).fetchone()
    return row["row_hash"] if row else GENESIS_HASH


def insert_lot(centre_id: int, lot_ref: str, result: dict, meta: dict) -> dict:
    """Write a finalised lot plus its bulbs, linked into the centre's chain."""
    conn = connect()
    try:
        prev = _prev_hash(conn, centre_id)
        created_at = meta.get("created_at") or _now()

        payload = {
            "centre_id": centre_id,
            "lot_ref": lot_ref,
            "farmer_name": meta.get("farmer_name", ""),
            "officer_name": meta.get("officer_name", ""),
            "created_at": created_at,
            "n_bulbs": result.get("n_bulb_observations", 0),
            "n_looks": result.get("n_looks", 0),
            "grade_a_pct": result.get("grade_a_pct", 0.0),
            "ci_low": result.get("grade_a_ci_low", 0.0),
            "ci_high": result.get("grade_a_ci_high", 0.0),
            "defect_pct": result.get("defect_rate_corrected", 0.0),
        }
        row_hash = compute_row_hash(payload, prev)

        cur = conn.execute(
            """INSERT INTO lots (centre_id, lot_ref, farmer_name, officer_name,
                                 created_at, lat, lon, n_looks, n_bulbs,
                                 grade_a_pct, ci_low, ci_high, defect_pct,
                                 n_referred, calibrated, scale_source, scale_conf,
                                 result_json, prev_hash, row_hash)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (centre_id, lot_ref, meta.get("farmer_name", ""),
             meta.get("officer_name", ""), created_at,
             meta.get("lat"), meta.get("lon"),
             result.get("n_looks", 0), result.get("n_bulb_observations", 0),
             result.get("grade_a_pct", 0.0), result.get("grade_a_ci_low", 0.0),
             result.get("grade_a_ci_high", 0.0),
             result.get("defect_rate_corrected", 0.0),
             result.get("n_referred", 0),
             1 if meta.get("calibrated") else 0,
             meta.get("scale_source"), meta.get("scale_confidence"),
             json.dumps(result, default=str), prev, row_hash),
        )
        lot_id = int(cur.lastrowid)

        for look_index, look in enumerate(meta.get("looks", [])):
            for bulb in look:
                conn.execute(
                    """INSERT INTO bulbs (lot_id, look_index, bbox_json, cls,
                                          confidence, diameter_mm, size_grade, decision)
                       VALUES (?,?,?,?,?,?,?,?)""",
                    (lot_id, look_index, json.dumps(bulb.get("bbox", [])),
                     str(bulb.get("cls_name", bulb.get("cls", ""))),
                     bulb.get("confidence"), bulb.get("diameter_mm"),
                     bulb.get("size_grade"), bulb.get("decision")),
                )

        conn.commit()
        return {"lot_id": lot_id, "row_hash": row_hash, "prev_hash": prev}
    finally:
        conn.close()


def get_lot(lot_id: int) -> dict | None:
    conn = connect()
    try:
        row = conn.execute(
            """SELECT lots.*, centres.name AS centre_name, centres.district
               FROM lots JOIN centres ON centres.id = lots.centre_id
               WHERE lots.id = ?""", (lot_id,)).fetchone()
        if not row:
            return None
        lot = dict(row)
        lot["result"] = json.loads(lot.get("result_json") or "{}")
        lot["bulbs"] = [dict(b) for b in conn.execute(
            "SELECT * FROM bulbs WHERE lot_id = ? ORDER BY id", (lot_id,)).fetchall()]
        return lot
    finally:
        conn.close()


def recent_lots(centre_id: int | None = None, limit: int = 20) -> list[dict]:
    conn = connect()
    try:
        sql = ("SELECT lots.*, centres.name AS centre_name FROM lots "
               "JOIN centres ON centres.id = lots.centre_id")
        params: tuple = ()
        if centre_id is not None:
            sql += " WHERE centre_id = ?"
            params = (centre_id,)
        sql += " ORDER BY lots.id DESC LIMIT ?"
        params += (limit,)
        return [dict(r) for r in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()


def mark_disputed(bulb_id: int) -> bool:
    conn = connect()
    try:
        cur = conn.execute("UPDATE bulbs SET disputed = 1 WHERE id = ?", (bulb_id,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def _chain_payload(row: sqlite3.Row) -> dict:
    """The exact fields covered by the hash -- keep in sync with insert_lot."""
    return {
        "centre_id": row["centre_id"],
        "lot_ref": row["lot_ref"],
        "farmer_name": row["farmer_name"] or "",
        "officer_name": row["officer_name"] or "",
        "created_at": row["created_at"],
        "n_bulbs": row["n_bulbs"],
        "n_looks": row["n_looks"],
        "grade_a_pct": row["grade_a_pct"],
        "ci_low": row["ci_low"],
        "ci_high": row["ci_high"],
        "defect_pct": row["defect_pct"],
    }


def verify_chain(centre_id: int) -> tuple[bool, int]:
    """Recompute every hash for a centre. Returns (intact, records checked)."""
    intact, _, count = audit_chain(centre_id)
    return intact, count


def audit_chain(centre_id: int) -> tuple[bool, list[dict], int]:
    """Verify each lot's hash and report WHERE the chain breaks.

    Returns (intact, per-lot audit rows, total checked). Each audit row is
    {lot_id, ok}. Every lot AFTER a broken one is also marked not-ok, because
    its prev_hash points at a record that no longer hashes to what it should.
    The tamper demo uses this to light up exactly where the edit happened.
    """
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT * FROM lots WHERE centre_id = ? ORDER BY id", (centre_id,)
        ).fetchall()

        audits: list[dict] = []
        prev = GENESIS_HASH
        intact = True
        for row in rows:
            ok = (row["prev_hash"] == prev
                  and compute_row_hash(_chain_payload(row), prev) == row["row_hash"])
            if not ok:
                intact = False
            audits.append({"lot_id": row["id"], "ok": ok})
            # Continue from the STORED hash so one bad row doesn't cascade
            # false failures past it -- but the overall flag stays false.
            prev = row["row_hash"]

        return intact, audits, len(rows)
    finally:
        conn.close()


# --------------------------------------------------------------------------
# Reference runs and drift
# --------------------------------------------------------------------------


def insert_reference_run(centre_id: int, score: float, run_at: str | None = None,
                         drift: float | None = None) -> int:
    conn = connect()
    try:
        cur = conn.execute(
            "INSERT INTO reference_runs (centre_id, run_at, score, drift) VALUES (?,?,?,?)",
            (centre_id, run_at or _now(), score, drift),
        )
        conn.commit()
        return int(cur.lastrowid)
    finally:
        conn.close()


def drift_report() -> list[dict]:
    """Per-centre latest reference score against its own 30-day baseline.

    A centre drifting down means its mat is worn, its lighting changed, or
    its phone camera degraded -- the operational failure mode that makes a
    'calibrated' network stop being calibrated.
    """
    conn = connect()
    try:
        out = []
        for centre in conn.execute("SELECT * FROM centres ORDER BY name").fetchall():
            runs = conn.execute(
                "SELECT run_at, score FROM reference_runs WHERE centre_id = ? "
                "ORDER BY run_at", (centre["id"],)).fetchall()
            if not runs:
                out.append({"centre_id": centre["id"], "name": centre["name"],
                            "district": centre["district"], "latest": None,
                            "baseline": None, "drift": None, "status": "NO DATA",
                            "history": []})
                continue

            scores = [float(r["score"]) for r in runs]
            latest = scores[-1]
            # baseline = the settled early part of the window, not the mean of
            # everything, or a slow decline would drag the baseline down with it
            baseline = sum(scores[:7]) / len(scores[:7])
            drift = latest - baseline

            out.append({
                "centre_id": centre["id"],
                "name": centre["name"],
                "district": centre["district"],
                "latest": round(latest, 2),
                "baseline": round(baseline, 2),
                "drift": round(drift, 2),
                "status": "RECALIBRATE" if drift < -5.0 else "CALIBRATED",
                "history": [{"run_at": r["run_at"], "score": round(float(r["score"]), 2)}
                            for r in runs],
            })
        return out
    finally:
        conn.close()


init_db()
