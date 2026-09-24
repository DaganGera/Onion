# SAMA — Multi-Agent Engineering Run: FINAL REPORT

Run date: 2026-08-24 · Orchestrator + 8 specialist agents · all on
openrouter/stealth/ox-alpha via OpenCode 1.18.21 (harness only).

## 1. Starting state
Software complete per STATUS.md; gates T0,T2-T7,T10-T12 passing on synthetic data;
68 pytest tests green; no git repo; OpenCode had NO project config (global default only).

## 2. What was built (the system itself)
- `opencode.json` — project model locked to openrouter/stealth/ox-alpha for all 8 agents.
- `.opencode/agents/` — master, cv-engineer, data-scientist, backend-engineer,
  frontend-engineer, qa-engineer, research-evidence, red-team-judge.
- `.agent/` — persistent state: RUN_STATE.json, METRICS.json, DECISIONS.md,
  HISTORY.jsonl, ROADMAP.md, BASELINE.md, RULES.md, EVIDENCE_AUDIT.md, redteam/.
- `orchestrator/run_cycle.py` — git-isolated dispatch → test gate → accept/reject,
  history logging. Verified working end-to-end on real tasks.

## 3. Cycles executed (each: audit → delegate → implement → test → verdict)
| Task | Agent | Result | Verdict |
|---|---|---|---|
| QA-000 audit | qa | found missing global exception handler class | finding |
| B-001 | backend | global JSON exception handlers, hardened /api/health + page routes, 17 tests | ACCEPTED |
| R-001 | research | evidence audit; flagged ICAR-DOGR band attribution + PS number | findings |
| Q-001 | qa | 23 failure-injection tests; zero app defects found | ACCEPTED |
| DS-001 | data-sci | bands verified against dogr.res.in — A>80 CONFIRMED (D7) | resolved D5 |
| RT-001 | red-team | 17 ranked findings incl. dead dispute flow, aruco boot fragility | findings |
| B-002 | backend | dispute workflow wired end-to-end; app boots without cv2.aruco; 18 tests | ACCEPTED |
| F-001 | frontend | HEIC fallback toast; replay exhaustion now cycles instead of dying | ACCEPTED |

## 4. Major bugs fixed
1. Any unhandled exception could produce a raw non-JSON 500 (whole defect class closed).
2. `/api/health` could crash on stray cache filenames.
3. Dispute button was dead code — farmer contest path now works end-to-end.
4. Missing cv2.aruco killed the entire app including replay mode at import time.
5. Replay demo hard-exhausted at capture #7.
6. Orchestrator itself: Windows needs `opencode.cmd` for subprocess (found+fixed in run 1).
7. LOOP-I858: `/tamper/restore-all` fallback sweep corrupted legacy v1 records by
   trusting their never-signed result_json as restore truth (live incident on lot 51;
   signed value recovered via row_hash brute-force; sweep now requires a matching
   pinned digest and names what it refused to touch — DECISIONS D17).

## 5. Verification status at close
- **127 pytest tests green** (68 baseline → 127), smoke_test ALL PASS.
- Gate T12 re-measured after all changes: 4/4 configs under 400 ms p95 budget
  (GPU 96.6 ms / CPU 139 ms on the NMS path that ships).
- Every merge verified by orchestrator test gate before acceptance.

## 6. Known limitations (honest)
- All model metrics remain SYNTHETIC-data numbers; real-photo revalidation still owed.
- Gates T8 (phone over tunnel) and printed-mat caliper check are physical, not done here.
- Disputes recorded but live outside the hash envelope (tamper-EVIDENT chain, stated).
- Grade-A CI two-look clustering (red-team S-2): CLOSED via finalize-time overlay (D11/D14); frozen pooled bounds kept on the record as provenance.
- Certified defect rate still uses max-per-look (RT-001 S-1) — unfreezing grading.py remains open. Visible compensation shipped (D15): every certificate prints the per-tray pooled cross-check beside the ceiling; measured structural bias quantified in IMPACT_EVIDENCE §3d.
- No signature mechanism beyond the hash chain (RT-001 T-2, open).
- PS number 26046 vs SIH26031 needs confirmation from registration (D6).## 7. Commands
```
# run (one process)
uvicorn app.main:app --host 0.0.0.0 --port 8000
# offline demo
http://localhost:8000/?replay=1
# tests
C:/Users/ADMIN/AppData/Local/Programs/Python/Python311/python.exe -m pytest tests -q   # expect: 127 passed
C:/Users/ADMIN/AppData/Local/Programs/Python/Python311/python.exe scripts/smoke_test.py # expect: ALL SMOKE CHECKS PASSED
C:/Users/ADMIN/AppData/Local/Programs/Python/Python311/python.exe scripts/bench.py     # expect: GATE T12 PASS
# orchestration loop (continue improving)
python orchestrator/run_cycle.py <agent> "<task>" [branch]
python orchestrator/run_cycle.py --status
```

## 8. Recommended next steps
1. Highest-value remaining engineering: CI correlation fix (S-2) with data-scientist
   sign-off, then defect-% confidence interval (S-3) so arbitration can compare defects.
2. Physical: print mat (Actual size/100%), caliper 40.0±0.3 mm, shoot real trays,
   run T8 phone-over-tunnel — these gate every real number in the pitch.
3. Re-run train/calibrate/occlusion/eval_lot on real photos; refit constants.json.
4. Rehearse the five demo beats from SAMA_SECOND_MEMORY §4.
