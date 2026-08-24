# SAMA — Onion Lot Grading for Procurement Arbitration

SIH 2026 · PS 26046 · Ministry of Consumer Affairs, Food & Public Distribution

A phone-first web app that grades a **lot** of onions by statistical sampling and issues a
signed, contestable digital certificate. It does not try to classify one onion perfectly. It
tries to tell a farmer and a procurement officer what percentage of *this lot* is Grade A,
accurately enough that both will sign.

---

## Demo day — start here

Three commands. Nothing else.

```powershell
# 1. serve
uvicorn app.main:app --host 0.0.0.0 --port 8000

# 2. expose to phones (second terminal) — HTTPS is required for the camera
.\cloudflared.exe tunnel --url http://localhost:8000

# 3. open the printed https://….trycloudflare.com URL on the phone
```

**If the network fails**, everything still works offline:

```
http://localhost:8000/?replay=1
```

Replay mode plays back cached results with a simulated delay. Capture, shake, results,
sign-off and certificate all behave identically. No model call, no GPU, no network.

**Check the server is healthy:** `http://localhost:8000/api/health`

---

## What is built

| Path | What it does |
|---|---|
| [app/grading.py](app/grading.py) | Scale detection, sizing, grade bands, Wilson CI, look merging. Pure functions, 34 tests. **Frozen.** |
| [app/main.py](app/main.py) | FastAPI. Serves the UI *and* the inference API from one process. |
| [app/db.py](app/db.py) | SQLite with a per-centre SHA-256 hash chain. |
| [app/static/index.html](app/static/index.html) | Capture flow: setup → capture → shake → capture → results → sign-off. |
| [app/static/report.html](app/static/report.html) | Print-optimised A4 certificate, WhatsApp share. |
| [app/static/dashboard.html](app/static/dashboard.html) | Centre calibration drift monitor. |
| [scripts/](scripts/) | Environment check, mat generator, dataset QA, training, evaluation, calibration fitters, replay builder, benchmark. |

No npm. No React. No build step. Two HTML files and Tailwind from a CDN.

---

## The five numbers

These come from real measurement scripts, not assertions. Re-run them after every retrain and
quote whatever they actually print.

```powershell
python scripts/calibrate_size.py      # size accuracy vs caliper
python scripts/measure_occlusion.py   # 1-look vs 2-look under-detection  (GATE T5)
python scripts/eval_lot.py            # lot Grade-A percentage error
python scripts/train.py               # per-class mAP on the holdout       (GATE T4)
python scripts/bench.py               # latency on the demo laptop         (GATE T12)
```

`calibrate_size.py` and `measure_occlusion.py` **write** their fitted factors into
`app/constants.json`. The app reads them at startup. Fit before you demo.

---

## ⚠️ The current numbers are from SYNTHETIC data

The repo ships with a procedural tray generator ([scripts/make_synthetic.py](scripts/make_synthetic.py))
so the entire pipeline runs and every gate is exercised *before* real photos exist.

**Synthetic mAP near 0.99 does not predict real-world accuracy.** Generated defects are drawn
with clean, separable colours. Real rot on a real onion under real market light is far harder.
Expect real mAP well below the synthetic figure.

What the synthetic set *does* legitimately prove:

- the ArUco → millimetre chain is correct end to end (the fitter recovers the planted
  magnification factor to within 0.7%)
- occlusion is modelled physically, so the Two-Look measurement is meaningful rather than
  a fake zero
- every script, gate and screen runs

**Replace it the moment you have real trays:**

```powershell
# delete the synthetic set, drop your Roboflow export into data/dataset/
python scripts/dataset_qa.py     # fix everything it flags
python scripts/train.py --model yolo26s.pt --imgsz 1024 --batch 12 --epochs 120
```

Never quote a synthetic number to a judge.

---

## Model: YOLO26

`yolo26s.pt` at **imgsz 1024**, not 640. The failure mode is small defects — a black smut
speck is ~12 px at 640 and ~22 px at 1024. YOLO26's **STAL** label assignment guarantees
small targets contribute to the loss, and **ProgLoss** handles the class imbalance we
genuinely have (~64% sound, ~1.4% doubles).

