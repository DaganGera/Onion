"""Shared run-config plumbing for every script that produces a number.

Two jobs, both about contestability of the certificate:

1. ONE reader for the YOLO26 inference mode. Scripts used to omit `end2end`
   on predict(), which falls back to Ultralytics' own default -- silently
   evaluating a DIFFERENT inference mode than the deployed app, which reads
   app/constants.json. Every script now pins the mode through
   yolo26_inference_kwargs(), sourced from app/constants.json key `e2e_mode`
   (default False, the accuracy-first NMS path).

2. echo_config() -- every run output carries its own configuration: UTC
   timestamp, git commit, library versions, plus whatever the caller
   measured. A number nobody can reproduce is an anecdote, not a metric.

No ultralytics/torch import at module level: this box may be the CPU laptop,
and the helpers must stay importable for tests either way.
"""

from __future__ import annotations

import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def resolve_e2e_mode() -> bool:
    """The shipped inference mode, from app/constants.json (default False).

    Single source of truth is grading.CONSTANTS -- the same dict the app
    serves inference with. If scripts disagree with the app, the scripts
    are wrong, and after this helper they cannot be.
    """
    from app import grading
    return bool(grading.CONSTANTS.get("e2e_mode", False))


def yolo26_inference_kwargs(imgsz: int = 1024) -> dict:
    """YOLO26 predict()/val() kwargs, pinned in one place.

    imgsz 1024 (small defects die at 640), max_det 300 (the one-to-one head
    was trained at 300), end2end from constants.json. Callers add conf /
    device / verbose themselves.
    """
    return {"imgsz": int(imgsz), "max_det": 300, "end2end": resolve_e2e_mode()}


def git_commit() -> str:
    """Short SHA of the working tree, 'unknown' outside a git checkout."""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(ROOT), capture_output=True, text=True, timeout=10, check=True,
        )
        sha = out.stdout.strip()
        return sha[:12] if sha else "unknown"
    except Exception:  # noqa: BLE001 -- no git, no problem, just say so
        return "unknown(no-git)"


def library_versions() -> dict:
    """Versions of everything that can move a number between machines."""
    versions: dict[str, str] = {}
    for module, label in (("numpy", "numpy"), ("cv2", "opencv"),
                          ("torch", "torch"), ("ultralytics", "ultralytics")):
        try:
            versions[label] = str(__import__(module).__version__)
        except Exception:  # noqa: BLE001
            versions[label] = "not-installed"
    return versions


def echo_config(out_path=None, **fields) -> dict:
    """Build the run's config record, print one line, optionally write JSON.

    Returns the dict so callers can embed it in their own summary files.
    Never raises on bad out_path -- a config echo must not kill a finished
    measurement.
    """
    cfg: dict = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "git_commit": git_commit(),
        "python": platform.python_version(),
        "platform": platform.platform(),
    }
    cfg.update(library_versions())
    cfg.update(fields)

    if out_path is not None:
        try:
            out_path = Path(out_path)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(json.dumps(cfg, indent=2, default=str),
                                encoding="utf-8")
        except OSError:
            pass

    printable = " ".join(f"{k}={v}" for k, v in fields.items())
    suffix = f" -> {out_path}" if out_path is not None else ""
    print(f"[run-config] {printable}{suffix}")
    return cfg
