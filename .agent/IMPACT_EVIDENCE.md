# IMPACT EVIDENCE — computed, not asserted

Generated 2026-08-25 by `scripts/impact_evidence.py`.
Every figure below is one of:

- **MEASURED-IN-REPO** — computed this run from files in this repo.
- **SYNTHETIC** — measured on procedurally generated imagery; never
  quote it as field accuracy (see EVIDENCE_AUDIT.md §2.2).
- **ASSUMED** — a stated planning assumption with its reasoning;
  replace with field data at the first opportunity.
- **LITERATURE** — an external published figure, cited author/year/
  url/access-date in EVIDENCE_AUDIT.md §6. Context for the problem
  size only; never presented as a SAMA measurement.

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

## 3b. What one percentage point of Grade A is worth (the money frame)

The certificate's ±points convert directly into rupees at the same
price band the app already renders. Rates below are the app's DEMO
defaults shipped in `app/arbitration.py` (A ₹2400 / B ₹1800 / C ₹1200 per quintal) anchored to Lasalgaon's Aug-2026 average
band (§5) but with INVENTED differentials; trolley mass is an
ASSUMED 20–50 q (a 2–5 t tractor-trolley, consistent with §4's
literature lot size). The conversion itself is arithmetic.
— MEASURED-IN-REPO (rates-as-shipped + arithmetic) + ASSUMED (mass)

- Each Grade-A point misgraded down to B moves ₹6/q; down to C, ₹12/q.
- Over a 20–50 q trolley, a 10-point Grade-A dispute is therefore ₹1,200–₹3,000 of exposure if the argument is A-vs-B, and ₹2,400–₹6,000 if A-vs-C — the size of fight this product exists to arbitrate.
- SAMA's own sampling band at the ±6-pt promise brackets that exposure to roughly ±₹720–±₹3,600 per lot: the interval a phone app prints for free carries real money.
- Defect errors price differently: a rotten bulb should be rejected, not re-banded, so each undetected rotten point costs its FULL grade rate — 5 rot points missed on a 20 q Grade-A lot is ≈₹2,400 of overpayment.

## 3c. The smallest Grade-A gap two SAMA certificates can separate

`arbitration.py` calls AGREE when two lots' 95% Wilson intervals
overlap, so the minimum resolvable gap between two certificates is
the SUM of their half-widths. At the sufficiency target (80
observations each): — MEASURED-IN-REPO (arithmetic)

- At the hand-sorted mix (Grade-A ≈ 8.1%): ±6.0 pts each → disputes wider than ≈11.9 pts are resolved statistically.
- At worst-case p=50%: ±10.7 pts each → ≈21.4 pts.
- Read honestly against §3's ASSUMED human band (±5–10 pts): at the
  target sample SAMA separates differences around or above the TOP
  of that band — the gross end of disputes — while staying
  reproducible, timestamped and free. It does not out-resolve a
  trained human on subtle calls, and nothing here claims otherwise.

## 3d. How fast does the worst-view defect estimator inflate with sample size? (RT-001 S-1)

The certified defect rate is `max(per-look rates) / occlusion_factor`
(grading.py D4 — frozen). A maximum over more looks or trays can only
grow, so photographing MORE of a lot mechanically raises the certified
figure. Measured on the 130 hand-sorted tray defect rates
(lot truth 44.4% defective): draw T trays at random, take
the worst, average over 20,000 seeded draws. — MEASURED-IN-REPO inputs +
MONTE-CARLO arithmetic (seed 20260825)

| trays photographed | E[worst-tray rate] | structural bias (pts) | after ÷0.877 correction (pts) | vs ±6-pt sampling promise |
|---|---|---|---|---|
| 1 | 44.4% | +0.1 | +0.1 | 0.0× the whole promise |
| 2 | 59.1% | +14.7 | +16.7 | 2.8× the whole promise |
| 3 | 69.3% | +24.9 | +28.4 | 4.7× the whole promise |
| 5 | 81.8% | +37.4 | +42.7 | 7.1× the whole promise |
| 10 | 95.4% | +51.0 | +58.2 | 9.7× the whole promise |

**ASSUMPTION (lower bound):** each look is treated as seeing its tray's
true rate perfectly and identically. Real views differ — blur, glare and
occlusion make some looks worse — and noise RAISES the expected maximum.
The fitted ÷0.877 factor cancels average occlusion on single-tray pairs;
applied to a cross-tray maximum, it scales the bias up, not down. So the
live inflation is AT LEAST these figures.

- At the fitted two-look design the bias alone is roughly +17 pts on the certified number; by five trays it is
 ~7× SAMA's entire ±6-point sampling promise. The error is not in
  the optics — it is the order statistic, and it lands against the party
  being paid less.
