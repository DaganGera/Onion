# ARCHITECTURE

See ../CLAUDE.md and D:/Marcben/SAMA_SECOND_MEMORY.md §2 for the locked architecture.
Summary: ONE FastAPI process (app/main.py) serves static UI + inference API; pure math in
app/grading.py (frozen); calibration ladder app/scale.py; geometry app/mat_layout.py;
SQLite hash chain app/db.py; arbitration app/arbitration.py; scripts/ gates T0-T12;
YOLO26s @1024 weights/best.pt.

Orchestration layer:
- .opencode/agents/*.md — 8 specialist agents, all pinned to openrouter/stealth/ox-alpha
- .agent/* — persistent state (RUN_STATE, METRICS, DECISIONS, HISTORY.jsonl, ROADMAP)
- orchestrator/run_cycle.py — one AUDIT→…→ACCEPT cycle driven through OpenCode CLI
