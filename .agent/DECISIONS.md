# DECISIONS

| # | Date | Decision | Rationale | Evidence |
|---|------|----------|-----------|----------|
| D1 | 2026-08-24 | Model locked to openrouter/stealth/ox-alpha for all agents | explicit user requirement; model present in opencode catalog | `opencode models` output |
| D2 | 2026-08-24 | Ship end2end=False (NMS path) | +0.5 mAP, refer rate 1.4% vs 14.1% | STATUS.md measured table |
| D3 | 2026-08-24 | mat_edge rung demoted below carried, confidence 0.25 | 16.9mm MAE vs caliper truth | occlusion_stress + caliper per-rung table |
| D4 | 2026-08-24 | merge_looks uses max per-look defect rate, pooled sizes | concatenation preserves occlusion bias | Defect MAE 7.34→2.95 |
