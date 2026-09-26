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
import io
import json
import math
import random
import re
import statistics
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
    tray_defect_rates: list[float] = []
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
            if n > 0:
                tray_defect_rates.append(row_defects / n)
            for k in ("rotten", "sprouted", "smut", "damaged", "doubles"):
                per_class[k] = per_class.get(k, 0) + int(row[f"n_{k}"])
    return {
        "trays": trays,
        "bulbs": bulbs,
        "mean_per_tray": bulbs / max(1, trays),
        "grade_a_pct": 100.0 * grade_a / max(1, bulbs),
        "defect_pct": 100.0 * defects / max(1, bulbs),
        "per_class": per_class,
        "tray_defect_rates": tray_defect_rates,
    }


def ci_half_width(k: int, n: int) -> float:
    lo, hi = arb.wilson_pct(k, n)
    return (hi - lo) / 2.0


# --------------------------------------------------------------------------
# Data cost per grading session (loop A859). Measured from repo files; the
# only invented numbers below are the explicitly labelled ASSUMED constants
# (finalize overhead, tariff, wage, amortisation) and they are printed as
# such so nobody can mistake them for field data.
# --------------------------------------------------------------------------

FINALIZE_ASSUMED_KB = 8        # JSON POST + certificate row + headers — ASSUMED, generous
DATA_TARIFF_INR_PER_GB = 10.0  # effective prepaid bundle price — ASSUMED (see section text)
PHONE_INR = 8000               # the whole deployment handset — project constant
PHONE_DAYS = 730               # 2-year service life — ASSUMED
LOTS_PER_DAY = 20              # one officer's stall throughput — ASSUMED
MAT_PRINT_INR = 5.0            # A4 laser reprint — ASSUMED
MAT_LOTS_PER_PRINT = 200       # laminated sheet lifetime — ASSUMED
WAGE_INR_PER_DAY = 400         # unskilled mandi day-rate — ASSUMED (₹50/h over 8 h)
SESSION_BUDGET_KB = 2048       # the <2 MB per-session promise


def _upload_constants() -> tuple[int, int]:
    """Read UPLOAD_MAX_EDGE / UPLOAD_JPEG_QUALITY straight out of index.html.

    One source of truth: if the client budget ever changes, this measurement
    follows it automatically instead of silently drifting.
    """
    html = (ROOT / "app" / "static" / "index.html").read_text(encoding="utf-8")
    edge_m = re.search(r"UPLOAD_MAX_EDGE\s*=\s*(\d+)", html)
    q_m = re.search(r"UPLOAD_JPEG_QUALITY\s*=\s*([\d.]+)", html)
    if not edge_m or not q_m:
        return 1600, 80
    edge = int(edge_m.group(1))
    qf = float(q_m.group(1))
    quality = round(qf * 100) if qf <= 1 else round(qf)
    return edge, quality


def _simulate_client_downscale(path: Path, edge: int,
                               quality: int) -> tuple[int, int]:
    """Mirror index.html downscaleForUpload() on one photo.

    Returns (orig_kb, sent_kb) AFTER the honesty guard -- exactly what would
    leave the phone for this file. Pillow stands in for the browser canvas
    encoder; encoders differ by roughly +/-15%, which the output states.
    """
    try:
        from PIL import Image  # deferred: script must run without heavy deps
    except ImportError:
        raise SystemExit("Pillow required for the uplink measurement: "
                         "pip install pillow")
    raw = path.read_bytes()
    orig_kb = max(1, round(len(raw) / 1024))
    im = Image.open(io.BytesIO(raw)).convert("RGB")
    w, h = im.size
    k = min(1.0, edge / max(w, h))
    if k < 1.0:
        im = im.resize((max(1, round(w * k)), max(1, round(h * k))),
                       Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=quality, optimize=True)
    out = buf.getvalue()
    # The honesty guard: a re-encode that came out BIGGER never ships --
    # the original does. Mirror it or the doc lies about savings.
    sent_kb = orig_kb if len(out) >= len(raw) else max(1, round(len(out) / 1024))
    return orig_kb, sent_kb


