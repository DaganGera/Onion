#!/usr/bin/env python
"""SAMA continuous improvement loop — runs until the deadline, no idle time.

Each iteration:
  1. Pick the highest-value task from a rotating priority ladder
     (open red-team findings > edge cases > polish > innovation).
  2. Dispatch one specialist agent via OpenCode (all on ox-alpha).
  3. Gate: full pytest must stay green; revert the working tree if not.
  4. Log to HISTORY.jsonl and update RUN_STATE.json.
Loops until START + BUDGET_HOURS. Never sleeps while work remains.

Usage: python orchestrator/loop.py [--dry-run]
"""
import json
import subprocess
import sys
import datetime
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AGENT_DIR = ROOT / ".agent"
MODEL = "openrouter/stealth/ox-alpha"
PY = "C:/Users/ADMIN/AppData/Local/Programs/Python/Python311/python.exe"
BUDGET_HOURS = float(__import__("os").environ.get("SAMA_LOOP_HOURS", "8"))

# Rotating priority ladder: (agent, task template). Index advances each cycle
# and wraps, so no single subsystem monopolizes the run.
LADDER = [
    ("backend-engineer", (
        "TASK LOOP-B{n}: Read .agent/redteam/RT-001.md and .agent/HISTORY.jsonl "
        "(last entries) to see what is already fixed. Pick the highest-value OPEN "
        "red-team finding in app/*.py scope (suggested order: T-7 certificate "
        "evidence section empty -> persist an annotated thumbnail per look and show "
        "it on report.html; T-5 chain-fork race guard; T-6 tamper cascade scoping). "
        "Implement it with tests. Never touch grading math or data/holdout.")),
    ("innovator", (
        "TASK LOOP-I{n}: Per your role: (1) counter one open documented limitation, "
        "(2) hunt one untested realistic field edge case and add a graceful path or "
        "test for it, (3) extend .agent/IMPACT_EVIDENCE.md with one new computed, "
        "honestly-labelled estimate that strengthens the pitch (e.g., CI width vs "
        "typical manual re-grade disagreement), (4) sharpen one first-90-seconds "
        "judge touchpoint. Keep changes small and tested.")),
    ("india-access", (
        "TASK LOOP-A{n}: India-viability pass {n}. Pick ONE highest-value item: "
        "client-side image downscale before upload (canvas ≤1600px, JPEG q80) with "
        "before/after KB measured and shown honestly in the UI; network timeout + "
        "retry-once + 'save and retry' on every fetch; verify zero external CDN "
        "dependencies for full offline demo; Hindi/English completeness + ≥48px "
        "touch targets audit; per-lot data-cost measurement written to "
        ".agent/IMPACT_EVIDENCE.md. Keep vanilla JS; pytest must stay green.")),
    ("demo-wow", (
        "TASK LOOP-W{n}: Wow-factor pass {n}. Pick ONE: make tamper-demo flip red "
        "in <1s and restore bulletproof; big glanceable Grade-A gauge with Wilson CI "
        "whiskers on result screen (Indian number format, bilingual); two-phone "
        "dispute theater polish; certificate A4 print perfection from a phone; honest "
        "progress text during inference ('analysing tray… 34 onions found'). Never "
        "fake evidence; every addition must degrade gracefully. pytest green.")),
    ("jury-simulator", (
        "TASK LOOP-J{n}: Per your role: rotate to the next panelist, fire 5 fresh "
        "questions grounded in the actual code/UI, answer honestly with file:line "
        "citations, mark weak answers CRITICAL-PREP, convert each into a small "
        "dispatchable prep task in .agent/JURY_LOG.md, and add polished 30-second "
        "answers to .agent/JURY_ANSWERS.md. Read-only on production code.")),
    ("qa-engineer", (
        "TASK LOOP-Q{n}: Adversarial pass {n}. Find NEW failure modes not covered by "
        "tests/test_failure_injection.py: concurrent /analyze uploads, duplicate lot "
        "finalization, unicode/multibyte garbage in JSON fields, clock skew in lot "
        "timestamps, DB disk-full simulation, oversized multipart. Add regression "
        "tests; fix genuine defects you expose (explain each fix).")),
    ("frontend-engineer", (
        "TASK LOOP-F{n}: Judge-experience pass {n} on app/static/. Pick ONE: "
        "sunlight-legibility contrast audit of result screen; bilingual completeness "
        "check (every new string has HI); certificate print layout at A4 from a phone; "
        "dashboard tells the drift story in one glance; error states all have recovery "
        "actions. Implement, keep vanilla JS, verify pages load without JS errors.")),
    ("data-scientist", (
        "TASK LOOP-D{n}: Statistical rigor pass {n}. Current top item: S-2 — Wilson "
        "CI treats two looks as independent bulbs. Analyze the actual correlation "
        "structure, design the honest fix (e.g., effective-n or cluster-aware width), "
        "and IF it requires touching grading.py follow the unfreeze protocol: new "
        "tests first, DECISIONS.md entry, minimal diff. Otherwise write the analysis "
        "to .agent/STATISTICS_NOTES.md and implement any non-frozen part (API fields, "
        "UI display of effective n).")),
    ("research-evidence", (
        "TASK LOOP-R{n}: Evidence hardening pass {n}. Verify one more claim family "
        "(NABCONS rates, mandi volumes, manual grading time-per-lot literature, "
        "onion post-harvest loss %). Update EVIDENCE_AUDIT.md and IMPACT_EVIDENCE.md "
        "with real citations (author, year, doi/url, access date). Flag anything in "
        "the UI still unsupported.")),
    ("cv-engineer", (
        "TASK LOOP-C{n}: Model/pipeline pass {n} WITHOUT training (no GPU budget): "
        "audit scripts/train.py, eval_lot.py, calibrate_size.py, measure_occlusion.py "
        "for correctness against the YOLO26 rules (imgsz 1024, max_det 300, e2e from "
        "constants.json); check constants.json consistency across app+scripts; add a "
        "reproducibility check (seed handling, config echo in run outputs); improve "
        "eval_lot.py reporting if it lacks per-lot error distribution output.")),
]


