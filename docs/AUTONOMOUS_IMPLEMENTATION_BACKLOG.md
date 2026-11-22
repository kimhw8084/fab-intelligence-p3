# Autonomous implementation backlog — FAB Spatial & Yield Intelligence

This ordered backlog is suitable for an empty Codex repository. Maintain `progress/STATE.md` as a durable work ledger, not a substitute for execution. Always choose next release-critical gap by its engineering risk, not aesthetic appeal.

## Stage 0 — Reproducible bootstrap, architecture freeze (first work)
- [x] Run integrity check, basic tests and seeded 13,000-table generator; classify the result as a candidate, not a release.
- [x] Read the supplied contracts, specs, policies and critical tests. Record the gap inventory; preserve the frozen shared v1 schema and folder/API boundaries.
- [x] Check the supplied folder for the authoritative R01–R53/Golden source; the literal text is absent and remains unverified. Do not invent requirement text.
- [x] Establish a product vertical-slice E2E harness with local selection/upload, deterministic calculation, typed evidence, refusal and export.

## Stage 1 — Full integrated product behavior
- [x] Implement C01: Spatial Fingerprint; independently validate result and negative path.
- [x] Implement C04: Spatial Anomaly; independently validate result and negative path.
- [x] Implement C05: Historical Similarity; independently validate result and negative path.
- [x] Implement C02: Spatial Evolution; independently validate result and negative path.
- [x] Implement C03: Downstream Association; independently validate result and negative path.
- [~] Implement source/relationship permission checks and rigorous provenance; synthetic denial, approved-relationship checks, lineage and refusal exist, while real source grants and mappings remain internal.
- [x] Build the local interactive UI with empty/error/permission/cancel/recovery paths and source-to-claim evidence drilldown; one synthetic walkthrough is recorded.
- [x] Implement safe deterministic operation with model use disabled; no model path showed an objective benefit for this candidate.

## Stage 2 — Independent qualification and simplification
- [~] Build fixed challenging positive/negative cases, independent numeric oracles and metamorphic tests. Hidden real-data holdouts and blinded engineer-review tasks require qualified site data and engineers.
- [x] Establish synthetic baseline metrics and benchmark the standard-library-only stack; no third-party dependency was justified by measured need.
- [~] Fix detected false positives, invalid relationships and unsupported conclusions; regressions cover supplied challenges. Real-data calibration remains unqualified.
- [~] Record p50/p95 and peak-memory measurements for the synthetic task mix. Target thresholds and hardware-specific optimization remain pending.

## Stage 3 — External release engineering
- [~] Build and test a fresh-extraction, standard-library-only archive on the available macOS arm64 host; a host sandbox also denied outbound sockets during the synthetic CLI run. The approved target OS and company egress policy are not supplied.
- [~] Produce a source inventory/SBOM, static authorization and input-boundary tests, stop/rollback instructions, hashes and a reproducible archive. Redistribution rights and a current vulnerability scanner/database are not supplied.
- [x] Deliver file-based internal capability discovery and compatibility/semantic preflight; no company endpoint is guessed.
- [~] Execute synthetic UI and scientific flows and record machine-readable evidence. Engineer review and independent external audit remain pending.
- [~] Create and freshly verify the P3 candidate archive. Suite compatibility awaits sibling product artifacts owned by P1.

`[~]` means the external portion is done while the named site-only or unavailable qualification remains open. Current state and evidence paths are recorded in `progress/STATE.md` and `release/GATE_REPORT.json`.

## No-handoff continuation policy
Every checkbox represents work to do, not a question to ask. Codex should autonomously resolve implementation questions, seek credible documented evidence, run commands, and iterate to completion. Site-only unknowns remain PENDING_INTERNAL while all external work continues. Halt only for permission/security/legal constraints or a genuinely unresolvable requirement after all authorized alternatives are exhausted; never falsely mark a blocked gate passed.
