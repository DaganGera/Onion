# Session log — 2026-08-24

Working session covering: OpenRouter/ox-alpha consultation setup, SIH 2026 hackathon
strategy for SAMA (PS 26046, onion lot grading), a full jury-feature brainstorm and demo
script, a real-repo audit of the existing SAMA build, and pulling + fixing public onion
datasets. API keys used during this session are intentionally **not** included below.

---

## 1. OpenRouter setup

- User wanted to route requests through an OpenRouter model, `stealth/ox-alpha`.
- First API key provided didn't match OpenRouter's key format (`sk-or-v1-...`) and was
  rejected (`401 Missing Authentication header`).
- Second key worked. Verified `stealth/ox-alpha` exists via `GET /api/v1/models`.
- All ox-alpha calls in this session went through `POST /api/v1/chat/completions`.

## 2. Hackathon strategy — first pass with ox-alpha

User's prompt: SIH 2026 internal round, PS 26046 (DoCA, onion quality grading), 3 days,
team of 6, no prior CV/ML experience, vibe-coding via Claude Code.

ox-alpha's response (relayed back to the user):
- **India landscape**: manual mandi grading dominant, mechanical size-graders exist but
  don't grade defects, optical sorters (Tomra/Bühler-class) cost lakhs–crores and aren't
  built for onions, Intello Labs / AgNext are the closest B2B competitors, DoCA framing
  ("neutral digital referee" for disputes) is the strongest pitch angle.
- **46-question bank** across hackathon logistics, team/resources, domain understanding,
  user targeting, technical direction, dataset, demo/validation, wow-factor ranking, risks.

**Claude's follow-up critique** (before the project's own CLAUDE.md was in scope): flagged
that ox-alpha's tech-stack questions (Flutter vs PWA, weight sensors, etc.) assumed a
blank-slate project and would conflict with an already-decided architecture once one exists.

## 3. Jury wow-feature menu + demo script (ox-alpha, fed the locked architecture)

Once the actual SAMA architecture (YOLO26, ArUco 8-marker mat, FastAPI single-process,
Wilson CI, frozen `grading.py`, etc.) was described to it, ox-alpha produced:

- **Feature menu** across four categories — Trust & Arbitration (verify page + QR, Ed25519
  signatures, live tamper-attack demo, model provenance block, lot comparison verdict,
  fair-price band calculator, sampling sufficiency meter), Capture & Vision Robustness
  (frame quality gate, perceptual-hash dedup, detection proof gallery, CLIP second-opinion),
  Vernacular & Accessibility (Hindi TTS, bilingual toggle, self-hosted CDN assets), Dashboard
  & Pitch Visuals.
- **Research recommendations**: mapped the three Roboflow onion datasets known at the time
  onto the locked 6-class schema; recommended YOLO-World for bootstrap auto-labeling instead
  of hand-drawing boxes; library picks (qrcode, pynacl, reportlab, edge-tts, open_clip).
- **Full 8-minute live demo script**: hook → calibration → live sampling with an
  interactive jury-plants-a-rotten-onion beat → live wifi-kill/offline-replay demo → live
  tamper attack on the hash chain → arbitration verdict + price band → close, plus a
  failure playbook and pre-assigned Q&A answers.

## 4. Real-repo audit (this is where the session got grounded in actual code)

Explored `d:\Marcben\sama-onion` directly instead of continuing to plan in the abstract.
Findings:

- The project is **not** a blank slate — 43 pytest tests, gates T0–T12 mostly passing,
  `weights/best.pt` already trained (on synthetic data), 6 cached offline-replay payloads,
  a working hash chain, dashboard, and certificate flow already built.
- **`STATUS.md` and `README.md`** were explicit: every number so far is measured on
  *synthetic* procedurally-generated trays, not real onions. Two gates are explicitly
  undone: **T1** (print + caliper the calibration mat) and **T8** (full flow on a real
  phone over the cloudflared tunnel) — flagged as the actual demo-killers, not missing
  features.
- Confirmed `app/main.py` and `app/db.py` already implement the hash chain and dispute
  stub that ox-alpha's feature list assumed didn't exist — reconciled ox-alpha's wishlist
  against what's real so nothing gets rebuilt twice.
- Ran the verification commands live rather than trusting the docs: `check_env.py` → ALL
  CHECKS PASSED, `pytest tests/ -q` → 43 passed, started `uvicorn`, confirmed
  `/api/health`, `/`, `/dashboard`, `/api/replay/0`, `/api/drift` all responded correctly.

**Agreed plan** (user picked "2–3+ days left" and "real data first"):
- **Phase 1** (physical, not code): print/caliper the mat, source real onions across all 6
  classes, `git init`, shoot real trays, `dataset_qa.py` → `train.py` → `calibrate_size.py`
  → `measure_occlusion.py` → `eval_lot.py` → `build_replay.py`, then Gate T8 on a real phone.
