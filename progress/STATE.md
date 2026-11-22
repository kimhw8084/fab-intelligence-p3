# Persistent Codex work ledger — P3

State: **CANDIDATE**. `EXTERNAL_TRANSFER_READY` and `READY_INTERNAL` are not asserted.

## Implemented product

- C01–C05 run in one deterministic, model-free workflow with a local UI/API, typed evidence, source lineage, an integrated synthetic fixture, JSON export and refusal/abstention paths.
- Spatial calculations preserve the observed-site mask; C02 matches physical sites only; C04 uses distinct earlier baseline lots and multiple-test correction; C05 ranks compatible prior maps without causal language; C03 requires approved die mapping, temporal ordering, exact site coverage, spatial blocks, and at least 20 holdout wafers from distinct lots.
- Real company adapters, data, and semantics are not included. `INTERNAL_AUTHORIZED` mode is refused; site-side preflight stays `PENDING_INTERNAL`.

## Evidence recorded

- `python bootstrap_check.py`: PASS after regenerating the exact package manifest; integrity covers 79 files and all 52 tests pass.
- `python -m unittest discover -s tests -v`: 52 tests pass, including negative paths and context/lot leakage checks.
- `python qualification/verify_critical_cases.py`: 12/12 frozen P3 cases pass.
- `python qualification/run_scientific_benchmark.py`: 100/100 seeded numeric oracle cases pass; 13,000-entry synthetic catalog; p50/p95 and memory measurements are in the benchmark artifact. These are synthetic, build-host timings.
- `python qualification/run_local_qualification.py`: unit suite, integrated demo, Node syntax pass; internal preflight reports `PENDING_INTERNAL`.
- `python qualification/supply_chain_audit.py`: zero third-party Python imports and no remote UI assets. Rights review and current vulnerability database/scanner remain pending.
- `python release/build_candidate.py`: two deterministic ZIP builds matched; fresh extraction passed all tests and the synthetic demo with Python site packages disabled on macOS arm64/Python 3.11.7.
- `python qualification/run_blocked_egress_check.py`: macOS sandbox denied a direct outbound socket, while the model-free synthetic CLI ran with all five capabilities valid. This qualifies only the local host sandbox path, not company target policy.
- Manual local UI walkthrough recorded in `release/LOCAL_UI_EVIDENCE.json`; one synthetic investigation, not an engineer usability study.

## Remaining gates

- `PENDING_INTERNAL`: approved Samsung MCP bindings/permissions, semantic and relationship mappings, authorized endpoint/auth configuration, target platform/network policy, actual security approval, and first true-data engineer investigation. No company data or approval is fabricated.
- `NOT_VERIFIED`: literal R01–R53 and Golden Standard reconciliation; the canonical source text is not included in this folder per `requirements/AUTHORITY_AND_GAPS.md` and is not a prerequisite for this external build.
- `PARTIAL`: actual target-OS and company egress-policy qualification, engineer usability/task-time study, precommitted production task thresholds, retrieval relevance and real-data scientific calibration.
- `PENDING_EXTERNAL`: source redistribution rights and current vulnerability scanning/database review. No root source license or scanner database is supplied locally.

## Authorized follow-up

The candidate package is prepared for site-side qualification when authorized resources exist locally: run the internal preflight with approved read-only Samsung MCP bindings, approved semantics/relationships, target OS and egress policy; then conduct the true-data pilot and engineer review. Separately complete the rights review and current vulnerability scan before redistribution. These are qualification gates, not permission to infer internal readiness from synthetic evidence.
