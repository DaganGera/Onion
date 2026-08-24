# DECISIONS

| # | Date | Decision | Rationale | Evidence |
|---|------|----------|-----------|----------|
| D1 | 2026-08-24 | Model locked to openrouter/stealth/ox-alpha for all agents | explicit user requirement; model present in opencode catalog | `opencode models` output |
| D2 | 2026-08-24 | Ship end2end=False (NMS path) | +0.5 mAP, refer rate 1.4% vs 14.1% | STATUS.md measured table |
| D3 | 2026-08-24 | mat_edge rung demoted below carried, confidence 0.25 | 16.9mm MAE vs caliper truth | occlusion_stress + caliper per-rung table |
| D4 | 2026-08-24 | merge_looks uses max per-look defect rate, pooled sizes | concatenation preserves occlusion bias | Defect MAE 7.34→2.95 |
| D5 | 2026-08-24 | ICAR-DOGR band attribution FLAGGED, not changed | research found published DOGR sources use A >60mm/B 50-60/C 35-50, not A >80. CLAUDE.md mandates >80 bands; changing frozen grading math + all UI on one literature pass is risky. Action: verify with the team's official problem-statement docs; if confirmed wrong, unfreeze grading.py with tests in Phase C | .agent/EVIDENCE_AUDIT.md |
| D6 | 2026-08-24 | PS number 26046 vs SIH26031 flagged for confirmation | archive search suggests DoCA onion PS is SIH26031 | .agent/EVIDENCE_AUDIT.md |
| D7 | 2026-08-24 | D5 RESOLVED - keep A>80 bands + ICAR-DOGR name. DS-001 web verification found dogr.res.in Agropedia source supporting >80; R-001's counter-sources were grader sieve classes, not grade standards. Mitigation: cite source+access date on report.html method note; correction appended to EVIDENCE_AUDIT.md | DS-001 report, HIGH confidence |
