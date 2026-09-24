# Limitations

This list is what a judge, an officer or a farmer should know before trusting a Parakh receipt.

## Measurement

- The camera sees one face of each bulb. Rot on the underside is invisible until the tray is shaken and photographed again, and even two looks miss some of it. The app never counts a second look as new onions.
- The colour model (Tier 0) was tuned on a single public dataset (one phone, markets in one city). On held-out photos from that dataset it separates healthy from unhealthy photos only moderately well (docs/EVALUATION.md). Nobody has yet compared it with trained graders.
- White onions on a white sheet are hard to separate from the background. Piled onions and patterned or wooden backgrounds cause merged or split bulbs. Use the printed mat or a plain dark cloth and one layer.
- The E5 stability sweep (docs/EVALUATION.md) shows the colour model is most sensitive to warm light, partial occlusion and a tilted phone: a noticeable share of image-level decisions flip. The Capture Guard's level check exists for this reason, and the sweep has to be repeated on field photos.
- The dry root plate and the neck are sometimes scored as sunburn or spots. Glossy highlights on red onions are ignored by a rule that may also hide some real pale patches.
- Cuts and mechanical damage are not measured in this version; receipts say "not assessed" for them.
- "One peeled outer layer allowed" cannot be counted from a photo. Peeled skin is scored as an area share.
- Without a calibration sheet the size comes from an assumed camera height, with a 25% uncertainty. Most size-borderline bulbs then go to a person.
- Weight is estimated from size with an assumed density until a kitchen-scale fit is loaded.

## Rules

- No official 2026 circular was found. All rule packs are built from press reports, two of which disagree on the size window. Grade A defect limits before the relaxation were never published in any source we found; the packs use placeholders marked as assumptions.
- The meaning of URS is unconfirmed.
- Lot acceptance thresholds for the sequential test are placeholders.

## Trust

- The receipt is tamper-evident, not tamper-proof. Changing a signed record is detectable; photographing a different, better tray than the one sold is not. The random sack draw reduces that risk but does not remove it.
- The signing key lives in the phone's browser storage. Clearing site data destroys it. A stolen unlocked phone can sign receipts.
- The transparency log protects history only if someone publishes its exports and others keep old tree heads.

## Software

- Tested in headless Chromium with a real photo as a fake camera. The team has not yet run it on the cheapest target phone; timings on a phone are unknown.
- Non-English strings are machine drafts. Five of the eight Indian languages cover only the main screens.
- The demo photos come from a public dataset and are marked REPLAY on every receipt.
