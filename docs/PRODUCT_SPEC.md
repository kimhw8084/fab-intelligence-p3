# Complete engineering product specification — FAB Spatial & Yield Intelligence

**Scope:** C01 Spatial Fingerprint + C02 Signature Evolution + C03 Quality Association + C04 Anomalies + C05 Similarity Search  
**Product ID:** `p3`  
**Shared interface:** `contracts/SHARED_ARCHITECTURE.md` v1.0.0  
**Starting state of supplied code:** BOOTSTRAP_ONLY. The implementation decisions and remaining candidate limitations are recorded in `docs/P3_IMPLEMENTATION_DECISIONS.md` and `release/GATE_REPORT.json`.

## Required result, not just a feature list
Reveal meaningful physical wafer patterns, spatial anomalies, historical matches and scientifically supported evolution/downstream relevance, without fabricating unmeasured pixels or causal claims from look-alike maps.

## One real end-to-end engineer workflow
**Start:** Engineer selects measured wafer/lot/map/metric/step or suspicious region, using approved wafer coordinate geometry (orientation, origin, radius, die/reticle/sampling mask).

**Finish:** One geometry-aware inspection with measured spatial fingerprint, anomaly evidence, nearest historical patterns, verified cross-step alignment and eligible downstream quality associations, all gated by data suitability.

Codex must implement the complete path, not four/five disconnected notebooks. The operator must be able to produce a new authorized investigation, inspect evidence source-by-source, understand uncertainty, save/share a reviewable artifact and rerun the same result with frozen inputs and software version.

## Combined capability contract
| Subsystem | Required source evidence | Implementation required | Explicit scientific refusal boundary |
|---|---|---|---|
| **C01+C04 characterize/detect** | Measured XY wafer coordinates, wafer geometry, metric, product/tool/sampling context | Robust ring/sector/gradient/reticle/local cluster features and comparable-population anomaly scores | Never render unmeasured space as equally observed or fabricate precision |
| **C05 historical search** | Compatible historical geometry and measurement definitions | Multiscale descriptors, spatially aligned comparisons, nearest neighbors, robust historical holdout | Visual similarity != same mechanism; quality of match reported |
| **C02 cross-step evolution** | Same wafer/approved compatible population and verified orientation/step/version | Coordinate registration, observed-to-observed comparison, signed differences and persistence with uncertainties | Different metric/layer/unit cannot be directly subtracted |
| **C03 downstream yield association** | Time-valid wafer/die mapping, measured spatial input and later electrical/yield outcome | Exact observed-site matching, fixed spatial-block centering, out-of-time holdouts grouped by wafer and lot (at least 20 distinct lots), effect estimates with confound caveats | Association != causation; yield link unavailable => feature disabled, others work |

## Shared scientific preconditions
1. Actual authorized source definitions are discovered from the existing approved Fab Insight MCP and checked for version/effective time; no invented company tool names or table joins.
2. Result data retains wafer/lot/step-instance/metric/tool/chamber where applicable, and always declares its true grain, timestamp semantics, units, sampling plan, exclusions and approved relationship source.
3. LLM may help translate user intent into a proposed plan; deterministic tools independently approve allowed sources/relationships/operations, compute results, and validate claims.
4. Every claim is typed, sourced, uncertainty-qualified, and distinguishable from a hypothesis. Invalid or incomplete analysis returns REFUSED/PARTIAL/INCONCLUSIVE as appropriate.
5. If advanced functionality requires unavailable real data, the rest of the product remains independently useful; no demo-generated fake findings in company mode.
6. No manufacturing equipment commands, recipes updates, unsupervised process holds, or other side effects.

## Expected usable deliverables
- Deterministic API/CLI and an interactive product view in ONE Fab Intelligence workspace, compatible with P1–P4 manifests.
- Source, population and assumption inspector; explanatory visuals with tabular alternatives; missing-data and refusal handling; evidence dossier with immutable source provenance.
- Independent scientific tests, held-out challenge suites, model-off path, permission-denial tests, full integration and UI interaction verification.
- Fully offline and tested target-OS binary/dependency package, licensing and SBOM, checksums, rollback/kill switch, minimal authorized internal MCP/model preflight.
- Reproducible user task evaluations and a nonfabricated ROI study plan; no unmeasured claims of customer adoption/financial returns.

## Non-goals and controlled dependencies
- Not a new semantic approval system or replacement for Fab Insight MCP.
- Not a generic RAG chatbot, autonomous production control service, or unrelated corporate workflow tool.
- Not a duplicate of the existing standalone sampling-prediction project.
- Not a promise that synthetic data proves any Samsung engineering effect.
- Keep independent capability modes when full cross-process/yield/change-control data is unavailable.

## Mandatory review artifacts
1. Algorithm and OSS tournament (`docs/SCIENCE_AND_METHODS.md`), showing why each included component is needed.
2. Data/source contract, every real permission/scope and invalid join case.
3. Product user journey, edge states and UI test evidence.
4. Scientific negative/positive oracles, verified comparisons with a simple baseline.
5. `release/GATE_REPORT.json` with gate-by-gate actual evidence and honest states.
6. Transfer package hash, offline dependency provenance, approved licensing and valid internal first-run preflight.