- **Phase 2** (code, buildable in parallel, doesn't touch frozen `grading.py`): new
  `app/arbitration.py` module for lot-comparison/price-band/sample-size math (with its own
  tests), new `/verify/{lot_id}` route + QR on the certificate, self-hosted CDN assets.

## 5. Real-world viability — honest assessment given

Asked directly whether SAMA would work in the real world. Answer given: the core method
(statistical lot sampling, honest Wilson-interval confidence bands, a calibration ladder
that withholds rather than guesses, tamper-*evident* not tamper-*proof* hash chain) is
methodologically sound, not hackathon theater. Real gaps flagged: domain shift across
regions/varieties/seasons, the internal-defect blind spot no camera can see, protocol-gaming
risk (an operator can bias which bulbs get photographed), mat logistics at national scale,
Ultralytics' AGPL-3.0 licence blocking a closed public deployment as-is, and the total
absence of regulatory recognition needed before a certificate can actually settle a dispute.
Verdict: a strong pilot prototype, not yet a deployable national system — which is the
correct scope for a hackathon.

## 6. Public dataset research and ingestion

- User pasted a 6-item list of "Roboflow datasets I saw" (likely LLM-assembled, not
  independently verified). Cross-checked every entry against the live Roboflow API using a
  provided key rather than trusting it at face value.
- **Corrections found**: two pasted URLs (`onion-detection-system/onion-disease-rdezg` and
  `anas-kadiri-ffnxr/onion-disease`) turned out to be the same underlying data (a fork),
  not two independent 53-image sets. `onions/onions-shlrv` was real but labeled
  `ready`/`not_ready` (harvest maturity), not defect grading — wrong task. Two entries were
  given only as generic search-query URLs, not verifiable direct project links.
  `imagelabelling/onion-sorting-cghvq` turned out to be **1,616 images**, not the
  183 either party had assumed.
- Added two verified, valuable new sources to `scripts/fetch_public_data.py`:
  - **`onion-spoilage`** (onionspoilagedetection, CC BY 4.0) — classes `healthy`, `mold`,
    `rotten`, `sprouted`. `mold` mapped to `black_smut` (fungal-family match, documented as
    an assumption, not a certainty).
  - **`onion-sorting`** (imagelabelling, CC BY 4.0) — 1,616 images, `Good Onion` /
    `Rotten Onion` / generic `onion`.
- Installed `roboflow` SDK with `--no-deps` deliberately — the package hard-depends on
  `opencv-python-headless`, which would have collided with the project's required
  `opencv-contrib-python` (needed for `cv2.aruco`) and silently broken Gate T0. Verified
  `check_env.py` still passed after install.

### Bug found and fixed in `scripts/fetch_public_data.py`

1. `remap()`'s class-name parser only handled one Roboflow YAML export style (inline
   `names: [...]` or old numbered-dict). This dataset used a plain YAML block list
   (`names:\n- healthy\n...`), which matched neither regex path and silently returned zero
   classes.
2. **That bug had a destructive side effect**: with zero classes recognized, every label
   line fell through to "dropped," and the old code overwrote each label file in place with
   empty content — no backup existed. The first `--remap` run silently wiped all 772
   downloaded label files down to 2 bytes each.
3. Caught it because the reported "0 boxes changed" looked wrong, re-downloaded the dataset
   clean, and fixed three things before re-running:
   - Parser now uses `yaml.safe_load` (handles any real YAML shape) instead of regex.
   - Refuses to touch any labels at all if zero source classes are found, instead of
     silently writing empty files.
   - Writes remapped labels to a new `labels_sama6/` folder next to each split's
     `images/`, leaving the original `labels/` untouched — a future bug can no longer
     destroy source data.
4. Also discovered mid-fix that labels were a **mix of plain bounding boxes and polygon
   annotations** (Roboflow allows both in one project). Added `to_yolo_bbox()` — a pure
   function that passes plain boxes through and collapses polygons to their tightest
   enclosing box (a deterministic min/max, not a guess) — since detection training and
   `measure_bbox_mm` both need boxes, not masks.
5. Added `tests/test_fetch_public_data.py` (3 new tests: bbox passthrough, centered
   polygon, off-center polygon) per the project's own rule to test anything with
   arithmetic in it.

**Final verification, all green:**
```powershell
python -m pytest tests/ -q          # 46 passed (was 43)
python scripts/check_env.py         # ALL CHECKS PASSED
python scripts/fetch_public_data.py --list
```

Confirmed both datasets downloaded, remapped, and 1:1 image/label counts:
- `data/public/onion-spoilage/` — 772 images, 772 remapped labels
- `data/public/onion-sorting/` — 1,616 images, 1,616 remapped labels

