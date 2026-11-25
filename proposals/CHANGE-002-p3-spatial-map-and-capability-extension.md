# CHANGE-002: P3 spatial map and capability integration

Date: 2026-11-23
Status: P3 now runs and qualifies independently through `fabintel.reference_host` with `fab-spatial-map.v2`; P1 is not a P3 runtime dependency. This proposal is the P1-owned shared-host compatibility change only. The observed P1 route still uses the older `suite-spatial-map.v1` converter and stale P3 snapshot, so actual shared-suite integration remains pending. See `docs/P1_INTEGRATION_HANDOFF.md` for the current source version, P3 evidence and exact P1 next action.

## Current P1 snapshot

The live P1 checkout contains the suite application route `/fab-intelligence/p3`, `SuiteHost`, the shared ECharts spatial renderer, module registration for C01–C05, `suite-spatial-map.v1`, and P3's headless React panel. P1 owns the shell, route, request lifecycle, shared schema and renderer. P3 does not add a product shell or chart implementation.

Current observed P1 test evidence, re-run against the local checkout on 2026-11-23:

- The complete P1 Python suite ran 154 tests: 138 passed and 16 optional MCP SDK cases skipped. The focused P1 suite-host set ran 13: 11 passed and 2 SDK-gated cases skipped. These cover synthetic P3 HTTP analysis, permission refusal, exact measured-site map contents and categorical string `PASS`/`FAIL` preservation.
- P1 `npm run typecheck`, `npm test` (39 tests) and `npm run build` passed. The build emitted Vite's advisory that the JavaScript chunk is 800 kB minified; it still completed successfully.
- The current P3 panel passes 12 P1-toolchain component tests and strict TypeScript, including typed values, count consistency/refusal, missing values, loading/cancellation/error states, provenance and host-owned export.
- The P1 route was exercised in a real local browser: a positive C01–C05 response showed provenance, five measured sites, evidence status and the shared wafer renderer; permission refusal suppressed values and findings; the P3 export action triggered a browser download event. The downloaded file bytes were not independently inspected.
- That browser route still imports P1's own P3 copy. Current P1/P3 snapshot comparison shows engine SHA-256 `7113b825d14f399efebd140a31d450d720e4702a553491e80a458834c4423140` vs tested P3 `b076b1b18410e8796c5d411b1f4ecacc2dcd4337a9d1ef6c9e28cabb2eb3d376`, and panel SHA-256 `9128c812767a11898abdfceaead0b0555c11c18b824364e7a6bf494942ffa1e7` vs tested P3 `4dd5091986c51823eba96b29c310a791694586f237955232ad9b3bbfa33a9d4f`. The fixture matches exactly at `7843120c45abfcc08d217986153db7f3fbf99393f53381d9ecc6775c8023d460`.
- The complete P1 Python suite passes with its optional SDK cases skipped; no unrelated `source_integrity` failure was reproduced.

Exact, remaining P1-owned data-contract defects:

1. `fabintel/suite.py::_spatial_map()` converts a numeric categorical value such as `2` to string `"2"`, and does not read `category`/`bin` for `defect_coordinates`.
2. `products/p1/ui/suiteSpatialMap.ts::suiteMapFromP3Input()` converts categorical numeric values with `String(category)`. For a continuous numeric modality, it accepts a numeric string as a categorical string rather than refusing the incompatible type.
3. `SharedVisualizations.tsx` infers numeric versus category versus missing from the JavaScript primitive alone. A numeric die-bin code is therefore rendered as quantitative metrology; an unlabeled defect event is represented as a missing measurement.
4. `suite-spatial-map.v1` has no modality or per-point kind field, so the current shared contract cannot distinguish a categorical numeric code from a continuous numeric measurement, or an unlabeled event from a missing measurement. The schema requires exact `points.length == sampling.observed_site_count`; it also counts every `null` as missing.
5. The P1 React test currently expects integer category `2` to become string `"2"`; update that expectation because it codifies type coercion.

## Exact host-side contract correction requested

P1 should own a versioned `suite-spatial-map.v2` contract. Do not change P1's route, common shell, semantic authority, or renderer ownership. The v2 model should add:

```json
{
  "schema_version": "suite-spatial-map.v2",
  "measurement_modality": "continuous | sparse_continuous | die_bin_categorical | defect_coordinates",
  "points": [{
    "site_id": "source site ID",
    "x": 0.0,
    "y": 0.0,
    "observation_kind": "MEASURED_NUMERIC | CATEGORICAL | DEFECT_EVENT | MISSING",
    "value": "number | string | null"
  }]
}
```

Normative conversion rules:

