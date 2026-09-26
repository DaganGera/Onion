# Your two questions: logins and roles, and sorting

## 1. Does SAMA have separate logins and roles?

**Not today.** Identity is set once per phone in Settings:
- a centre ID (for example LSG-01) and an officer ID (for example OFF-07);
- a signing key generated on the phone, which never leaves it.

Every receipt is signed with that key, so it is clear which device and which officer issued it. The farmer needs no account at all: they only scan and verify.

The app does have roles *in the workflow*: "Officer: change" (override) and "Farmer: contest" are separate actions, recorded separately. But there is no login screen, and nothing stops someone who picks up the officer's phone from using it.

### Would roles make it better? Yes, if done the right way

Real procurement has distinct people with distinct powers, and the audit trail is only as good as knowing who did what. The design that fits SAMA:

| Role | Can do | Login |
|---|---|---|
| **Procurement officer** | Create lots, capture, grade, override with a reason, sign receipts | PIN or fingerprint on their phone, unlocking their own signing key |
| **Centre supervisor** | Everything an officer can do, plus approve overrides above a threshold, enrol officers' phones, switch the active rule pack | PIN + fingerprint |
| **Farmer / FPO** | Contest a bulb on the officer's screen, verify receipts on their own phone | **No login.** Verification must stay open to anyone, or it stops being independent |
| **Auditor / NAFED HQ** | Read-only fleet dashboard, override statistics, drift between centres, re-grade any lot under any pack | Online login (web), because auditing happens in an office |

**Keep it offline-friendly.** Don't use a username and password that need a server. Instead:
- Each officer's phone creates its own key.
- A supervisor "enrols" that key once by signing it (a QR scan between the two phones).
- From then on, every receipt carries the officer's key plus the supervisor's enrolment signature, so a verifier can check **who** signed and **that they were authorised**, still offline.
- Biometric unlock (Android's fingerprint prompt) protects the key on the phone.

**How to say it in the pitch:** "Today every receipt is signed by the device and officer that issued it. The next step is role-based access with offline-verifiable officer enrolment: officers, supervisors and auditors each get exactly their powers, and farmers never need an account to verify."

The team can build this in about 1 to 2 days of work if you want it in the demo.

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
