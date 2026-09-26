# SAMA workflow

## 1. At the procurement centre (field workflow)

```
 Farmer arrives with N sacks
          │
          ▼
 ┌────────────────────┐   Farmer's code + officer's code → which sacks and which layer to open.
 │ 1. New lot + draw  │   Neither side chooses; anyone can recompute the draw later.
 └────────┬───────────┘
          ▼
 ┌────────────────────┐   Tray of onions on the printed mat (or an A4 sheet, or a ₹5 coin).
 │ 2. Capture         │   The capture guard checks level, blur, glare, exposure and scale in view,
 └────────┬───────────┘   then the auto-shutter fires. Shake, look again: a second view of the same tray.
          ▼
 ┌────────────────────┐   On the phone: find every onion → size in mm → estimated weight
 │ 3. Measure         │   → share of surface with blackening, rot, spots, sunburn, sprouting, peel, cuts
 └────────┬───────────┘   → the learned health check clears false colour marks on healthy bulbs.
          ▼
 ┌────────────────────┐   The rule pack maps each onion to Grade A / URS / Reject / needs human check,
 │ 4. Grade           │   with a reason code. The lot result is by weight, with a 95% interval,
 └────────┬───────────┘   plus advice: accept, reject, or sample one more tray.
          ▼
 ┌────────────────────┐   The officer can override (with a reason); the farmer can contest.
 │ 5. Review          │   The AI verdict is never erased; each change becomes a new signed revision.
 └────────┬───────────┘
          ▼
 ┌────────────────────┐   Canonical JSON → SHA-256 hash → signed with the device key → QR code.
 │ 6. Receipt         │   Added to the centre's hash chain. Printed on A4 or shared on WhatsApp.
 └────────┬───────────┘
          ▼
 ┌────────────────────┐   The farmer, a buyer or an auditor scans the QR on any phone, offline:
 │ 7. Verify          │   checks the signature and re-runs the grading. "Receipt checks out".
 └────────┬───────────┘
          ▼
 ┌────────────────────┐   Across centres: override rates, drift in measurements, disagreement
 │ 8. Fleet view      │   between officers and the AI. Spots a centre that grades differently.
 └────────────────────┘
```

## 2. Where each piece lives

| Step | Code |
|---|---|
| App screens (Home, New lot, Capture, Result, Receipt, Verify, Packs, Fleet) | `apps/web/src/screens` |
| Capture guard, calibration, measurement | `packages/vision` |
| Onion finder (Tier 2) and health check (Tier 1) running on the phone | `apps/web/src/workers`, models in `apps/web/public/models` |
| Rule packs, grading, lot statistics, signing, QR payload, hash chain | `packages/core` (pure TypeScript, unit tested) |
| Android app | `apps/web/android` (Capacitor wrapper around the same web app) |
| Landing page and in-browser demo | `apps/landing` |

## 3. How the models were built (development workflow)

```
 Public real photos (Zenodo, CC BY 4.0, 12,260 onion photos from Pune markets)
          │
          ├─► Split by image blocks: 60% train, 20% tune, 20% held out (never used for training)
          │
          ├─► Onion finder (Tier 2)
          │     OWLv2 ("onion") + SAM propose outlines offline → 828 labelled training photos
          │     → U-Net (MobileNetV3-Large encoder) trained on 3 classes: background, interior, edge
          │     → exported to ONNX (16 MB) → runs in the app
          │
          ├─► Health check (Tier 1)
          │     Bulb crops from single-onion photos → MobileNetV3-Small, healthy vs unhealthy
          │     → threshold chosen on the tune split → ONNX → runs in the app
          │
          └─► Evaluation scripts run on the held-out photos → reports/*.json → docs/EVALUATION.md
                (no number is typed by hand)
```

The in-app corrections an officer makes can be exported and fed back into training (`scripts/retrain.sh`), so the models improve with field use.

## 4. Future workflow with sorting (see file 07)

```
 Grade per onion ──► position of each onion in the photo ──► sorting action
                                                         ├─ manual: highlight rejects on screen, a worker picks them
                                                         └─ automatic: camera over a conveyor → air jet or flap per lane
```
