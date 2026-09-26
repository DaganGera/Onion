# Model accuracy and datasets

Every number here was printed by an evaluation script into `reports/*.json`; none was typed by hand. The raw JSON files and the full evaluation page are in the `evidence/` folder next to this file.

## Dataset

| | |
|---|---|
| **Name** | Image Dataset of Red and White Onion Bulbs and Leaves |
| **Where** | Zenodo, DOI [10.5281/zenodo.20254934](https://doi.org/10.5281/zenodo.20254934) |
| **Licence** | CC BY 4.0 (free to use with credit) |
| **What it is** | Real photos of onions from markets in Pune, taken with one phone (Motorola Edge 50 Ultra), 1024×768 px |
| **Onion bulb photos used** | **12,260** |

The bulb photos break down as follows:

| Folder | Single onion | Several onions | Total |
|---|---|---|---|
| Healthy, red | 3,000 | 1,110 | 4,110 |
| Healthy, white | 3,000 | 1,110 | 4,110 |
| Unhealthy, red | 1,010 | 1,010 | 2,020 |
| Unhealthy, white | 1,010 | 1,010 | 2,020 |

**How it was split:** photos are grouped into blocks of 25 consecutive IDs, so near-identical shots stay together. Of every 5 blocks, 3 train the models, 1 tunes the thresholds, and 1 is **held out**: never seen in training and used only for the numbers below.

**No synthetic images** are used for any reported number. Training for the onion finder did paste real onion cut-outs onto real backgrounds, to teach it that the printed mat isn't an onion. That augmentation is used for training only.

**Labels:**
- Health check: the dataset authors' healthy/unhealthy folders.
- Onion outlines for training: proposed offline by OWLv2 and SAM, two large open models (Apache-2.0). Neither ships in the app.
- Onion counts for testing: counted by eye on 18 held-out photos.

## The models in the app

| Model | Job | Architecture | Size | Trained on |
|---|---|---|---|---|
| Tier 2: onion finder | Outline every onion, separate touching ones | U-Net, MobileNetV3-Large encoder, 3 classes (background, interior, edge), 512 px input | 16 MB (ONNX, full precision) | 828 training photos with teacher outlines |
| Tier 1: health check | Healthy vs unhealthy, per onion | MobileNetV3-Small, 128 px crop | small (ONNX) | 4,171 single-onion crops |
| Tier 0: colour measurer | Defect area fractions (blackening, rot, spots, sunburn, and so on) and the fallback onion finder | Rules in Lab colour space, no training | none | thresholds tuned on the tune split |

## Accuracy on held-out photos

### Finding and counting onions (18 held-out photos, counted by eye)

| Detector | Average count error | Exactly right | Within ±1 onion |
|---|---|---|---|
| **Tier 2 (the shipped model)** | **0.56 onions** | **61%** | **89%** |
| Tier 0 colour rules (old method) | 10.89 onions | 6% | 17% |

On the team's own photo taken on a wooden table with the printed mat, Tier 2 found exactly the 6 onions present and ignored the mat, the table, a cable and a bag.

### Health check (Tier 1)

| Held-out set | Crops | AUC | Sensitivity | Specificity | Accuracy |
|---|---|---|---|---|---|
| **All** | **2,234** | **0.98** | **91.8%** | **92.8%** | **92.5%** |
| Red onions | 1,218 | 0.998 | 99.0% | 96.3% | 97.2% |
| White onions | 1,016 | 0.946 | 84.6% | 88.2% | 86.8% |
| Photos with several onions (harder) | 846 | 0.953 | 94.0% | 77.2% | 85.1% |

On the same 306 held-out photos, Tier 1 scored AUC 0.975 (90.8% accuracy) against Tier 0's AUC 0.756 (68.3%). That comparison is why Tier 1 ships.

### Full pipeline: defects on held-out photos

| | Colour rules alone | With the learned health check |
|---|---|---|
| Unhealthy photos where rot or mould was found | 85.0% | 85.0% |
| Healthy photos wrongly flagged for rot or mould | 68.3% | **13.3%** |
| Healthy onions wrongly failing a Grade A defect limit | 91.9% | **10.1%** |

### Software checks

17 of 17 automated end-to-end checks pass in a real browser. They cover:
- grading a lot;
- the receipt QR;
- offline verification on a second device;
- rejecting a tampered code;
- offline load;
- Hindi.

The Android APK was tested in an emulator: a 4-photo lot graded in 7.1 s and the receipt verified offline.

## What is NOT measured yet (be upfront about this)

| Study | What it would prove | Status |
|---|---|---|
| E1 size vs calipers | Millimetre accuracy | Needs about 30 onions measured with a caliper. **Start this at the shop** |
| E2 repeatability | Same lot, different phone and light, same grade? | Needs 6 re-photographed lots |
| E3 human baseline | How much do 3 human graders disagree, compared with SAMA? | Needs 3 people to grade the same lot |
| E4 lot truth | Does the lot percentage match a hand-sorted and weighed lot? | Needs a hand-sorted lot and a scale |
| E6 real-phone speed | Seconds per photo on a mid-range phone | The app shows the time after every photo; just note it down |

**Caveats on the numbers above:**
- The data comes from one phone and one city; field photos will differ.
- The labels are "healthy/unhealthy", not procurement grades.
- Single-onion photos repeat the same onions, which likely inflates those scores. The several-onion photos are the harder, more honest test.
