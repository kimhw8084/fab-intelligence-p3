# P3 Final Handoff and Frozen Baseline — 2026-11-23

## Frozen candidate

- Base commit: `83a08682a189944adf984fe891353e84485ac381`; candidate source remains an uncommitted tested worktree snapshot.
- Source-tree SHA-256: `9044a31aa5e79480aaa614496d6ee05778ea72862db3df07bc518030d700755f`.
- Archive: `release/p3-candidate-20261123.zip` — SHA-256 `aa51df3d510c26d2cfa56ce13603b0d7cdb48ee16a6124de75176729df012499`, 9,284,796 bytes.
- Archive sidecar: `release/p3-candidate-20261123.zip.sha256`.
- `release/PACKAGE_QUALIFICATION.json` reports repeated deterministic builds equal and matching source-tree digest. The release archive is not rebuilt by this handoff.
- React dependency roots: React/React DOM 19.2.0, ECharts 6.1.0, TypeScript 5.9.3, Vite 7.3.8, Vitest 5.1.1. Node engine constraint `^22.12.0 || ^24.0.0 || >=26.0.0`; tested with Node.js v26.13.0 and npm 11.20.0. `package-lock.json` SHA-256: `fab3478bb04736094b3f3e3e84f93edfb44d667bf7b31c90273dd3b82bd64a5f`.
- Python target: macOS-26.6.2-arm64-arm-64bit, Python 3.11.7; official MCP SDK 2.3.0. The 28-wheel hash lock is `vendor/mcp-sdk-2.3.0/macos-arm64-cp311/requirements.lock` (SHA-256 `91bb6e70d813a23f630db5b3956e2755558dbd5c1b25ca6a17dcc5382fd84de7`).

## Acceptance evidence already present

- Fresh archive extraction, demo, hash-locked offline Python SDK installation, `pip check`, and 123 Python tests pass: `release/PACKAGE_QUALIFICATION.json`.
- React host/module: 15/15 tests, strict TypeScript, Vite build pass: `release/LOCAL_UI_EVIDENCE.json` and `release/P3_SOURCE_VERSION.json`.
- Scientific acceptance: 14/14 frozen critical cases and 100/100 independent numeric oracles: `release/CRITICAL_CASE_EVIDENCE.json` and `release/SCIENTIFIC_PERFORMANCE_BENCHMARK.json`.
- Real local-browser synthetic investigation: five bounded reads; C01–C05 `VALID`; numeric/category/defect/missing rows preserved; refusal/cancel/retry; provenance inspection; evidence export SHA-256 `eaae2687607fff72a8194fa4e7c0de2bd38819005c917ae918e8aa2afc025e22`. Record: `release/P3_STANDALONE_BROWSER_EVIDENCE.json`.

## Executable shared-suite handoff

The single machine-readable integration manifest is [NEXT_ACTIONS.json](NEXT_ACTIONS.json). It records entry points, contracts, capabilities, fixtures, dependency lock hashes, lifecycle, export callback, exact commands and expected results, current P1 diagnostics, and host ownership.

- P3 suite panel: `products/p3/ui/P3Panel.tsx#P3Panel`; module registration: `integration/p3-suite-ui-module.v1.json`.
- Standalone P3 application: `products/p3/reference_host/src/App.tsx#App`; this is not the product-neutral suite route.
- Typed P3 model/renderer reference: `products/p3/contracts/spatial-map.v2.*` and `products/p3/reference_host/src/SpatialMapRenderer.tsx#SpatialMapRenderer`.
- Synthetic protocol/evidence path: `fixtures/p3_integrated_synthetic.json`, `tests/fixtures/mcp_mock_server.py`, `qualification/synthetic_mcp_peer.py`, `tests/test_reference_host.py`.
- Suite spatial visualization and the accessible typed observation table remain shared-host responsibilities. Do not feed `fab-spatial-map.v2` through the P3 panel’s legacy `P3WaferMap` v1 prop: it lacks modality and per-observation kind. Mount P3Panel with its map prop omitted and mount the same typed result in the shared host renderer/table, or coordinate a future versioned module-prop extension. Preserve the existing converter regression fixture/tests unchanged.

## P1 defects and acceptance

Current diagnostic: `release/P1_MODULE_INTEGRATION_EVIDENCE.json` (`PARTIAL_P1_SHARED_CONTRACT_CHANGES_REQUIRED`). The actual P1 Python/TypeScript route has not passed. Exact diagnostics in `release/P1_MODULE_INTEGRATION_EVIDENCE.json`: the TS path changes numeric category `2` to string `"2"`, loses the numeric type of defect code `7`, counts an unlabeled event as missing, and does not refuse continuous string `"42.5"`; the Python path changes category `2` to `"2"`, accepts continuous `"42.5"` as a string, drops defect label `"BRIDGE"` and counts it missing, and counts an unlabeled event as missing. Explicit numeric null is retained. The v1 shared schema cannot represent modality or observation kind. P1’s routed P3 source snapshot is stale.

After the host changes, P1 should run from this repository root:

```sh
python qualification/run_p1_module_integration.py
```

The expected acceptance is runner status `PASS_P3_MODULE_MOUNTED_WITH_P1_SHARED_RENDERER`, 4/4 generated Vitest cases, strict TypeScript exit 0, no `p1_host_owner_changes`, current source snapshot hashes, typed input/output counts reconciled, and a passing real route with the v2 map/table. Until then, **actual suite integration remains pending**.

## Bounded wafermap reuse decision