- **Mitigation shipped (loop I858):** every new certificate also carries
  the plain pooled incidence (`defect_pooled_*`, per-tray clustered Wilson)
  printed beside the ceiling, so both readings and their gap are visible
  on the document itself. Replacing the estimator inside frozen grading.py
  remains a data-scientist unfreeze decision.

## 4. Time-per-lot estimate

- Analysis cost per look: p95 139 ms CPU / 97 ms GPU on the dev machine. — SYNTHETIC (real hardware, generated imagery; measures pipeline cost only)
- Two looks ≈ 0.28 s of inference. The lot is therefore dominated by PHYSICAL handling, not compute.
- **ASSUMPTION:** handling ~45–90 s per look (lay tray beside mat, frame, capture, shake, recapture). A 1-tray two-look lot therefore lands at **~2–3 minutes end-to-end** including the result screen; a sample sized to the ±6-pt promise (~3 trays) at **~15–30 minutes**. — ASSUMED
- Manual whole-lot grading is literature-slow, not assumption-slow: a Nashik-market trade survey found **~30 persons are needed to grade 20 tonnes of onions in a day** (≈0.72 person-minutes per kg), and ~50–55 lakh tonnes/year are graded manually in India (Bisen, Bakane & Sakkalkar 2022, J Food Sci Technol 59(6):2370–2380, doi:10.1007/s13197-021-05253-8; accessed 2026-08-25; survey figure, not a time-motion study — defect sorting may be slower still). At that rate one 2–5 t tractor-trolley lot is **24–60 person-hours**: hours even for a ten-person crew, and it produces no signed interval. — LITERATURE

## 5. External impact numbers — LITERATURE (problem-size context)

All verified against primary documents on 2026-08-25; full citations
and verification notes in EVIDENCE_AUDIT.md §6. These are context
figures from published sources — never present them as SAMA data.

- **Onion harvest+post-harvest loss, India: 8.20% overall** (farm
  operations 6.05%, storage 2.16%; regional range 5.49–12.72%;
  Maharashtra-inclusive region worst at 12.72%). Economic value of
  onion loss ≈ ₹2,312 crore/yr (2012-13 production 16.66 Mt × 8.20% × ₹16,920/t). — Jha et al. 2015, ICAR-CIPHET/MoFPI report, Table 6.8 & §6.4.2 — LITERATURE
- Category cross-check: vegetables lose **4.58–12.44%** (ICAR-CIPHET
  2015) / **4.87–11.61%** (NABCONS 2022); all-India monetary loss
  across 45 crops ₹1.53 lakh crore/yr (NABCONS). Onion alone ≈ ₹5,156 crore/yr per the NABCONS study as reported to Lok Sabha. — MoFPI reply, LS US Q.839 (04-Dec-2025) + HT (05-Dec-2024) — LITERATURE
- **Mandi volumes:** official monthly onion arrivals in Maharashtra
  ran ~0.41–1.07 million tonnes/month through 2023-24 (HSAG 2024,
  Tables 8.1.1–8.1.3); national production 242.7 lakh t (~24.3 Mt)
  from 15.4 lakh ha in 2023-24 (Table 1.6). Lasalgaon APMC — called
  the country's largest onion market — auctions ~8,000–30,000 q/day
  seasonally (~15,000 q/day baseline; avg price ₹2,180→₹2,760/q over
  five sessions in Aug-2026, day's range ₹800–3,117/q). — HSAG 2024;
  Business Today 14-Aug-2026 — LITERATURE
- Price sanity for the app's demo rates (A ₹2,400/B ₹1,800/C ₹1,200/q): the Grade-A default sits inside Lasalgaon's observed Aug-2026 average band, but the size-grade differentials themselves
  remain invented demo values — see EVIDENCE_AUDIT §6 flags. — LITERATURE (anchor) + DEMO (differentials)

## 6. What would falsify this page

- A dual-grading study (two inspectors, same lots) replacing §3's assumed band with data.
- Real-phone tray photos re-run through eval_lot/calibrate_size converting §1–§2 inputs from synthetic to field data (gates T8, printed-mat caliper check).
- The ₹ figures in §3b–§3c ride on DEMO rate differentials and an ASSUMED trolley mass; replace either with a mandi-rate feed or a weighed-lot study before quoting them as field losses.
- §3d assumes perfect, view-independent detection to isolate the max()-selection bias; a real two-view tray dataset (or the S-1 unfreeze) would replace it with measured inflation.
- Any §5 literature link rot or a superseding national loss study: re-verify the citations in EVIDENCE_AUDIT.md §6 before quoting.

