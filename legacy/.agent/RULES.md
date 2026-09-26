# RULES — enforced by every agent

1. Model: openrouter/stealth/ox-alpha ONLY. Any other provider = loud failure.
2. app/grading.py FROZEN (34 tests). Unfreeze only with new tests + explicit decision.
3. data/holdout/ sacred — never trained on, never moved.
4. YOLO26 only. imgsz 1024. max_det 300. e2e_mode from constants.json.
5. No npm/React/build step. Plain HTML + vanilla JS + local Tailwind vendor.
6. One server process. Static at /static. JSON errors always, never raw 500.
7. ArUco >=4.7 class API (ArucoDetector).
8. sqlite check_same_thread=False; model loaded once module-level.
9. Never quote synthetic numbers as real-world numbers.
10. No change merges without: tests pass -> benchmark -> independent review -> master accept.
11. Never print or commit secrets/API keys.
12. git branch per substantial task (agent/<role>-<nnn>); rollback on failure.
