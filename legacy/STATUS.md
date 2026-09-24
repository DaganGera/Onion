# SAMA — build status

Built and verified on **2026-08-24** · RTX 5060 Ti 15.9 GB · Python 3.11.4 · torch 2.13.0+cu132 · ultralytics 8.4.127 · cv2 5.0.0

---

## Gates passing

| Gate | Result | Evidence |
|---|---|---|
| **T0** environment | PASS | CUDA True, `ArucoDetector` present, `yolo26s.pt` loads (10.0M params) |
| **T1** calibration mat | PASS *(software half)* | mat self-verifies at 0.093% scale error — **you still have to print and caliper it** |
| **T2** grading math | PASS | 34 pytest tests |
| **T3** dataset QA | PASS | 284 images, 9,683 boxes, zero leakage, all mats detected |
| **T4** training | PASS | holdout mAP50 0.989 (see the warning below) |
| **T5** occlusion | PASS | 1-look misses 20.5%, 2-look misses 10.8% |
| **T6** hash chain | PASS | chain verifies; editing a historical row is detected |
| **T7** `/analyze` | PASS | 34 bulbs, both markers, 35–91 mm diameters |
| **T10** dashboard | PASS | Kurnool-02 flagged at −8.6 drift |
| **T11** offline replay | PASS *(software half)* | 6 cached responses — **you still have to pull the cable and try it** |
| **T12** latency | PASS | GPU 20 ms p95, CPU 108 ms p95, budget 400 ms |
| — | PASS | 27-check end-to-end smoke test: analyze → finalize → certificate → dashboard |

Still yours, and not doable in software: **T8** (full flow on a real phone over the tunnel) and the printed-mat half of T1.

---

## ⚠️ Read this before quoting any number

**Every figure above is measured on SYNTHETIC trays.** The repo ships a procedural generator
so the pipeline runs before real photos exist. Generated defects are drawn with clean,
separable colours; a 0.989 mAP means the model solved a drawing, not onions.

**Do not put synthetic numbers in the deck.** Re-run every script after your first real shoot
and quote whatever it prints then. Expect real mAP far lower.

What the synthetic set *does* legitimately prove:

- **The millimetre chain is correct.** The generator plants a 1.06× magnification (bulbs sit
  above the mat plane); `calibrate_size.py` independently recovers 0.9267 against a true
  0.9434 — within 1.8%, and MAE drops 4.87 mm → 0.37 mm. That arithmetic will hold on real photos.
- **Occlusion is physical, not assumed.** Defects are placed as spherical caps on a 3D bulb;
  ones facing away are invisible to any camera angle. The 20.5% / 10.8% gap comes from geometry.
- **Every script, gate, endpoint and screen runs.**

---

## Two bugs found and fixed during the build

**1. Inconsistent look-pooling.** `measure_occlusion.py` fitted the 2-look correction using
`max()` across looks, but `merge_looks` *concatenated* observations. Concatenating two looks
of the same tray averages them — it keeps the occlusion bias and merely halves it. The
correction was being applied to a quantity it was never measured against.

Fixed: `merge_looks` now takes the **highest per-look defect rate** (the least-occluded view)
while still pooling every observation for size, where nothing hides. Result — Defect % 2-look
MAE went **7.34 → 2.95**, and 2-look now beats 1-look (4.50) as the Two-Look claim requires.

**2. The generator swapped the onions on shake.** Look 2 was rendered from a fresh random
roster, so the two looks described different lots and every 2-look metric was measured against
the wrong ground truth. Fixed: one roster per tray, reused across both looks; the seed now
changes only arrangement, stacking and which face points up.

Both are recorded because they are the kind of error that silently produces a *better-looking*
number. `grading.py` was unfrozen for fix 1, tests extended to 34, and re-frozen.

---

## Fitted constants (`app/constants.json`)

```json
{
  "height_correction":          0.9267,
  "occlusion_correction_1look": 0.7951,
  "occlusion_correction_2look": 0.8919,
  "accept_threshold":           0.75,
  "e2e_mode":                   false
}
```

