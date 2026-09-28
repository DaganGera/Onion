# How SAMA works, explained from scratch

Read this once and you'll be able to answer almost any judge's question. Each section starts with the one-line answer, then the detail.

## The big idea

SAMA separates two jobs that grading by eye mixes together:

1. **Measuring** (probabilistic): how big is this onion, and how much of its surface is black, rotten or sunburnt? Cameras and models do this, with some error.
2. **Deciding** (deterministic): given those measurements, is it Grade A, URS or Reject? A published rulebook decides, the same way every time.

Because the decision is a pure function of the stored measurements plus the rule pack, anyone can recompute it. That is what makes the receipt checkable.

## 1. Capture guard: "only good photos get in"

**One line:** before taking the photo, the app checks the live camera and refuses bad shots with one plain sentence.

It checks that:
- the phone is level;
- the image is sharp, not blurred;
- there is no glare and the exposure is right;
- the scale reference (mat, A4 sheet or coin) is fully in view;
- there are enough onions.

When every check passes, the shutter fires by itself. Tapping three times forces a capture, and the receipt records that it was forced.

**Why:** bad evidence produces bad grades. Refusing it at the door is cheaper than arguing later.

## 2. Calibration: turning pixels into millimetres

**One line:** something of known size in the photo tells the app how many millimetres one pixel is.

There are four levels, from most to least precise:

| Scale source | How it works | Precision the app assumes |
|---|---|---|
| Printed mat | ArUco markers (like mini QR codes) at known positions; also corrects for tilt | about 0.6% |
| A4 sheet | The sheet is 210 × 297 mm; its corners give the scale | about 1.5% |
| Coin | Tap the ₹5 coin; its diameter is known | about 3% |
| Camera only | Uses the phone's lens properties and an assumed height | about 25%, so borderline onions go to a human |

The receipt prints which method was used. The app also corrects for the fact that an onion's widest point sits about one radius above the table, not on it.

## 3. Finding each onion (the Tier-2 model)

**One line:** a neural network colours every pixel as background, onion inside or onion edge, and the app separates touching onions using those edges.

- The model is a U-Net, a standard network for pixel-level outlines, with a small, phone-friendly MobileNetV3 encoder. It is 16 MB.
- Teaching it to output "edge" as a separate class is the trick for heaps: the thin edge band between two touching onions keeps them apart.
- Each onion's inside becomes a seed, and the onion's pixels grow out from their nearest seed.
- It was trained on real market photos, whose outlines were proposed by two large open models (OWLv2 and SAM) offline. Those big models are not in the app; only the small trained model ships.

**Result:** on 18 held-out photos, the average count error is 0.56 onions. The earlier colour-only method was off by about 11.

## 4. Measuring size, weight and shape

- **Size:** the widest and narrowest diameters (Feret diameters) of the onion's body, in mm. The neck and roots are trimmed off first, so a long dry neck doesn't inflate the size.
- **Weight:** estimated from size, treating the onion as a sphere with density 0.95 g/cm³. This is an assumption until someone weighs real onions on a kitchen scale and fits the formula.
- **Shape flags:** double bulbs, split bulbs and thick necks ("bottleneck"), from how convex and how elongated the body is.

## 5. Measuring defects

**One line:** each onion's own healthy skin colour is the baseline, and defects are the patches that differ from it.

- Colours are compared in Lab colour space, which separates lightness from colour, so shadows matter less.
- Blackening, rot, spots, sunburn, sprouting, peeled skin and cuts are each measured as a **percentage of the visible surface**, corrected for the curve of the bulb.
- This matters because the norms speak in exactly those terms (for example "blackening up to 30%").

## 6. The learned health check (the Tier-1 model)

**One line:** a second small network looks at each onion crop and says how likely it is to be unhealthy. It never changes a measurement; it only double-checks.

- The model is MobileNetV3-Small, run on a 128 px crop of each onion.
- If it is confident an onion is **healthy**, it clears colour marks that were probably light reflections or natural skin streaks. This cut healthy onions wrongly failing Grade A from 91.9% to 10.1%.
- If it is confident an onion is **unhealthy** but no rot was measured, the onion goes to a human.
- It scores AUC 0.98 and 92.5% accuracy on 2,234 held-out onion crops.

## 7. Rule packs: the rulebook as data

**One line:** a rule pack is a small, versioned file listing the size window and defect limits for each grade. SAMA grades by whichever pack is selected.

