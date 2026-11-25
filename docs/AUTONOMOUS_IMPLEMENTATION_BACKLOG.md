# Autonomous implementation backlog — FAB Spatial & Yield Intelligence

This ordered backlog is suitable for an empty Codex repository. Maintain `progress/STATE.md` as a durable work ledger, not a substitute for execution. Always choose next release-critical gap by its engineering risk, not aesthetic appeal.

## Stage 0 — Reproducible bootstrap, architecture freeze (first work)
- [x] Run integrity check, basic tests and seeded 13,000-table generator; classify the result as a candidate, not a release.
- [x] Read the supplied contracts, specs, policies and critical tests. Record the gap inventory; preserve the frozen shared v1 schema and folder/API boundaries.
- [x] Check the supplied folder for the authoritative R01–R53/Golden source; the literal text is absent and remains unverified. Do not invent requirement text.
- [x] Establish a product vertical-slice E2E harness with official MCP SDK transport, exact approved tool/plan bindings, server-returned semantic-role mapping, bounded current/prior/baseline/history/quality reads, immutable source-version correlation across semantics/read/audit, deterministic C01–C05 analysis, and a validated evidence envelope. The synthetic server verifies all five results and fail-closed permission, stale semantics, source drift, relation, geometry, unit, response-size, sampling and cancellation cases. Company sources remain `PENDING_INTERNAL`.

## Stage 1 — Full integrated product behavior
- [x] Implement C01: Spatial Fingerprint; independently validate result and negative path.
- [x] Implement C04: Spatial Anomaly; independently validate result and negative path.
- [x] Implement C05: Historical Similarity; independently validate result and negative path.
- [x] Implement C02: Spatial Evolution; independently validate result and negative path.
- [x] Implement C03: Downstream Association; independently validate result and negative path.
- [~] Implement source/relationship permission checks and rigorous provenance; synthetic end-to-end approval, source scoping, exact plan/tool hashes, row lineage, correlated remote audit and refusal are verified. Real source grants and mappings remain internal.
- [x] Build the P3-owned standalone React reference host and headless suite panel with typed spatial rendering, source inspection, C01-C05 detail, provenance, cancellation/refusal/recovery, count-checked semantic tables, and canonical evidence export. Both the host and panel suites run through one P3-owned locked Vitest toolchain; P3 runs independently of P1. The P1 route compatibility issue is a separate host integration gate, and formal accessibility/engineer studies remain pending.
- [x] Implement safe deterministic operation with model use disabled; no model path showed an objective benefit for this candidate.

## Stage 2 — Independent qualification and simplification
- [~] Build fixed challenging positive/negative cases, independent numeric oracles and metamorphic tests. Hidden real-data holdouts and blinded engineer-review tasks require qualified site data and engineers.
- [x] Establish synthetic baseline metrics and benchmark the standard-library-only stack; no third-party dependency was justified by measured need.
- [~] Fix detected false positives, invalid relationships and unsupported conclusions; regressions cover supplied challenges. Real-data calibration remains unqualified.
- [~] Record p50/p95 and peak-memory measurements for the synthetic task mix. The refreshed 1,000-map retrieval benchmark includes five generated regimes, 50 repeated queries, alternate sampling, ineligible historical records, relevance oracles, 21.5 MB index-build allocation, explicit invalidation/refresh, and direct/index parity. C04 now includes a whole-wafer temporal shift screen; full synthetic calibration and its subtle-drift limits are recorded in `release/SCIENTIFIC_PERFORMANCE_BENCHMARK.json`. Product targets and hardware-specific optimization remain pending.

## Stage 3 — External release engineering
- [~] Build and test a fresh-extraction, standard-library-only archive on the available macOS arm64 host; a host sandbox also denied outbound sockets during the synthetic CLI run. The approved target OS and company egress policy are not supplied.
- [~] Produce a source inventory/SBOM, static authorization and input-boundary tests, stop/rollback instructions, hashes and a reproducible archive. Redistribution rights and a current vulnerability scanner/database are not supplied.
- [x] Deliver file-based internal capability discovery and compatibility/semantic preflight; no company endpoint is guessed.
- [~] Execute synthetic UI and scientific flows and record machine-readable evidence. Engineer review and independent external audit remain pending.
- [~] Create and freshly verify the P3 candidate archive. Standalone P3 is verified; compatibility with the current P1 route remains separately pending until its typed converter/renderer migration is accepted.
- [~] Complete Golden's 14 formerly `NOT_RUN` checks individually. The latest pinned replay passes 10/19 rules including PY-003, WEB-001/002, UI-001 and SEC-001; 9 remain `NOT_RUN` for runner limitations or missing owner applicability. Golden 0.1.0-dev still does not qualify the release.

`[~]` means the external portion is done while the named site-only or unavailable qualification remains open. Current state and evidence paths are recorded in `progress/STATE.md` and `release/GATE_REPORT.json`.

## No-handoff continuation policy
Every checkbox represents work to do, not a question to ask. Codex should autonomously resolve implementation questions, seek credible documented evidence, run commands, and iterate to completion. Site-only unknowns remain PENDING_INTERNAL while all external work continues. Halt only for permission/security/legal constraints or a genuinely unresolvable requirement after all authorized alternatives are exhausted; never falsely mark a blocked gate passed.
