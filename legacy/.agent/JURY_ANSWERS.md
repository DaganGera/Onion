# JURY ANSWERS — rehearsal sheet

Polished 30-second spoken answers from jury rounds. Tag legend:
**[READY]** = answerable today from the repo. **[READY AFTER P#]** =
honest core is ready; deliver only after the prep task lands.
Sources are file:line so any panellist claim can be checked on the spot.

---

## Round 1 — LOOP-J2215 · Dept of Consumer Affairs official

### A1. "Why divide by the occlusion factor, and why the WORST look?" — [READY AFTER P1]
"The division direction comes straight from how the factor was measured:
occlusion makes trays read CLEANER than they are, so observed rate equals
factor times true rate, and we invert it — you can read that rule in a
comment at grading.py lines 226-227. We deliberately do not average our
two looks, because both looks photograph the same bulbs: averaging would
keep the hidden-defect bias and just dilute it. The less-occluded view is
the better estimate of the lot, and the certificate prints the raw rate,
the corrected rate, and a Wilson interval explicitly labelled 'least-
occluded view' — report.html lines 165-176. What I will say plainly: the
factor was fitted on synthetic trays, and before this ships we re-fit it
on real photos and publish a sensitivity table showing exactly how much
the certified number moves if the factor is off by ten percent."
*(P1 produces that table — do not quote specific sensitivity numbers until P1 lands.)*

### A2. "Where is your ICAR-DOGR citation on the certificate?" — [READY AFTER P2]
"The bands — A above 80, B 50 to 80, C 30 to 50 millimetres — are the
constants mandated by the problem statement, and when our own evidence
audit challenged the attribution we ran a second verification against
ICAR-DOGR's public material and kept the bands on that basis; it's
decision D7 in our decision log. You've caught a real gap: the decision
promised a source-and-access-date citation printed on the certificate's
method note and it isn't there yet. That's a one-sentence fix to the
certificate page, and either the citation goes on or the label changes to
'project-defined bands' — an uncited standards claim has no place on an
instrument farmers dispute over."
*(Do not name the Agropedia URL verbally until P2 confirms it is recoverable.)*

### A3. "Prove the tamper story live, including killing the server mid-attack." — [READY]
"Happy to, right now, in four beats. One: we finalise a lot — the seeder
gives us forty across six centres, scripts/seed_demo.py. Two: we attack
it — that endpoint genuinely runs UPDATE on the row, no simulation flag,
main.py line 735 — then the audit recomputes every hash in the centre's
chain, db.py line 299, and the public verify page flips to TAMPERED
RECORD DETECTED. Three: the part most demos skip — we kill the server
mid-attack. On restart, restore-all recovers the true value from the
lot's own result_json copy, which the hash never covered and nothing else
writes — main.py line 783. Four: verify again — green. And the copy on
that page says tamper-evident, not tamper-proof: someone with full
database access could recompute the chain. We say that out loud because
an informed question deserves an honest answer."

### A4. "What does 'Confirmed on device' legally attest?" — [READY AFTER P4]
"Today it attests exactly what it says and nothing more: both named
parties saw this result on this device before generation was unlocked —
the button stays disabled until two taps land, index.html line 952. The
names go inside the hashed payload, db.py line 168, so editing them later
breaks every hash after them. The certificate already refuses borrowed
authority — it's stamped 'Prototype, not an official DoCA instrument' —
and the chain text states tamper-evident, not tamper-proof. Your point
stands: confirmation is not identity authentication, and the signature
block should say so in one sentence rather than let a checkmark imply a
digital signature. Identity binding — departmental SSO or Aadhaar-style
verification — is an integration item for pilot, not something we pretend
to have."

### A5. "200 lots a day: what breaks first, and what does a centre cost?" — [READY AFTER P5]
"Compute isn't the bottleneck: inference measured 139 milliseconds p95 on
CPU, so two hundred lots at two looks each is under a minute of compute
per day. Storage is one SQLite file per centre in WAL mode with
short-lived connections, which comfortably covers one centre's write
rate; drift monitoring per centre already exists. Data cost — the real
rural constraint — we attacked directly: photos shrink on-device before
upload, measured at roughly thirty-fold reduction, with an honesty guard
that ships the original if compression somehow doesn't help. Per centre:
a printed A4 mat costing about ten rupees and one Android phone. What I
won't oversell: central multi-centre aggregation, offline sync, and
nightly backup are designed on paper but not built — the honest scaling
story is one process per centre, proven cheap, with aggregation as the
explicit next milestone."
*(Quote BOM/backup only after P5 fixes them in SCALING.md.)*

---

## Round 2 — LOOP-J2259 · CV/ML professor

### A1. "Your headline numbers all come from your own generator. What transfers to real onions?" — [READY AFTER P6]
"I'll give you the uncomfortable part first, because it's already printed in
our own status page: every accuracy number we quote was measured on synthetic
trays, and our own words are 'the model solved a drawing, not onions — expect
real mAP far lower'. So here is what transfers with evidence and what doesn't.
Transfers: the millimetre chain — we planted a known 1.06x magnification into
the generator and the calibration script recovered it within 1.8 percent,
which is arithmetic that holds on any photo. Occlusion physics — defects are
spherical caps on a three-dimensional bulb, so back-facing rot is invisible to
any camera at any angle; the fact that a second look halves our miss rate from
20.5 to 10.8 percent is geometry, not a colour shortcut. And the entire
software path runs end to end. Does not transfer: absolute mAP, defect-class
appearance, and the fitted correction factors — which is exactly why those
factors live in a JSON file rewritten by calibration scripts, never hardcoded,
with 're-fit after your first real shoot' written above them. The sampling
protocol for that shoot — quotas, doubles oversampling because it's our rarest
and weakest class, caliper truth, holdout discipline of different day and
different phone — is written down."
*(Deliver the protocol specifics only after P6 lands REAL_SHOOT_PROTOCOL.md.)*

### A2. "Your pitch MAE was measured at conf 0.35 but you ship 0.25." — [READY AFTER P7]
"You're right, and I won't defend it with hand-waving. Our run-config helper
pins end-to-end mode, resolution and max detections through one shared module
so scripts can't silently drift from deployment — but confidence was left to
the caller, and the caller diverged: the app predicts at 0.25, the eval script
defaulted to 0.35. Worse, the direction of the error isn't flattering: our lot
merge counts every detection's predicted label regardless of its decision, so
the extra boxes admitted between 0.25 and 0.35 are additional low-confidence
votes inside the certified statistic, not filtered noise. So we treat the 1.2
point Grade-A error as stale until re-measured at the shipped threshold. We've
now added a parity test that fails the build if those two configs ever
disagree again — the fix is one line today and structural forever."
*(Only claim 're-measured' once P7's re-run actually happens on GPU; until
then say 'stale, parity-locked'.)*

### A3. "Show me 0.75 means something. Open the calibration panel." — [READY AFTER P8]
"Gladly — and note we wrote that attack ourselves: the dashboard literally
says if stated confidence doesn't match observed accuracy, then the ACCEPT
line at 0.75 is decoration. The measurement runs the deployed inference path,
matches every detection to ground truth at IoU 0.5, and bins stated confidence
against observed accuracy — reporting ECE, the worst bin, a temperature-scaling
fit, and the smallest cut that is right at least ninety-five percent of the
time with meaningful support. Two design points I want you to notice: when no cut
meets the target, the script returns NO recommendation rather than quietly
lowering the bar, and writing a new threshold into the app requires an explicit
opt-in flag that refuses values outside a sane band — a measurement cannot
launder itself into certificate policy. Here is the reliability curve, and here
is our ECE on the holdout split."
*(Quote ECE/recommendation ONLY after P8 has actually generated
calibration.json and verified /api/calibration says available:true.)*

### A4. "Trace what happens to a REFER'd bulb. Who is the human?" — [READY AFTER P9]
"There isn't one, and the old certificate sentence claimed otherwise — that's
the strongest thing I'll concede today. Traced honestly: below 0.75 the bulb
is flagged REFER, the certificate counts how many, and — this is the part that
matters — their model-assigned classes still contribute to the certified
percentages. No notification, no queue, no inspector. We've replaced the false
sentence with the plain truth on the method note. What remains true around it:
the band is thin — measured at 1.4 percent of predictions — so the exposure is
bounded; every bulb row is individually stored and disputable through the
public dispute endpoint; and the annotated tray photographs ship ON the
certificate itself, so any human holding the paper can audit the machine's
calls without our software in the room. REFER is a disclosure mechanism today,
not a workflow — and now the document says so."
*(Do not say 'thin' with the 1.4% number unless STATUS round-2 figures are
re-confirmed after the real-data retrain.)*

### A5. "Who funds the data flywheel across six hundred mandis?" — [READY AFTER P10]
"What we watch today: every centre periodically grades a sealed reference tray
of known composition, and the dashboard plots each centre's latest score
against its own settled baseline — drop more than five points and it prints
RECALIBRATE, which catches the worn mat, the changed phone, the degraded
lighting. Every certificate also stores its scale rung and every bulb's
decision, so per-centre refer-rate trends and rung mixtures are queryable
right now with zero new infrastructure. What we don't have, in writing, under
a heading called NOT BUILT: input-distribution monitoring — nothing today
detects that Kurnool switched variety and drifted out of our training data;
automated retraining triggers; and a priced labelling pipeline. The economics
sketch: model-assisted pre-labelling makes humans correctors rather than
labellers, which cuts cost per image by an order of magnitude in common
practice — but we refuse to quote you rupees until we've timed real
correction work, and the template with blanks is in our notes where a
fabricated number would look better."
*(Cost placeholders stay blank until someone times a real labelling session;
cite DATA_FLYWHEEL.md after P10 lands.)*
