# What SIH26031 asks for, what we built, and what we added

**Problem statement:** SIH26031, Ministry of Consumer Affairs, Food & Public Distribution (Department of Consumer Affairs). Category Software, theme Smart Automation.

**The problem:** onion quality assessment and grading is subjective and varies across procurement centres, which leads to disputes and inconsistencies.

## The five things the PS expects

| # | The PS asks for | What SAMA does | Where to show it |
|---|---|---|---|
| 1 | An AI-based mobile app that uses image processing to assess onion quality | An Android app (also a web app) running three on-device vision models: an onion finder (U-Net segmentation), a colour-based defect measurer, and a learned healthy/unhealthy check (MobileNetV3). Everything runs on the phone, offline | Airplane-mode shot, then the capture |
| 2 | Identify damaged, rotten, sprouted or undersized onions | Every onion gets a diameter in millimetres, an estimated weight, and the share of its surface showing blackening, rot, spots, sunburn, sprouting, peeled skin or cuts. Shape flags cover double, split and thick-necked bulbs | Tap an onion → bulb sheet |
| 3 | Estimate Grade A and URS percentages | Grade A / URS / Reject / "needs human check" shares **by weight** and by count, each with a 95% interval, under the chosen rule pack | Result screen |
| 4 | Generate a digital quality report instantly | A signed receipt with a QR code, printable on A4 and shareable on WhatsApp. A second phone can verify it offline | Receipt → Verify on phone B |
| 5 | Reduce human bias and improve transparency | Random sack draw from two parties' codes; a visible reason for every rejection; the officer can override and the farmer can contest, with both kept on record; published, hashed rule packs; a tamper-evident log; a fleet dashboard showing override patterns | Sack draw, bulb reason, contest, tamper test |

## What we added beyond the PS

These are the things most teams won't have. Each one answers a question a judge is likely to ask.

| Added | Why it matters |
|---|---|
| **Fully offline**, with airplane mode on | Procurement centres and farm gates often have poor signal. Nothing depends on a server |
| **Receipt the farmer can verify on their own phone**, which re-runs the grading | Moves trust from "believe the officer" to "check it yourself". This is the core of transparency |
| **Rule packs**: the grading norms are data, versioned and hashed | The norms changed on 4 June and 30 July 2026. SAMA switches in one tap and can re-grade old lots under either rule |
| **"Needs human check" band** | An onion within measuring error of a limit goes to a person instead of being decided by chance. The app knows when it doesn't know |
| **Grades by weight, with an interval** | Procurement is paid by weight, and a sample needs an honest error range |
| **Scale from a mat, an A4 sheet or a ₹5 coin** | Real millimetres, not guesses. The receipt prints how the scale was set and how precise it was |
| **Capture guard with auto-shutter** | Bad photos are refused with a one-line reason, so bad evidence never enters the record |
| **Fair sampling**: two codes decide which sacks to open | Neither side can cherry-pick the sample |
| **Override and contest never erase the AI verdict** | Every human action is signed into a new revision. Audits can see who overrode what |
| **9 Indian languages** (Hindi, Marathi, Gujarati, Punjabi, Bangla, Tamil, Telugu, Kannada, English) | Usable by officers and farmers in their own language |
| **Landing page with an in-browser demo** | Anyone can try the model without installing anything |
| **Honest evaluation** | Every number comes from a script run on real held-out photos. What isn't measured yet is listed |

## How SAMA differs from the usual answer

Most teams will build "YOLO box detector + classifier + PDF report". SAMA differs in three ways:

1. **It measures instead of labelling.** The norms speak in millimetres and percentage of surface (for example "blackening up to 30%"), so SAMA outlines each onion pixel by pixel and measures area fractions. A box and a label can't give you "34% blackening".
2. **It is honest about uncertainty.** The receipt gives intervals, says how the scale was set, and sends borderline onions to a human.
3. **It can be contested and verified.** The party who disagrees can check the result independently, offline, with the same rulebook.

## Honest limits (say these before a judge finds them)

- The procurement limits come from press reports. We found no official NAFED/NCCF circular, and the meaning of "URS" is unconfirmed. Both are configurable in the rule pack.
- Accuracy numbers come from a public real-photo dataset (Pune markets, one phone). Size against calipers, repeatability, and a comparison with human graders still need field data. The shop visit can start these studies.
- Only the visible surface of an onion is measured. Shaking the tray and looking again helps, but hidden faces stay hidden.
- Weight is estimated from size with an assumed density until a kitchen-scale fit is done.
- The receipt is tamper-evident, not tamper-proof. It can't prove the photographed onions came from the sacks that were sold.
