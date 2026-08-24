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