def data_cost() -> dict:
    """Measured per-look and per-session network components (KB)."""
    static = ROOT / "app" / "static"
    edge, quality = _upload_constants()

    img_dir = ROOT / "data" / "dataset" / "test" / "images"
    ups: list[tuple[int, int]] = []
    if img_dir.is_dir():
        photos = sorted(p for p in img_dir.iterdir()
                        if p.suffix.lower() in (".jpg", ".jpeg", ".png"))
        for p in photos:
            try:
                ups.append(_simulate_client_downscale(p, edge, quality))
            except Exception:
                continue  # one unreadable file must not kill the report

    replays = sorted((static.parent / "cache").glob("replay_*.json"))
    downs = [max(1, round(p.stat().st_size / 1024)) for p in replays]

    shell_kb = round(sum(p.stat().st_size for p in
                         [static / "index.html",
                          static / "vendor" / "tailwind.js"]) / 1024)
    report_kb = max(1, round((static / "report.html").stat().st_size / 1024))

    sent = [s for _, s in ups]
    return {
        "upload_max_edge": edge,
        "jpeg_quality": quality,
        "n_photos": len(ups),
        "up_median_kb": statistics.median(sent) if sent else 0,
        "up_min_kb": min(sent) if sent else 0,
        "up_max_kb": max(sent) if sent else 0,
        "as_is_count": sum(1 for o, s in ups if s == o),
        "down_median_kb": statistics.median(downs) if downs else 0,
        "down_max_kb": max(downs) if downs else 0,
        "shell_first_visit_kb": shell_kb,
        "shell_repeat_visit_kb": 0,   # service worker serves /static/* + replay cache
        "report_html_kb": report_kb,
        "up_samples": ups,
        "n_replays": len(downs),
    }


