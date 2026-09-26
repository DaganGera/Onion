# JURY LOG

## Panelist rotation state
Rotation order: **DoCA official → CV/ML professor → mandi procurement veteran →
farmer-rights advocate → startup judge** (next = least-recently questioned).

- 2026-08-24 · LOOP-J2215 · **DoCA official** (skeptical, round 1) questioned.
- 2026-08-25 · LOOP-J2259 · **CV/ML professor** (round 2) questioned.
  **Next up: mandi procurement veteran.**

---

## Session LOOP-J2259 — CV/ML professor
Grounding: main.py, grading.py, arbitration.py, db.py, scripts/{train,
eval_lot,eval_calibration,run_config}.py, static/{report,index,dashboard}.html,
constants.json, METRICS.json, STATUS.md; filesystem facts: runs/ EMPTY,
weights/best.pt present, data/holdout = 24 labelled images. Production code
read-only. 127-test baseline assumed standing.

### Q1 — TECHNICAL GRILLING: what survives contact with real onions?
"Every number you will quote me — mAP50 0.978, lot Grade-A error 1.2 points,
20.5%/10.8% occlusion misses — was measured on trays from YOUR OWN procedural
generator (METRICS.json:31-34; STATUS.md:30-33 literally admits 'the model
solved a drawing, not onions'). Even your holdout is the same generator with a
different seed — 'different day, different phone' is simulated diversity. Tell
me precisely what transfers to a Nashik red-onion heap and what does not, give
me your expected real-mAP range, and hand me the sampling protocol for the
first real shoot."

**Answer given TODAY (honest core strong, protocol missing):** We attack
ourselves first: the warning is ON the status page (STATUS.md:28-35: "Expect
real mAP far lower"; METRICS.json:41 top risk #1). What legitimately
transfers, with measurements: (a) the millimetre chain — generator planted a
1.06x magnification and calibrate_size recovered it within 1.8%, MAE 4.87 ->
0.37 mm (STATUS.md:38-41); (b) occlusion physics — defects placed as
spherical caps on a 3D bulb, back-facing caps invisible to ANY camera, so the
two-look gain (misses 20.5% -> 10.8%) is geometry, not a colour shortcut
(STATUS.md:42-43; METRICS.json:32-33); (c) every script/gate/endpoint runs
(STATUS.md:44). What does NOT transfer: absolute mAP (realism ceiling
admitted after hard-negative work moved it only 0.989 -> 0.978, STATUS.md:244-
248), defect-class appearance, and all three fitted factors — which is why
they live in a script-written JSON, never hardcoded (app/constants.json;
STATUS.md:81-82 "Re-fit all three after your first real shoot"). Leakage is
checked for real: dataset QA gate, zero leakage, 284 imgs/9683 boxes
(STATUS.md:14). **WEAK SPOT:** no written first-shoot SAMPLING PROTOCOL —
quotas per variety/lighting, doubles oversampling (rarest class, 1.4% of
boxes, weakest at 0.894 — STATUS.md:104-106; METRICS.json:44), caliper-truth
column contract. Only the bare re-run command chain exists (STATUS.md:115-123).
-> **CRITICAL-PREP P6.**

### Q2 — METHOD CHALLENGE: your pitch metric was measured at a different
operating point than the thing that signs certificates
"Your eval script's own docstring says inference mode is pinned 'identical to
deployment, so an eval number is transferable' (eval_lot.py:22-23). It pins
end2end/imgsz/max_det through one shared helper (run_config.py:45-52) — and
then leaves confidence to the caller: the APP predicts at conf=0.25
(main.py:385-386), your eval defaults to conf=0.35 (eval_lot.py:206). The 1.2
point MAE you pitch was measured at a threshold the app never runs. Quantify
the delta or withdraw the number."

**Answer given TODAY (weak — concede):** TRUE. The pinning helper
deliberately omits conf ("Callers add conf themselves", run_config.py:49-51)
and the two callers diverged. Direction of the delta is UNMEASURED, and the
plausible sign is bad: merge_looks counts every detection's PREDICTED label
into the pooled percentages with no decision filtering (grading.py:194-199),
so the extra detections admitted between 0.25 and 0.35 are additional
low-confidence votes in the certified statistic, not filtered-out noise. The
honest position: the pitch MAE is stale relative to the shipped operating
point; nothing in the repo quantifies the gap; re-measurement needs the
weights+data run (GPU present per STATUS.md:3, feasible, not done).
**WEAK SPOT:** nothing even LOCKS the two configs together, so this can
silently recur after any retune. -> **CRITICAL-PREP P7.**

### Q3 — PROVE IT LIVE: show me 0.75 means something
"Your dashboard says: if stated confidence is not observed accuracy, 'the
ACCEPT / REFER line at 0.75 is decoration' (dashboard.html:105-108). Fine.
Open that panel now and show me your reliability curve and ECE. If the
measurement behind the certificate's most important gate was never run, every
ACCEPT on every certificate is decoration."

**Answer given TODAY (infrastructure strong, artifact MISSING):** The
measurement pipeline exists end-to-end and is honest-by-construction:
scripts/eval_calibration.py runs the DEPLOYED inference path, IoU>=0.5
greedy-matched correctness, 10 reliability bins, ECE/MCE, a recommended
smallest-trustworthy cut with min-support, and a temperature fit (docstring +
ASSUMPTIONS, eval_calibration.py:1-66; report written to exactly
runs/report/calibration.json, :383). It refuses to launder bad data: no
recommendation when the target is unreachable (:323-327) and --write-threshold
refuses cuts outside [0.30, 0.95] (:53-56, :339-342). The endpoint degrades
cleanly when the report is absent ({"available": false, "reason":
"not_generated"}, main.py:721-723) and the dashboard renders a hint, not a
dead panel (dashboard.html:353-354, 390-391, 437). **BUT:** runs/ is EMPTY on
this machine — the measurement has NEVER been run here. Live today, the panel
shows "not_generated". Assets are present and sufficient: weights/best.pt
exists; data/holdout holds 24 labelled images; --split holdout is supported
(eval_calibration.py:51). **WEAK SPOT:** we cannot show a number, and we must
not quote one, until the script runs. -> **CRITICAL-PREP P8.**

### Q4 — ETHICS/TRUST PROBE: trace what actually happens to a REFER'd bulb
"The certificate's method note says bulbs below the confidence threshold are
'referred to a human inspector rather than auto-graded' (report.html:130-131).
Walk me through the referral. Who is notified? Where is the queue? And if no
human ever sees them — did your model just disclaim those bulbs while you
counted their guesses at full weight in the certified percentage anyway?"

**Answer given TODAY (concede fully; surroundings partially strong):**
Traced: decide() flags conf<0.75 REFER (grading.py:125-127); /analyze attaches
it per bulb (main.py:404); finalize -> merge_looks counts EVERY observation's
predicted class into class_counts, grade_pcts and the worst-look defect rate
regardless of decision (grading.py:194-199, 217-222); n_referred is displayed
as a bare count (report.html:105-106, :303). There is NO notification, NO
queue, NO routing anywhere in the repo. So the method-note sentence is FALSE
as written: those bulbs were auto-graded into the certified statistics; the
only human who can see them is whoever later opens the certificate's annotated
tray photos (evidence gallery, main.py:233) or files a bulb-level dispute
(/dispute/{bulb_id}, main.py:637-652; db.mark_disputed db.py:391). Mitigation
in fact: the band is measured thin (1.4% of predictions below threshold on the
NMS path, STATUS.md:95) — but thin is not zero and the copy overclaims.
index.html repeats the overclaim ("Referred to inspector", index.html:406).
**WEAK SPOT:** the certificate asserts human oversight that does not exist.
-> **CRITICAL-PREP P9.**

### Q5 — SCALING/COST: the data flywheel nobody funded
"You trained on one generator plus public Roboflow pulls (fetch_public_data.py),
pre-labelled by your own model (bootstrap_label.py). Six hundred mandis, a
dozen varieties, three seasons. What watches for Kurnool's pink onions drifting
out of your training distribution BEFORE certificates go wrong, what does
continuous labelling cost per centre, and what triggers a retrain?"

**Answer given TODAY (partial):** Instrumented today: per-centre drift
monitoring against a sealed reference tray — baseline is the centre's own
settled early window, latest score vs baseline, RECALIBRATE below -5.0
(db.py:495-536, esp. :520 and :530); the digital-twin endpoint replays a
certified lot under quality drift, measured-vs-simulated clearly separated
(main.py:681-705); the capture-quality gate blocks degraded frames before
inference (main.py:373-375). Crucially, every lot persists its looks, per-bulb
decisions, scale rung and scale confidence (meta at main.py:554-564), so
per-centre REFER-rate trends and scale-rung mixtures are RETROSPECTIVELY
queryable with zero new instrumentation. **WEAK SPOT:** all of that is
OUTCOME/operations drift. Nothing monitors INPUT distribution shift (variety/
season/appearance) — that would need embedding-level monitoring we have not
built; there is no labelling-cost arithmetic anywhere in the repo; there is no
retraining trigger policy. Saying "the flywheel exists" would be a lie.
-> **CRITICAL-PREP P10.**

### What survived the attack (credited by the panellist)
- Unusual candour: the synthetic-data warning lives in STATUS.md:28-35 and
  METRICS.json:28/41 — the repo prosecutes itself harder than this panel can.
- run_config.py echo_config: every number-producing script stamps git commit,
  versions, seed and full config onto its own output — contestable numbers by
  construction.
- Calibration tooling that refuses to launder a bad measurement into a signed
  threshold (SAFE_THRESHOLD_BAND, unreachable-target refusal,
  eval_calibration.py:53-56, :323-327, :339-342).
- The mat_edge demotion: a rung that LOOKED excellent was measured against
  caliper truth, found confidently wrong (16.9 mm MAE), and demoted BELOW
  carried-scale (STATUS.md:209-230) — the team kills its own good-looking
  numbers when the data disagrees.
- Two self-caught metric bugs documented with the fix and the honesty lesson
  (generator roster swap inflated every 2-look number; pooling bug kept
  occlusion bias — STATUS.md:48-65).

---

## Session LOOP-J2215 — Skeptical Dept of Consumer Affairs official
Grounding: app/main.py, grading.py, scale.py, db.py, arbitration.py,
capture_quality.py, mat_layout.py, static/*.html, constants.json,
.agent/{METRICS,EVIDENCE_AUDIT,DECISIONS,FINAL_REPORT}.md, scripts/seed_demo.py.
Production code read-only. 127-test baseline assumed standing.

### Q1 — TECHNICAL GRILLING: the defect-rate correction chain
"The defect percentage that drives rejection is: take the WORST per-look
defect rate, divide by magic constants 0.7886/0.877 fitted on synthetic
trays (constants.json:3-4, grading.py:224-227). Justify the division
direction, justify 'worst look' as an estimator, and tell me what my
certified number reads if real mandi stacking hides twice what your
simulator did."

**Answer given TODAY (honest):** Division direction is stated in-code:
observed = factor x true, so true = observed / factor (grading.py:226-227).
'Worst look' rationale: two looks re-observe the SAME bulbs; pooling would
keep the occlusion bias and merely halve it; the less-occluded view is the
better estimate (grading.py:209-216, decision D4). The certificate carries
raw AND corrected figures plus an interval explicitly labelled
"least-occluded view" (report.html:94-95, 165-176; arbitration.py:194-228),
and the interval builder reconstructs (k,n) from the already-published
per-look rates so it cannot drift from the printed statistic
(arbitration.py:240-254, decision D8). **WEAK SPOT:** both factors come
from synthetic-tray fitting (METRICS.json:28 admits all such numbers are
synthetic); nobody has quantified how the certified % moves if the factor
is wrong by 10-25% on a real heap. No sensitivity table exists anywhere.
→ **CRITICAL-PREP P1.**

### Q2 — DOMAIN CHALLENGE: ICAR-DOGR band attribution on a signed document
"You print 'graded to ICAR-DOGR bands' (report.html:85). Your own evidence
audit initially found published DOGR-lineage sources using A >60 mm
(EVIDENCE_AUDIT.md section 1.1). Decision D7 claims resolution via a
dogr.res.in Agropedia source and promises 'cite source+access date on
report.html method note'. Show me that citation on the certificate."

**Answer given TODAY (honest):** Bands are the mandated problem-statement
constants (grading.py:29-34; CLAUDE.md domain rules); D7 documents the
resolution and its rationale. **BUT the promised mitigation was never
shipped:** report.html:82-97 contains no source citation and no access
date. The certificate asserts a standard without the citation the team's
own decision record says should be there. → **CRITICAL-PREP P2.**

### Q3 — PROVE IT LIVE: tamper demo survives a server restart
"Do it now: seed a centre, finalise a lot, attack it, show me red on the
public verify page, KILL the server mid-attack, restart, restore, show me
green again. Any step needing an incantation you can't produce makes the
whole trust story theatre."

**Answer given TODAY (strong):** Attack really mutates the row — no
simulation flag (main.py:735-759, UPDATE at db via _set_grade_a
main.py:724-732); audit_chain recomputes every hash and reports WHERE the
break is (db.py:299-328); verify flips to TAMPERED RECORD DETECTED
(verify.html:72-82). Restart-mid-attack is covered: restore-all sweeps
in-memory state AND every row disagreeing with its own result_json, which
the hash never covered and nothing else updates (main.py:783-844,
_GRADE_A_MATCH_TOL main.py:780). Seeder defaults to 40 historical lots
across six centres (scripts/seed_demo.py:81). **WEAK SPOT:** no rehearsed
runbook with expected outputs; an empty/dirty venue DB turns beat 2 into a
404 in front of the panel. → **CRITICAL-PREP P3.**

### Q4 — ETHICS/TRUST PROBE: what does 'Confirmed on device' legally attest?
"Both signatures are free-text fields plus a tap on the SAME device,
presumably held by one officer (index.html:189-207, 947-959). The farmer
may never have touched the phone. What exactly does the certificate attest,
and who wrongs whom when it is wrong?"

**Answer given TODAY (partially strong):** The artifact already refuses to
borrow authority: "Prototype — not an official DoCA instrument"
(report.html:35-37); chain copy says tamper-evident, not tamper-proof
(report.html:131-134, verify.html:50-55); both-party taps gate certificate
generation (index.html:209-212, 952-956); names enter the hashed payload
(db.py:168-181); disputes are recorded honestly against real bulb rows and
sit OUTSIDE the hash envelope by stated design (main.py:405-420,
main.py:204-208, db.py:10-14). **WEAK SPOT:** the signature blocks print
"✓ Confirmed on device" with no statement that this records attestation,
not identity authentication — an informed panellist will read the glyph as
a digital signature. → **CRITICAL-PREP P4.**

### Q5 — SCALING/COST: 200 lots/day, one SQLite file, who pays for the tunnel?
"One process, per-request SQLite connections (db.py:87-94), a 32-lot
in-memory scale cache (main.py:53-57). Lasalgaon clears hundreds of
arrivals a day. What breaks first at 200 lots/day, what does one centre
cost the department, and where do certificates live when the machine dies?"

**Answer given TODAY (partial):** WAL journal + 10 s busy timeout +
short-lived connections (db.py:87-94) is adequate for one centre's write
rate; measured compute headroom is large (p95 139 ms CPU per look,
METRICS.json:36); rural-bandwidth wall already addressed with measured
numbers (upload downscale, decision D10); per-centre drift monitoring
exists (db.py:350-391). **WEAK SPOT:** no written capacity arithmetic, no
backup/export story beyond the live file, no per-centre BOM, and "central
aggregation" simply does not exist — none of this is anywhere in the repo.
→ **CRITICAL-PREP P5.**

### What survived the attack (credited by the panellist)
- JSON-error guarantee incl. global catch-alls (main.py:106-129) and the
  aruco/model 503s that keep replay alive (main.py:285-292).
- Calibration ladder that withholds sizes rather than inventing them
  (scale.py:351-354) and prints its own rung on the certificate
  (report.html:196-219).
- Capture-quality gate refusing godown-dark frames before inference
  (capture_quality.py:40-52, main.py:302-308).
- Internal-rot RGB blindness disclosed ON the certificate
  (report.html:90-93).
- Restart-safe tamper recovery (main.py:783-844).

---

## Open prep tasks
Format: ready-to-dispatch. Each is small, testable, and independent.
Suggested owner in brackets. Read-only rule applies to the dispatcher, not
implementers; implementers must follow CLAUDE.md working rules.

### P1 · Defect-correction sensitivity defense [data-scientist]
Gap: nobody can quantify how the certified defect % moves if the occlusion
factor is wrong on real stacks (Q1 weak spot).
Do ALL of:
1. Add `tests/test_factor_sensitivity.py`: build a fixed two-look fixture
   (~60 bulbs/look, ~12% hidden defects), run `grading.merge_looks`, assert
   `defect_rate_corrected == min(1, raw/factor)` for the shipped factors
   AND for factors scaled by 0.75x / 0.9x / 1.1x / 1.25x; assert the
   corrected rate moves INVERSELY to the factor and never exceeds 100%.
   Pure functions, no torch, no network.
2. Write `.agent/DEFECT_FACTOR_DEFENSE.md` (<=1 page): the direction rule
   (observed = factor x true => true = observed/factor, grading.py:226-227),
   the table produced by the new test, and one plain sentence that both
   factors were fitted on synthetic trays (cite METRICS.json:28) plus the
   plan to refit on real photos.
Verify: `python -m pytest tests/test_factor_sensitivity.py -q` -> all pass;
doc contains 0.7886 and 0.877 verbatim.

### P2 · Ship the D7 band citation on the certificate [frontend]
Gap: DECISIONS.md D7 promised "cite source+access date on report.html
method note"; it was never added (Q2 weak spot).
Do ALL of:
1. Recover the exact source DS-001 recorded supporting A>80 mm
   (FINAL_REPORT.md cycle table; dogr.res.in Agropedia). If the URL/date is
   recoverable, append one sentence to the report.html Method note:
   "Size bands A >80 / B 50-80 / C 30-50 mm per <source>, accessed
   2026-08-24." If NOT recoverable, relabel instead: "project-defined
   bands aligned to the problem statement" — do not leave an uncited
   standards claim either way.
2. Keep wording consistent with verify.html and index.html (they do not
   currently claim ICAR-DOGR outside report.html:85 — grep to confirm).
Verify: `rg -n "ICAR-DOGR|dogr|project-defined" app/static/report.html`
shows the citation or the relabel; `python -m pytest tests -q` still green;
`python scripts/smoke_test.py` -> ALL PASS.

### P3 · Tamper-demo live runbook, executed once [qa-engineer]
Gap: demo beats exist and are restart-safe, but no rehearsed command
sequence with expected outputs (Q3 weak spot).
Do ALL of:
1. Write `.agent/TAMPER_RUNBOOK.md`: exact commands — start uvicorn;
   `python scripts/seed_demo.py`; pick a seeded lot id; POST
   `/tamper/attack/{id}` (expect `broken_lot_ids` containing that id);
   GET `/verify/{id}` (expect "TAMPERED RECORD DETECTED"); kill server
   mid-attack; restart; POST `/tamper/restore-all` (expect
   `intact_after: true`); GET `/verify/{id}` (expect VERIFIED). Include the
   empty-DB fallback (run seeder first) and expected JSON snippets.
2. Execute the runbook once on this machine; paste ACTUAL outputs at the
   bottom of the file; leave the DB intact afterwards.
Verify: runbook ends with a pasted transcript showing broken_lot_ids
non-empty then intact_after=true; `python scripts/smoke_test.py` -> ALL PASS.

### P4 · Attestation-vs-identity line on signatures [frontend]
Gap: "✓ Confirmed on device" reads as authenticated identity; nothing on
the certificate says otherwise (Q4 weak spot).
Do ALL of:
1. In report.html, under BOTH signature blocks (farmer + officer), add one
   shared clarifying line, small print: "Device confirmation records that
   both parties saw this result on this device; it does not authenticate
   identity." Match existing text-xs styling; keep the prototype badge.
2. Mirror the same sentence into verify.html's certificate-details card if
   space allows; optional.
Verify: `rg -n "does not authenticate identity" app/static/report.html`;
`python -m pytest tests -q` green; visually check `/report/<seeded lot id>`.

### P5 · SCALING.md — capacity arithmetic + ops costs + backup story [backend]
Gap: scaling/cost questions have partial answers scattered across decisions
but no written arithmetic (Q5 weak spot).
Do ALL of:
1. Write `.agent/SCALING.md` with sections, every number traced to its
   source (METRICS.json, scripts/bench.py output, DECISIONS D10):
   a. Capacity: 200 lots/day x 2 looks = 400 inferences x 139 ms CPU p95
      ~= 56 s pure compute/day — compute is not the bottleneck; name what
      is (single-writer SQLite at finalize bursts; tunnel availability;
      annotated-image size cap main.py:223-233).
   b. Data path: client downscale measured savings (D10: 5925->187 KB/look)
      and the honesty guard.
   c. Per-centre BOM: printed mat (A4, ~INR 10), one Android phone, shared
      laptop or mini-PC running the one process; cloudflared tunnel = no
      public IP needed.
   d. Backup/export: current state = single data/sama.db (WAL);
      PROPOSE nightly file copy + result_json CSV export; state plainly
      this is proposed, not built.
   e. Explicitly list "NOT BUILT": central multi-centre aggregation,
      offline queue-and-sync, authn.
2. No production changes.
Verify: every figure footnoted to file:line or bench output; master review;
`python -m pytest tests -q` unaffected/green.

### P6 · REAL_SHOOT_PROTOCOL.md — first-real-shoot sampling design [data-scientist]
Gap: the professor asked for the sampling protocol behind "re-run everything on
real photos"; only the bare command chain exists (Q1 weak spot).
Do ALL of:
1. Write `.agent/REAL_SHOOT_PROTOCOL.md` (<=1 page), every quota justified by
   a repo fact:
   a. Minimum image target >= the current 284-image set (STATUS.md:14, gate
      T3) so the swap is additive, not a shrink.
   b. Oversample `doubles`: rarest class (1.4% of boxes) and weakest mAP50
      (0.894) — METRICS.json:44, STATUS.md:104-106. State the oversampling
      ratio chosen and why.
   c. Diversity axes: >= 2 varieties, >= 2 lighting conditions, >= 2 phones —
      mirrors the augmentation intent in train.py:210-213 and the holdout rule
      (different day AND different phone, CLAUDE.md).
   d. Ground-truth contract: caliper-measured diameters + hand-sorted counts,
      columns matching what eval_lot.py reads (tray_id, composition, n_total,
      n_grade_A, n_rotten/n_sprouted/n_smut/n_damaged/n_doubles — see
      eval_lot.py:45 and :87-93).
   e. Section "After the shoot": paste the exact re-run chain verbatim from
      STATUS.md:115-123.
2. No production changes; no data collection tonight.
Verify: file exists; contains the words "doubles", "holdout", all six re-run
commands; master review.

### P7 · Lock eval conf to deployment conf [backend]
Gap: eval_lot.py measures the pitch metric at --conf 0.35 default while the
app ships conf=0.25 (main.py:385-386); nothing prevents recurrence (Q2 weak
spot).
Do ALL of:
1. Add `tests/test_inference_parity.py`: parse app/main.py for the
   MODEL.predict conf literal and scripts/eval_lot.py for its --conf default;
   assert equality with a failure message naming both values and files. Run it
   BEFORE step 2, confirm it FAILS, note the observed pair in the task notes.
2. Change scripts/eval_lot.py default --conf to 0.25 (single edit ~line 206)
   and extend the docstring pinning sentence (:21-24) to include conf.
3. Append one line to .agent/METRICS.json cycle_log:
   "LOOP-J2259: eval conf aligned to deployed 0.25; lot-MAE re-measurement
   pending real-data shoot" — the previously quoted MAE is stale until then.
4. Do NOT attempt the GPU re-run of eval_lot.py tonight; record that openly.
Verify: `python -m pytest tests/test_inference_parity.py -q` green;
`rg -n "default=0.25" scripts/eval_lot.py`; full suite still green.

### P8 · Generate the calibration evidence, verify the panel [ml-infra]
Gap: dashboard + /api/calibration promise a MEASURED reliability report;
runs/report/calibration.json was never produced on this machine — a live demo
shows not_generated (Q3 weak spot).
Do ALL of:
1. Run `python scripts/eval_calibration.py --split holdout` (weights/best.pt
   and 24 labelled holdout images are present). Confirm
   runs/report/calibration.json + reliability_diagram.png are written.
2. Start uvicorn; GET /api/calibration -> expect `"available": true`;
   open /dashboard -> Detector calibration card renders ECE/bins, NOT the
   degrade message.
3. Write `.agent/CALIBRATION_EVIDENCE.md`: pasted console summary (ECE, MCE,
   recommendation or its explicit refusal), one honest sentence on whether the
   0.75 threshold survived measurement, path to the PNG. DO NOT pass
   --write-threshold — moving a signed-certificate threshold is a human
   decision; the script enforces this, so must we.
4. If the run fails on this box (missing torch etc.), paste the exact error
   into CALIBRATION_EVIDENCE.md and STOP — never fabricate the artifact.
Verify: calibration.json exists and parses; endpoint returns available:true
with real numbers; CALIBRATION_EVIDENCE.md ends with the pasted transcript.

### P9 · Make the REFER disclosure true [frontend]
Gap: report.html:130-131 claims referred bulbs go "to a human inspector rather
than auto-graded"; in reality their predicted labels count fully in certified
stats and no routing exists (Q4 weak spot).
Do ALL of:
1. In report.html method note, replace that sentence with: "Bulbs below the
   confidence threshold are flagged REFER and counted separately; their
   model-assigned classes still contribute to the statistics above, and the
   Referred figure states how many." Keep text-xs styling.
2. index.html i18n strings (:406 en, :486 hi): change "Referred to inspector —"
   to "Flagged for human review —" (hi: "मानव समीक्षा के लिए चिह्नित —").
   Keys unchanged.
3. Grep sweep: `rg -n "inspector" app/static/*.html` — fix any remaining claim
   that a human automatically sees referrals; dispute flow wording may stay.
Verify: `rg -n "rather than auto-graded" app/static/report.html` -> no match;
`rg -n "Flagged for human review" app/static/index.html` -> en+hi match;
`python -m pytest tests -q` green; visual check of `/report/<seeded lot id>`.

### P10 · DATA_FLYWHEEL.md — what drift we watch, what we don't [backend]
Gap: flywheel/distribution-shift question has partial instrumentation but no
written scope, cost arithmetic, or triggers (Q5 weak spot).
Do ALL of:
1. Write `.agent/DATA_FLYWHEEL.md` (<=1 page), every claim cited file:line:
   a. Instrumented TODAY: per-centre reference-tray drift with RECALIBRATE at
      < -5.0 (db.py:495-536, esp. :520 baseline rule and :530 threshold);
      capture-quality gate (main.py:373-375); scale rung/source persisted per
      lot (meta at main.py:554-564); n_referred inside result_json.
   b. Retrospective tripwires computable WITHOUT new infra — one query sketch
      each: per-centre REFER-rate trend (from stored looks' per-bulb
      decisions); scale-rung distribution shift (scale_source/scale_confidence);
      capture-block frequency (quality field in analyze responses if logged,
      else say where it is NOT stored — do not invent persistence).
   c. Section "NOT BUILT" stated plainly: input/embedding distribution-shift
      detection; automated retraining triggers; priced labelling pipeline.
      Include a labelling-cost TEMPLATE with explicit placeholders
      (seconds/image x INR/hour = blank), no invented totals.
   d. One paragraph citing bootstrap_label.py (humans become correctors, not
      labellers) and fetch_public_data.py (multi-source ingestion + class
      remap) — script names only, no capability claims beyond their docstrings.
2. No production changes.
Verify: `rg -n "NOT BUILT|db.py:495|main.py:554" .agent/DATA_FLYWHEEL.md`
matches; every file:line citation checked by master review.