def log(event, detail, agent="master"):
    ts = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    with open(AGENT_DIR / "HISTORY.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": ts, "agent": agent, "event": event,
                            "detail": str(detail)[:500]}) + "\n")


def sh(cmd, timeout=2400):
    return subprocess.run(cmd, capture_output=True, text=True,
                          cwd=ROOT, timeout=timeout)


def tests_pass():
    r = sh([PY, "-m", "pytest", "tests", "-q"], timeout=600)
    ok = r.returncode == 0
    tail = (r.stdout or "").strip().splitlines()[-1:] or ["(no output)"]
    return ok, tail[0]


def update_state(fn):
    p = AGENT_DIR / "RUN_STATE.json"
    st = json.loads(p.read_text(encoding="utf-8"))
    fn(st)
    st["last_audit"] = datetime.datetime.now().astimezone().isoformat(
        timespec="seconds")
    p.write_text(json.dumps(st, indent=2), encoding="utf-8")


def main():
    dry = "--dry-run" in sys.argv
    start = time.time()
    deadline = start + BUDGET_HOURS * 3600
    n = int(datetime.datetime.now().strftime("%H%M"))  # unique-ish task suffix
    i = 0
    print(f"[loop] starting, budget {BUDGET_HOURS} h, until "
          f"{datetime.datetime.fromtimestamp(deadline)}")
    log("loop_start", f"budget_hours={BUDGET_HOURS}")

    while time.time() < deadline:
        remaining_h = (deadline - time.time()) / 3600
        # Final 10%: stabilization only — restrict to QA/frontend/backend safe passes.
        if remaining_h < BUDGET_HOURS * 0.10:
            pool = [e for e in LADDER if e[0] in
                    ("qa-engineer", "frontend-engineer", "backend-engineer")]
            phase = "F-stabilization"
        else:
            pool = LADDER
            phase = "B/C/D-loop"

        agent, tmpl = pool[i % len(pool)]
        n += 1
        task = tmpl.format(n=n)

        ok0, msg0 = tests_pass()
        if not ok0:
            print(f"[loop] PRE-TASK TESTS BROKEN ({msg0}) — halting dispatches")
            log("loop_blocked", f"baseline broken: {msg0}")
            time.sleep(60)
            continue

        print(f"\n[loop] === cycle {i+1} | phase {phase} | {agent} | "
              f"{remaining_h:.1f} h left ===")
        print(f"[loop] task: {task[:140]}...")
        log("cycle_start", {"cycle": i + 1, "agent": agent, "phase": phase})

        if dry:
            time.sleep(2)
        else:
            try:
                r = sh(["opencode.cmd", "run", "--model", MODEL,
                        "--agent", agent, task], timeout=2400)
                out = (r.stdout or "")[-1500:]
                print(out)
                log("cycle_result", {"agent": agent,
                                     "rc": r.returncode, "tail": out[-300:]},
                    agent=agent)
            except subprocess.TimeoutExpired:
                print("[loop] agent timed out; moving on")
                log("cycle_timeout", agent)

        # Post gate: tree must be green; otherwise discard uncommitted changes.
        ok1, msg1 = tests_pass()
        dirty = sh(["git", "status", "--porcelain"]).stdout.strip()
        if ok1:
            if dirty:
                sh(["git", "add", "-A"])
                sh(["git", "-c", "user.name=ox-alpha loop",
                    "-c", "user.email=loop@local",
                    "commit", "-qm", f"LOOP cycle {i+1}: {agent} — {msg1}"])
                log("cycle_committed", msg1)
                update_state(lambda s: s.setdefault(
                    "completed_tasks", []).append(
                    f"cycle{i+1}:{agent}:{msg1}"))
            print(f"[loop] cycle {i+1} COMMITTED ({msg1})")
        else:
            if dirty:
                sh(["git", "checkout", "--", "."])
                sh(["git", "clean", "-fd", "app", "tests", "scripts"])
                log("cycle_rolled_back", msg1)
            print(f"[loop] cycle {i+1} ROLLED BACK ({msg1})")

        i += 1

    print(f"\n[loop] BUDGET EXHAUSTED after {i} cycles. Writing final summary.")
    log("loop_end", f"cycles={i}")
    update_state(lambda s: s.update(phase="COMPLETE"))
    r = sh([PY, "-m", "pytest", "tests", "-q"], timeout=600)
    summary = ["# Loop final state",
               f"cycles: {i}",
               f"final tests: {(r.stdout or '').strip().splitlines()[-1:]}"]
    (AGENT_DIR / "LOOP_SUMMARY.md").write_text("\n".join(summary),
                                               encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
