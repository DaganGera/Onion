# Impact and numbers

Every number below has a source link. **Sourced** figures come straight from the source. Figures marked **estimate** are our own arithmetic on sourced numbers; say "about" or "roughly" when you use them, and show the calculation if asked.

## The scale of the problem

| Figure | Value | Source |
|---|---|---|
| India onion production 2025-26 | **307.37 lakh tonnes** (about 30.7 million tonnes) | [Business Today, 26 Aug 2026](https://www.businesstoday.in/latest/economy/story/govt-starts-buffer-onion-releases-as-festive-demand-nears-551618-2026-08-26) |
| PSF Rabi onion procurement target 2026-27 | **2 lakh tonnes**, via NAFED and NCCF, from 15 May 2026 | Business Today (above); [Indian Express via SuperKalam, 15 May 2026](https://superkalam.com/current-affairs/daily-news-analysis/15-05-2026/centre-to-begin-onion-procurement-today-2-lakh-tonne-target-set-pg5-a26bd968-b987-4a5f-9327-34ccaa0f5a35) |
| Procured by 26 Aug 2026 | **1.21 lakh tonnes** | Business Today (above) |
| Procurement price for Grade A from 30 Jul 2026 | **₹2,335 per quintal** | [Free Press Journal, 3 Aug 2026](https://www.freepressjournal.in/pune/nashik-exporter-alleges-substandard-onions-procured-at-a-grade-prices-seeks-independent-probe-into-nafed-nccf-purchases) |
| Buffer onions moved by rail ("Kanda Express") 2025-26 | 88,000 tonnes in 86 rakes to 16 cities | Business Today (above) |
| Onion post-harvest loss in Maharashtra, whole value chain | **12.59%** of production (9.12% of value); 7.23% at the producer level | [Frontiers in Sustainable Food Systems, 2026 (survey, 2022-23)](https://www.frontiersin.org/journals/sustainable-food-systems/articles/10.3389/fsufs.2026.1773566/full) |
| Vegetable post-harvest losses in India | 4.87% to 11.61% | NABCONS study for MoFPI (2022), as quoted in the same Frontiers paper |

## Evidence that grading is disputed right now (2026)

| What happened | Source |
|---|---|
| A farmer had about **8 of 30 quintals rejected** at a NAFED centre, carried the rejected onions home at his own cost, and grading lasted from morning to evening. Farmers demanded that NAFED make grading criteria "more transparent and farmer-friendly" | [Free Press Journal, 11 Jun 2026](https://www.freepressjournal.in/pune/nashik-farmers-allege-quality-onion-rejections-in-nafed-procurement-demand-transparent-grading-system) |
| After complaints, the norms were relaxed: size window 45–65 mm widened to 35–70 mm, with tolerances for blackening (30%), spots (40%) and sunburn (10%) | [Free Press Journal, 4 Jun 2026](https://www.freepressjournal.in/pune/nashik-nafed-relaxes-onion-procurement-norms-providing-major-relief-to-farmers-hit-by-crop-damage); [ETV Bharat, 7 Jun 2026](https://www.etvbharat.com/en/state/as-centre-eases-onion-procurement-norms-farmers-seek-rs-3000-per-quintal-support-price-enn26060701140) |
| An exporter alleged **substandard onions were bought at A-grade prices** under the URS category and asked for an independent probe | [Free Press Journal, 3 Aug 2026](https://www.freepressjournal.in/pune/nashik-exporter-alleges-substandard-onions-procured-at-a-grade-prices-seeks-independent-probe-into-nafed-nccf-purchases) |

**The point for the pitch:** within three months, the same system was accused of being too strict (farmers) and too lenient (an exporter). Both complaints have the same root cause: no measured, recorded, checkable grade. That is exactly the gap SAMA fills.

## What that means in money (estimates)

| Estimate | Calculation |
|---|---|
| **About ₹467 crore** of onions pass through PSF grading this season at the target | 2 lakh tonnes = 20 lakh quintals × ₹2,335 = ₹467 crore |
| **About ₹4.7 crore** swings for every 1% of the buffer that is misgraded | 1% of ₹467 crore. Every percentage point graded wrongly, in either direction, is money either lost by farmers or overpaid by the government |
| **About ₹19,000** of produce sent back in the reported Chandwad case | About 8.1 quintals × ₹2,335 (at the 30 Jul rate; the rate on the day may have differed) |
| **About 38.7 lakh tonnes** (3.9 million tonnes) of onions lost after harvest nationally each year, if Maharashtra's 12.59% loss rate held nationwide | 307.37 lakh tonnes × 12.59% ≈ 38.7 lakh tonnes. This is a rough extrapolation, not a national study; say so if you use it |

## The benefits SAMA brings, and to whom

| Who | Today | With SAMA |
|---|---|---|
| **Farmer** | Rejected onions with no reason, a day lost, transport back paid by them | A reason for every rejected onion, a receipt they can verify themselves, the right to contest, and the option to grade at home before travelling |
| **Procurement officer** | Grades by eye and absorbs every dispute personally | A measured, rule-based grade to point to, with the officer's own override recorded |
| **NAFED / NCCF / the Department** | Can't compare centres or audit grading after the fact | The same rules at every centre; a fleet view of override rates and drift; an audit trail that can't be quietly edited |
| **Taxpayer** | Pays A-grade prices, possibly for sub-standard onions (as alleged) | Every purchase has a measured grade and a signed record |
| **Consumer** | Buffer release quality is a black box | Released stock carries its grade history |

## Measured about SAMA itself

| Metric | Value | Where it comes from |
|---|---|---|
| Onion count error on held-out photos | 0.56 onions average (61% exact, 89% within ±1, 18 photos) | `reports/count_eval.json` |
| Health check on held-out crops | AUC 0.98, accuracy 92.5%, 2,234 crops | `reports/zenodo_tier1.json` |
| Healthy onions wrongly failing Grade A | 10.1% (colour rules alone: 91.9%) | `reports/fit_gate.json` |
| Time to grade a 4-photo demo lot | 7.1 s on an Android emulator; about 1 to 2.7 s per photo | `reports/apk_webview.json`. Not yet measured on a real phone |
| Data sent to any server | 0 bytes; all on the phone | By design; the demo runs in airplane mode |
| Languages | 9 | App settings |

**Line for the pitch:** "In one reported case, grading took a farmer from morning to evening. SAMA grades a sample in seconds per photo, on a phone, offline."

(Say "seconds per photo", not a precise number, until you have timed it on your own phone. The app shows the time after every photo.)
