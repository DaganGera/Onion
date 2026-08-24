"""Generate .agent/IMPACT_EVIDENCE.md from repo data. Nothing invented here:
every number is computed live from data/groundtruth.csv, app/arbitration.py
statistics and .agent/METRICS.json, or explicitly labelled as an assumption.

    python scripts/impact_evidence.py            # writes the markdown file
    python scripts/impact_evidence.py --stdout   # print instead of writing

Re-run after any change to ground truth or metrics so the pitch numbers stay
honest by construction.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import arbitration as arb  # noqa: E402


def groundtruth_stats() -> dict:
    """Hand-sorted tray counts (MEASURED-IN-REPO: human labelling)."""
    path = ROOT / "data" / "groundtruth.csv"
    trays = bulbs = grade_a = 0
    defects = 0
    per_class = {}
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            n = int(row["n_total"])
            trays += 1
            bulbs += n
            grade_a += int(row["n_grade_A"])
            row_defects = sum(int(row[k]) for k in
                              ("n_rotten", "n_sprouted", "n_smut",
                               "n_damaged", "n_doubles"))
            defects += row_defects
            for k in ("rotten", "sprouted", "smut", "damaged", "doubles"):
                per_class[k] = per_class.get(k, 0) + int(row[f"n_{k}"])
    return {
        "trays": trays,
        "bulbs": bulbs,
        "mean_per_tray": bulbs / max(1, trays),
        "grade_a_pct": 100.0 * grade_a / max(1, bulbs),
        "defect_pct": 100.0 * defects / max(1, bulbs),
        "per_class": per_class,
    }


def ci_half_width(k: int, n: int) -> float:
    lo, hi = arb.wilson_pct(k, n)
    return (hi - lo) / 2.0


def build_markdown(gt: dict, metrics: dict) -> str:
    z = arb.Z95

    # --- CI widths at realistic observation counts -------------------------
    p_a = gt["grade_a_pct"] / 100.0          # hand-sorted Grade A share
    rows = []
    for label, n in (("1 tray (~%d bulbs)" % round(gt["mean_per_tray"]),
                      round(gt["mean_per_tray"])),
                     ("2 looks x 1 tray", round(2 * gt["mean_per_tray"])),
                     ("2 trays x 2 looks", round(4 * gt["mean_per_tray"]))):
        k = round(p_a * n)
        hw_obs = ci_half_width(k, n)
        hw_worst = ci_half_width(n // 2, n)   # p=0.5 maximises width
        rows.append((label, n, hw_obs, hw_worst))

    # --- sufficiency target arithmetic -------------------------------------
    n_req_worst = math.ceil(z * z * 0.25 / ((arb.TARGET_HALF_WIDTH_PCT / 100) ** 2))
    n_req_obs = math.ceil(z * z * p_a * (1 - p_a)
                          / ((arb.TARGET_HALF_WIDTH_PCT / 100) ** 2))

    # --- analysis latency -> time-per-lot -----------------------------------
    cpu_p95 = metrics.get("metrics", {}).get("cpu_p95_ms")
    gpu_p95 = metrics.get("metrics", {}).get("gpu_p95_ms")

    lines = []
    add = lines.append
    add("# IMPACT EVIDENCE — computed, not asserted")
    add("")
    add(f"Generated {date.today().isoformat()} by `scripts/impact_evidence.py`.")
    add("Every figure below is one of:")
    add("")
    add("- **MEASURED-IN-REPO** — computed this run from files in this repo.")
    add("- **SYNTHETIC** — measured on procedurally generated imagery; never")
    add("  quote it as field accuracy (see EVIDENCE_AUDIT.md §2.2).")
    add("- **ASSUMED** — a stated planning assumption with its reasoning;")
    add("  replace with field data at the first opportunity.")
    add("- **LITERATURE** — an external published figure, cited author/year/")
    add("  url/access-date in EVIDENCE_AUDIT.md §6. Context for the problem")
    add("  size only; never presented as a SAMA measurement.")
    add("")

    add("## 1. The hand-sorted ground truth we actually have")
    add("")
    add(f"- **{gt['trays']} trays, {gt['bulbs']} bulbs** individually hand-sorted "
        f"and calipered (`data/groundtruth.csv`). — MEASURED-IN-REPO")
    add(f"- Mean tray size {gt['mean_per_tray']:.1f} bulbs; hand-sorted mix is "
        f"{gt['grade_a_pct']:.1f}% Grade A, {gt['defect_pct']:.1f}% defective "
        f"(by count). — MEASURED-IN-REPO")
    add(f"- Defect mix: {', '.join(f'{k} {v}' for k, v in gt['per_class'].items())} "
        f"bulbs across all trays. — MEASURED-IN-REPO")
    add("")

    add("## 2. How wide is our own uncertainty? (the honest pitch number)")
    add("")
    add("95% Wilson half-widths on the Grade-A proportion at the hand-sorted "
        "Grade-A share, and at worst-case p=50%: — MEASURED-IN-REPO (arithmetic)")
    add("")
    add("| Sample | bulb-observations | ± pts at observed mix | ± pts worst case |")
    add("|---|---|---|---|")
    for label, n, hw_obs, hw_worst in rows:
        add(f"| {label} | {n} | ±{hw_obs:.1f} | ±{hw_worst:.1f} |")
    add("")
    add(f"To keep the Grade-A promise of ±{arb.TARGET_HALF_WIDTH_PCT:g} points "
        f"(`TARGET_HALF_WIDTH_PCT`) needs **{n_req_obs} observations at the "
        f"observed mix** ({n_req_worst} at worst case p=50%) — i.e. roughly "
        f"{math.ceil(n_req_obs / max(1, 2 * gt['mean_per_tray']))} two-look "
        "trays. The in-app sufficiency card says the same thing to the officer "
        "in real time. — MEASURED-IN-REPO (arithmetic)")
    add("")
    add("**Pitch line:** SAMA is the only option on the table that prints its "
        "own error bars — and now (loop I2211) the defect percentage carries a "
        "Wilson interval too, not just Grade A.")
    add("")

    add("## 3. Our CI vs manual re-grade disagreement")
    add("")
    add("The whole product exists because two humans disagree about a lot. No")
    add("inter-inspector agreement study exists **in this repo**, so the human")
    add("spread below is an ASSUMED band, not a measurement:")
    add("")
    add("- **ASSUMPTION:** visual lot-grading disagreement between two trained")
    add("  inspectors on the same lot is typically ±5–10 percentage points on")
    add("  Grade A share. Reasoning: disputes are common enough that DoCA runs")
    add("  a problem statement on them; per-bulb class calls near boundaries")
    add("  are subjective (e.g. damaged_skin vs sound), and boundary bulbs are")
    add("  exactly where two humans split. Replace this band with a real")
    add("  dual-grading study before quoting it as data.")
    add("")
    add(f"- Our sampling error alone at a 2-tray/4-look sample is "
        f"±{rows[2][2]:.1f} pts (observed mix). — MEASURED-IN-REPO")
    add("- Consequence, stated both ways so nobody can accuse us of spin:")
    add(f"  - At small samples our CI is WIDER than assumed human disagreement "
        f"— which is why the app refuses to bless small samples and shows the "
        f"sufficiency card ({n_req_obs}-observation target).")
    add(f"  - Once the sample reaches that target, SAMA's interval (±"
        f"{arb.TARGET_HALF_WIDTH_PCT:g} pts by construction) is comparable to "
        f"or tighter than ASSUMED human-to-human spread — and unlike a human "
        f"re-grade, it is reproducible, timestamped, hash-chained and free.")
    add("")

    add("## 4. Time-per-lot estimate")
    add("")
    if cpu_p95 and gpu_p95:
        add(f"- Analysis cost per look: p95 {cpu_p95:.0f} ms CPU / "
            f"{gpu_p95:.0f} ms GPU on the dev machine. — SYNTHETIC (real "
            "hardware, generated imagery; measures pipeline cost only)")
        two_look_ms = 2 * max(cpu_p95, gpu_p95)
        add(f"- Two looks ≈ {two_look_ms / 1000:.2f} s of inference. The lot "
            "is therefore dominated by PHYSICAL handling, not compute.")
    add("- **ASSUMPTION:** handling ~45–90 s per look (lay tray beside mat, "
        "frame, capture, shake, recapture). A 1-tray two-look lot therefore "
        "lands at **~2–3 minutes end-to-end** including the result screen; a "
        f"sample sized to the ±6-pt promise (~{math.ceil(n_req_obs / max(1, gt['mean_per_tray']))} "
        "trays) at **~15–30 minutes**. — ASSUMED")
    add("- Manual whole-lot grading is literature-slow, not assumption-slow: "
        "a Nashik-market trade survey found **~30 persons are needed to grade "
        "20 tonnes of onions in a day** (≈0.72 person-minutes per kg), and "
        "~50–55 lakh tonnes/year are graded manually in India (Bisen, Bakane "
        "& Sakkalkar 2022, J Food Sci Technol 59(6):2370–2380, "
        "doi:10.1007/s13197-021-05253-8; accessed 2026-08-25; survey figure, "
        "not a time-motion study — defect sorting may be slower still). At "
        "that rate one 2–5 t tractor-trolley lot is **24–60 person-hours**: "
        "hours even for a ten-person crew, and it produces no signed "
        "interval. — LITERATURE")
    add("")

    add("## 5. External impact numbers — LITERATURE (problem-size context)")
    add("")
    add("All verified against primary documents on 2026-08-25; full citations")
    add("and verification notes in EVIDENCE_AUDIT.md §6. These are context")
    add("figures from published sources — never present them as SAMA data.")
    add("")
    add("- **Onion harvest+post-harvest loss, India: 8.20% overall** (farm")
    add("  operations 6.05%, storage 2.16%; regional range 5.49–12.72%;")
    add("  Maharashtra-inclusive region worst at 12.72%). Economic value of")
    add("  onion loss ≈ ₹2,312 crore/yr (2012-13 production 16.66 Mt × "
        "8.20% × ₹16,920/t). — Jha et al. 2015, ICAR-CIPHET/MoFPI report, "
        "Table 6.8 & §6.4.2 — LITERATURE")
    add("- Category cross-check: vegetables lose **4.58–12.44%** (ICAR-CIPHET")
    add("  2015) / **4.87–11.61%** (NABCONS 2022); all-India monetary loss")
    add("  across 45 crops ₹1.53 lakh crore/yr (NABCONS). Onion alone ≈ "
        "₹5,156 crore/yr per the NABCONS study as reported to Lok Sabha. — "
        "MoFPI reply, LS US Q.839 (04-Dec-2025) + HT (05-Dec-2024) — LITERATURE")
    add("- **Mandi volumes:** official monthly onion arrivals in Maharashtra")
    add("  ran ~0.41–1.07 million tonnes/month through 2023-24 (HSAG 2024,")
    add("  Tables 8.1.1–8.1.3); national production 242.7 lakh t (~24.3 Mt)")
    add("  from 15.4 lakh ha in 2023-24 (Table 1.6). Lasalgaon APMC — called")
    add("  the country's largest onion market — auctions ~8,000–30,000 q/day")
    add("  seasonally (~15,000 q/day baseline; avg price ₹2,180→₹2,760/q over")
    add("  five sessions in Aug-2026, day's range ₹800–3,117/q). — HSAG 2024;")
    add("  Business Today 14-Aug-2026 — LITERATURE")
    add("- Price sanity for the app's demo rates (A ₹2,400/B ₹1,800/C "
        "₹1,200/q): the Grade-A default sits inside Lasalgaon's observed "
        "Aug-2026 average band, but the size-grade differentials themselves")
    add("  remain invented demo values — see EVIDENCE_AUDIT §6 flags. — "
        "LITERATURE (anchor) + DEMO (differentials)")

    add("")
    add("## 6. What would falsify this page")
    add("")
    add("- A dual-grading study (two inspectors, same lots) replacing §3's "
        "assumed band with data.")
    add("- Real-phone tray photos re-run through eval_lot/calibrate_size "
        "converting §1–§2 inputs from synthetic to field data (gates T8, "
        "printed-mat caliper check).")
    add("- Any §5 literature link rot or a superseding national loss study: "
        "re-verify the citations in EVIDENCE_AUDIT.md §6 before quoting.")
    add("")
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--stdout", action="store_true",
                    help="print markdown instead of writing the file")
    args = ap.parse_args()

    gt = groundtruth_stats()
    metrics_path = ROOT / ".agent" / "METRICS.json"
    try:
        metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        metrics = {}

    md = build_markdown(gt, metrics)
    if args.stdout:
        print(md)
    else:
        out = ROOT / ".agent" / "IMPACT_EVIDENCE.md"
        out.write_text(md, encoding="utf-8")
        print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
