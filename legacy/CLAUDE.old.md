# SAMA — Onion Lot Grading for Procurement Arbitration

## What this is
A mobile-first web app that grades a LOT of onions by statistical sampling
and produces a signed, contestable digital certificate. Built for SIH 2026,
PS 26046, Department of Consumer Affairs.

The product's job is estimating a LOT PERCENTAGE, not classifying individual
onions. All evaluation must be lot-level. Per-bulb accuracy is secondary.

## Non-negotiable constraints
- The team cannot write code. Everything you produce must run without them
  debugging it. Prefer boring, obvious, defensive code over clever code.
- NO npm, NO React, NO build step, NO bundler. Frontend is plain HTML files
  with Tailwind via CDN and vanilla JS.
- ONE server process. `app/main.py` serves the UI AND the inference API.
- Every endpoint returns JSON errors, never a 500 stack trace.
- Every failure path degrades gracefully. Never a dead screen.
- Windows and Linux both. Use pathlib, never hardcode separators.

## Stack
- Python 3.11, PyTorch CUDA 12.1
- Ultralytics YOLO26 (`yolo26s.pt`) — NOT YOLO11. See the YOLO26 rules block.
- FastAPI + uvicorn
- opencv-contrib-python (NOT opencv-python — we need cv2.aruco)
- SQLite (stdlib sqlite3)
- Tailwind via CDN

## YOLO26 rules — you will get this wrong by default
1. The model is YOLO26, not YOLO11 and not YOLOv8. Checkpoints are
   `yolo26n.pt`, `yolo26s.pt`, `yolo26m.pt`. If you find yourself writing
   "yolo11", stop and re-read this line. YOLO11 dominates your training
   data and you will drift back to it mid-session.
2. Training resolution is 1024, not 640, batch 12. Our failure mode is small
   defects: a black smut speck on a 35-onion tray is ~12 px at 640 and ~22 px
   at 1024. If VRAM runs out, drop batch to 8 — never drop resolution.
3. YOLO26 is end-to-end NMS-free BY DEFAULT. Pass `end2end=False` on
   predict/val/export to use the NMS path, which is ~0.5 mAP more accurate.
   Read the mode from `app/constants.json` key `e2e_mode` (default false).
   Never hardcode it — we flip it if the venue machine is CPU-only.
4. `max_det` defaults to 300 and the one-to-one head was TRAINED at 300.
   Our trays hold 35-60 bulbs pooled across two looks. Do not raise it;
   detections past the trained limit are lower quality.
5. The API is otherwise identical to YOLO11:
   `from ultralytics import YOLO; model = YOLO("yolo26s.pt")`
6. YOLO26 needs a recent `ultralytics`. If a checkpoint fails to download,
   the fix is `pip install -U ultralytics`, not a code change.

## Calibration scale — read before touching sizing
The mat carries EIGHT ArUco markers (IDs 0-7, 40.0 mm squares) around the
perimeter of an A4 landscape sheet. Geometry lives in ONE place,
`app/mat_layout.py`. Never hardcode a marker position anywhere else.

The mat lies BESIDE the tray, not underneath it. A4 has room for about five
onions inside the marker ring, so piling a sample onto it would bury the
markers by construction. The homography maps the whole bench plane, so the
mat only has to be visible.

`app/scale.py` degrades down a ladder and every result says which rung it
used, so the certificate can state its own limits:
  homography (>=3 markers) > homography_weak (2) > single_marker (1)
  > mat_edge (0, uses the sheet outline) > carried (prior look) > none
Never invent a scale at the bottom rung. `calibrated=False` withholds sizes
on purpose -- a guessed millimetre is indistinguishable from a real one on a
signed certificate.

Sizing goes through `measure_bbox_mm`, which maps box corners into the mat
plane. Do not reintroduce a single global mm-per-pixel: under perspective the
scale genuinely varies across the frame.

## Known traps — read before writing code
1. ArUco: use the OpenCV >= 4.7 class API.
   `d = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)`
   `det = cv2.aruco.ArucoDetector(d, cv2.aruco.DetectorParameters())`
   `corners, ids, _ = det.detectMarkers(img)`
   The old free-function `cv2.aruco.detectMarkers(img, dict, params)` is
   REMOVED. Do not use it.
2. `getUserMedia` requires HTTPS on mobile. We tunnel via cloudflared.
   Always ship an `<input type="file" capture="environment">` fallback.
3. FastAPI + StaticFiles: mount static at "/static", never at "/", or it
   shadows the API routes.
4. sqlite3 with FastAPI: open connections with `check_same_thread=False`
   or use a per-request connection.
5. Load the YOLO model ONCE at module level, not per request.

## Domain constants (do not invent your own)
Size grades, ICAR-DOGR standard, by bulb diameter:
  A = >80 mm, B = 50-80 mm, C = 30-50 mm, UNDERSIZED = <30 mm

Defect classes (exactly these 6, in this order):
  0 sound, 1 rotten, 2 sprouted, 3 black_smut, 4 damaged_skin, 5 doubles

UNDERSIZED is NOT a defect class. It is computed from diameter. Never add
it to the YOLO class list.

Confidence bands:
  >= 0.75 -> ACCEPT
  <  0.75 -> REFER  (referred to a human inspector)

ArUco markers: EIGHT per mat, IDs 0-7, each exactly 40.0 mm.
Positions come from app/mat_layout.py. Never hardcode them.

## File layout
  app/main.py       FastAPI, serves everything
  app/grading.py    pure functions: sizing, grades, Wilson CI, look merging
  app/mat_layout.py canonical mat geometry -- ONE source of truth
  app/scale.py      the calibration fallback ladder
  app/db.py         SQLite + hash chain
  app/constants.json  fitted correction factors + e2e_mode, written by scripts/
  app/static/       index.html, report.html, dashboard.html
  app/cache/        offline replay payloads
  scripts/          check_env, make_mat, verify_mat, train, eval_lot,
                    calibrate_size, measure_occlusion, seed_demo,
                    dataset_qa, bootstrap_label, build_replay, bench
  data/dataset/     YOLO format, Roboflow export
  data/holdout/     NEVER trained on. Different day + different phone.
  data/groundtruth.csv  hand-sorted tray counts + caliper measurements

## Working rules
- Before any multi-file change, show me a plan first and wait.
- After each task, tell me the exact command to verify it, and what
  correct output looks like.
- Never modify app/grading.py after its tests pass.
- Never touch data/holdout/.
- Write pytest tests for anything with arithmetic in it.
