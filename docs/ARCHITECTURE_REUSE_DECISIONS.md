# Architecture reuse decisions — P3

Date: 2026-11-22  
Reference: Golden Agentic Engineering v0.1.0-dev at `dc2ece864b2d744e47dfe8c7d9ad78aadbed369e`. Golden is a pre-qualification development-method foundation; its standards are not represented as enforced or company-approved.

## Product UI and single workspace

**Selected:** P1's React 19 / TypeScript panel contract and host-owned route/shell. P3 now exports `P3Panel` and a schema-valid `suite-ui-module.v1` contribution manifest. The former HTML/CSS/JavaScript application shell and P3 HTTP server were removed from the product package; the former API remains only as a test fixture. The panel accepts source preview and evidence from the host, delegates spatial drawing to a host callback, and has no design tokens, route, request controls, or renderer of its own. P3's CLI analysis entrypoint remains available for offline synthetic checks.

**NiceGUI Base audit:** An installed `nicegui-base==3.0.0a8` package was found and inspected at source commit `000298562d6bcbf6df304edbd41b98b30fe4bfcf` (the package reports 1,022 installed files totaling 13,074,408 bytes, including bytecode caches, and 334 Python source files). Its upstream README calls this version a source-complete alpha and says live target, browser, and human certification remain pending. It contains useful wafer radial/sector/center-edge and ECharts surfaces, but its Python/NiceGUI runtime does not mount as a module in P1's React host. Its installed distribution has no license metadata or embedded root license, so P3 cannot redistribute or add it as a public runtime dependency on the available evidence. See the [NiceGUI Base repository](https://github.com/kimhw8084/nicegui-base) and its pinned [source commit](https://github.com/kimhw8084/nicegui-base/tree/000298562d6bcbf6df304edbd41b98b30fe4bfcf). P3 therefore uses P1's actual React module contract: two P3 TypeScript files, five component tests, and zero new P3 runtime packages. This preserves the single suite shell and needs no bridge or second route. The comparison is based on current source and local package measurements, not a matched engineer usability study; browser usability and the P1 host remain unqualified.

**React/shadcn audit:** P1 stages React 19.2.0, React DOM 19.2.0, Vite 7.3.8, TypeScript 5.9.3, Vitest 5.1.1, Testing Library and happy-dom. It does not stage Tailwind or shadcn. P3 reuses the actual React panel conventions and semantic elements; it does not claim reuse of shadcn or create another component system. No package was added to P3 for the panel. The P3 module's five Vitest component tests and strict TypeScript check pass against the P1 staged dependencies under Node 26.13.0, which satisfies P1's declared engine range. This qualifies the local module checks only; host/browser integration remains pending.

**Integration status:** P1's schema restricts module capability IDs to `Axx`, while P3's product contract uses `C01`–`C05`; its `capabilities` array is temporarily empty and the mismatch is recorded in `proposals/CHANGE-002-p3-spatial-map-and-capability-extension.md`. The v1 chart schema has only line/scatter models, so P3 supplies a typed spatial model to the host renderer extension requested there. Existing product-level analysis, evidence, and source contracts remain unchanged.

## Visualization and tables

**Selected:** One host-owned visualization runtime, with native semantic HTML tables as the no-chart and accessible data path. P1's local bake-off used the same line/scatter features and measured ECharts 6.1.0 at 785.84 KB minified / 218.27 KB gzip / 1.11 s build, versus Plotly.js 4.3.0 core + scatter at 1,651.75 KB JS + 83.13 KB CSS / 454.46 KB JS + 10.59 KB CSS gzip / 1.37 s build. P1 reported about 52% less gzip JavaScript for ECharts and selected it as the shared candidate. P1 does not bundle it. P3 introduces only a renderer callback and does not add a chart package. Timings are one local observation, not a repeated benchmark.

| Candidate | P3 decision | Local evidence and cost |
|---|---|---|
| Apache ECharts | Reuse only through P1's host adapter | P1 selected it as the shared line/scatter candidate; P3 adds zero renderer packages. Wafer-map support requires the versioned spatial model requested in CHANGE-002. |
| Plotly.js 4.3.0 | Do not add | In P1's matched build it was 454.46 KB gzip JS + 10.59 KB CSS versus ECharts at 218.27 KB gzip JS; no P3 gain offsets a second renderer. |
| AG Grid Community 36.3.0 | Do not add | P1's accessible table path is native HTML. The reviewed unpacked package was 21,947,043 bytes; no P3 workflow or measured task requires a separate grid. |
| Cytoscape.js 3.35.0 | Not applicable | The reviewed package was 5,814,108 unpacked bytes. P3 has no graph model/workflow; a graph would also risk implying unapproved manufacturing relationships. |

P1's candidate bake-off reused locked local packages and reported no known advisories in the available audit data; it is not company license clearance or host qualification. These are reuse and scope decisions, not claims of a P3 map-rendering benchmark. The P1 host remains responsible for spatial-map and shared-renderer qualification.