YOLO26 is NMS-free by default. `train.py` evaluates **both** modes and prints which wins;
`app/main.py` reads `e2e_mode` from `app/constants.json` so the mode can be flipped without
a code edit. `max_det` stays at 300 — the one-to-one head was trained at that limit and our
trays hold 35–60 bulbs.

**Licence: AGPL-3.0.** Fine for the hackathon. Deploying SAMA as a public network service
would require publishing the source or buying an Ultralytics Enterprise licence. Put this on
a slide; a ministry judge will ask.

---

## Design decisions worth defending

**Why the confidence interval is as large as the percentage.** A lot percentage without its
uncertainty is what causes the disputes this product exists to settle. "64% ± 8%" is an
honest claim; "64%" is not.

**Why two looks, and why not simply averaged.** A defect can sit on the underside of a bulb
where no camera reaches. Shaking re-seats every onion. But the two looks re-observe the *same*
onions, so pooling them would keep the occlusion bias and merely halve it. `merge_looks` takes
the **highest per-look defect rate** — the least-occluded view — while pooling all observations
for size, where nothing hides. See the comment block in [app/grading.py](app/grading.py).

**Why a REFER band.** Below 0.75 confidence the app refuses to grade and hands the bulb to a
human. A system that is confidently wrong in front of a farmer is worse than one that admits
uncertainty.

**Why the hash chain is called tamper-evident, not tamper-proof.** Anyone with write access to
the SQLite file could recompute the whole chain. It detects *casual* edits after a dispute is
raised. Claiming more would not survive one informed question.

**Why `n` is reported as "bulb-observations".** Two looks at 30 onions is 60 observations of
30 objects, not 60 independent samples. Naming the field honestly keeps the CI honest.

---

## Setup from scratch

```powershell
py -3.11 -m venv .venv
.venv\Scripts\activate

pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121
pip install -r requirements.txt

python scripts/check_env.py          # GATE T0 — must print ALL CHECKS PASSED
python scripts/make_mat.py           # GATE T1 — then PRINT and caliper it
python -m pytest tests/ -q           # GATE T2 — 34 tests

python scripts/make_synthetic.py --trays 130 --holdout 24   # bootstrap data
python scripts/dataset_qa.py                                # GATE T3
python scripts/train.py                                     # GATE T4
python scripts/calibrate_size.py
python scripts/measure_occlusion.py                         # GATE T5
python scripts/seed_demo.py --reset
python scripts/build_replay.py                              # GATE T11
```

### Printing the calibration mat

`python scripts/make_mat.py` writes `calibration_mat.pdf`.

Print at **Actual size / 100%**, never "Fit to page", then caliper the printed 100 mm
verification ruler. If it does not read 100.0 ± 0.5 mm the printer scaled the page and every
size measurement will be wrong by the same factor. Laminate two copies — onions are damp.

---

## Public datasets

```powershell
python scripts/fetch_public_data.py --list
```

Two real onion sets exist on Roboflow Universe (261 and 53 images). Neither has a calibration
mat, tray context, or size ground truth, and their class schemes differ from ours. Use them to
pad rare defect classes only. **Never** put them in `data/holdout/`, and never quote a metric
measured on them.

---

## Gates

| Gate | Command | Passes if |
|---|---|---|
| T0 | `python scripts/check_env.py` | ALL CHECKS PASSED, `yolo26s.pt` loads |
| T1 | print the mat | ruler calipers to 100.0 ± 0.5 mm |
| T2 | `python -m pytest tests/ -q` | all green → `grading.py` frozen |
| T3 | `python scripts/dataset_qa.py` | no blocking problems |
| T4 | `python scripts/train.py` | mAP50 ≥ 0.60 sound, ≥ 0.45 on 3 defect classes |
| T5 | `python scripts/measure_occlusion.py` | 2-look under-detection < 1-look |
| T6 | `python -c "from app.db import *; print(verify_chain(1))"` | runs clean |
| T7 | `curl` to `/analyze` | plausible `diameter_mm` (30–90) |
| T8 | phone over the tunnel | full flow, laptop untouched |
| T10 | `/dashboard` | Kurnool-02 unmistakable on load |
| T11 | network unplugged, `?replay=1` | complete demo |
| T12 | `python scripts/bench.py` | p95 < 400 ms on the demo laptop |

Miss a gate → stop and fix it. `git commit && git tag t<N>` after each one.
