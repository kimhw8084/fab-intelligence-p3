# Persistent Codex work ledger — P3

State: **CANDIDATE**. `EXTERNAL_TRANSFER_READY` and `READY_INTERNAL` are not asserted.

## Implemented product

- C01–C05 deterministic, model-free analysis is preserved in `products/p3/engine.py`; CLI inputs/outputs remain synthetic or caller-supplied and carry provenance. Refusal and abstention rules prevent unsupported geometry, joins, comparisons, or causal claims.
- P3 contributes a headless React panel and module metadata through P1's shared UI contract. P1 owns the suite shell, route, token system, request lifecycle, and shared chart renderer. P3 has no standalone page, route server, or chart dependency.
- The official MCP Python SDK 2.3.0 supplies protocol/transport behavior. `ReadOnlyMCPAdapter` retains product authorization, semantic binding, bounded reads, provenance, audit, and refusal policy. The complete local macOS arm64 CPython 3.11 candidate wheelhouse is hash-locked; internal MCP authority is not configured.
- Five Golden skills were adapted into `.agents/skills/`; their `.opencode/skills/` copies match the pinned source. Golden's 0.1.0-dev fast and full checks were run; the full report passes five rules and leaves 14 mandatory rules `NOT_RUN`, so it is not release qualification.

## Evidence recorded

- Product Python suite: 77 tests pass. The P1-hosted React panel checks pass all five tests and strict TypeScript checking under Node 26.13.0, matching the P1 engine declaration.
- Scientific catalog: all 12 frozen P3 critical cases pass. The independent numeric benchmark passes 100/100 cases. In the latest isolated run, a synthetic 13,000-site fingerprint had p50 67.0 ms and p95 69.5 ms; for 1,000 compatible historical maps, direct-query p50/p95 was 145.3/146.0 ms versus indexed p50/p95 63.6/64.9 ms, with result parity. Index build was 1.05 s with 13.42 MB incremental traced allocation. These measurements describe synthetic local workloads, not company thresholds.
- Official SDK candidate: offline `--no-index --require-hashes` install and `pip check` pass from 28 bundled wheels; 15 SDK and logical-adapter tests pass for stdio and Streamable HTTP fixtures. The supply audit verified 28 wheel hashes and all 28 embedded license-file hashes; three missing metadata expressions were resolved from verified MIT license texts. First-party licensing and company rights review remain pending.
- Host egress evidence: the macOS sandbox denied the outbound socket probe while the synthetic workflow completed all five capabilities. This is not company target/network-policy qualification.
- NiceGUI Base candidate evaluation is in `release/REUSE_COMPARISON_EVIDENCE.json`. A fixed 100 mm geometry with observations only through 60 mm makes P3 correctly report no physical edge sample; the candidate helper normalized to observed radius and reported two outer samples with a 7-unit difference. The alpha framework is not a P1 React module, and its installed distribution had no license metadata.
- `release/SBOM.spdx.json` lists source files and the 28 candidate wheel packages. Only the macOS arm64 CPython 3.11 candidate wheelhouse is present. The source license, company redistribution rights, vulnerability scanner/database, Windows/Linux MCP installs, P1 suite host, company source mappings/approvals, and engineer study remain unqualified.
- Golden evidence: fast mode passes 2 rules, defers 11, and leaves 6 applicability/criticality decisions `NOT_RUN`; full mode passes 5 rules and leaves 14 mandatory rules `NOT_RUN`. Both reports say `qualifies_release: false`; see `docs/GOLDEN_REUSE_MAPPING.md`.

## Remaining gates

- P1 must approve C01–C05 capability IDs and a versioned spatial-map renderer contract before actual suite-host integration. The requested changes are recorded in `proposals/CHANGE-002-p3-spatial-map-and-capability-extension.md`.
- Company-side gates remain `PENDING_INTERNAL`: actual Samsung MCP permissions/tool bindings, data-source grants and semantics, endpoint/auth config, target OS/network policy, approvals, and first true-data engineer investigation.
- Target-OS/offline and full release security remain partial/pending: only local macOS arm64/Python 3.11.7 evidence exists; public source licensing and current vulnerability review are incomplete.
- Scientific calibration, retrieval relevance, target thresholds, and engineer usability/task-time studies require approved data and participants.
- Literal R01–R53 and Golden Standard reconciliation remains `NOT_VERIFIED`; authoritative text is absent from this folder and no requirement text has been fabricated.

## Evidence paths

Machine-readable gates: `release/GATE_REPORT.json` and `qualification/external_gates.csv`. Local test records: `release/LOCAL_TEST_EVIDENCE.json`, `release/LOCAL_TEST_LOG.txt`, and `release/LOCAL_UI_EVIDENCE.json`. Scientific records: `release/CRITICAL_CASE_EVIDENCE.json`, `release/SCIENTIFIC_PERFORMANCE_BENCHMARK.json`, and `release/REUSE_COMPARISON_EVIDENCE.json`. Offline SDK and host-egress records: `release/PACKAGE_QUALIFICATION.json` and `release/OFFLINE_RUNTIME_EVIDENCE.json`.
