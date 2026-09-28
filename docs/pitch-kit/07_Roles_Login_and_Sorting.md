# Roles and logins, and sorting

## 1. Roles: built into the app (v0.4.0)

Each phone has its own accounts, protected by a PIN. The PIN is stored only as a salted PBKDF2 hash, never in plain text. Five wrong PINs lock that account for 30 seconds, and the app locks itself after 15 minutes without a tap. All of this works offline.

| Role | Signs in? | Can do | Cannot do |
|---|---|---|---|
| Supervisor | Yes, PIN | Everything an officer can do. Also adds or switches off accounts, resets PINs, changes centre settings and the rule pack in force, and re-grades a lot under another pack | |
| Procurement officer | Yes, PIN | Starts lots, photographs trays, changes a verdict with a reason, signs receipts | Change the rule pack, manage accounts |
| Auditor | Yes, PIN | Reads lots and receipts, opens the fleet dashboard, exports the log | Grade, override or sign |
| Farmer or buyer | No account | Contests a bulb on the officer's screen; checks any receipt on their own phone | |

Every lot, every change and every receipt records who did it. The receipt shows "Signed by R. Shinde (OFF-07), Procurement officer", and a farmer checking it on their own phone sees the same line. Accounts are switched off, never deleted, so old receipts still name who signed them.

### The workflow with roles, as a story

This example uses the three demo accounts in the app ("Explore the demo" on first launch):

| Account | Role | Demo PIN |
|---|---|---|
| S. Patil | Supervisor | 1111 |
| R. Shinde | Procurement officer | 2222 |
| A. Kulkarni | Auditor | 3333 |

1. **Morning, set-up (supervisor).** S. Patil opens SAMA on the centre phone and adds today's officer, R. Shinde (OFF-07), with a PIN. She checks that the rule pack in force is "30 Jul 2026 · Grade A only". Officers can't change it, so every lot today is graded by the same rule.
2. **A farmer arrives (officer).** Ramesh brings 24 sacks. R. Shinde signs in with the PIN and starts a new lot. Ramesh types a 4-digit code and Shinde types another; together they pick which 5 sacks get opened.
3. **Grading (officer).** Shinde photographs a tray from each sack on the mat, and SAMA grades the lot: say 71% Grade A by weight.
4. **Disagreement (farmer and officer).** Ramesh thinks one rejected onion is fine and taps "Farmer: contest" on the officer's screen. Shinde looks again and taps "Officer: change" with the reason "re-inspected by hand". Both actions are saved under OFF-07, next to the AI's original verdict.
5. **Receipt (officer).** Shinde signs. The receipt carries the grade, the rule pack, "Signed by R. Shinde (OFF-07)" and a QR code. Ramesh gets it on WhatsApp.
6. **At home (farmer, no login).** Ramesh's son opens SAMA and taps "Check a receipt without an account". His phone, with no internet, re-runs the grading: "Receipt checks out. Signed by R. Shinde (OFF-07), Procurement officer."
7. **Month-end audit (auditor).** A. Kulkarni from the district office signs in on the centre phone as an auditor. She can open every lot and receipt and the fleet dashboard, where she sees how often each officer overrode the AI. She has no button to grade, change or sign anything.
8. **Staff change (supervisor).** An officer leaves. The supervisor switches their account off. Their old receipts still verify and still show their name.

### What's next for roles

Today the receipt is signed with the phone's key, and the account name is written inside the signed record. The next step is a separate key per officer, with the supervisor's approval signed onto it (a QR scan between the two phones). A verifier could then check offline both who signed and that they were authorised. Online auditor logins for a head-office dashboard would come with the sync server.

## 2. How to add a sorting mechanism after grading

SAMA already knows, for every onion, its grade **and where it is in the photo** (its outline). Sorting means turning that into a physical action. There are three levels, from cheapest to most automated.

### Level 1: Guided hand sorting (possible almost immediately, no hardware)

- After grading a tray, the app shows the photo with each onion outlined in its grade colour (green A, amber URS, red Reject, grey "check"). This colour overlay already exists; numbering the rejects is a small addition.
- A worker picks the red ones off the tray while looking at the screen.
- Optional: point the phone at the tray again and let the live camera highlight the rejects in real time, so the worker doesn't need to match numbers.
- **Where it fits:** procurement centres, FPOs sorting before travel, retail shops.
- **Cost:** zero; it's a software feature. The grading output (`bulb id → outline → grade`) is already there.

### Level 2: Grading table with a lane guide (low-cost hardware)

- A fixed phone or USB camera on a stand above a table.
- The table has 3 bins: A, URS and Reject.
- After each photo, a cheap projector or an LED strip lights up each onion's target bin, or a tablet screen beside the table shows it.
- Throughput depends on the worker, but every decision is measured and logged.

### Level 3: Automatic conveyor sorter (for large centres and cold stores)

```
 Onions ──► vibrating singulator (one onion per cup or lane)
           ──► conveyor under a camera + LED light box (consistent light, no glare)
           ──► edge computer runs SAMA's models (same ONNX files) + the same rule pack
           ──► belt encoder tracks each onion's position
           ──► at the right moment, an air jet or flap pushes it into the A / URS / Reject chute
```

- **Same brain, new body.** The models are already ONNX, so they run on an edge computer such as a Raspberry Pi 5 with an AI accelerator, or an NVIDIA Jetson, the same way they run on the phone. The rule pack and the grading core are unchanged, so a conveyor-graded lot gets the same kind of signed receipt.
- **What changes:**
  - Rolling rollers turn each onion as it moves, so the camera sees all sides. That is better than "shake, look again".
  - Controlled lighting removes the glare and white-balance problems of handheld photos.
  - A load cell can weigh each onion, replacing the size-based weight estimate with a real weight.
- **What needs building:** the mechanical conveyor and ejectors (standard parts used in fruit sorters), a timing controller (a microcontroller such as ESP32 or Arduino driving solenoid valves), and a small program that links "onion id + grade" to "fire ejector N at time T".

**How to say it in the pitch:** "SAMA outputs a grade and a position for every onion. Today a worker uses that to sort by hand. The same models and rulebook can drive a conveyor sorter with air-jet ejectors, and every sorted lot still gets a signed receipt."

**Recommendation for SIH:** build Level 1 into the app (a "sorting view" on the result screen). It is quick to build and demos well: the rejects light up red and a hand picks them off. Present Levels 2 and 3 as the roadmap, with the diagram above.
