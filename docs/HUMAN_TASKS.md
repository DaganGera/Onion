# Human tasks

Things only a person with onions, a phone and friends can do. Nothing in the software waits for them: until each is done, the app runs on the stand-ins listed in docs/SOURCES.md and says so. Each task says what to send back and where to put it. Templates are in `docs/field-kit/`.

Put every returned file under `field/` at the repo root (create it). Photos go in `field/photos/<date>_<place>_<phone>/`. Keep the original files; do not edit or crop.

## T1. Print and check the calibration mat (20 min)

1. Open `apps/web/public/calibration_mat.pdf`. Print on A4 at 100% ("actual size"; turn off "fit to page").
2. Measure the black square of marker 0 with a caliper or steel ruler. It must be 40.0 mm on both sides. Measure the distance between the left edges of markers 0 and 2: it must be 233.0 mm.
3. If either is off by more than 0.5 mm, reprint with scaling fixed. Glue the mat onto card so it stays flat.
4. Send back: a photo of the caliper on the marker, and the two numbers, in `field/mat_check.txt`.

## T2. Buy onions and ask for the cull pile (1 hour)

1. Buy about 10 kg across two or three varieties you can find (for example Nashik red, a pink or Bellary type, and white).
2. Ask vendors for their reject pile: rotten, sprouted, split, sunburnt, peeled. They usually give it free. This is what graders actually see and it is the only way to get real defects.
3. Keep good and bad bulbs apart for now. Number every bulb with a marker pen on the neck (1, 2, 3...). The numbers let us match photos, caliper readings and human grades.
4. Send back: `field/inventory.csv` using `docs/field-kit/inventory.csv` (bulb number, variety, source, your first impression).

## T3. Photograph (3 to 4 hours over two days)

Follow `docs/field-kit/shot_list.md`. It asks for about 350 photos across light, backgrounds, arrangements and two or three phones. The second day, second place and (if you can borrow one) a different phone make the holdout set. Never mix holdout photos into training folders.

Use the app itself for most photos (it stores them with their measurements), then export each lot's evidence file from the receipt screen. For the rest, use the phone camera normally.

Send back: the photo folders, and every exported `*.parakh.json`.

## T4. Caliper and weigh 60 bulbs (1.5 hours)

1. For 60 numbered bulbs (mix of sizes and varieties), measure the widest diameter across the equator, then the smallest diameter across the equator (turn the bulb). Measure in mm with a caliper.
2. If you can borrow ring gauges (45, 55, 65 mm), record which rings each bulb passes.
3. Weigh each bulb on a kitchen scale in grams.
4. Photograph the same bulbs on the mat with the app, 6 to 8 per photo, laid out in bulb-number order: left to right, then the next row. Name the lot "E1". Export the evidence file; in `size_truth.csv`, `photo_file` is the capture id shown in the evidence file (for example `LSG-01-20261001-AB12-t1-l1-...`).
5. Send back: `field/size_truth.csv` from `docs/field-kit/size_truth.csv`. This feeds E1 (size accuracy) and replaces the assumed weight model.

## T5. Hand-sort 10 lots (2 hours)

1. Make 10 lots of 40 to 60 numbered bulbs each, mixing good and cull bulbs in different proportions (for example 90/10, 70/30, 50/50).
2. Sort each lot by hand into Grade A, URS and Reject following `docs/field-kit/grading_rules_card.md` (the same limits as the default rule pack). Weigh each group.
3. Put each lot back together, then grade it with the app: two or three trays, two looks per tray.
4. Send back: `field/lot_truth.csv` from `docs/field-kit/lot_truth.csv` and each lot's evidence file. This is E4: does the app's 95% interval contain the truth about 95% of the time?

## T6. Blind grading by three people (30 min each)

1. Recruit three friends or family members. Nobody sees the others' answers or the app.
2. Lay out 60 numbered bulbs. Give each person `docs/field-kit/grading_rules_card.md` and a copy of `docs/field-kit/e3_blind_grading.csv`.
3. Each person writes A, URS, R or ? for every bulb. No talking.
4. Photograph the same 60 bulbs with the app in a lot named "E3", in bulb-number order (left to right, row by row), 6 to 8 per photo, one look each.
5. Send back: the three filled CSVs as `field/e3_rater1.csv` etc. This is E3: how much do humans disagree, and does the app agree with the majority at least as well as a typical person?

## T7. Repeatability runs (1.5 hours)

For one lot of about 50 bulbs: capture it 5 times (re-spread the bulbs each time) with each of 3 phones under 3 kinds of light (shade outdoors, direct sun, indoor tube light). That is 45 lots in the app. Name the farmer field "E2 <phone> <light> <n>". Export all evidence files. This is E2 (Gauge R&R).

## T8. Check auto-labels for Tier 1 (2 hours, after T3)

When `scripts/train_tier1.py` has run on your photos it writes per-bulb crops with proposed labels to `field/tier1_review/`. Open them in AnyLabeling or Label Studio (both free), fix wrong labels, and save. Only then retrain.

## T9. Test on the cheapest phone you can borrow (30 min)

1. Install the APK (`apps/web/android/app/build/outputs/apk/debug/app-debug.apk`) or open the deployed web app and "Add to home screen".
2. Turn on airplane mode. Open the app, run the demo lot, grade one real tray, sign, and verify the QR from a second phone.
3. Note the phone model, the capture-to-verdict time shown after each photo, and anything that broke.
4. Send back: `field/device_test.md`.

## Before the demo

- Proofread your language files in `apps/web/src/locales/` (Hindi, Marathi, Tamil at least).
- Re-run `npm run eval` so every number in the docs comes from your field data, then rebuild the pitch numbers slide from `docs/EVALUATION.md`.