**Re-fit all three after your first real shoot.** They encode the physics of *your* mat, *your*
phones and *your* trays, and the synthetic values will be wrong for real onions.

---

## YOLO26 findings

`yolo26s.pt` @ 1024, batch 12 — used **3.1 GB of 15.9 GB**. Batch 24 would fit comfortably if
you want faster epochs on real data.

Both inference modes were measured rather than assumed:

| | mAP50 (holdout) | refer rate | CPU p95 |
|---|---|---|---|
| `end2end=False` (NMS) | 0.989 | 1.4% | 108 ms |
| `end2end=True` (NMS-free) | 0.982 | 14.1% | 105 ms |

NMS-free came out only **3% faster on CPU**, not the 43% Ultralytics advertises — at 1200×900
the backbone dominates, not NMS. It also pushes the refer rate from 1.4% to 14.1%, which
would send ten times as many bulbs to a human inspector.

**Ship `end2end=False`.** It is already the default in `constants.json`.

`doubles` is the weakest class (0.961 NMS / 0.920 E2E) and the rarest at 1.4% of boxes —
`dataset_qa.py` flags it as under-represented. Shoot extra doubles trays when you collect real
onions.

---

## Immediate next steps

1. **Onions.** Start the rot/sprout/mould bags, and buy culls at Koyambedu — see `PLAN.md` §0.2.
2. **Print the mat** at Actual size / 100%, caliper the 100 mm ruler. This is Gate T1's real half.
3. **`git init`** and tag per gate. I did not create commits — that is your call.
4. **Shoot real trays**, drop the Roboflow export into `data/dataset/`, then:
   ```powershell
   python scripts/dataset_qa.py
   python scripts/train.py --model yolo26s.pt --imgsz 1024 --batch 12 --epochs 120
   python scripts/calibrate_size.py
   python scripts/measure_occlusion.py
   python scripts/eval_lot.py
   python scripts/build_replay.py
   ```
5. **Test on four physical phones over the tunnel** — Gate T8, the #1 demo-killer.

---

## File map

```
app/grading.py        scale, sizing, grades, Wilson CI, look merging   [FROZEN, 34 tests]
app/main.py           FastAPI: UI + inference, one process
app/db.py             SQLite + per-centre SHA-256 hash chain
app/constants.json    fitted factors, read at startup
app/static/           index.html, report.html, dashboard.html
app/cache/            6 cached replay responses

scripts/check_env.py       Gate T0
scripts/make_mat.py        A4 calibration mat, self-verifying
scripts/verify_mat.py      check a photo of a PRINTED mat for print scaling and tilt
scripts/make_synthetic.py  procedural trays with honest occlusion  [replace with real data]
scripts/fetch_public_data.py  Roboflow onion sets + class remapping
scripts/dataset_qa.py      leakage, balance, box sanity, missing mats
scripts/bootstrap_label.py pre-label so humans only correct classes
scripts/train.py           train + holdout eval, both inference modes
scripts/eval_lot.py        lot-percentage error, the metric that matters
scripts/calibrate_size.py  fits height_correction
scripts/measure_occlusion.py  fits both occlusion factors, Gate T5
scripts/seed_demo.py       6 centres, 30 days, Kurnool-02 degrading
scripts/build_replay.py    offline demo cache
scripts/bench.py           latency on the demo laptop
scripts/smoke_test.py      27-check end-to-end integration test
```

---

## Round 2 — marker occlusion, and what it exposed

### The question: what if onions hide the calibration reference?

**Before:** total collapse, not degradation. `detect_scale` needed one of two
ArUco markers. Lose both and `mm_per_px` became `None`, every diameter became
`None`, every grade became `UNKNOWN`, and Grade A% — the one number the product
exists to report — read 0. Two unlucky onions could do it.

**And the test set was rigged.** The generator had a `_hits_marker()` keep-out
that forbade onions from ever touching a marker, so every calibration figure in
the first report came from a distribution where this failure could not occur.
That keep-out is gone.

### What changed

