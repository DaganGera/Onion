# IMPACT EVIDENCE — computed, not asserted

Generated 2026-08-24 by `scripts/impact_evidence.py`.
Every figure below is one of:

- **MEASURED-IN-REPO** — computed this run from files in this repo.
- **SYNTHETIC** — measured on procedurally generated imagery; never
  quote it as field accuracy (see EVIDENCE_AUDIT.md §2.2).
- **ASSUMED** — a stated planning assumption with its reasoning;
  replace with field data at the first opportunity.

## 1. The hand-sorted ground truth we actually have

- **130 trays, 4182 bulbs** individually hand-sorted and calipered (`data/groundtruth.csv`). — MEASURED-IN-REPO
- Mean tray size 32.2 bulbs; hand-sorted mix is 8.1% Grade A, 44.4% defective (by count). — MEASURED-IN-REPO
- Defect mix: rotten 529, sprouted 488, smut 368, damaged 395, doubles 75 bulbs across all trays. — MEASURED-IN-REPO

## 2. How wide is our own uncertainty? (the honest pitch number)

95% Wilson half-widths on the Grade-A proportion at the hand-sorted Grade-A share, and at worst-case p=50%: — MEASURED-IN-REPO (arithmetic)

| Sample | bulb-observations | ± pts at observed mix | ± pts worst case |
|---|---|---|---|
| 1 tray (~32 bulbs) | 32 | ±10.5 | ±16.4 |
| 2 looks x 1 tray | 64 | ±6.8 | ±11.9 |
| 2 trays x 2 looks | 129 | ±4.7 | ±8.5 |

To keep the Grade-A promise of ±6 points (`TARGET_HALF_WIDTH_PCT`) needs **80 observations at the observed mix** (267 at worst case p=50%) — i.e. roughly 2 two-look trays. The in-app sufficiency card says the same thing to the officer in real time. — MEASURED-IN-REPO (arithmetic)

**Pitch line:** SAMA is the only option on the table that prints its own error bars — and now (loop I2211) the defect percentage carries a Wilson interval too, not just Grade A.

## 3. Our CI vs manual re-grade disagreement

The whole product exists because two humans disagree about a lot. No
inter-inspector agreement study exists **in this repo**, so the human
spread below is an ASSUMED band, not a measurement:

- **ASSUMPTION:** visual lot-grading disagreement between two trained
  inspectors on the same lot is typically ±5–10 percentage points on
  Grade A share. Reasoning: disputes are common enough that DoCA runs
  a problem statement on them; per-bulb class calls near boundaries
  are subjective (e.g. damaged_skin vs sound), and boundary bulbs are
  exactly where two humans split. Replace this band with a real
  dual-grading study before quoting it as data.

- Our sampling error alone at a 2-tray/4-look sample is ±4.7 pts (observed mix). — MEASURED-IN-REPO
- Consequence, stated both ways so nobody can accuse us of spin:
  - At small samples our CI is WIDER than assumed human disagreement — which is why the app refuses to bless small samples and shows the sufficiency card (80-observation target).
  - Once the sample reaches that target, SAMA's interval (±6 pts by construction) is comparable to or tighter than ASSUMED human-to-human spread — and unlike a human re-grade, it is reproducible, timestamped, hash-chained and free.

## 4. Time-per-lot estimate

- Analysis cost per look: p95 139 ms CPU / 97 ms GPU on the dev machine. — SYNTHETIC (real hardware, generated imagery; measures pipeline cost only)
- Two looks ≈ 0.28 s of inference. The lot is therefore dominated by PHYSICAL handling, not compute.
- **ASSUMPTION:** handling ~45–90 s per look (lay tray beside mat, frame, capture, shake, recapture). A 1-tray two-look lot therefore lands at **~2–3 minutes end-to-end** including the result screen; a sample sized to the ±6-pt promise (~3 trays) at **~15–30 minutes**. Manual whole-lot grading of thousands of bulbs takes hours and cannot produce a signed interval. — ASSUMED

## 5. What would falsify this page

- A dual-grading study (two inspectors, same lots) replacing §3's assumed band with data.
- Real-phone tray photos re-run through eval_lot/calibrate_size converting §1–§2 inputs from synthetic to field data (gates T8, printed-mat caliper check).

