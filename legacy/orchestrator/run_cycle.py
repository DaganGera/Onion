#!/usr/bin/env python
"""SAMA multi-agent orchestrator.

Drives one full AUDIT -> DELEGATE -> IMPLEMENT -> TEST -> REVIEW -> ACCEPT/REJECT
cycle through the OpenCode CLI. All agents run on openrouter/stealth/ox-alpha.

Usage:
    python orchestrator/run_cycle.py <agent-name> "<task instruction>" [branch]
    python orchestrator/run_cycle.py --status

The orchestrator is deliberately small: it manages git isolation, runs tests,
records state in .agent/, and shells out to `opencode run` for all reasoning.
"""
import json
import subprocess
import sys
import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AGENT_DIR = ROOT / ".agent"
MODEL = "openrouter/stealth/ox-alpha"

AGENTS = {
    "cv-engineer": "cv-engineer",
    "data-scientist": "data-scientist",
    "backend-engineer": "backend-engineer",
    "frontend-engineer": "frontend-engineer",
    "qa-engineer": "qa-engineer",
    "research-evidence": "research-evidence",
    "red-team-judge": "red-team-judge",
}

PY = "C:/Users/ADMIN/AppData/Local/Programs/Python/Python311/python.exe"


def log(event, detail, agent="master"):
    ts = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    with open(AGENT_DIR / "HISTORY.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": ts, "agent": agent, "event": event,
                            "detail": detail}) + "\n")


def sh(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT, **kw)


def tests_pass():
    r = sh([PY, "-m", "pytest", "tests", "-q"])
    ok = r.returncode == 0
    tail = (r.stdout or "").strip().splitlines()[-1:] or ["(no output)"]
    return ok, tail[0]


def opencode_run(agent, prompt):
    """Run a task through OpenCode as a specific agent on the locked model."""
    cmd = ["opencode.cmd", "run", "--model", MODEL, "--agent", agent, prompt]
    return sh(cmd, timeout=1800)


def git(*args):
    return sh(["git", *args])


def main():
    if len(sys.argv) >= 2 and sys.argv[1] == "--status":
        for name in ("RUN_STATE.json", "METRICS.json"):
            print(f"--- {name} ---")
            print((AGENT_DIR / name).read_text(encoding="utf-8"))
        return 0

    if len(sys.argv) < 3:
        print(__doc__)
        return 2

    agent, task = sys.argv[1], sys.argv[2]
    if agent != "master" and agent not in AGENTS:
        print(f"unknown agent {agent!r}; allowed: master + {list(AGENTS)}")
        return 2

    branch = sys.argv[3] if len(sys.argv) > 3 else None
    dirty = git("status", "--porcelain")
    if branch:
        git("checkout", "-b", branch)
        log("branch_created", branch)

    # Baseline gate: tests must be green before work starts.
    ok0, msg0 = tests_pass()
    log("baseline_tests", f"pass={ok0} {msg0}")
    if not ok0:
        print(f"ABORT: baseline tests failing before task start ({msg0})")
        return 1

    contract = (
        f"{task}\n\nTASK CONTRACT — obey .agent/RULES.md. Work only inside your "
        "subsystem. Before finishing: run the test suite "
        f"('{PY} -m pytest tests -q'), report TASK ID/summary/files changed/"
        "tests/baseline vs new metrics/regressions/recommendation/confidence."
    )
    print(f"[orchestrator] dispatching to {agent} on {MODEL} ...")
    r = opencode_run(agent, contract)
    print(r.stdout[-4000:] if r.stdout else "(no stdout)")
    if r.returncode != 0:
        print(f"[orchestrator] agent exited {r.returncode}: {r.stderr[-2000:]}")
        log("task_failed", f"{agent}: rc={r.returncode}")

    # Post gate: tests must still be green.
    ok1, msg1 = tests_pass()
    log("post_tests", f"pass={ok1} {msg1}", agent=agent)

    verdict = "ACCEPTED" if ok1 and r.returncode == 0 else "REJECTED/ROLLBACK-REQUIRED"
    log("verdict", f"{verdict} for task given to {agent}")
    state = json.loads((AGENT_DIR / "RUN_STATE.json").read_text(encoding="utf-8"))
    bucket = "completed_tasks" if verdict == "ACCEPTED" else "failed_tasks"
    state[bucket].append({"agent": agent, "task": task[:200], "tests": msg1})
    state["last_successful_action"] = f"{verdict}: {task[:120]}" if ok1 else None
    (AGENT_DIR / "RUN_STATE.json").write_text(
        json.dumps(state, indent=2), encoding="utf-8")
    print(f"[orchestrator] VERDICT: {verdict} ({msg1})")
    return 0 if verdict == "ACCEPTED" else 1


if __name__ == "__main__":
    sys.exit(main())
