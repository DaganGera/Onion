# JURY LOG

## Panelist rotation state
Rotation order: **DoCA official → CV/ML professor → mandi procurement veteran →
farmer-rights advocate → startup judge** (next = least-recently questioned).

- 2026-08-24 · LOOP-J2215 · **DoCA official** (skeptical, round 1) questioned.
  **Next up: CV/ML professor.**

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