- Continuous modalities accept finite JSON numbers or explicit `null`. Numeric strings are incompatible and must reject the map/request; never cast them. A missing `value` property is invalid, not a default `null`.
- `die_bin_categorical` accepts a nonempty string or finite JSON number. Preserve the exact primitive type and value. `category` and `bin` may alias only if both are present and deeply equal with the same primitive type; otherwise reject. Never stringify a numeric code.
- `defect_coordinates` preserves an optional `category`/`bin` with the same exact type as CATEGORICAL. A point without a label is `DEFECT_EVENT` with `value: null`; this is not MISSING. Null must not increment `explicit_missing_value_count` for a DEFECT_EVENT.
- An explicit missing numeric measurement is `observation_kind: MISSING`, `value: null`, with site ID and coordinates retained. No interpolation, row deletion, zero/default insertion, or measurement arithmetic on missing/categorical points.
- `sampling.observed_site_count` equals the number of input points and the number of table rows. `explicit_missing_value_count` equals only points tagged MISSING. Preserve input order and source site identity. If coverage metadata is invalid or a map contains mixed modalities, refuse it rather than reconciling by coercion.
- Renderer series selection uses `measurement_modality` plus `observation_kind`, not `typeof value`; numeric category codes render categorical, missing measurements render separately, and defect events render as events. The adjacent semantic table shows the original primitive value and observation kind.

The P1 migration should publish the v2 JSON schema and TypeScript type, update both `fabintel.suite::_spatial_map()` and `suiteMapFromP3Input()`, update the P3 registration/host model compatibility, and keep v1 only as an explicit legacy path if another module still uses it. The shared renderer and host remain P1-owned.

## Required executable acceptance cases

The independent fixture is `tests/fixtures/spatial_value_contract.json`. P3 tests additionally cover these cases in `tests/test_p3_integrated.py` and `products/p3/ui/P3Panel.test.tsx`. P1 should port the same fixture into its own suite tests:

| Input | Required result |
|---|---|
| numeric `42.5` / integer `42` metrology | number stays number; numeric series only |
| category `"BIN-A"` | identical string; category series/table |
| category code `2` | identical number and categorical series because modality is categorical |
| defect label `"BRIDGE"` or numeric bin `7` | exact type/value and CATEGORICAL observation kind |
| unlabeled defect coordinate | DEFECT_EVENT with null value, not a missing-measurement count |
| explicit numeric `null` | MISSING with null value, retained source row and table row |
| continuous value `"42.5"` | conversion/request refused; no numeric coercion |
| category and bin conflict, e.g. `2` and `"2"` | conversion/request refused |
| 7 input points with numeric, category, event and missing cases | exactly 7 output points and accessible table rows; counts reconcile; `interpolation: "none"` |
| unsupported object/boolean/infinite category | refusal, with no deletion or fallback label |

Acceptance must exercise the P1 API map adapter and TS adapter, P1 schema validation, the actual shared renderer model, source table, and the integrated P1 route. Existing executable P1 references are `tests/test_suite_host.py`, `products/p1/ui/suiteSpatialMap.test.ts`, `products/p1/ui/SuiteHost.test.tsx`, and P3's `qualification/run_p1_module_integration.py`. P3's runner now reports the P1-owned gaps rather than silently treating the v1 conversion as complete.

## P3 contribution and current evidence

P3 supplies `products/p3/ui/P3Panel.tsx`, the module manifest at `integration/p3-suite-ui-module.v1.json`, C01–C05 capability states, source/provenance inspection, the accessible measured-site table, explicit no-interpolation text, loading/cancellation/error/refusal/empty behavior, and an optional host-owned evidence export callback. P1's suite host passes the shared renderer and host export callback. The P3 panel does not serialize or choose an export destination.

P3 now preserves string, integer and finite float category values in the scientific engine, reports labeled defect-category counts without inventing labels, refuses conflicting category aliases, refuses numeric strings for numerical analysis and never fills explicit null values. The headless panel passes typed values unchanged to the injected shared renderer, reconciles declared site/missing counts and site identities, and refuses to render ambiguous v1 maps where an unlabeled defect event could be mistaken for an explicit missing measurement. These tests pass locally. The P1-owned v1 schema still cannot encode modality/event kind, so P1 must complete the v2 extension before numeric category codes and defect events can be rendered semantically.

The changed P3 engine and panel sources do not match P1's routed P3 copy. P1 must update its reviewed snapshot and engine digest, then exercise the latest module on the real route before integrated qualification. The fixture is already byte-identical. Exact source SHA-256 values are in `release/P1_MODULE_INTEGRATION_EVIDENCE.json`.

## Integration state

P3's standalone scientific workflow and reference host are independently available. `SHARED_SUITE_COMPATIBILITY_READY` means that P3 supplies a versioned module, typed contract, accessible table/rendering model, evidence envelope, fixtures, and host tests for future integration. It does not mean the actual P1 route has passed.

`SUITE_INTEGRATION_PENDING` remains the correct shared-suite state because the audited P1 route uses stale P3 source copies, the P1 v1 spatial contract cannot express the modality/event distinction, and P1's Python/TypeScript converters fail the typed regression cases recorded in `release/P1_MODULE_INTEGRATION_EVIDENCE.json`. P1 owns those shared-host corrections. P3's independent runtime, C01–C05 engine and completion state do not depend on P1 making them.
