# Persistent Codex work ledger — P3

State: **CANDIDATE**. `EXTERNAL_TRANSFER_READY` and `READY_INTERNAL` are not asserted.

## Implemented product

- One deterministic, model-free workflow supports C01–C05 through the local UI and CLI, with typed evidence, source lineage, local JSON/bundle selection, export, cancellation, and refusal/abstention paths.
- C01 covers observed radial/sector summaries, numeric edge-center with uncertainty when supplied, direction and exploratory local clusters, categorical die/bin counts, and defect-coordinate counts. Unobserved sites are never filled.
- C02 aligns exact same-wafer/lot observations; a pair with different masks can use a predeclared exact-common-site policy only when declared overlap and coverage limits pass. C03 uses exact context, spatial blocks, wafer-level uncertainty, and leave-one-lot-out sensitivity. C04 uses a leave-one-wafer-out spatial max-T rank screen; localized sites are not individually significant. C05 supports exact-site or adequately covered radial/sector profile comparisons across masks, and its bounded index holds a validated snapshot.
- Configurable MCP stdio and Streamable HTTP clients, exact tool and approved-plan checks, bounded read-only access, semantic/relationship validation, source lineage, cancellation, and a synthetic mock are included. Production endpoint, mappings, credentials, source grants, and approvals are not included.
- `INTERNAL_AUTHORIZED` analysis remains refused; company mappings and model endpoints are pending internal qualification.

## Evidence recorded

- Source commit: `ef5550c553ce8405437d08393b133c2b2e63ea4a`; canonical source-tree SHA-256: `b9caccc7d066bb2a005ed8c0ed059c00baad6ac333d125e87d5f17407ddde23a`.
- `python bootstrap_check.py`: PASS with an 89-file integrity manifest and all 78 tests passing.
- `python -m unittest discover -s tests`: 78 tests pass. `node --check ui/app.js`: PASS.
- `qualification/verify_critical_cases.py`: 12/12 frozen P3 cases pass.
- `qualification/run_scientific_benchmark.py`: 100/100 independent numeric oracles pass; the 13,000-site fingerprint p95 was 73.1 ms with 6.0 MB traced peak allocation. On 1,000 compatible synthetic 13-site maps, direct-search p50 was 146.3 ms and indexed-search p50 was 64.2 ms with result parity; index build was 1.06 s with 13.4 MB incremental traced allocation. These are build-host synthetic timings, not target thresholds.
- `qualification/run_local_qualification.py`: 78-test suite, synthetic demo, and JS syntax pass; internal preflight reports `PENDING_INTERNAL`.
- `qualification/run_blocked_egress_check.py`: host OS sandbox denied outbound sockets while the synthetic CLI completed. This does not establish company target OS or egress policy.
- `qualification/supply_chain_audit.py`: 82 inventoried files, zero third-party Python imports, and no remote UI assets. Rights review and a current vulnerability database/scanner remain pending.
- `release/LOCAL_UI_EVIDENCE.json`: one in-browser synthetic C01–C05 walkthrough completed with all five capability cards `VALID`; this is not an engineer usability study.
- `python release/build_candidate.py`: two deterministic builds matched; the fresh-extracted archive passed all 78 tests and the synthetic demo using Python without site packages on macOS arm64/Python 3.11.7. The ZIP SHA-256 and full log are recorded in `release/PACKAGE_QUALIFICATION.json` and its sidecar.

## Remaining gates

- `PENDING_INTERNAL`: actual authorized Samsung MCP permissions/bindings, source grants, semantic and relationship mappings, endpoint/auth configuration, target OS/network policy, security and engineering approvals, and the first true-data engineer investigation.
- `NOT_VERIFIED`: literal R01–R53 and Golden Standard reconciliation. Their authoritative source text is absent from this folder; no requirement text has been invented.
- `PARTIAL`: target-OS/company-egress qualification, real-data scientific calibration, retrieval relevance, engineer usability/task-time study, and precommitted production thresholds.
- `PENDING_EXTERNAL`: source redistribution rights and current vulnerability scanning/database review. No root source license or scanner database is supplied locally.

## Evidence paths

The machine-readable gate ledger is `release/GATE_REPORT.json`; per-gate statuses also appear in `qualification/external_gates.csv`. Rebuild and offline test output is recorded in `release/PACKAGE_QUALIFICATION.json`, with the ZIP SHA-256 sidecar in `release/p3-candidate-20261122.zip.sha256`. Host-only egress evidence is `release/OFFLINE_RUNTIME_EVIDENCE.json`.