Neither is merged into `data/dataset/` yet — deliberately held so it happens together with
real photo ingestion via `dataset_qa.py`, per the project's own "pad rare classes only,
never quote a metric measured on them" rule.

## Files changed this session

- `scripts/fetch_public_data.py` — added `onion-spoilage` and `onion-sorting` sources,
  updated stale `kadiri-onion-disease` count (53→125), added `mold`→`black_smut` remap,
  fixed the YAML-parsing bug, made `remap()` non-destructive, added `to_yolo_bbox()`.
- `tests/test_fetch_public_data.py` — new, 3 tests for the bbox/polygon conversion.
- `data/public/onion-spoilage/`, `data/public/onion-sorting/` — new, downloaded + remapped
  public datasets (not yet merged into training data).

## Still open / not done in this session

- Phase 1 (real onions, printed+calibered mat, real-phone Gate T8) — physical work, not
  something this session could do.
- Phase 2 code (verify page + QR, `arbitration.py` comparison/price module, Hindi audio,
  self-hosted CDN assets) — planned, not yet built.
- `git init` was flagged as still the user's call per `STATUS.md`; not done this session.
- Rotating the Roboflow API key used this session, if desired — it's now in this
  terminal's shell history.

---

## Frontier-tech pass (LOOP-T2214) — digital twin adopted

Implemented menu item 1 from the frontier-tech roadmap: a **digital twin** of a
graded lot (`app/twin.py` + `/api/twin/{lot_id}` + dashboard panel). The twin
replays a certified lot's recorded bulb observations forward under a seeded
quality-drift scenario and reports what happens to saleable Grade A %, defect
rate and farmer payout, using the SAME pricing code as the certificate
(`arbitration.fair_price_band`, cull model). Deterministic per lot via SHA-256
seed derivation; measured vs simulated labels on every response block; two data
paths (per-bulb exact / aggregate fallback with documented independence
assumption). Rationale + limitations in `.agent/FRONTIER_TECH.md`.

Verification: `py -3.11 -m pytest tests -q` → 190 passed (17 new in
`tests/test_twin.py`); `python scripts/smoke_test.py` → ALL PASS including 5 new
twin checks; live `GET /api/twin/45?severity=0.2` returns deterministic labelled
JSON. Live uvicorn on :8000 restarted onto current code.

---

## India-access pass (LOOP-A2223) — deadlines, one retry, save-and-retry on every request

Picked the highest-value open item from the five-candidate list: **network
timeout + retry-once + "save and retry" on every fetch** (the other four were
already covered by earlier passes: client-side downscale ≤1600px/q80 with honest
KB line — A2212; Tailwind vendored to `static/vendor/tailwind.js` so the offline
demo loads zero CDN bytes; i18n largely complete; IMPACT_EVIDENCE.md carries the
per-lot cost story).

What changed (`app/static/index.html` only):

- `saFetch(url, opts, timeoutMs)`: AbortController deadline (15 s JSON,
  60 s photo/finalize uploads), retries EXACTLY once after a 1.5 s backoff and
  ONLY when the server never answered (radio drop / stalled DNS / our deadline).
  A real HTTP answer — even a 500 — is final and never repeated. Failures throw
  typed `NetError{timeout|unreachable}` so callers can print WHY in Hindi or
  English. Engines without AbortController lose only the deadline, not the request.
- All seven call sites routed through it: `/api/centres`, `/api/replay/N`,
  `/analyze`, `/finalize`, `/api/sufficiency`, `/api/price-band`, `/dispute`.
- Retry safety proven endpoint-by-endpoint before wiring: /analyze writes no DB
  rows; /finalize is server-deduped (`dedupe=True`, built for exactly this);
  /dispute is a boolean UPDATE. Nothing can double-apply.
- Save-and-retry bar: if /analyze fails even after the automatic retry, the
  compressed photo AND its exact prepared FormData wait in memory; a red bar
  offers "↻ Retry upload" (≥48 px touch target, bilingual) which re-sends
  byte-for-byte without re-photographing, and "Discard" which says plainly that
  nothing was analysed. The officer never re-shoots a good tray over a network
  hiccup.
- submit()'s success tail extracted into acceptLook(), shared by capture and
  resend so both paths stay identical (scale-rung banners, quality advisories,
  lookIndex advance, tally, LOOP-I2222 checkpoint).

Verification: `py -3.11 -m pytest tests -q` → 332 passed (40 new in
`tests/test_network_resilience.py`; test_session_resume's checkpoint-ordering
contract strengthened to cover the shared success path). Inline script passes
`node --check`. Live uvicorn over plain HTTP: `/`, `/static/index.html`,
`/api/replay/0`, `/api/centres` all 200; real multipart POST of a 1.25 MB
1600px JPEG → `/analyze` 200 in 1.3 s against the 60 s deadline (~10x headroom
at rural-3G uplink speeds).