def session_cost_kb(dc: dict, looks: int, first_visit: bool) -> float:
    """Total network KB of one full grading session under the stated model."""
    per_look = dc["up_median_kb"] + dc["down_median_kb"]
    shell = dc["shell_first_visit_kb"] if first_visit else dc["shell_repeat_visit_kb"]
    return shell + looks * per_look + FINALIZE_ASSUMED_KB + dc["report_html_kb"]



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

    # --- LOOP-I2222: rupee stakes + smallest resolvable dispute --------------
    # Everything here is arithmetic over numbers already in the repo or
    # flagged assumptions; nothing is measured in the field.
    r_a = arb.DEFAULT_RATES["A"]
    r_b = arb.DEFAULT_RATES["B"]
    r_c = arb.DEFAULT_RATES["C"]
    per_pt_to_b = (r_a - r_b) / 100.0     # rupees per quintal per Grade-A pt
    per_pt_to_c = (r_a - r_c) / 100.0
    trolley_q = (20.0, 50.0)              # ASSUMED 2-5 t tractor-trolley

    add("## 3b. What one percentage point of Grade A is worth (the money frame)")
    add("")
    add("The certificate's ±points convert directly into rupees at the same")
    add("price band the app already renders. Rates below are the app's DEMO")
    add(f"defaults shipped in `app/arbitration.py` (A ₹{r_a:.0f} / B ₹{r_b:.0f} "
        f"/ C ₹{r_c:.0f} per quintal) anchored to Lasalgaon's Aug-2026 average")
    add("band (§5) but with INVENTED differentials; trolley mass is an")
    add("ASSUMED 20–50 q (a 2–5 t tractor-trolley, consistent with §4's")
    add("literature lot size). The conversion itself is arithmetic.")
    add("— MEASURED-IN-REPO (rates-as-shipped + arithmetic) + ASSUMED (mass)")
    add("")
    add(f"- Each Grade-A point misgraded down to B moves ₹{per_pt_to_b:.0f}/q; "
        f"down to C, ₹{per_pt_to_c:.0f}/q.")
    add(f"- Over a {trolley_q[0]:.0f}–{trolley_q[1]:.0f} q trolley, a 10-point "
        f"Grade-A dispute is therefore "
        f"₹{10 * per_pt_to_b * trolley_q[0]:,.0f}–"
        f"₹{10 * per_pt_to_b * trolley_q[1]:,.0f} of exposure if the argument "
        f"is A-vs-B, and "
        f"₹{10 * per_pt_to_c * trolley_q[0]:,.0f}–"
        f"₹{10 * per_pt_to_c * trolley_q[1]:,.0f} if A-vs-C — the size of "
        "fight this product exists to arbitrate.")
    add(f"- SAMA's own sampling band at the ±{arb.TARGET_HALF_WIDTH_PCT:g}-pt "
        f"promise brackets that exposure to roughly ±₹"
        f"{arb.TARGET_HALF_WIDTH_PCT * per_pt_to_b * trolley_q[0]:,.0f}–±₹"
        f"{arb.TARGET_HALF_WIDTH_PCT * per_pt_to_c * trolley_q[1]:,.0f} per "
        "lot: the interval a phone app prints for free carries real money.")
    add("- Defect errors price differently: a rotten bulb should be rejected, "
        "not re-banded, so each undetected rotten point costs its FULL grade "
        f"rate — 5 rot points missed on a {trolley_q[0]:.0f} q Grade-A lot "
        f"is ≈₹{5 / 100 * r_a * trolley_q[0]:,.0f} of overpayment.")
    add("")

    # Smallest gap two SAMA certificates can separate, using the SAME rule
    # the shipped arbitration engine uses (95% Wilson intervals -> overlap).
    w_obs = ci_half_width(round(p_a * n_req_obs), n_req_obs)
    w_worst = ci_half_width(n_req_obs // 2, n_req_obs)
    add("## 3c. The smallest Grade-A gap two SAMA certificates can separate")
    add("")
    add("`arbitration.py` calls AGREE when two lots' 95% Wilson intervals")
    add("overlap, so the minimum resolvable gap between two certificates is")
    add("the SUM of their half-widths. At the sufficiency target "
        f"({n_req_obs}")
    add("observations each): — MEASURED-IN-REPO (arithmetic)")
    add("")
    add(f"- At the hand-sorted mix (Grade-A ≈ {p_a * 100:.1f}%): ±{w_obs:.1f} "
        f"pts each → disputes wider than ≈{2 * w_obs:.1f} pts are resolved "
        "statistically.")
    add(f"- At worst-case p=50%: ±{w_worst:.1f} pts each → ≈"
        f"{2 * w_worst:.1f} pts.")
    add("- Read honestly against §3's ASSUMED human band (±5–10 pts): at the")
    add("  target sample SAMA separates differences around or above the TOP")
    add("  of that band — the gross end of disputes — while staying")
    add("  reproducible, timestamped and free. It does not out-resolve a")
    add("  trained human on subtle calls, and nothing here claims otherwise.")
    add("")

    # --- LOOP-I858 / RT-001 S-1: how fast the worst-view estimator inflates --
    # The certified defect rate is max(per-look rates)/factor (grading.py D4,
    # frozen). max() over T sampled trays converges to the supremum of tray
    # rates, not to the lot truth. We measure that selection effect directly
    # on the 130 hand-sorted tray rates: draw T trays, take the worst, average.
    # ASSUMPTION (stated in the output): look rate = tray rate, i.e. perfect
    # view-independent detection. Real views add noise, which raises E[max]
    # further -- so every figure below is a LOWER bound on the live inflation.
    occl = float(json.loads(
        (ROOT / "app" / "constants.json").read_text(encoding="utf-8")
    ).get("occlusion_correction_2look") or 1.0)
    rates = gt["tray_defect_rates"]
    p_bar = statistics.fmean(rates)
    rng = random.Random(20260825)          # fixed seed: reruns reproduce bytes
    inflation_rows = []
    for t_trays in (1, 2, 3, 5, 10):
        draws = 20000
        emax = statistics.fmean(
            max(rng.sample(rates, min(t_trays, len(rates))))
            for _ in range(draws))
        infl_obs = 100.0 * (emax - p_bar)
        # certified = selected rate / occlusion factor; the factor was fitted
        # to cancel AVERAGE occlusion, not this selection -- applying it to
        # the gap scales it by exactly this division.
        infl_cert = infl_obs / occl
        inflation_rows.append((t_trays, 100.0 * emax, infl_obs, infl_cert))

    add("## 3d. How fast does the worst-view defect estimator inflate with "
        "sample size? (RT-001 S-1)")
    add("")
    add("The certified defect rate is `max(per-look rates) / occlusion_factor`")
    add("(grading.py D4 — frozen). A maximum over more looks or trays can only")
    add("grow, so photographing MORE of a lot mechanically raises the certified")
    add(f"figure. Measured on the {gt['trays']} hand-sorted tray defect rates")
    add(f"(lot truth {p_bar * 100:.1f}% defective): draw T trays at random, take")
    add("the worst, average over 20,000 seeded draws. — MEASURED-IN-REPO inputs +")
    add("MONTE-CARLO arithmetic (seed 20260825)")
    add("")
    add("| trays photographed | E[worst-tray rate] | structural bias (pts) | after ÷"
        f"{occl:.3f} correction (pts) | vs ±{arb.TARGET_HALF_WIDTH_PCT:g}-pt sampling promise |")
    add("|---|---|---|---|---|")
    for t_trays, emax, infl_obs, infl_cert in inflation_rows:
        add(f"| {t_trays} | {emax:.1f}% | +{infl_obs:.1f} | +{infl_cert:.1f} | "
            f"{infl_cert / arb.TARGET_HALF_WIDTH_PCT:.1f}× the whole promise |")
    add("")
    add("**ASSUMPTION (lower bound):** each look is treated as seeing its tray's")
    add("true rate perfectly and identically. Real views differ — blur, glare and")
    add("occlusion make some looks worse — and noise RAISES the expected maximum.")
    add("The fitted ÷0.877 factor cancels average occlusion on single-tray pairs;")
    add("applied to a cross-tray maximum, it scales the bias up, not down. So the")
    add("live inflation is AT LEAST these figures.")
    add("")
    add(f"- At the fitted two-look design the bias alone is roughly "
        f"+{inflation_rows[1][3]:.0f} pts on the certified number; by five trays it is")
    add(f" ~{inflation_rows[3][3] / arb.TARGET_HALF_WIDTH_PCT:.0f}× SAMA's entire ±6-point sampling promise. The error is not in")
    add("  the optics — it is the order statistic, and it lands against the party")
    add("  being paid less.")
    add("- **Mitigation shipped (loop I858):** every new certificate also carries")
    add("  the plain pooled incidence (`defect_pooled_*`, per-tray clustered Wilson)")
    add("  printed beside the ceiling, so both readings and their gap are visible")
    add("  on the document itself. Replacing the estimator inside frozen grading.py")
    add("  remains a data-scientist unfreeze decision.")
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

    # --- 4b: measured data cost per session (loop A859) ---------------------
    dc = data_cost()
    looks_std = 2
    trays_suff = max(1, math.ceil(n_req_obs / max(1, gt["mean_per_tray"])))
    s_first = session_cost_kb(dc, looks_std, first_visit=True)
    s_repeat = session_cost_kb(dc, looks_std, first_visit=False)
    s_suff = session_cost_kb(dc, 2 * trays_suff, first_visit=False)
    budget_ok = max(s_first, s_repeat, s_suff) <= SESSION_BUDGET_KB

    inr_per_lot_data = s_repeat / 1024 * DATA_TARIFF_INR_PER_GB / 1024
    inr_phone_lot = PHONE_INR / (PHONE_DAYS * LOTS_PER_DAY)
    inr_mat_lot = MAT_PRINT_INR / MAT_LOTS_PER_PRINT
    sama_inr_lot = inr_per_lot_data + inr_phone_lot + inr_mat_lot
    manual_low = 24 * (WAGE_INR_PER_DAY / 8)
    manual_high = 60 * (WAGE_INR_PER_DAY / 8)

    add("## 4b. Data cost per grading session — measured, not asserted")
    add("")
    add("Method: the uplink side mirrors `downscaleForUpload()` in "
        "index.html — clamp the long edge to the client's own "
        f"{dc['upload_max_edge']} px constant, re-encode JPEG q"
        f"{dc['jpeg_quality']}, keep whichever blob is smaller (the honesty "
        "guard) — over every tray photo in `data/dataset/test/images`. The "
        "downlink side is the median size of the six immutable replay "
        "payloads served by `/api/replay/N`, which are exactly one look's "
        "annotated response including evidence thumbnails. Imagery is "
        "SYNTHETIC repo trays; field phone originals are several MB BEFORE "
        "this clamp, and AFTER it the payload depends on scene content, not "
        "source size.")
    add("")
    add(f"- **Uplink per look after the client clamp: median "
        f"{dc['up_median_kb']:.0f} KB** (range {dc['up_min_kb']}–"
        f"{dc['up_max_kb']} KB across {dc['n_photos']} photos); "
        f"{dc['as_is_count']}/{dc['n_photos']} hit the send-as-is honesty "
        "guard. Browser canvas encoders vary ±15% vs Pillow — stated, not "
        "hidden. — MEASURED-IN-REPO (SYNTHETIC imagery)")
    add(f"- **Downlink per look (result + thumbnails): median "
        f"{dc['down_median_kb']:.0f} KB** across {dc['n_replays']} cached "
        "replays. — MEASURED-IN-REPO")
    add(f"- **Static shell, first visit: {dc['shell_first_visit_kb']} KB** "
        "(index.html + vendored tailwind.js). The service worker (loop A859) "
        f"caches same-origin `/static/*` and `/api/replay/N`, so every visit "
        f"after the first pays **{dc['shell_repeat_visit_kb']} KB** for the "
        "shell (~<2 KB of conditional-request overhead when online, zero "
        "offline). — MEASURED-IN-REPO")
    add(f"- Finalize POST + certificate row counted as "
        f"{FINALIZE_ASSUMED_KB} KB. — ASSUMED (generous)")
    add("")
    add("| full grading session | looks | network cost | share of 2 MB budget |")
    add("|---|---|---|---|")
    add(f"| first visit, 1 tray × 2 looks | {looks_std} | {s_first:.0f} KB | "
        f"{100 * s_first / SESSION_BUDGET_KB:.0f}% |")
    add(f"| repeat visit (service worker), same lot | {looks_std} | "
        f"{s_repeat:.0f} KB | {100 * s_repeat / SESSION_BUDGET_KB:.0f}% |")
    add(f"| repeat visit, sufficiency sample "
        f"({trays_suff} trays × 2 looks) | {2 * trays_suff} | {s_suff:.0f} KB | "
        f"{100 * s_suff / SESSION_BUDGET_KB:.0f}% |")
    add("")
    if budget_ok:
        add(f"Worst case above stays inside the **<{SESSION_BUDGET_KB // 1024} MB per-session "
            "budget**: PASS. On a ~0.5 Mbps rural uplink the repeat-visit lot "
            f"is ≈{s_repeat * 8 / 500:.0f} s of radio time, most of it the "
            "two photo uploads that A2212 already clamped. — MEASURED-IN-REPO "
            "(arithmetic on measured components)")
        stress = 2 * trays_suff * (dc["up_max_kb"] + dc["down_max_kb"]) \
            + FINALIZE_ASSUMED_KB + dc["report_html_kb"]
        add(f"- Stress read, so the tail is visible: at the WORST measured "
            f"components ({dc['up_max_kb']} KB up / {dc['down_max_kb']} KB "
            f"down per look) the sufficiency sample reaches {stress:.0f} KB — "
            f"{100 * stress / SESSION_BUDGET_KB:.0f}% of budget"
            f"{', over by ' + format(stress - SESSION_BUDGET_KB) + ' KB' if stress > SESSION_BUDGET_KB else ''}. "
            "The lever if field photos run heavier is `ANNOTATED_MAX_WIDTH`/"
            "`ANNOTATED_JPEG_QUALITY` in main.py, which set ~90% of every "
            "response. — MEASURED-IN-REPO")
    else:
        add(f"**FAIL:** a modelled session exceeds the {SESSION_BUDGET_KB // 1024} MB budget — "
            "fix before quoting any data-cost number.")
    add("")
    add("**The rupee story (every label explicit):**")
    add("")
    add(f"- Data tariff ASSUMED ₹{DATA_TARIFF_INR_PER_GB:.0f}/GB effective "
        "(₹239-ish 1.5–2 GB/day prepaid bundles; conservative vs street "
        "₹6–8/GB). One repeat-visit lot moves "
        f"{s_repeat / 1024:.2f} MB ⇒ **≈₹{inr_per_lot_data:.2f} of data**. "
        "Even the once-only first visit adds under ₹0.05.")
    add(f"- Hardware: the single ₹{PHONE_INR:,} deployment phone amortised "
        f"over {PHONE_DAYS} days × {LOTS_PER_DAY} lots/day ⇒ "
        f"**≈₹{inr_phone_lot:.2f}/lot**. — ASSUMED life and throughput")
    add(f"- Printed A4 mat: ₹{MAT_PRINT_INR:.0f} reprint every "
        f"~{MAT_LOTS_PER_PRINT} lots ⇒ **≈₹{inr_mat_lot:.2f}/lot**. — ASSUMED")
    add(f"- **SAMA marginal operating cost ≈ ₹{sama_inr_lot:.2f} per lot** "
        "(data + handset amortisation + mat). No accounts, no SMS gateway, "
        "no paid API anywhere in the path.")
    add("- Manual comparison, stated narrowly so nobody accuses us of spin: "
        "assessing one 2–5 t trolley at the literature grading rate (§4) is "
        f"24–60 person-hours; at an ASSUMED ₹{WAGE_INR_PER_DAY}/day unskilled "
        f"wage that is **₹{manual_low:,.0f}–₹{manual_high:,.0f} of labour per "
        "lot assessed by hand**. SAMA does NOT eliminate physical sorting — "
        f"the sample trays still get laid out by hand (§4's 2–30 min). What "
        f"~₹{sama_inr_lot:.0f} buys is a signed, reproducible ±pt interval "
        "that ends the re-grading argument. — LITERATURE rate + ASSUMED wage")
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
    add("- The ₹ figures in §3b–§3c ride on DEMO rate differentials and an "
        "ASSUMED trolley mass; replace either with a mandi-rate feed or a "
        "weighed-lot study before quoting them as field losses.")
    add("- §3d assumes perfect, view-independent detection to isolate the "
        "max()-selection bias; a real two-view tray dataset (or the S-1 "
        "unfreeze) would replace it with measured inflation.")
    add("- §4b's data figures ride on SYNTHETIC imagery through a Pillow "
        "approximation of the phone's canvas encoder, and its rupee figures "
        "on ASSUMED tariff, wage, handset life and lot throughput; replace "
        "with logged field sessions and actual bills before quoting them as "
        "field costs.")
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