| | Before | After |
|---|---|---|
| Markers | 2 × 50 mm, opposite corners | **8 × 40 mm** ringing the perimeter ([app/mat_layout.py](sama-onion/app/mat_layout.py)) |
| Sizing | one global mm/px | **homography** — box corners mapped into the mat plane, perspective-correct |
| Mat placement | under the onions | **beside** them |
| 0 markers | total failure | ladder: carried → mat_edge → withhold |
| Reporting | `calibrated` true/false | rung, confidence, and `grades_certified` on every response and on the certificate |

### The A4 finding

Piling a sample onto the mat cannot work. A4 is 297×210 mm; the area inside the
marker ring is 181×94 mm ≈ 17,000 mm². A 60 mm bulb is ~2,800 mm². That is room
for about **five onions**, so any tray large enough to sample meaningfully buries
the markers by construction.

The mat does not need to be underneath. The homography maps the whole **bench
plane**, so a bulb resting anywhere on that plane is sized correctly as long as
the mat is visible somewhere in frame. Put the mat beside the tray.

Measured effect on generated trays: markers visible went from 1.0/8 (mat under
the pile) to **2.8/8**, and calibration success from 93% to **98.6%**.

### The ladder, measured

`python scripts/occlusion_stress.py` — 20 trials per level, mats at a random angle:

| buried | visible | calibrated | rung | 100 mm error |
|---|---|---|---|---|
| 0–4 | 8–4 | 100% | homography | 0.02–0.04 mm |
| 5 | 3 | 100% | homography | 0.19 mm |
| 6 | 2 | 100% | homography_weak | 0.22 mm |
| 7 | 1 | 100% | single_marker | 4.32 mm |
| 8 | 0 | 100% | mat_edge | 2.96 mm |

The original 2-marker design, same test: fine at 0–1 buried, **total failure at 2**.

### mat_edge is a trap, and the data caught it

On the clean stress bench `mat_edge` looked excellent (0.1–3 mm). Measured against
caliper ground truth on **cluttered** trays it came out at **16.9 mm MAE**, versus
0.5–0.7 mm for every marker-based rung. A 17 mm error on a 60 mm bulb moves it two
grade bands — confidently wrong, which on a signed certificate is worse than
useless.

Per-rung accuracy against caliper truth:

| rung | n | MAE |
|---|---|---|
| homography | 180 | 0.72 mm |
| homography_weak | 54 | 0.57 mm |
| single_marker | 22 | 0.47 mm |
| **mat_edge** | 2 | **16.96 mm** |

So `mat_edge` was demoted **below** `carried` (a homography from thirty seconds
ago beats a guessed rectangle) and given confidence 0.25, under a
`GRADING_FLOOR` of 0.35. Anything at or below the floor is flagged **provisional**
in the app and on the certificate, and must not be presented as a certified
ICAR-DOGR grade.

Two other silent-failure guards came out of the same work: a featureless frame
(blank wall, lens cap) used to threshold into one full-frame blob and yield
confident meaningless millimetres — now rejected on a contrast check and a
90%-of-frame area cap.

### Model work

Synthetic defects were flat colour fills, which is why mAP sat at 0.99 and meant
nothing. They now get random severity, per-pixel texture, feathered edges,
specular highlights, and **contact shadows as hard negatives** — the dark patch
where two bulbs touch looks a great deal like early rot.

Honest result: holdout mAP moved 0.989 → **0.978**. Barely. `doubles`, the one
class where the colour cue was genuinely removed, fell 0.961 → 0.894. **Synthetic
data has a realism ceiling and more texture will not break it.** The number stays
inflated until real photos replace it. That remains the single highest-value
task on the list.

### Current state

- **43 unit tests**, 29 smoke checks, lint clean
- Gates T0, T2, T3, T4, T5, T6, T7, T10, T11, T12 pass
- Fitted: `height_correction` 0.9378 (true 0.9434 — 0.6% off, better than the
  1.8% the old global-scale sizing managed)
- One look misses 21% of defects, two looks miss 12% — Gate T5 holds
- Lot Grade-A error 1.2 points (n=102 trays)

### ⚠️ Reprint the mat

The 2-marker sheet is obsolete. `python scripts/make_mat.py`, print at Actual
size / 100%, and caliper a marker square — it must read **40.0 ± 0.3 mm**.
