# BASELINE (Phase A) — recorded 2026-08-24

## Environment
- Python 3.11.4 at C:/Users/ADMIN/AppData/Local/Programs/Python/Python311/python.exe
  (NOTE: bare `python` on PATH resolves to the Hermes agent venv — always use the full path)
- torch cu132, ultralytics 8.4.127, cv2 5.0.0, RTX 5060 Ti 15.9GB
- opencode 1.18.21 at C:/Users/ADMIN/AppData/Roaming/npm/opencode
- openrouter/stealth/ox-alpha verified in catalog

## Tests
`python -m pytest tests -q` → 68 passed, 0 failed.

## Gates passing (synthetic data): T0 T2 T3 T4 T5 T6 T7 T10 T11 T12
Not executed (physical): T1-print half, T8 phone-over-tunnel.

## Key baseline metrics (SYNTHETIC)
| metric | value |
|---|---|
| holdout mAP50 | 0.978 |
| 1-look defect miss | 20.5% |
| 2-look defect miss | 10.8% |
| lot Grade-A error | 1.2 pts |
| homography size MAE | 0.72 mm |
| CPU p95 latency | 108 ms |
| refer rate (NMS) | 1.4% |

## Known gaps / risks
1. All model evidence is synthetic; realism ceiling documented.
2. doubles class weakest & rarest.
3. No git repo yet (init pending).
4. Failure-injection coverage for API edge cases untested by automation.
