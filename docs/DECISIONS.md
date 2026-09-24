# Decisions made during the autonomous build

The team asked for no questions during the 8-hour run, so each judgement call is logged here with its reason. Any of them can be reversed.

1. **Name: Parakh.** परख means assay or appraisal in Hindi and Marathi and is understood across north India. It says what the app does (test the quality of a lot) better than SAMA, which had no stated meaning. The old name survives in `legacy/`.
2. **Default rule pack: 30 Jul 2026, Grade A only.** It is the latest rule reported (S4). The June packs stay available for time travel, which is also the best demo of why packs exist.
3. **URS wording.** Defined as "bulbs that miss this pack's Grade A limits but stay within the relaxed limits", with the press phrase "relaxed-specification" quoted and the expansion marked unverified. We did not expand the acronym.
4. **Server: none in this build.** The brief allows FastAPI but everything the demo needs (signing, log, verification, fleet view) runs on the phone. A server adds a deployment and a failure mode for no demo value. The Merkle log exports to a JSON file that a centre can publish anywhere static.
5. **Evaluation scripts in TypeScript, not Python.** The brief says eval scripts stay in Python. Numbers about grading must come from the same code that ships, and that code is TypeScript. Training (Tier 1) stays in Python.
6. **Replay mode shows no "look again".** The public photos are different scenes, not the same tray shaken. Offering a second look in replay would fake the two-look protocol.
7. **Replay photos use the camera-only size tier at an assumed 260 mm height (A-REPLAY-1).** The photos have no calibration sheet. The receipt prints the tier and the wide uncertainty, and most size-borderline bulbs go to a human. We did not invent a scale.
8. **Design: "instrument and receipt".** Warm paper, near-black ink, one violet accent that echoes the ink of a government rubber stamp, IBM Plex Sans / Condensed / Mono, bucket colours always paired with a letter (A, U, R, ?) so colour-blind users and black-and-white printouts still work. Light theme only, for sunlight; the camera screen is dark.
9. **Nine languages.** English plus Hindi, Marathi, Tamil, Telugu, Kannada, Gujarati, Bengali and Punjabi. All non-English strings are machine drafts (OPEN_QUESTIONS 11).
10. **QR payload: base45 over deflated binary, the EU Digital COVID Certificate approach.** It fits the QR alphanumeric mode. A lot of about 60-80 bulb-observations fits one QR code; bigger lots fall back to the evidence file.
11. **Tier-1 model: a bulb-crop classifier, not a segmentation student.** Without field photos and without a person to correct teacher masks, a segmentation student would learn Tier-0's own mistakes. The public dataset has exact per-bulb labels only for its single-bulb photos, so a small classifier trained on those is the one learned model we can evaluate honestly. See docs/MODEL_CARD_tier1.md for whether it ships.
12. **Coarse location.** Rounded to two decimals of latitude and longitude (about 1 km) and only when the browser grants permission.
