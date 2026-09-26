# EVIDENCE AUDIT — R-001

Auditor: Research/Evidence Engineer
Date: 2026-08-24
Scope: README.md, STATUS.md, app/static/*.html (index, report, dashboard,
arbitrate, verify, tamper-demo). No production code was read-modified or touched.
Method: full read of each file; every quantitative or comparative claim extracted;
external claims checked against public sources on 2026-08-24 via web.

## Classification definitions

| Label | Meaning |
|---|---|
| **OK** | Verifiable in-repo (tests/scripts/code) or against an authoritative external source checked during this audit. |
| **SYNTHETIC-ONLY** | Number was genuinely measured, but on procedurally generated trays (`make_synthetic.py`). Not predictive of real-world performance. Must never be quoted to a judge without that label. |
| **UNSUPPORTED** | No evidence found in-repo or externally — or contradicted by better evidence located during this audit. Needs a source or a rewrite of the claim. |

---

## 1. External verifications performed (2026-08-24)

### 1.1 ICAR-DOGR size-grade bands — PROBLEM FOUND

SAMA implements and prints (CLAUDE.md; report.html method note "graded to ICAR-DOGR
bands"): **A = >80 mm, B = 50–80 mm, C = 30–50 mm** (UNDERSIZED <30 mm).

What public sources actually say:

| Source | Bands stated | Match to SAMA? |
|---|---|---|
| ICAR-DOGR-affiliated extension bulletin *"Onion Graders – Bulletins"* (ResearchGate pub. 303802648) | A >60 mm; B 50–60 mm; C 35–50 mm | **NO** |
| *"Onion Grading in India"* (ResearchGate pub. 304791556; NRC Onion & Garlic lineage) | Grade table with A >60 mm as top grade | **NO** |
| Bisen, Bakane & Sakkalkar (2022), *J Food Sci Technol* 59(6):2370–2380, doi:10.1007/s13197-021-05253-8, PMC9114269 (rotary onion grader, Nashik/Akola, ICAR-AICRP PHET) | Commercial classes <40 / 40–60 / >60 mm | **NO** |
| Export trade specs (APEDA Agmark procedure refs; exporter trade pages) | 45–55 / 55–65 / 65–80 mm; one trade page calls 50–80 mm "Grade A premium export" | Partial overlap only |
| Agmark: Fruits & Vegetables Grading and Marking Rules, 2004, Schedule XIX (governs onion export grading; APEDA/DMI) | Full text not retrievable this session (binary .doc/.pdf) | UNVERIFIED |

**Conclusion:** No public source located that supports A >80 / B 50–80 / C 30–50 as an
"ICAR-DOGR standard". Published DOGR-lineage material instead puts the top boundary at
~60 mm. The implemented bands appear **UNSUPPORTED**. Per audit rules this is documented,
not silently corrected — but before demo day someone must either (a) produce a primary
ICAR-DOGR document stating these bands, or (b) relabel them as project-defined bands
aligned to a citable source. Highest-severity finding in this audit because the signed
certificate repeats it.

### 1.2 SIH problem-statement number — DISCREPANCY

README.md line 3 claims "**PS 26046**". A community archive of the official SIH 2026 PS
database (sih2026.vuce.in, snapshot 2026-08-21, linking to sih.gov.in/sih2026PS) shows:

- The DoCA onion-grading statement exists and matches SAMA's product almost word for word:
  **SIH26031** — "Quality assessment and grading of onions are often subjective and vary
  across procurement centers, resulting in disputes and inconsistencies." Expected solution:
  image processing; identifies damaged/rotten/sprouted/undersized; estimates Grade A and URS
  percentages; instant digital report; reduces bias.
- Under Ministry of Consumer Affairs, Food & Public Distribution the archive lists exactly
  10 PSs: SIH26029–SIH26036, SIH26107, SIH26108. **No 26046.**

Caveat: the archive is unofficial. Action: confirm the team's actual PS number from the
sih.gov.in registration before anything is printed or presented. Documented here; not
silently changed anywhere.

### 1.3 Ultralytics YOLO26 comparative claim — SUPPORTED

STATUS.md says NMS-free was "not the 43% Ultralytics advertises". Verified at
docs.ultralytics.com/models/yolo26/: the paper reports "**up to 43% faster CPU ONNX
inference for YOLO26n compared with YOLO11n**" (Intel Xeon @ 2.00 GHz). Precision note:
the vendor figure is yolo26*n*, ONNX, Xeon — STATUS's own 3%-on-CPU measurement is for
yolo26*s*, PyTorch, ~1200×900 inputs, so the comparison is fair and honestly framed.
STAL ("Small-Target-Aware Label Assignment"), Progressive Loss, end-to-end default,
`max_det=300`, AGPL-3.0/Enterprise dual licence: all confirmed by the same docs page.
Minor wording note: README says STAL "*guarantees*" small targets contribute to the loss;
docs say it "*improves positive label coverage for small objects*". Slightly strong.

### 1.4 Roboflow dataset counts — UNVERIFIED

README: "Two real onion sets exist on Roboflow Universe (261 and 53 images)". Onion
datasets demonstrably exist on Roboflow Universe (e.g., a 3.08k-image multi-project
account), but the specific counts 261/53 could not be confirmed this session.
Low severity (internal tooling note), but verify before quoting.

---

## 2. Claim-by-claim register

### 2.1 README.md

| # | Line(s) | Claim | Class | Note |
|---|---|---|---|---|
| R1 | 3 | "SIH 2026 · PS 26046 · Ministry of Consumer Affairs" | **UNSUPPORTED** (discrepant) | Archive says onion PS = SIH26031; no 26046 found. Confirm on sih.gov.in. |
| R2 | 43 | grading.py "Pure functions, 34 tests. Frozen." | OK | In-repo (pytest). STATUS later reports 43 tests — keep numbers in sync when quoting. |
| R3 | 104–105 | smut speck "~12 px at 640 and ~22 px at 1024" | OK (illustrative) | Geometric illustration, not a measurement. Fine if presented as such. |
| R4 | 107 | "~64% sound, ~1.4% doubles" class mix | **SYNTHETIC-ONLY** | Distribution of the procedural generator; no field survey cited. |
| R5 | 112 | "trays hold 35–60 bulbs" | OK | Design parameter. |
| R6 | 84–86 | fitter recovers planted magnification "within 0.7%" | **SYNTHETIC-ONLY** | Measured, synthetic bench. README already frames honestly. |
| R7 | 104–107 | STAL/ProgLoss/NMS-free/max_det 300 | OK | Verified vs Ultralytics docs; soften "guarantees". |
| R8 | 114–116 | AGPL-3.0 → network service needs source publication or Enterprise licence | OK | Confirmed dual licensing. Presentation as legal advice should be avoided; phrase as "Ultralytics' published licence terms state…". |
| R9 | 122–125 | "'64% ± 8%' is honest; '64%' is not" | OK (rhetoric) | Motivational framing, no empirical claim. |
| R10 | 183–186 | Roboflow sets "261 and 53 images", no mat/no size GT/different classes | **UNSUPPORTED** (counts) | Existence plausible; exact counts unverified. |
| R11 | 198 | Gate T4 thresholds mAP ≥0.60 / ≥0.45 | OK | Self-imposed engineering targets. |
| R12 | 205 | p95 < 400 ms latency budget | OK | Self-imposed budget. |

### 2.2 STATUS.md

Every gate number below carries the file's own warning that all figures are measured on
synthetic trays. They are correctly labelled *in this file* — the risk is quote-mining
into slides.

| # | Line(s) | Claim | Class | Note |
|---|---|---|---|---|
| S1 | 3 | Build env (RTX 5060 Ti, torch 2.13.0+cu132, ultralytics 8.4.127, cv2 5.0.0) | OK | Repo-verifiable via check_env. |
| S2 | 11 | yolo26s.pt loads, 10.0M params | OK | Ultralytics lists 9.5M *fused*; unfused checkpoint higher — consistent. |
| S3 | 12 | mat self-verifies 0.093% scale error | **SYNTHETIC-ONLY** | Software half; printed-mat half still open. |
| S4 | 14 | T3: 284 images, 9,683 boxes, zero leakage | **SYNTHETIC-ONLY** | Dataset QA ran over generated set. |
| S5 | 15 | holdout mAP50 0.989 (later 0.978 after texture hardening) | **SYNTHETIC-ONLY** | Both figures explicitly flagged in-file. Never quote bare. |
| S6 | 16 | occlusion: 1-look misses 20.5%, 2-look 10.8% | **SYNTHETIC-ONLY** | Physical model of geometry, still generated data. |
| S7 | 18 | T7: 34 bulbs, 35–91 mm diameters | **SYNTHETIC-ONLY** | Demo run output. |
| S8 | 19 | Kurnool-02 flagged at −8.6 drift | **SYNTHETIC-ONLY** | Centre itself is seeded fiction (`seed_demo.py`). See §3.4. |
| S9 | 21 | GPU 20 ms p95, CPU 108 ms p95 | **SYNTHETIC-ONLY** | Real hardware, synthetic imagery; representative of pipeline cost, not field accuracy. |
| S10 | 39–41 | calibrate_size recovers 0.9267 vs true 0.9434 (1.8%), MAE 4.87→0.37 mm | **SYNTHETIC-ONLY** | |
| S11 | 55–57 | merge fix: Defect % MAE 7.34→2.95; 2-look 4.50→beats 1-look | **SYNTHETIC-ONLY** | |
| S12 | 71–79 | constants.json fitted values (0.9267 / 0.7951 / 0.8919) | **SYNTHETIC-ONLY** | File itself says re-fit after first real shoot. |
| S13 | 93–101 | e2e comparison table + "only 3% faster on CPU, not the 43% Ultralytics advertises" | Own numbers: **SYNTHETIC-ONLY**; the 43% attribution: OK | Vendor figure verified, scoped to yolo26n/ONNX/Xeon. |
| S14 | 104–106 | doubles weakest class (0.961/0.894), rarest at 1.4% | **SYNTHETIC-ONLY** | |
| S15 | 199–207 | occlusion stress ladder table (0.02–0.04 mm … 2.96 mm) | **SYNTHETIC-ONLY** | Generated stress bench. |
| S16 | 217–224 | per-rung caliper MAE incl. mat_edge 16.96 mm (n=2) | **SYNTHETIC-ONLY** | Phrasing "caliper ground truth on cluttered trays" reads physical; if any part used physical calipers, say so explicitly — otherwise reword. n=2 is anecdotal even internally. |
| S17 | 252 | 43 unit tests, 29 smoke checks | OK | In-repo. |
| S18 | 255–257 | height_correction 0.9378 (0.6% off); 21%/12%; lot error 1.2 pts (n=102) | **SYNTHETIC-ONLY** | |
| S19 | 183–193 | A4 geometry: ring 181×94 ≈ 17,000 mm²; 60 mm bulb ≈ 2,800 mm²; ~five onions; markers 1.0/8 → 2.8/8; calibration success 93%→98.6% | Arithmetic parts OK; measured parts **SYNTHETIC-ONLY** | Geometry derivation is checkable arithmetic. |

### 2.3 app/static/index.html

| # | Location | Claim | Class | Note |
|---|---|---|---|---|
| I1 | results card | "± x%" beside Grade A, "95% confidence" | OK | Wilson CI named and tested in grading.py. |
| I2 | priceCard | "Fair price band · per quintal" ₹ band | **UNSUPPORTED** | Rates are hardcoded demo values; sub-label does say "demo rates" (good), but the headline "Fair price band" implies market grounding it doesn't have. Add "(illustrative)" to the title or source real rates. |
| I3 | suffCard | "Sample sufficiency check" verdict | OK (method) / basis undocumented | Sufficiency threshold formula needs a one-line derivation somewhere citable. |
| I4 | scaleLine | quality labels good ≥0.85 / reduced ≥0.6 / LOW | **UNSUPPORTED** (thresholds) | Cutoffs are self-chosen; fine as UI convention, but don't present as metrologically derived. |
| I5 | shakeText | "Roll the onions so hidden faces come up…" | OK | Consistent with two-look design. Does NOT address internal rot — see §3.1. |
| I6 | referText | "A human inspector decides these, not the model." | OK | Honest-limitation copy, enforced. |
| I7 | Hindi strings | translation fidelity | Unaudited | Native-speaker check recommended before demo; not an evidence item per se. |

### 2.4 app/static/report.html (the signed certificate)

| # | Location | Claim | Class | Note |
|---|---|---|---|---|
| C1 | header | "Ministry of Consumer Affairs, Food & Public Distribution / Department of Consumer Affairs" letterhead | **UNSUPPORTED** (as branding) | No authorization exists. On a signed artifact this implies governmental provenance. Must carry visible "PROTOTYPE — not an official DoCA instrument" marking until/unless authorized. See §3.3. |
| C2 | method note | "graded to ICAR-DOGR bands" | **UNSUPPORTED** | Inherits §1.1. Headline finding. |
| C3 | method note | "eight-marker ArUco mat (40.0 mm squares)" | OK | Design fact from mat_layout/make_mat. |
| C4 | method note | "95% Wilson confidence interval, not a census" | OK | Correctly named and scoped. |
| C5 | method note | referred-bulbs disclosure | OK | Honest limitation, enforced. |
| C6 | chain note | "Tamper-evident, not tamper-proof" | OK | Matches db.py threat model; exemplary wording. |
| C7 | signatures | "✓ Confirmed on device" | OK w/ caveat | It records taps + typed names, not cryptographic identity. Don't let anyone call this a digital signature. |
| C8 | badge text | GOOD/REDUCED/LOW quality mapping | **UNSUPPORTED** (thresholds) | Same as I4. |
| C9 | QR block | "Anyone can verify this certificate" | OK w/ caveat | True only while the server/tunnel is reachable; offline certificates can't be verified. State the dependency. |
| C10 | defect rate | "corrected for occlusion" figure | **SYNTHETIC-ONLY** | Correction factors fitted on generated trays (constants.json). |

### 2.5 app/static/dashboard.html

| # | Location | Claim | Class | Note |
|---|---|---|---|---|
| D1 | whole page | centres, baselines, drift, sparklines | **SYNTHETIC-ONLY** | Data comes from `seed_demo.py`; Kurnool-02 etc. are fictional. Concept is real code; displayed network is invented. Disclose on-screen ("demo data") or verbally. |
| D2 | methodology note | reference-score definition (sealed tray re-grade) | OK (method description) | Sound practice; no external precedent claimed. |
| D3 | sparkline colour | drift < −5 amber | **UNSUPPORTED** (threshold) | Arbitrary cutoff, same family as I4. |

### 2.6 app/static/arbitrate.html

| # | Location | Claim | Class | Note |
|---|---|---|---|---|
| A1 | tagline | "settled by statistics, not shouting" | OK (method) | Two-proportion test + CI-overlap logic is defensible; p-value shown raw. Good. |
| A2 | moneyCard | price bands from certificate grade mix | **UNSUPPORTED** | Same hardcoded rates as I2. |
| A3 | stats line | combined best estimate | OK | Standard inverse-variance style pooling; fine as demo. |

### 2.7 app/static/verify.html

| # | Location | Claim | Class | Note |
|---|---|---|---|---|
| V1 | verdict banner | "✔ CERTIFICATE VERIFIED" | Wording risk | It verifies chain integrity only — NOT that the measurement was accurate. A verifier can read "verified" as "the grading was validated". Consider "RECORD INTACT" vs "TAMPERED RECORD DETECTED". See §3.5. |
| V2 | chain explainer | SHA-256 chaining explanation + honest limits | OK | Accurate and candid. |

### 2.8 app/static/tamper-demo.html

| # | Location | Claim | Class | Note |
|---|---|---|---|---|
| T1 | script | attack edits DB "+25 points", caught by chain | OK | Behavior is implemented server-side. |
| T2 | limits para | explicit tamper-evident-not-proof statement | OK | Enforced honest limitation. Good demo hygiene. |

---

## 3. Cross-cutting limitation gaps (must be closed everywhere)

### 3.1 Internal rot is invisible to RGB — NOT stated anywhere user-facing (HIGH)
The 6-class list includes `rotten`, graded from RGB photos. Bulbs whose rot is internal
with a sound exterior cannot be detected by this system at all. Neither index.html,
report.html, nor verify.html states this. A signed certificate that reports "Rotten 1.2%"
without the RGB-blindness disclaimer invites exactly the dispute the product exists to
settle. Required: add to the certificate method note and the REFER copy:
*"Surface-visible defects only; internal rot with sound exterior skin cannot be detected
from photographs."*
This is a standing honest-limitation rule; enforce in every artifact.

### 3.2 Variety/generalization scope absent (MEDIUM)
Nothing states that accuracy claims do not generalize to varieties, growing conditions or
lighting regimes not represented in training data. One sentence on the certificate method
note closes it.

### 3.3 Government letterhead on a prototype artifact (HIGH)
report.html presents the certificate under a ministry/department masthead with no
authorization behind it. Combined with C7 (tap-to-sign) this overstates provenance.
Required: visible prototype watermark/disclaimer until a real authority is engaged.

### 3.4 Fictional procurement centres look real (MEDIUM)
Dashboard and seeded lots show named centres/districts (Kurnool-02) with plausible drift
histories. Any judge will assume they are real unless told otherwise. Add a persistent
"DEMO DATA" chip on dashboard and seeded reports.

### 3.5 "VERIFIED" ambiguity (MEDIUM)
Verify page conflates record integrity with measurement validity (V1). Reword.

### 3.6 Price band sourcing (MEDIUM)
All money numbers derive from hardcoded demo rates labelled only in small print.
Either cite a live source (Agmarknet/e-NAM modal prices) or keep the "demo rates"
label at equal prominence to the number.

### Competitive landscape (clean)
No file visited claims that nothing else detects onions or disparages competitors.
Differentiation is correctly positioned around procurement arbitration, sampling
statistics, and contestable certification. Nothing to fix; keep it that way.

---

## 4. The five most hostile SIH judge questions (and what evidence answers them)

**Q1 — "Your own certificate says 'graded to ICAR-DOGR bands'. Show me the ICAR-DOGR
document that defines Grade A as above 80 millimetres."**
Status today: unanswerable. Published DOGR-lineage material puts top grade at >60 mm
(§1.1).
Evidence that answers it: a primary source (DOGR bulletin/extension folder or Agmark
Schedule XIX text) matching the implemented bands — or the bands renamed to
"SAMA project bands, chosen to align with [cited source]" plus a slide acknowledging the
>60 mm convention in DOGR literature. Either path survives; silence does not.

**Q2 — "Every accuracy number you have shown was measured on cartoon onions. What will
you show us that isn't?"**
Evidence that answers it: a minimum real-data evidence pack — e.g., ≥100 physically shot
tray photos across ≥2 days and ≥2 phones, hand-sorted counts + caliper diameters as
ground truth (`data/groundtruth.csv` protocol), then re-run `eval_lot.py`,
`calibrate_size.py`, `measure_occlusion.py` and publish the synthetic-vs-real delta side
by side. Even a mediocre real number beats an excellent synthetic one for credibility,
provided both are shown.

**Q3 — "A rotten onion that looks fine on the outside sails through your camera. Your
certificate still prints a 'Rotten %'. How is that not fraudulent precision?"**
Evidence that answers it: the §3.1 disclaimer on the certificate and UI; the REFER-band
statistics (what fraction of bulbs get human review); and ideally a validation protocol
where a destructive cut-test subsample of each lot is compared against the photographic
defect estimate, quantifying the internal-rot blind spot rather than denying it.

**Q4 — "Why does a student prototype carry a Government of India letterhead? Is this
certificate legally meaningful, and who is liable when two parties act on it and lose
money?"**
Evidence that answers it: visible prototype/non-authoritative marking (§3.3); a one-page
position note distinguishing (a) decision support between two consenting parties at a
procurement centre from (b) statutory certification under Agmark/Legal Metrology; and the
tamper-evidence threat model already written into db.py docs, explicitly disclaiming
regulatory certification.

**Q5 — "You photograph one tray twice and call it statistics. Two looks at the same bulbs
are correlated observations — is your ±CI honest, and what sample actually suffices for a
lot-level decision?"**
Evidence that answers it: the sufficiency derivation behind `/api/sufficiency`
(n_required formula, stated design CI width and confidence); an effective-sample-size
argument or cluster-aware (tray-level bootstrap) interval demonstrating Wilson coverage
under the two-look dependence structure; and the merge_looks max-defect-rate rationale
already in grading.py comments, promoted from code comment to a citable methods paragraph.

Runners-up (prepare one-liners): price-band provenance (§3.6); latency on a ₹8k phone vs
RTX 5060 Ti; why `doubles` at 1.4% prevalence can be learned at all; lighting robustness
across mandi daylight variance.

---

## 5. Priority fix list (documentation/UI only — no code changes made)

1. Resolve the ICAR-DOGR band discrepancy (§1.1) — blocks every certificate shown publicly. [HIGH]
2. Confirm true PS number against sih.gov.in registration (§1.2). [HIGH]
3. Add internal-rot blindness disclaimer to certificate + capture UI (§3.1). [HIGH]
4. Prototype marking on report.html masthead (§3.3). [HIGH]
5. DEMO DATA chip on dashboard/seeded artifacts (§3.4); reword verify verdict (§3.5);
   promote "demo rates" prominence (§3.6). [MEDIUM]
6. Soften README "STAL guarantees…" to docs' wording; sync test-count references
   (34 vs 43) wherever quoted. [LOW]

— End of audit. All external sources accessed 2026-08-24. No production code was modified.

---

# ADDENDUM — Evidence hardening pass R-2219 (2026-08-25)

Auditor: Research/Evidence Engineer. Scope of this pass ONLY: four claim
families — NABCONS rates/losses, mandi volumes, manual grading time-per-lot,
onion post-harvest loss %. Method: primary documents downloaded and text-extracted
(CIPHET report PDF, Horticultural Statistics at a Glance PDF, Lok Sabha answer PDF);
news pages fetched in full where noted; search-index snippets treated as leads,
not evidence. All sources accessed **2026-08-25** unless stated otherwise.
`scripts/impact_evidence.py` was extended so `IMPACT_EVIDENCE.md` carries these
citations on regeneration (script is the generator; editing the .md alone would be
overwritten). No production code touched.

## 6.1 NABCONS rates — PARTIALLY VERIFIED, with an honest scope correction

**What could NOT be verified:** no public NABCONS rate schedule for mandi grading
labour (hamali/majdoori charges) was found in any session. Such charges are set
per-APMC locally; treat any spoken "NABCONS grading rate" as **UNSUPPORTED** until
someone produces the document.

**What IS verifiable — NABCONS post-harvest LOSS study (2020–22):**

| Figure | Value | Source |
|---|---|---|
| Category loss %, vegetables | **4.87–11.61%** | Lok Sabha US Q.839 table [S3] |
| Monetary loss, vegetables | ₹27,459.08 crore/yr | same |
| Total monetary loss, all 45 commodities | ₹1,52,790.42 crore (~₹1.53 lakh crore) | same |
| Onion monetary loss | **₹5,156 crore** | MoFPI reply reported by HT, 05-Dec-2024 [S4] |
| Perishables transport-only loss | 5–10% | same |

The pairing of ICAR-CIPHET (2015) percentages with NABCONS (2022) percentages and
rupees in one official Government table is the citation to use for both bodies.
Corroboration attempt: NABCONS corporate pitchbook PDF exists (nabcons.com) with an
onion value-chain section per search snippet; download timed out this session —
do not cite its contents until retrieved.

## 6.2 Mandi volumes — SUPPORTED

| Claim | Verified figure | Source |
|---|---|---|
| National onion production 2023-24 | **242.7 lakh t (~24.3 Mt)** from 15.4 lakh ha, productivity 15.8 t/ha | HSAG 2024, Table 1.6 [S5] |
| Maharashtra monthly onion arrivals 2023-24 | **~0.41–1.07 million t/month** (min Nov-23, max Jul-23); same order across 2021-22→2023-24 tables | HSAG 2024, Tables 8.1.1–8.1.3 [S5] |
| Lasalgaon APMC daily arrivals | ~15,000 q/day baseline; fell to ~8,000 q (Aug-2026 rains); up to 25–30k q at peak supply (Feb-2026) | Business Today 14-Aug-2026 [S6, fully fetched]; FreshPlaza 09-Feb-2026 (headline/snippet only — corroborative, not load-bearing) |
| Lasalgaon price levels Aug-2026 | avg ₹2,180→₹2,760/q over five sessions; day's min/max ₹800/₹3,117/q; crossed ₹4,250/q avg by 24-Aug (ToI headline only) | [S6]; ToI 24-Aug-2026 (snippet) |
| JURY_LOG Q5 spoken claim "Lasalgaon clears hundreds of arrivals a day" | Consistent: ~15,000 q/day ≈ 1,500 t/day ≈ roughly 150–300 truck arrivals at 5–10 t/truck | derived from [S5][S6] |

Note for slides: HSAG's own monthly-arrival tables are the citable source;
newspaper arrival figures fluctuate with season and should carry their date.

## 6.3 Manual grading time-per-lot — SUPPORTED (converts IMPACT_EVIDENCE §4 from pure assumption)

Bisen, Bakane & Sakkalkar (2022), rotary-onion-grader paper (ICAR-AICRP PHET,
Dr PDKV Akola), doi:10.1007/s13197-021-05253-8, PMC9114269 — full text read
2026-08-25 [S2]:

- Nashik-area trade survey (wholesalers/retailers/traders/storage): "**about 30
  persons are required to grade 20 tonnes of onions in a day**".
- Derived: ≈667 kg/person-day ≈ **0.72 person-min/kg** ⇒ a 2–5 t tractor-trolley
  lot = **24–60 person-hours** of manual grading.
- India grades **~50–55 lakh t/year manually** (paper cites Tripathi 2005,
  NRC Onion & Garlic conference — historical figure, pre-mechanisation).
- Machine context: their rotary grader does 20 t/day at 92.99% grading efficiency;
  Gunathilake et al. 2016 onion grader capacity 630 kg/h (doi:10.1016/j.profoo.2016.02.022,
  verified via [S2]'s reference list — secondary verification).
- Same paper confirms manual grading is "expensive and time-consuming", labour-scarce
  at peak season (citing Narvankar et al. 2005), and that repeated handling removes
  skin and shortens shelf life.

Honesty caveats enforced: (a) survey figure, not a time-motion study; (b) measures SIZE
grading, not defect sorting — defect sorting is likely slower per bulb, so using it as a
LOWER bound on manual effort is the conservative direction and is how IMPACT_EVIDENCE §4
now words it; (c) Nashik-region figure, not an all-India average.

Consequence: IMPACT_EVIDENCE §4's old bare assertion "manual whole-lot grading takes hours"
is now literature-backed; the app-side handling estimate (~45–90 s/look) remains ASSUMED.

## 6.4 Onion post-harvest loss % — SUPPORTED

Primary source read end-to-end where cited (PDF downloaded, text extracted):

- **Jha SN, Vishwakarma RK, Ahmad T, Rai A, Dixit AK (2015).** Report on Assessment of
  Quantitative Harvest and Post-Harvest Losses of Major Crops and Commodities in India.
  ICAR-CIPHET, Ludhiana (MoFPI-sponsored), 174 pp [S1].
  - Onion overall national loss: **8.20%** (2005-07 study: 7.51%).
    Farm operations 6.05% (harvesting + sorting/grading dominate); storage 2.16%.
    Regional range **5.49% (Gujarat) → 12.72% (western plateau & hills, incl. Maharashtra)**.
  - Table 6.8: onion row = production 16.66 Mt (2012-13) × price ₹16,920/t (2014 national
    avg wholesale) × 8.20% ⇒ **₹2,312 crore** loss. Arithmetic re-checked this session ✓.
  - Literature reviewed inside the same report: Kumar et al. 2006 Karnataka onion survey —
    field 6.21%, wholesaler 1.85%, retail 2.36%; Nanda et al. 2012 eight-vegetable study
    incl. onion (totals 6.9–13.0%). Cite as secondary if needed.
- Cross-check table pairing both studies (Vegetables 4.58–12.44% CIPHET / 4.87–11.61%
  NABCONS): Lok Sabha US Q.839 [S3].

Pitch guidance: quote "**~8% harvest-to-retail loss nationally (ICAR-CIPHET), worst region
12.7% including Maharashtra**, worth ~₹2,300 crore/yr at 2014 prices" — never the inflated
20–40% figures that circulate without primary sources; nothing verified this session
supports those.

## 6.5 UI items STILL unsupported or still open after this pass

Re-checked against app/static on 2026-08-25:

| Item | Location | Status |
|---|---|---|
| I2/A2/D-dashboard money figures | index.html:148,274; arbitrate.html:139-142; dashboard.html:297-298 | **STILL FLAGGED.** Headline "Fair price band · per quintal" implies market grounding; only small-print "demo rates". New context: Grade-A default ₹2,400 sits inside observed Aug-2026 Lasalgaon band ₹800–3,117/q (avg ₹2,180–2,760) [S6], but the B/C/UNDERSIZED differentials are invented. Fix options unchanged: "(illustrative)" at equal prominence, wire Agmarknet/e-NAM modal price, or cite buffer-procurement rate ₹2,125/q effective 04-Jul-2026 (Zee headline seen in search index only — retrieve full article before quoting). |
| C2 band attribution | report.html:85 | **STILL OPEN (P2).** "graded to ICAR-DOGR bands" prints with NO source+access-date despite D7 promising exactly that. This pass did not re-litigate D7; the promised citation must ship or relabel. |
| V1 verdict wording | verify.html:76 | **STILL OPEN.** "✔ CERTIFICATE VERIFIED" still conflates record integrity with measurement validity ("RECORD INTACT" proposed in R-001 §3.5). |
| C7 signature semantics | report.html signatures | **STILL OPEN (P4).** No "records attestation, does not authenticate identity" line under signature blocks. |
| I4/C8/D3 quality & drift thresholds | index/report/dashboard | Unchanged — self-chosen UI conventions; keep presenting them as such. |

Fixed earlier and confirmed still in place (no regression): prototype masthead marking
(report.html:36), internal-rot RGB blindness sentence (report.html:97), dashboard DEMO DATA
chip (dashboard.html:22).

## 6.6 Reference list for this pass (labels [S#]; deliberately not [R#], which are claim IDs in §2.1) (author, year, doi/url, access date)

- **[S1]** Jha, S.N., Vishwakarma, R.K., Ahmad, T., Rai, A., Dixit, A.K. (2015).
  *Report on Assessment of Quantitative Harvest and Post-Harvest Losses of Major Crops
  and Commodities in India.* ICAR-AICRP on Post-Harvest Technology, ICAR-CIPHET, Ludhiana.
  https://ciphet.res.in/wp-content/uploads/pdf/MOFPI%20REPORT1.pdf — accessed &
  downloaded 2026-08-25 (174 pp; onion §6.4.2 p.90-91, Table 6.8 p.100).
- **[S2]** Bisen, R.D., Bakane, P.H., Sakkalkar, S.R. (2022). Design, development and
  performance evaluation of rotary onion grader. *J Food Sci Technol* 59(6):2370–2380.
  doi:10.1007/s13197-021-05253-8. PMCID PMC9114269.
  https://pmc.ncbi.nlm.nih.gov/articles/PMC9114269/ — accessed 2026-08-25 (full text).
- **[S3]** Ministry of Food Processing Industries, Govt of India (2025). Lok Sabha
  Unstarred Question No. 839, answered 04-Dec-2025 ("Post Harvest Losses"; table pairing
  ICAR-CIPHET 2015 % with NABCONS 2022 % and ₹).
  https://sansad.in/getFile/loksabhaquestions/annex/186/AU839_b5IiJw.pdf?source=pqals
  — accessed & downloaded 2026-08-25.
- **[S4]** Hindustan Times (2024). "India loses ₹1.5 lakh crore worth of farm produce each
  year, study reveals" (reports MoFPI written reply citing NABCONS study; onion ₹5,156 cr).
  Published 05-Dec-2024. https://www.hindustantimes.com/india-news/india-loses-rs-1-5-lakh-crore-worth-of-farm-produce-each-year-study-reveals-101733408241490.html
  — accessed 2026-08-25 (full text).
- **[S5]** Ministry of Agriculture & Farmers Welfare, Govt of India (2024). *Horticultural
  Statistics at a Glance 2024.* https://agriwelfare.gov.in/Documents/HORTICULTURAL_STATISTICS_AT_A_GLANCE_2024.pdf
  — accessed & downloaded 2026-08-25 (320 pp; Table 1.6 p.33 TOP crops; Tables
  8.1.1–8.1.3 p.200-202 monthly onion arrivals, state-wise, tonnes).
- **[S6]** Business Today Desk (2026). "Wholesale onion prices go up by 25% at Lasalgaon,
  Pimpalgaon mandis." Published/updated 14-Aug-2026.
  https://www.businesstoday.in/india/story/wholesale-onion-prices-go-up-by-25-percent-at-lasalgaon-pimpalgaon-mandis-549144-2026-08-14
  — accessed 2026-08-25 (full text; attributes arrivals/prices to Economic Times report
  and Lasalgaon APMC officials).

Snippet-only corroboration (seen in search index 2026-08-25, NOT fully retrieved — do not
quote figures from these without retrieval): Times of India 24-Aug-2026 (Lasalgaon >₹4,250/q);
Zee Business 04-Jul-2026 (buffer procurement price raised to ₹2,125/q); FreshPlaza
09-Feb-2026 (arrivals 25–30k q); NABCONS Corporate Pitchbook PDF (download timed out).

— End of R-2219 addendum. No production code modified; scripts/impact_evidence.py edited
as the IMPACT_EVIDENCE.md generator; regenerated output diffed by eye against prior version.