- Five packs are included, covering the 2026 norm changes (15 May, 4 June, 30 July). The default is the 30 July pack: only Grade A (45–65 mm) is procured, and URS is measured but not bought.
- Each pack is hashed, and the hash is printed on the receipt, so nobody can quietly change the rules after the fact.
- **The borderline rule:** if an onion is within measuring error of a limit (for example 64.5 mm against a 65 mm limit), it goes to "needs human check" instead of being decided by chance.
- The outputs are Grade A, URS, Reject or needs human check, each with a reason code such as `BLACKENING_34PCT_GT_30PCT`.

## 8. Lot statistics: from a sample to the whole lot

**One line:** SAMA photographs a sample, so it reports the lot's grade shares with a 95% interval, by weight.

- **Fair sample:** the farmer's code and the officer's code are combined to pick which sacks and which layer to open, so neither side chooses. Anyone can recompute the draw.
- **Intervals:** onions in the same tray are similar, so the uncertainty is computed tray by tray (a bootstrap over trays), not by pretending every onion is independent.
- **When to stop sampling:** a sequential test (SPRT) tells the officer after each tray: accept, reject, sample one more tray, or refer to a human.
- **Two looks:** after "shake, look again", the second photo shows other faces of the same onions. It adds defect evidence without double-counting onions.

## 9. The receipt: why it can be trusted

**One line:** the result is written in a fixed format, fingerprinted, signed by the phone's own key, and packed into a QR code that any phone can check offline.

1. The lot's measurements and verdict are written as **canonical JSON** (RFC 8785), so the same data always gives the same bytes.
2. **SHA-256** makes a fingerprint (hash). Change any character and the hash changes completely.
3. The phone **signs** the hash with a key that never leaves the device (WebCrypto ECDSA P-256; Ed25519 where the phone supports it).
4. The payload is squeezed into a **QR code** (base45 encoding).
5. **Verification on another phone:** it checks the signature, recomputes the hash and **re-runs the grading** from the stored measurements under the same rule pack. If everything matches: "Receipt checks out".
6. Each receipt includes the previous receipt's hash, forming a **hash chain** per centre, plus an append-only **Merkle log** (the same idea as Certificate Transparency, RFC 6962). Deleting or editing an old receipt breaks the chain.

**Say it carefully:** it is *tamper-evident*, not tamper-proof. It shows that something changed; it can't prove the onions in the photo came from the sacks that were sold.

## 10. Why offline, and how

- The Android app bundles the whole web app and all models. ONNX Runtime Web runs the models inside the phone's WebView, using WebAssembly.
- Lots and receipts are stored on the phone in IndexedDB.
- The web app caches itself with a service worker, so it also works offline after the first load.

## 11. Quick glossary

| Term | Meaning |
|---|---|
| PSF | Price Stabilisation Fund; the government buys onions into a buffer stock to release when prices rise |
| NAFED / NCCF | The central cooperative agencies that procure for the buffer |
| URS | The press describes it as a relaxed-specification category (smaller or slightly blemished onions). Its full form is unconfirmed |
| ONNX | A standard file format for trained models, so one model runs anywhere |
| U-Net | A neural network that labels every pixel of an image |
| MobileNetV3 | A small, fast image network designed for phones |
| AUC | How well a model ranks unhealthy above healthy: 1.0 is perfect, 0.5 is guessing |
| Held-out (holdout) | Photos never used in training, kept only for testing |
| Feret diameter | The width of a shape measured like a caliper, at a given angle |
| SPRT | Sequential probability ratio test: decides after each sample whether you have seen enough |

## 12. Likely judge questions

| Question | Answer |
|---|---|
| "How accurate is it?" | Counting: 0.56 onions average error on held-out photos. Health check: AUC 0.98 on 2,234 held-out crops. Size against calipers is the next field study; we started it at a local shop. |
| "What if the officer disagrees with the AI?" | They override with a reason. The AI's verdict stays on record next to theirs, and both are signed into a new revision. |
| "Does it need internet?" | No. Everything runs on the phone. We demoed it in airplane mode. |
| "What if the norms change?" | Select a new rule pack. Old receipts still verify under the pack they were issued with. |
| "Can the officer fake a receipt?" | They can't alter one without breaking the signature and the chain. They could photograph different onions; that's why the sack draw and the timestamped, located photos exist. |
| "Why not YOLO?" | Boxes can't measure "34% of the surface is black". The norms are surface percentages and millimetres, so we measure pixel outlines. |
| "Where is your data from?" | A public dataset of real onion photos from Pune markets (Zenodo, CC BY 4.0). No synthetic images are used for any reported number. |
| "What is URS?" | The press describes it as the relaxed-specification category. We found no official definition, so it lives in the rule pack as a configurable bucket and the receipt says so. |
