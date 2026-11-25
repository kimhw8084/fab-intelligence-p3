# P3 to shared host integration handoff

Date: 2026-11-23. This document records the current P3 contribution and the exact remaining P1-owned host work. P3 is independently runnable and does not require P1 at runtime. The existing CHANGE-002 proposal remains the detailed defect fixture and migration proposal; this file records the completed P3 side.

## P3 source version and verification

- Repository: `fab-intelligence-p3` local worktree; base commit `83a08682a189944adf984fe891353e84485ac381` plus the uncommitted candidate source tree identified in `release/P3_SOURCE_VERSION.json`.
- Source-tree digest: see `release/P3_SOURCE_VERSION.json`; archive digest is recorded in `release/PACKAGE_QUALIFICATION.json` after the final candidate build.
- Module manifest: `products/p3/reference_host/module-manifest.v2.json` (`p3-reference-module.v2`, C01–C05, `fab-spatial-map.v2`).
- Product-neutral runtime: `fabintel.reference_host`, loopback-only, with locally bundled React and Apache ECharts assets.
- Scientific implementation: `products/p3/engine.py`; SDK adapter: official `mcp` 2.3.0 SDK through `fabintel.mcp_adapter.ReadOnlyMCPAdapter`.
- Typed spatial schema and TS type: `products/p3/contracts/spatial-map.v2.schema.json` and `products/p3/contracts/spatial-map.v2.ts`.
- Reproducible synthetic peer: `qualification/synthetic_mcp_peer.py`; the browser never supplies a tool name, credential, or source configuration.

## Typed observation contract

`fab-spatial-map.v2` carries `NUMERIC_MEASUREMENT`, `CATEGORICAL_MEASUREMENT`, `DEFECT_EVENT`, and `MISSING_MEASUREMENT` observations with source site ID, coordinates, primitive `value`, explicit `value_type`, units, modality, geometry, sampling counts, and source/semantic hashes. Numeric category codes remain JSON numbers. An unlabeled event is represented with `value: null` as a defect event and does not increase the missing-measurement count. A missing numeric reading remains an explicit table row with `null`. Numeric strings are refused for continuous analysis. No inference, coercion, deletion, interpolation, or default value is inserted.

The independent reference host uses only this v2 model. `suite-ui-module.v1` is an explicit loss-aware compatibility adapter: it refuses a defect-event map if the legacy model cannot distinguish an unlabeled event from missingness. Shared-suite contract ownership remains with the shared foundation/P1 host; P3 has not changed the frozen common contract.

## Executed P3 acceptance

Run from this repository after installing the hash-locked SDK bundle when testing the MCP paths:

```sh
python -m unittest discover -s tests -v
npm run typecheck
npm test
npm run build
python -m fabintel reference-host --port 8765
```

Verified in the current candidate: 123 Python tests with the offline official-SDK peer; 15 React host/module tests; TypeScript typecheck; Vite production build; real browser workflow at 390 px with no document-width overflow; C01–C05 synthetic execution with five bounded reads; C02 exact five-site alignment and zero registration residual; source/evidence inspection; canonical JSON download; categorical, missing, defect-event and permission-refusal browser scenarios; cancellation followed by successful retry. The C01 null-value regression proves that explicit numeric/categorical null rows remain visible while unrelated features still analyze remaining observations, and returns `PARTIAL` when supported features continue. The browser export bytes are independently hashed in `release/P3_STANDALONE_BROWSER_EVIDENCE.json`. These checks use synthetic sources only.

## P1-owned host compatibility changes

The P1 checkout audited on 2026-11-23 still uses `suite-spatial-map.v1`. Its P3 conversion test recorded these failures in `release/P1_MODULE_INTEGRATION_EVIDENCE.json`:

1. `fabintel.suite._spatial_map()` stringifies numeric category `2`, drops labeled defect categories in the Python path, counts an unlabeled defect event as a missing reading, and accepts a numeric string in continuous data.
2. The P1 TypeScript adapter stringifies numeric category values and cannot reject the continuous numeric string based on modality.
3. The shared renderer derives semantics from JavaScript primitive type and therefore cannot distinguish a numeric bin category from metrology or an unlabeled event from missing data.
4. P1's v1 schema has no modality/per-point observation kind, so this ambiguity cannot be represented losslessly.
5. The current P1 route uses a stale P3 engine/panel snapshot. Refresh it only after reviewing the current manifest and source hashes.

P1 should make these host-owned changes:

- Add a versioned shared spatial-map contract with explicit modality and per-observation kind, preserving number/string/null values exactly. P1 owns the shared contract migration and backwards-compatible route behavior.
- Update both Python and TypeScript conversion paths; refuse incompatible numeric strings, conflicting category/bin aliases, invalid geometry, and unsupported values before rendering.
- Select renderer series from modality plus observation kind. Keep the semantic measured-site table adjacent to the chart; show events separately from missing measurements and reconcile input/table counts.
- Register all five P3 capabilities against the current P3 manifest and expose loading, cancellation, empty, refusal, error, provenance, and export states through the shared host.
- Update the reviewed P3 source snapshot; do not copy P3 scientific code into P1's A-series implementation.
- Run the generated host acceptance fixture against the actual route and require every typed case in CHANGE-002 to pass before declaring suite integration complete.

P3-owned executable regressions are `tests/fixtures/spatial_value_contract.json`, `tests/test_spatial_observations.py`, `tests/test_reference_host.py`, and the existing headless module tests. P1's test-only integration runner is `qualification/run_p1_module_integration.py`; it must be run from an authorized writable P1 integration checkout after those owner changes. It was not run during this standalone qualification because it creates transient files in the P1 worktree.

## State handoff

- `P3_PRODUCT_IMPLEMENTATION_COMPLETE`: verified for the P3-owned module and synthetic external workflow; it does not claim company calibration or company data correctness.
- `P3_STANDALONE_WORKFLOW_VERIFIED`: verified with the actual loopback browser and official SDK synthetic MCP peer.
- `SHARED_SUITE_COMPATIBILITY_READY`: P3 supplies a versioned module manifest, loss-aware typed spatial model, headless panel, fixtures, and executable tests.
- `SHARED_SUITE_INTEGRATION_PENDING`: the actual P1 host still needs the converter/renderer corrections and current-source integration test above.
- `EXTERNAL_TRANSFER_READY`: false; first-party ownership/redistribution, target platform beyond macOS arm64/CPython 3.11, and authorized security/transfer review remain open.
- `INTERNAL_QUALIFICATION_PENDING`: true; real MCP grants, reviewed semantic mappings, company data, target environment, method calibration, and engineer acceptance are company-side steps.

The smallest next action is for P1 to apply the typed contract migration, review the P3 source hash in `release/P3_SOURCE_VERSION.json`, and execute its route acceptance suite. No P1 change blocks continued P3 standalone use or tests.
