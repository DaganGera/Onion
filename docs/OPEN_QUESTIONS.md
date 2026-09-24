# Open questions

Each one blocks a number from becoming `verified`. The software treats every answer as configuration, so answering a question changes a rule pack or a config file, not code.

1. **What does URS stand for, and what exactly is in it?** Press coverage (docs/SOURCES.md S4) calls it a "relaxed-specification" category of "smaller-sized and slightly blemished produce". We do not know the official expansion or limits. The app's working definition, printed on every receipt: bulbs that miss the pack's Grade A limits but stay within the relaxed limits. Ask a NAFED/NCCF procurement officer or find the June 2026 circular.
2. **Which press variant of the June 2026 relaxation is right?** Variant A (S2, S3): size window 45-65 mm widened to 35-70 mm. Variant B (S1): minimum 55 mm lowered to 45 mm. Both are shipped as packs. The official circular settles it.
3. **What were the Grade A defect tolerances before the relaxation?** No source gives them. The packs use placeholders (A-GRADEA-1).
4. **Is any rot or sprouting tolerated per bulb?** The packs reject above a 1% detection floor (A-REJECT-1). UNECE Class I allows at most 1% decayed produce per lot, which is a lot tolerance, not a per-bulb one.
5. **How should "one peeled outer layer allowed" be checked from a photo?** We score peeled area. A grader may count layers by hand. Field photos of peeled bulbs will tell us whether area is a usable proxy.
6. **What is the lot acceptance rule?** For example: a lot is Grade A if at most X% by weight fails. The SPRT thresholds (A-LOT-1) are placeholders.
7. **What sampling plan do centres use?** How many sacks, which layer, how many bulbs per tray. The random draw (A-SAMPLE-1) follows a square-root rule until we know.
8. **Is the "size" in the norm the minimum or maximum diameter?** UNECE FFV-25 uses the maximum diameter of the equatorial section (R1). A ring gauge passes a bulb in its smallest orientation. Packs use min Feret for now; the E1 ring-and-caliper study decides.
9. **Is the problem statement ID 26031 or 26046?** The old README said 26046; the team was given 26031. Check the SIH portal.
10. **Can a receipt carry a farmer's name?** Under the DPDP Act 2023 the farmer reference is personal data. The app stores it only on the phone and prints it on the receipt. A reference number may be safer; ask the department.
11. **Hindi, Marathi, Tamil, Telugu, Kannada, Gujarati, Bengali and Punjabi strings are machine drafts.** A native speaker must proofread each file in apps/web/src/locales before any demo in that language.