Reviewed upstream `wafertools/wafermap` v0.40.1 and `main` commit `28a2479e67ba601aff3a70a6809a8c7d46f5fe0c` on 2026-11-23. It is MIT and advertises no runtime dependencies, but its API is organized around die-grid coordinates and numeric bins/test values. Its API documentation defines `x/y` as integer prober/die positions and derives physical positions from die pitch; invalid/non-finite readings can be treated as missing/dropped, and partial-coverage geometry requires authoritative wafer center/diameter. That does not preserve P3’s arbitrary verified physical site coordinates, typed category/event-vs-missing semantics, or canonical provenance/export model. It also brings a second canvas map and its own toolbar into a stack that already has P3 ECharts and a shared suite renderer. **Decision: reject for P3 integration; do not add or bundle it.** A future die-grid product could evaluate it independently with matching source data and acceptance cases. Sources: [upstream README and MIT license](https://github.com/wafertools/wafermap), [coordinate/data API](https://wafertools.github.io/wafermap/api/core/), [render API](https://wafertools.github.io/wafermap/api/render-map/), and [bins/value semantics](https://wafertools.github.io/wafermap/guide/data/).

## Remaining gates and pause

- P3 implementation complete for synthetic external scope; standalone browser workflow verified; integration handoff ready.
- Actual multi-product suite integration pending P1’s typed contract, converter, renderer/table, source snapshot, and route tests.
- External transfer not qualified: first-party rights, third-party redistribution, target OS/egress policy, independent security review, formal accessibility review, and release authorization remain pending.
- Internal qualification pending real approved MCP grants/semantics, company data and calibration, and engineer acceptance.
- No source publication or transfer was performed. **Pause P3-specific development after this handoff. Resume only for a genuine shared-integration defect, independently evidenced scientific finding, or authorized qualification task.**


## 2026-11-23 independent engineer-challenge milestone

This is a separate P3 working revision. The frozen source tree and candidate archive were rechecked from the original checkout and remain `9044a31aa5e79480aaa614496d6ee05778ea72862db3df07bc518030d700755f` and `aa51df3d510c26d2cfa56ce13603b0d7cdb48ee16a6124de75176729df012499`. No archive rebuild, push, transfer or company data access occurred.

### Weaknesses found and changes

1. **C01 dense-map masking:** an independent challenge showed the fixed raw-value local screen missed a subtle planted cluster under a broad linear wafer gradient. Added a density-gated observed-site plane-residual screen for maps with at least 200 numeric sites, verified orientation and broad quadrant coverage. Sparse maps retain the original raw screen; values are not inferred; candidate groups remain exploratory.
2. **C04 finite-rank headline:** the 20-lot synthetic case had empirical p=1/21=0.0476 at alpha=0.05. The prior headline said “crossed its supplied threshold” and left rank resolution to the caveat. It now says the result meets alpha only at the minimum resolvable rank and calls it coarse conditional screening, not factory confidence.
3. **C03 cohort selection:** an independent null challenge generated independent feature/outcome values for 80 candidate wafers and selected the 20 largest positive within-wafer correlations after inspecting outcomes. The frozen engine returned VALID positive associations with nominal intervals excluding zero in 40/40 fixed seeds (mean reported r=0.1869). C03 now requires reviewed, predeclared, outcome-blind complete eligible-wafer-frame semantics and reconciliation of eligible, selected and observed wafer counts. Unsupported or missing designs abstain. Evidence displays the frame/rule and states P3 cannot independently audit the source registry. The MCP semantic path carries these fields.

The browser task also showed that C02 repeatability uncertainty was buried below the transition details; the capability summary now exposes per-transition propagated 1-sigma uncertainty alongside exact common-site counts and coverage.

### Independent proof

- C01 script `qualification/run_c01_density_benchmark.py`: 80 null and 80 planted maps per missingness condition, comparing frozen raw screening to the dense candidate. No missing: planted detection 0/80 to 74/80, null candidates 0/80 to 0/80; mean planted-site recall 0.1669 and candidate-site precision 0.7865. With 40% random missing: planted detection 0/80 to 54/80, null candidates 0/80 to 0/80; recall 0.1449 and precision 0.6569. Exploratory groups are not calibrated alerts.
- C03 script `qualification/run_c03_selection_bias_benchmark.py --baseline-root ../FAB_INTELLIGENCE_P3_CODEX_LAUNCHKIT_2026-11-22`: frozen baseline accepted all 40 post-outcome-selected cohorts (40/40 nominal intervals positive/excluding zero; mean reported r=0.1869); revised engine abstained in 40/40 because the cohort was outcome-informed and did not represent a complete eligible frame. Synthetic guard test only; source-registry truth and causation remain outside P3's proof.
- Real local browser used the actual standalone host and official-SDK synthetic MCP workflow: five bounded reads, all C01-C05 VALID on the engineer challenge; latest full-run UI latency 186 ms. C03 showed r=-0.021, 95% wafer interval [-0.112, 0.071], declared complete frame 20/20, and its source-registry limitation. C04 showed the p=0.0476 rank-floor qualifier. C02 previously showed 44 exact sites for each transition, step coverages 91.7%/100.0% and 100.0%/91.7%, and propagated 1-sigma 0.038 nm per transition. Browser keyboard navigation advanced C01 → C02 → C03 with no console errors. The full-run browser evidence digest was `6c609dfa12784973c6eaf2da2d4c28cafcf9ee867a332fd7a2ca9d616ecf0e2a`; the exported canonical evidence was observed in the UI, not written as a release package.
- Regression: 127 Python tests passed; 19 React tests passed; strict TypeScript, Python compileall and Vite production build passed. The build retains the existing large-chunk advisory (756.51 KB minified JS). `git diff --check` passed.
- Current working source-tree SHA-256: `25cdaf1b0c48df96739473c73081800877c85c61080fe14c532d289ef3444830`.

### Changed files in this milestone

`products/p3/engine.py`; `products/p3/reference_host/src/App.tsx`; `products/p3/reference_host/src/App.test.tsx`; `fabintel/mcp_workflow.py`; `qualification/synthetic_mcp_peer.py`; `qualification/engineer_challenge.py`; `qualification/generate_synthetic_workflow.py`; `qualification/run_scientific_benchmark.py`; new `qualification/run_c01_density_benchmark.py`; new `qualification/run_c03_selection_bias_benchmark.py`; `tests/test_p3_integrated.py`; `tests/test_mcp_adapter.py`; `fixtures/p3_integrated_synthetic.json`; `fixtures/p3_engineer_challenge.json`; `README.md`; `docs/SCIENCE_AND_METHODS.md`; `docs/MCP_ADAPTER.md`.

### States and next executable action

- P3 implementation: improved and regression-verified against synthetic scope.
- Standalone browser workflow: verified with synthetic official-SDK MCP; no manufacturing validation.
- Shared-suite compatibility: existing P3 handoff unchanged; actual suite integration remains pending.
- External transfer/security/rights/target OS: not newly qualified; remain pending.
- Internal company qualification: pending permissions, real source semantics/data, calibration and engineer acceptance.

The C05 challenge is now complete; the result and next task are recorded below.


## 2026-11-23 C05 retrieval, C01 density and interpretation follow-up

This work continues only in `../FAB_INTELLIGENCE_P3_NEXT_PHASE_2026-11-23`. The immutable source tree remains `9044a31aa5e79480aaa614496d6ee05778ea72862db3df07bc518030d700755f`; the candidate archive remains `aa51df3d510c26d2cfa56ce13603b0d7cdb48ee16a6124de75176729df012499` in both the working and original checkout. No package rebuild, push, company-data access or transfer occurred. Working source-tree digest is `5436b57e4939b374ab7b0e3b9a7fba82ed7424a070a527298ef43ddd387cd23a`.

### C05 — cross-layout alias and adversarial context

- A radial-by-sector signature showed that separate radial and sector marginals can exactly alias different patterns across changed sampling layouts. Before the joint descriptor, the wrong analog ranked first in all 40 fixed seeds (0/40 correct); the candidate with a shared radial-sector descriptor ranked the true analog first in 40/40.
- Cross-layout retrieval now requires at least eight shared radial-sector bins, reports bin coverage, and discloses that within-bin structure remains unresolved. It uses measured descriptors only; no site values are reconstructed.
- The existing similarity regression now also challenges a same-mean/different-pattern decoy, wrong product/layer/metric, and a future record. Compatible true pattern remains top-ranked; incompatible/future rows are excluded, and direct/index results agree.
- The unchanged 1,000-map labeled relevance oracle remains 5/5 top-five sets passing, mean precision@5 1.0, direct/index parity true. Index build was about 2.4 s, peak traced memory about 29.1 MB; five sampled indexed queries were 56–92 ms versus 227–275 ms direct. This is synthetic scale and resemblance does not establish cause.
- Actual browser C05 summary showed 27 common joint bins, 48 target vs 44 analog sites, excluded incompatible/future records, and stated no reconstruction or causal inference.

### C01 — density-adaptive cells with resolution fallback

- A 340-site measured wafer on a smooth quadratic radial background exposed that the prior 16×16 minimum grid supplied too few sites per cell for its three-observation candidate rule. The previous behavior missed a planted 8 nm shift on four measured sites. The 8–32 density-sized grid detects one four-site exploratory group at grid 10; the radial-only control has none.
- A coarser adaptive grid can dilute a weaker, previously detected 697-site signature. The engine now checks the prior 16-cell resolution only when a density-sized pass found no candidate. The 697-site synthetic MCP fixture again reports its existing three-site exploratory group at 18.8 mm cells. This fallback is descriptive sensitivity review, not an alert or significance test.
- Re-run of `qualification/run_c01_density_benchmark.py`: over 80 seeds per condition, null candidate counts stayed 0/80 at 0% and 40% random missingness. Planted map detection stayed 74/80 and 54/80; mean site recall 0.1669/0.1449 and candidate-site precision 0.7865/0.6569. The broad benchmark did not show a sensitivity increase, but also did not regress; the specific 340-site density failure is fixed.
- Actual browser C01 showed 697 numeric observations, one three-site exploratory group and 18.8 mm cells. The UI continues to label local groups uncalibrated.

### C02/C04 engineering limits made explicit

- C02 still performs exact common-site comparisons only. The standalone browser shows 44 matches for each step transition, coverage 91.7%/100% then 100%/91.7%, and propagated 1σ 0.038 nm. The summary now states that propagation assumes independent errors across transitions and matched sites; shared calibration covariance is not modeled.
- C04 evidence now declares `SINGLE_TARGET_CONDITIONAL_SCREEN` with `repeated_target_adjustment=NOT_APPLIED`. The actual browser showed 20 earlier lots and p=0.0476 at the minimum resolvable rank, and warns that repeated/adaptively selected target searches are not multiplicity-adjusted.

### Regression and next action

- Latest full Python suite: 129 passed. Latest React suite: 19 passed. Strict TypeScript, Python compileall, targeted `git diff --check` on this milestone’s changed files, and Vite production build pass. Vite reports the existing large-chunk advisory: 757.03 kB minified / 250.79 kB gzip.
- Full-worktree `git diff --check` still reports pre-existing trailing whitespace in the proposal date and CRLF CSV lines; the files changed in this milestone pass the targeted check.
- P3 synthetic implementation and standalone browser workflow remain verified. Actual suite integration remains pending; external transfer/rights/security/target OS remain unqualified; internal company permissions, semantics/data, manufacturing calibration and engineer acceptance remain pending.
- Next executable task: quantify C04 per-target versus repeated-target false-alert behavior on independent synthetic null streams sharing a fixed baseline. Preserve the single-target method unless the oracle supports a safe predeclared family-level API. Do not rebuild or publish the frozen candidate.


## 2026-11-23 C02 uncertainty semantics, C04 family control, and C05 scale closeout

At this C02/C04/C05 checkpoint, the working source-tree SHA-256 was `0b13e22c05c0791a9d862dc966de7eb4df1bcded993896cca9d268ce3e002f29`; the later C01 correction supersedes that digest below. The frozen original source tree remains `9044a31aa5e79480aaa614496d6ee05778ea72862db3df07bc518030d700755f`. The frozen candidate is `release/p3-candidate-20261123.zip`, SHA-256 `aa51df3d510c26d2cfa56ce13603b0d7cdb48ee16a6124de75176729df012499`, 9,284,796 bytes; the checksum was verified in both the original and working checkout. Generated progress evidence is excluded from the source digest to avoid self-reference. No archive rebuild, push, transfer or company-data access occurred.

### C02 — state the uncertainty assumption precisely

- The existing result labeled generic supplied standard uncertainty as repeatability. That claim was stronger than the source contract: cross-step and cross-site covariance are not supplied.
- The engine now emits `measurement_uncertainty` with machine-readable covariance fields marked `NOT_SUPPLIED`, `conditional_on_independence: true`, and the explicit independent-error assumption. The host labels it “Measurement uncertainty” and displays the limitation next to exact-site step changes. Scientific calculations remain conditional on the declared model; no interpolation or engine method change was made.
- Focused `ComparisonTests` passed (11 tests); the live browser showed 44 exact common-site matches for each transition, coverage 91.7%/100.0% then 100.0%/91.7%, propagated 1σ 0.038 nm, and the covariance limitation. Browser observation details are in `progress/C02_COVARIANCE_BROWSER_ACCEPTANCE.json`.

### C04 — repeated target searches and rank-limited family correction

- The independent fixed-baseline null study (`progress/C04_REPEATED_TARGET_NULL_STUDY.json`) used 20 independent shared-baseline families per distribution, with 20 targets per family and 20 baseline lots. Per-target alerts occurred in 24/400 Gaussian targets (6%) and 28/400 t(3) targets (7%); at least one alert occurred in 9/20 Gaussian families (45%) and 11/20 t(3) families (55%). These synthetic estimates are imprecise and are not manufacturing calibration.
- Per-target confidence intervals now bootstrap independent shared-baseline families (10,000 family resamples), rather than treating correlated target decisions as independent: Gaussian 95% interval 2.75–10.0%; t(3) 3.75–10.5%. Family-wise Wilson intervals are 25.8–65.8% and 34.2–74.2%, respectively.
- C04 accepts a caller-declared complete pre-reviewed target family and applies Bonferroni alpha/m while preserving the within-wafer max-T method. It abstains if the holdout rank floor cannot resolve adjusted alpha. A boundary regression covers 398 baseline lots abstaining for 20 targets and 399 lots resolving the exact 1/400 boundary. The workflow records the caller declaration but says P3 cannot audit the source registry.
- Live browser proof (`progress/C04_FAMILY_BROWSER_ACCEPTANCE.json`): five bounded synthetic SDK reads; C01/C02/C03/C05 VALID; C04 INCONCLUSIVE for family size 2 because 1/21 exceeds adjusted alpha .025; source-registry limitation visible and other capabilities remained usable.

### C05 — 10,000-map bounded retrieval stress

- `qualification/run_c05_scale_benchmark.py` and `progress/C05_SCALE_10K_BENCHMARK.json` challenge 10,000 historical maps / 293,328 measured sites, 60 relevant analogs with changing sampling masks, 500 same-pattern wrong-context decoys, 500 same-context opposite-pattern decoys, and three invalid-geometry records.
- Five independently labeled queries achieved P@5 1.0 and direct/indexed top-five parity. All incompatible-context and invalid-geometry records were excluded. Index build was 3,106.7 ms, full-snapshot refresh 2,993.5 ms; indexed median query 970.2 ms versus 3,042.3 ms direct. Traced index allocation was 331,205,524 bytes; estimated incremental peak RSS was 391,888,896 bytes and process peak RSS 528,580,608 bytes. Invalidation returned INCONCLUSIVE until refresh. The 15,000-map/500,000-site bound remains a configured limit, not a benchmark result; these are one-machine synthetic results, not a company-catalog or fleet-memory claim.

### Regression, browser, and status

- Full SDK-enabled Python suite: `rtk env PYTHONPATH=.venv/lib/python3.11/site-packages python -m pytest -q` — 129 passed. Critical catalog: `rtk env PYTHONPATH=.venv/lib/python3.11/site-packages python qualification/verify_critical_cases.py` — 14/14 passed. React: `rtk npm test -- --run` — 20 passed. `rtk npm run typecheck`, Python `compileall`, and `rtk npm run build` passed; Vite 7.3.8 reports the existing 759.50 kB minified / 251.51 kB gzip chunk advisory. Targeted `git diff --check` passed for the changed C02/C04 source, tests and science documentation.
- Standalone browser still uses the real loopback P3 host with the synthetic official-SDK MCP peer. C04 family abstention and C02 covariance disclosure were directly inspected. No company data was used.
- P3-owned implementation and synthetic standalone workflow remain verified. Shared-suite integration remains pending; external transfer is not qualified; internal permissions, semantics, data, target environment, calibration and engineer acceptance remain pending. Do not publish or rebuild the frozen archive.

### Next executable action

The C04 repeated-target task is complete. Continue only after defining a fresh failure hypothesis and an independent acceptance oracle; do not re-run the completed C01/C03/C04/C05 benchmarks just to refresh counts. A new C02 covariance input or company source mapping must remain explicitly unverified until an authorized source declares its semantics. Preserve the frozen source/archive and the separate suite, transfer and company qualification states.


## 2026-11-23 C01 physical-radius and orientation invariance correction

The planned independent C01 check exposed a concrete defect at exact radial cutoffs. The same 40 observed sites at fractions 0.1, 0.2, 0.5, 0.8 and 0.9 of a declared 150 mm wafer were encoded once in the physical frame and once in a sensor frame translated to origin `(800, -350)` mm and rotated 37 degrees. At mathematical cutoff coordinates, floating-point roundoff split samples across radial bands. Against the frozen engine, physical-frame counts were `[16, 7, 9, 8]`, while equivalent transformed-frame counts were `[12, 11, 6, 11]`; the radial means also disagreed.

The C01 normalizer now snaps only normalized radii within its existing relative geometry-validation tolerance to exact 0.2/0.5/0.8 cutoffs. It continues to compute from the verified coordinate origin and true physical radius. Candidate outputs are identical across the two frames: counts `[16, 8, 8, 8]` and means `[107.15, 107.5, 107.8, 107.9]` nm. No measured value, coordinate or missingness state is altered. The separate truncated-scan oracle uses a 150 mm physical radius with sites only through 0.65R; it reports no edge observations and withholds the edge-center comparison rather than treating the maximum sampled radius as the wafer edge.

Evidence: `progress/C01_GEOMETRY_ORACLE.json`; regression tests `test_equivalent_rotated_sensor_coordinates_preserve_physical_fingerprint` and `test_truncated_sampling_uses_verified_radius_and_coordinate_origin` in `tests/test_p3_integrated.py`. Both targeted tests pass. The full SDK-enabled Python suite now passes 131 tests; critical catalog is 14/14; Python compileall and targeted whitespace validation pass. React remains 20/20 with strict TypeScript and production build passing from the immediately preceding UI build; this C01 fix changes only Python engine/tests/science documentation.

Working source-tree SHA-256 is now `75c3ffefab1e4d827534d0c103a447bbe61c5b3bab126e9162e0e897d643766d`. Generated progress evidence is excluded from that digest. The frozen original source and `p3-candidate-20261123.zip` remain unchanged at `9044a31aa5e79480aaa614496d6ee05778ea72862db3df07bc518030d700755f` and `aa51df3d510c26d2cfa56ce13603b0d7cdb48ee16a6124de75176729df012499`.

Next independent task: challenge C02’s explicitly conditional independent-error uncertainty with a known correlated-error oracle. Keep the current qualification conditional and add covariance handling only if a typed, source-verifiable input can be defined; company-provided covariance semantics remain pending authorization.


## 2026-11-23 live C02 uncertainty communication

The engineer-facing C02 value now includes its assumption inline: “conditional 1σ assuming independent errors: 0.038 nm.” This prevents the numerical uncertainty from reading as unconditional before the broader covariance limitation is encountered. After a fresh production build and restart of the actual loopback reference host, the browser ran the synthetic MCP investigation and visibly rendered the updated text for both step transitions, each with 44 exact common sites and the existing coverage values. The displayed canonical evidence digest was `718ad486212b4c198c886ba7d8d812ff4f6e2bbc482507203e604a7cf0f67ca5`; browser details are in `progress/C02_COVARIANCE_BROWSER_ACCEPTANCE.json`.

React tests: 20 passed; strict TypeScript passed; production build passed at 759.53 kB minified / 251.52 kB gzip with the existing >500 kB advisory. The latest working source-tree SHA-256 is `84e3c0aabb39e1efd27b05943368baf82b8ddd9f95a14e1aa5acbb0139d1fe74`. The frozen source and archive remain unchanged. No company source or manufacturing data was used.

## 2026-11-23 C02 correlated-error challenge

Added the reproducible oracle `qualification/run_c02_covariance_benchmark.py`; result is `progress/C02_CORRELATED_ERROR_STUDY.json`. It verifies the C02 engine returns the independent-site/step formula for 44 matched sites, then simulates 10,000 zero-process-change investigations with the same 1.005 nm marginal uncertainty per site and a 1.0 nm shared calibration component. Only the known correlation between step-level common errors varies.

- With cross-step common-error correlation 0.0, conditional 1σ was 0.2143 nm versus 1.4144 nm under the known covariance model (6.60× ratio); 12.01% of Monte Carlo changes fell within that reported 1σ (95% Wilson 11.39–12.66%).
- At correlation 0.5, the known model σ was 1.0002 nm (4.67× ratio); empirical coverage was 17.75% (95% Wilson 17.01–18.51%).
- At correlation 1.0, the common component canceled between steps; the known model σ was 0.02132 nm, while conditional independence reported 0.2143 nm (0.10× ratio); all simulated changes fell within the wider reported 1σ.

This confirms scalar per-site uncertainty does not identify the uncertainty of a wafer mean change. P3 does not infer covariance or claim these synthetic rates describe manufacturing. The app states the independence condition next to its conditional value. A typed covariance input requires source-approved semantics; none are fabricated.

Full Python regression: 131 passed; 14/14 critical cases; compileall passes. React 20 passed; strict TypeScript and Vite production build pass. Frozen source/archive hashes remain unchanged. Next independent task: challenge C03 block-adjusted association using an independently generated product/process-zone confound with no within-block association; alter the engine only if the false-association oracle exposes a concrete failure.

Latest working source-tree SHA-256: `f3513a5826d35691573ead399a228daea23869aacea6f35eb1857442079acdc0`. Generated progress evidence is excluded from the digest.

## 2026-11-23 C03 confounding and C05 memory closeout

- C03 independent zone-confound oracle: `qualification/run_c03_zone_confound_benchmark.py` / `progress/C03_ZONE_CONFOUND_BENCHMARK.json`. Across 40 seeded replicates of 20 distinct wafer-lots and 48 sites, a shared radial-zone cause generated pooled r=0.9617 while the adjusted within-wafer mean was -0.00229. The nominal 95% interval covered zero in 37/40 replicates (Wilson 80.1–97.4%). This supports only the declared synthetic within-block estimand; it does not establish general confounding control or causation.
- C05 configured ceiling: 15,000 maps / 440,000 sites, with five labeled queries. Before index compaction: peak RSS 797,130,752 B; traced allocation 496,995,364 B. The index now discards only its duplicate copied raw point dictionaries after validation; normalized observations, profiles, metadata and source identity remain available to retrieval. After: peak RSS 707,592,192 B (89,538,560 B / 11.2% lower); traced peak 412,521,508 B; top-five parity and P@5=1.0 remain. Evidence: `progress/C05_SCALE_15K_BENCHMARK.json` and `progress/C05_SCALE_15K_COMPACTED_BENCHMARK.json`. One local synthetic run only.
- Final regression after the engine change: 131 Python passed, 14/14 critical cases, compileall passed. React 20 tests, strict TypeScript and Vite build passed before the Python-only compaction; no frontend source changed afterward. Targeted whitespace check for changed engine/hash files passes.
- Working source-tree SHA-256: `e13a0869c5a5f5394d26b9a3896744f8d83ad535fcff98d5f9cd7a905404d2f0`. Frozen original source remains `9044a31aa5e79480aaa614496d6ee05778ea72862db3df07bc518030d700755f`; frozen archive remains `aa51df3d510c26d2cfa56ce13603b0d7cdb48ee16a6124de75176729df012499` and was not rebuilt. No public push or company data used.
- Next: challenge C03 exact process-context matching under temporal product/recipe confounding. Shared-suite integration, external transfer and internal qualification remain pending.

## 2026-11-24 C03 context drift and spatial source onboarding

- C03: `qualification/run_c03_context_drift_benchmark.py` / `progress/C03_CONTEXT_DRIFT_BENCHMARK.json`. Across 500 stable-null trials with 20 distinct lots and 48 sites, nominal 95% coverage was 477/500 (95.4%; Monte Carlo and Wilson uncertainty recorded). Each of seven declared product/recipe/metric/definition/unit/mask/population drifts and four support/selection violations abstained in 100/100 trials. Hidden site confounding still produced a VALID nonzero association in 500/500 trials, with the noncausal caveat; stale/unreported population epochs cannot be detected if the authority omits them. No C03 engine change was justified.
- Onboarding: implemented metadata-only MCP discovery, typed C01 mapping proposals, bounded plan requirements and digest-bound source/relationship review using the existing official SDK adapter. `qualification/fixtures/spatial_catalog_oracle.json` predates evaluation. The 13,000-descriptor benchmark achieved 15/15 oracle cases, 10/10 expected profiles, 9/9 source roles, 54/54 correct positive-vs-abstain ranking pairs and zero accepted invalid ready mappings; median classification was 17.325 ms. Two protocol peer schemas, including opaque source/field names, each completed simulated review and all five valid capabilities. Discovery/review made zero row reads; analysis made five bounded reads. Evidence: `progress/SPATIAL_ONBOARDING_BENCHMARK.json`.
- `tests/test_onboarding.py` covers catalog roles, deceptive/opaque naming, explicit categorical and defect semantics, invalid relationship abstention, SDK discovery-to-analysis and all three CLI stages. The OpenCode skill is mirrored to `.opencode/skills/p3-spatial-onboarding/SKILL.md`; Codex version is in `.agents/skills/p3-spatial-onboarding/SKILL.md`.
- Actual browser: the existing P3 loopback host loaded the simulated reviewed configuration in configured read-only MCP mode. The browser showed C01–C05 VALID, five typed observation rows and five bounded reads, allowed C03/C05/provenance inspection, and generated the canonical export. UI result and export hash are recorded in `progress/SPATIAL_ONBOARDING_BROWSER_ACCEPTANCE.json`. The exported download itself was not separately re-opened or re-hashed.
- Effort comparison is explicitly a task rubric: one manual triage item per catalog descriptor versus 14 surfaced proposals (99.8923% fewer screening items); two source approvals and one relationship approval remain necessary in both flows. Human time, actual engineer effort and ROI are unmeasured. Synthetic approvals confer no real permission.
- Frozen baseline remains source SHA `9044a31aa5e79480aaa614496d6ee05778ea72862db3df07bc518030d700755f` and candidate SHA `aa51df3d510c26d2cfa56ce13603b0d7cdb48ee16a6124de75176729df012499`; neither was changed, rebuilt or published.
- Onboarding worst-case performance: `candidate_relationship_pairs` previously examined every eligible pair even when none could satisfy its declared join rules. It now indexes sorted spatial/geometry and wafer-site/wafer-die role buckets. A 13,000-descriptor non-joinable catalog emitted zero candidates in 7.707 ms; the candidate output cap remains 200. The actual fixture/harness still verifies typed pair proposals and authority-reported relationship refusal.
- C02 uncertainty improvement: independent known-covariance Monte Carlo showed the independence-conditional ±1σ coverage at 12.01%, 17.75%, and 100% for between-step common-error correlations 0, .5, and 1 (10,000 trials each). The engine now retains that explicitly conditional estimate and also reports sharp standard-deviation bounds implied solely by supplied marginal uncertainties under arbitrary valid cross-site/cross-step covariance. All three analytical SDs fell within [0, 2.00998] nm. These bounds are not confidence intervals or production calibration. The standalone UI labels the conditional estimate and distinguishes the bounds; the real local synthetic browser flow showed the limitation and all five capabilities VALID. The synthetic fixture had no site uncertainty, so browser run did not show numeric bounds; React tests verified numeric range rendering.
- Final pre-sequence checks: 138 Python tests; 14/14 critical cases; 20 React tests; strict TypeScript; Python compileall; Ruff for changed Python files; Vite production build; whitespace diff check. Bundle warning remains at 759.76 kB minified / 251.59 kB gzip. Actual synthetic browser workflow completed in 381 ms, with 5 bounded reads and valid C01–C05. Browser evidence: `progress/C02_BROWSER_UNCERTAINTY_ACCEPTANCE.json`.
- Current working source-tree SHA-256: `57bf59314e30d21ea9385662cea693135e5c58f6d40a72adf1e2f010a4a5fd41`. The immutable frozen source SHA remains `9044a31aa5e79480aaa614496d6ee05778ea72862db3df07bc518030d700755f`; the untouched candidate archive remains `aa51df3d510c26d2cfa56ce13603b0d7cdb48ee16a6124de75176729df012499`.

## 2026-11-24 C02 multi-step support correction

- `compare_evolution_sequence` previously unioned sites across transitions, so sites seen in only part of a sequence could contribute partial sums to a value presented as cumulative. It now intersects exact normalized observed-site keys across every transition. Predeclared site-count and coverage minima are applied to this sequence-wide set. If sequence support fails, the capability abstains while preserving each adjacent comparison that remains valid.
- A second issue was demonstrated in sequence uncertainty: adjacent transition variances included repeated intermediate-step readings even though those observations cancel from the first-to-last endpoint change. Cumulative uncertainty now propagates only first/last marginal uncertainties, reports an independent-endpoint estimate plus arbitrary-covariance SD bounds, and retains per-transition uncertainty separately.
- Independent deterministic cases: three changing-mask maps with five common sites yielded a valid +5 endpoint mean; a five-map case had four valid adjacent comparisons but zero sequence-wide common sites and correctly returned INCONCLUSIVE with all four comparisons preserved. With 0.1/0.2/0.3 nm marginal site SDs over four unchanged sites, endpoint-conditional mean SD is 0.1581 nm (intermediate 0.2 does not enter); arbitrary-covariance upper bound is 0.4 nm. Evidence: `progress/C02_SEQUENCE_MASK_CHALLENGE.json`.
- Post-change verification: 139 Python tests, 14/14 critical cases, compileall, changed-Python Ruff and `git diff --check` passed. Frontend code did not change in this sequence correction; prior same-checkpoint React, TypeScript, build and browser evidence remains applicable to the UI. Working tree digest is recorded in `progress/NEXT_ACTIONS.json`.
- Final current working source-tree SHA-256: `57bf59314e30d21ea9385662cea693135e5c58f6d40a72adf1e2f010a4a5fd41`; final critical runner confirms the same digest. Frozen source and archive hashes remain unchanged.
- Next executable action: challenge C04 anomaly screening under baseline contamination and historical population shift with independent synthetic ground truth. Keep production calibration, company source permissions, legal/security/target-platform gates and engineer acceptance pending.

## 2026-11-24 C04 baseline contamination counterexample

- Independent deterministic challenge: clean 20-wafer baseline detects the target-like signature at rank floor p=1/21. Adding one earlier baseline wafer with the same signature changes p to 2/21 (above alpha .05), suppresses the alert, while the temporal stability check reports `NO_SHIFT_DETECTED`. Four ordered target-like baseline maps trigger temporal-shift abstention in this fixture. Evidence and executable runner: `qualification/run_c04_baseline_contamination_benchmark.py`, `progress/C04_BASELINE_CONTAMINATION_CHALLENGE.json`.
- P3 does not have a valid external signal to distinguish a stable contaminated population from a legitimate rare subpopulation. The validated response is explicit disclosure: baseline cohort `NOT_CERTIFIED_CLEAN`, contamination `NOT_PERFORMED`, and an engineer action to verify source-approved inclusion criteria. C04’s max-T method and threshold behavior were not altered.
- The C04 panel now displays the same baseline-cleanliness caveat. 20 React tests and TypeScript passed; Vite rebuilt the bundled standalone UI. Existing chunk advisory: 759.85 kB minified / 251.63 kB gzip.
- Latest full acceptance: 140 Python tests; 14/14 critical cases; compileall; changed-Python Ruff; `git diff --check`; React 20; TypeScript; production build all pass. No frozen artifact changed or public push occurred.
- Working source-tree SHA-256: `bb76be14763090c760b78f05dc756eb57e93fe96054cb61127ce9f885114f267`. Frozen source SHA remains `9044a31aa5e79480aaa614496d6ee05778ea72862db3df07bc518030d700755f`; frozen archive SHA remains `aa51df3d510c26d2cfa56ce13603b0d7cdb48ee16a6124de75176729df012499`.
- Next executable action: challenge C01 spatial summaries against synthetic metrology artifacts that mimic gradients and edge signatures. Test what the observations can and cannot distinguish, keep measured-only findings, and add a review path only if it answers a specific uncertainty question.

## 2026-11-24 C01 interpretation and C05 memory follow-up

- C01 sampling challenge: the same declared linear wafer field `10 + 2r nm` yielded observed edge-minus-center values of 1.42 nm with edge sites at radius fraction 0.81 and 1.78 nm at 0.99. This is an observation-layout effect, not an area-weighted wafer change. Product output now labels equal observed-record weighting, marks area weighting `NOT_COMPUTED`, and asks whether the conclusion persists on a fixed common mask or validated design weights. See `progress/C01_SAMPLING_AND_ARTIFACT_CHALLENGE.json`.
- C01 artifact ambiguity: identical spatial observations under two independently assigned latent explanations (physical radial thickness versus flat material plus measurement-system radial bias) produce identical fingerprints. The engine/UI now say attribution is not identifiable from one map and ask whether an independent calibrated path reproduces the pattern or approved calibration diagnostics identify an artifact. No values or causes are inferred.
- C05 index snapshot now copies metadata only, normalizes source points into its own cache, and leaves caller inputs untouched. On 15,000 maps / 440,000 sites: peak RSS 665,157,632 B, down 42,434,560 B (6.0%) from the prior compacted snapshot; direct/index top-five parity, P@5=1.0, exclusion oracles, invalidation, and refresh pass. Build 3,996.539 ms; refresh 3,950.634 ms; indexed median query 1,446.981 ms versus direct 4,658.283 ms. One local synthetic ceiling run; not a company/fleet scale claim.
- Standalone host now lazy-loads the existing ECharts renderer. Initial JS fell from 760.22 kB / 251.75 kB gzip to 217.84 kB / 69.20 kB gzip; the 542.26 kB / 182.31 kB renderer chunk loads when observations are displayed. This is bundle-byte evidence, not a measured browser latency. Vite still flags the deferred chunk size.
- Verification on this source: 143 Python tests passed (52 conditional skips), 14/14 critical cases, 21 React tests, TypeScript typecheck, compileall, C01 challenge, C05 15k benchmark, production build and `git diff --check` passed. Ruff could not run because its executable is unavailable in this environment.
- Working source-tree SHA-256: `46a10b26d02bd675f881c7b013d8ca7c97fb0b9468e99d9f4b7b986a35417bca`. Frozen source SHA remains `9044a31aa5e79480aaa614496d6ee05778ea72862db3df07bc518030d700755f`; frozen candidate archive remains `aa51df3d510c26d2cfa56ce13603b0d7cdb48ee16a6124de75176729df012499` and was not rebuilt.
- Next: continue only for a new falsifiable independent weakness; otherwise resume with authorized MCP metadata or a concrete new engineer finding. Company permissions, target OS, rights, security, manufacturing calibration, transfer and engineer acceptance remain pending.

## 2026-11-24 current-source offline browser qualification

- The first replay used the base system Python, which lacked `mcp` and surfaced a generic source error. No company source was used. Reproduced the error directly, then installed the bundled official MCP SDK 2.3.0 with `--no-index --require-hashes` into an isolated macOS arm64 CPython 3.11.7 environment; `pip check` passed.
- Updated `README.md` and `docs/P3_REFERENCE_HOST.md` with exact venv/install/build/launch commands. The local host now returns a safe actionable 503 when the SDK is missing; `MissingSDKReferenceHostTests` passes.
- Replayed the current built host in the real local browser: synthetic MCP discovery, five bounded reads, C01-C05 all VALID, 5 measured numeric observations, lazy wafer renderer visible, C01 sampling and independent-metrology questions visible. Export saved; SHA-256 `7378eb5f61b78fc0b9a6a838c3f525129febb2cc58d90ca25711484230898c7c`; browser-reported workflow time 274 ms. This was a numeric synthetic investigation, not internal qualification.
- Offline qualification from the bundled lock and wheelhouse: 144/144 Python tests passed, no skips; dependency consistency passed. The current source also passes 14/14 critical cases, C01 falsification runner, compileall, and `git diff --check`. React 21/21, TypeScript and Vite build had passed for the same UI source; no UI code changed during the offline-host diagnostic fix.
- Current source-tree SHA-256: `e5446a8a5bdc33051031786f3018d19d2927e90571b3ef2040a3a3467d6ae375`. Frozen candidate archive remains `aa51df3d510c26d2cfa56ce13603b0d7cdb48ee16a6124de75176729df012499`, unchanged and not rebuilt. No public push occurred.
- Ruff, Bandit and pip-audit are unavailable in the base environment; no dependency was added or changed. Existing transfer, target OS, rights, security clearance, authorized mappings, manufacturing validation and engineer-acceptance gates remain pending.

## 2026-11-24 C03 temporal heterogeneity and nested-lot inference

- Reproduced temporal averaging failure: across 500 seeded runs, the pooled within-wafer estimate was about 0.00056 while predeclared early/late estimates pointed strongly in opposite directions. The engine now accepts a reviewed partition with source ID, approval reference, pre-outcome predeclaration and at least 10 independent lots per stratum; mixed-lot boundaries abstain. UI and evidence distinguish observed reversal from unassessed pooling. Stratum intervals remain nominal and unadjusted. Hidden or misreported epochs remain source-authority limitations.
- Context-drift runner passed 500 stable-null runs with 95.4% nominal interval coverage, 500/500 context-mismatch abstentions, 400/400 support/selection abstentions, and visible caveating of 500/500 hidden-confounding results. Evidence: `progress/C03_CONTEXT_DRIFT_BENCHMARK.json`.
- Broadened the one-wafer-per-lot restriction after an independent nested-lot challenge. `associate_quality` averages Fisher-z wafer associations within each lot, then infers across independent lots; leave-one-lot-out removes the full lot. On 500 simulations with 20 independent lots, coverage was 95.6% for one wafer/lot and 96.2% for two, with the two-wafer median interval 11.37% narrower. Evidence: `qualification/run_c03_nested_lot_benchmark.py`, `progress/C03_NESTED_LOT_BENCHMARK.json`.
- Regression: 144 Python tests passed in a fresh hash-locked offline SDK environment with no skips; 14/14 critical cases; 22 React tests; TypeScript; compileall; targeted whitespace check; Vite build. The deferred renderer remains 542.26 kB / 182.31 kB gzip, with Vite's >500 kB advisory.
- Current working source-tree SHA-256: `409a656e8a7798a3bf9b41902fe231c3c0f3bd36ae851532b86b9909a3986daa`. Frozen source SHA remains `9044a31aa5e79480aaa614496d6ee05778ea72862db3df07bc518030d700755f`; frozen candidate SHA remains `aa51df3d510c26d2cfa56ce13603b0d7cdb48ee16a6124de75176729df012499`. No archive rebuild or public push.
- No further C03 change is justified by these independent designs. Resume on a fresh falsifiable P3 defect, newly authorized MCP semantics/permissions, or external target-platform/security/rights qualification. Company transfer and internal qualification remain pending.
