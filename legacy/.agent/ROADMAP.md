# ROADMAP — SAMA self-improving engineering loop

## Phase B — Core correctness (now)
- [ ] AUDIT-001: full-repo audit (endpoints, error paths, grading math vs spec)
- [ ] Backend: fuzz malformed requests to /analyze, /finalize; verify JSON errors everywhere
- [ ] QA: failure-injection suite (empty/invalid image, zero detections, DB locked)
- [ ] Data: verify dataset split integrity + no public leakage into valid/test

## Phase C — Differentiation
- [ ] Two-Look merge behavior covered by regression test
- [ ] Referral-rate reporting surfaced in API response and certificate
- [ ] Drift monitor edge cases

## Phase D — End-to-end
- [ ] smoke_test green after every change
- [ ] replay mode covers arbitration + verify pages

## Phase E — Adversarial
- [ ] red-team findings triaged; unsupported claims removed
- [ ] evidence audit of all UI/doc claims

## Phase F — Stabilization (final 10%)
- [ ] latency re-check, docs current, demo script rehearsed via commands only
