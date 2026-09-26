# Who uses Parakh, and how

Parakh does three jobs: it measures a sample of onions from a phone photo, grades it by a published rulebook, and issues a receipt anyone can check. The same three jobs matter at every step from farm gate to kitchen, with different stakes at each. The examples below use made-up names and quantities; the prices come from the press reports in docs/SOURCES.md and are indicative only.

## 1. Government procurement centres (NAFED, NCCF, state agencies)

**Who:** the procurement officer at a buffer-stock centre, the farmer or FPO selling to it, and the auditor who checks the centre later.

**Problem today:** the officer grades by eye. Two officers can grade the same lot differently, farmers dispute rejections, and there is no record that someone else can re-check.

**Example.** Ramesh brings 24 sacks (about 1,200 kg) of red onions to a PSF centre in Lasalgaon. He and the officer each type a 4-digit code; the app picks sacks 3, 10, 12, 19 and 20 and which layer to open, so neither side chooses the sample. The officer photographs a tray from each sack on the printed mat. The app finds 71% Grade A by weight (interval 64–78%), 19% URS and 10% reject. It points to the reason for each rejected bulb, for example "blackening 34% above the 30% limit". Ramesh disagrees with two bulbs; he taps them and contests. The officer re-inspects one by hand and overrides it. The app signs a new revision and keeps both the AI's and the officer's verdicts. Ramesh leaves with a receipt on WhatsApp. At home, his son scans the QR on another phone with no internet and sees "Receipt checks out".

**What it changes:** the same onions get the same grade at every centre; the sample can't be cherry-picked; every rejection has a visible reason; the farmer can prove what was agreed.

**When norms change** (as on 4 June and 30 July 2026): the centre switches rule pack. Old receipts still verify under the pack they were issued with, and a disputed lot can be re-graded under either pack in one tap.

## 2. Primary vendors: farmers, FPOs, village aggregators

**Who:** a farmer or farmer-producer organisation that sells at the mandi or to procurement.

**Example 1: grade before you travel.** An FPO in Niphad has 40 quintals ready. Before hiring a truck to the centre, the secretary grades three trays at the farm. The app shows 38% URS. Since URS was reportedly not procured after 30 July 2026, a large share might be turned away. The FPO sorts out the pale, blemished bulbs at the farm and sells those locally. It only trucks the Grade A share, saving a wasted trip and a rejection.

**Example 2: price conversation.** With the day's rate typed in, the app shows an indicative value range for the lot (for example ₹20,500 to ₹23,400 for 1,200 kg at ₹2,125 per quintal). This is not an official price. It gives the farmer a number grounded in measurements rather than in the buyer's word.

**Example 3: storage decisions.** Onions with sprouting or rot don't store well. A farmer grading after harvest can see how much of the crop shows early rot and sell that part first.

## 3. Secondary vendors: traders, commission agents, wholesalers, exporters, cold stores

**Who:** anyone who buys from farmers or mandis in bulk and sells on.

**Example 1: trader buying at the mandi.** A trader buys three lots at Pimpalgaon. For each, the app records the grade mix by weight on a signed receipt. When a buyer in Delhi later complains that the onions arrived with rot, the trader can show what the grade was on the day of purchase, with photos and a timestamp. It then becomes clear whether the damage happened in transit or storage.

**Example 2: cold-store intake and release.** A cold store grades each lot at intake and again at release months later. Comparing the two receipts gives a measured storage loss per lot, which settles who pays for losses and shows which varieties store well.

**Example 3: exporter pre-check.** An exporter checks lots against a stricter rule pack built from the UNECE Class I structure (size window, lower defect tolerance) before booking a container. The rulebook is data, so a buyer's own specification can be loaded as a pack.

## 4. Tertiary consumers: retailers, institutional kitchens, households

**Who:** the end of the chain: supermarkets, hotel and hostel kitchens, government canteens and mid-day-meal schemes, and households buying in bulk.

**Example 1: institutional buying.** A hostel mess buys 500 kg a month from a local wholesaler. Its store-keeper photographs a tray on delivery. If more than 15% by weight is rejected, the mess returns the lot, and the signed receipt is the evidence in the complaint.

**Example 2: retail shelf check.** A supermarket's receiving desk grades one tray per incoming lot. Over a month, the fleet dashboard shows which supplier's lots most often fall below Grade A.

**Example 3: consumer checking a claim.** A consumer buying a "Grade A" sack from an FPO outlet scans the QR on the sack tag. The phone shows who graded it, when, under which rule pack, and the measured grade mix.

## 5. Oversight: department officials and auditors

**Who:** the Department of Consumer Affairs, state agriculture departments, vigilance.

**Example.** Receipts from all centres feed a dashboard. One centre's lots are graded 20 points more generous than its neighbours'. Its officers override the app three times as often as elsewhere, and it has recently stopped using the printed mat (weaker size calibration). The auditor downloads that centre's published transparency log. With an older signed tree head, the auditor can prove that no past receipts were rewritten. A field visit follows, targeted rather than random.

## What Parakh does not do

It does not see inside a bulb (internal rot), it does not replace a grader's final decision on a disputed lot, and it cannot prove that the photographed onions came from the sacks being sold (the random sack draw reduces that risk). See docs/LIMITATIONS.md.