## Backend, tests, and offline packaging

P3's former loopback HTTP implementation duplicated P1's same-shape synthetic server without adding suite dispatch. P3 now exposes its deterministic `products.p3.engine:analyze` entrypoint and a React panel; HTTP request validation/cancellation tests exercise an API fixture under `tests/fixtures/` only. No independent web framework, service, route handler, or deployment process remains in `fabintel/`.

P3 keeps the existing standard-library `unittest` scientific suite and uses P1's staged Vitest/Testing Library/happy-dom and TypeScript toolchain for the panel. It does not add pytest, Playwright, a second component-test runner, or a P3 `node_modules` tree. Golden's local runner and rules are v0.1.0-dev pilot tooling, not qualified enforcement; applicable commands were run directly and their results are kept in P3 release evidence.

Golden's offline packager is a source-only package tool tied to its own clean-worktree and package identity. P3 retains its existing product-specific deterministic archive builder, adopts per-file hash, fresh-extraction, and offline-install checks, and now includes its hash-locked local SDK wheelhouse in the archive. It does not use Golden as a binary staging service or infer approval from a successful local install.

## MCP and semantic authority

**Selected:** Official Model Context Protocol Python SDK 2.3.0 as the protocol/transport implementation, with P3's existing logical `ReadOnlyMCPAdapter` preserving reviewed operation bindings, bounded read limits, authorization checks, provenance and refusal behavior. The local candidate is pinned to upstream commit `2118f14f8a19bc158d8a1cf90af58d85d187f849`; its complete macOS arm64 CPython 3.11 wheelhouse, requirements hash lock, license inventory and CycloneDX SBOM are in `vendor/mcp-sdk-2.3.0/macos-arm64-cp311/`. It was copied from a local sibling-product vendor directory and installed with pip `--no-index --require-hashes` in an isolated environment.

The SDK is a candidate, not company-cleared. Golden's candidate manifest records no company OSS approval, no independent vulnerability review, no native Windows/Linux install, and no company OpenCode handshake. Only a local macOS arm64 synthetic SDK/client test has been run here. No credentials, real server names, semantic mappings, approvals or internal endpoints were supplied. Fab Insight MCP remains the sole real semantic authority.

## Scientific methods and dependencies

P3 keeps its existing deterministic, dependency-free scientific core and independent arithmetic/metamorphic oracles. Existing tests cover coordinate/orientation refusals, non-interpolation, independence and holdout requirements, overlap/aliasing, missing center sites, source provenance, and synthetic false-alert behavior. The installed NiceGUI Base spatial helpers were inspected as a reuse candidate. They provide radial/sector summaries, center-edge decomposition, deltas, and exploratory contour/defect helpers; they do not provide P3's population compatibility, same-wafer/time lineage, matched-lot max-T test, historical exclusion rules, or block-adjusted outcome design. A matched synthetic boundary fixture with physical radius 100 and sampled radius only 60 gives the independent oracle/P3 `INCONCLUSIVE` with zero measured edge sites, while NiceGUI Base's maximum-observed-radius normalization reports two outer sites and a 7-unit center-edge difference. The mismatch is recorded in `release/REUSE_COMPARISON_EVIDENCE.json`. These methods were not substituted; an equivalence claim would require passing the existing independent refusal/oracle suite, and the package has no distribution license metadata in the staged copy. Golden's capability registry identifies Polars only as a candidate for large local-data analytics; P3's measured inputs and deterministic index do not show a need for that dependency. No candidate library has demonstrated a qualified improvement across P3's accepted scientific methods, offline targets, and license checks, so no spatial/statistical runtime package was added. This is not a claim that all P3 scientific methods have source-derived or held-out qualification.

## Shared dependency/interface register

| Concern | Owner | Contract or pin | P3 use |
|---|---|---|---|
| Suite shell, route, tokens, request lifecycle | P1 / suite host | `suite-ui-module.v1` | P3 supplies `P3Panel`; no local shell |
| Shared charts and spatial visualization runtime | P1 / suite host | `suite-chart.v1`; spatial extension requested in CHANGE-002 | Injected renderer callback only; accessible data table remains |
| Evidence envelope | Shared FAB contract owner | evidence schema `1.0.0` | P3 panel consumes validated envelope |
| Semantic authority and company authorization | Fab Insight administrator | approved deployment mapping only | Existing P3 logical adapter; all actual bindings pending internal |
| MCP wire protocol and transports | Official MCP Python SDK | `mcp==2.3.0`, upstream commit above | SDK-backed facade; zero custom JSON-RPC framing |
| Local deterministic calculations | P3 | P3 method versions in evidence | Existing scientific baseline preserved |

The table records current source decisions; it does not imply suite assembly, company qualification, deployment approval or engineering ROI.
