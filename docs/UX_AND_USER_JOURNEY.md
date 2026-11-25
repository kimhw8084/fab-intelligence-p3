# Concrete engineer experience and acceptance walkthrough — FAB Spatial & Yield Intelligence

P3 owns C01–C05 and now operates independently through `products/p3/reference_host/`. The small loopback host composes the official SDK adapter, the typed spatial-map v2 boundary, P3 analysis, locally bundled React/ECharts visualization, and reproducible evidence export. It is a reference host, not a competing suite framework. The separate `products/p3/ui/P3Panel.tsx` remains an embeddable module for future product-neutral suite integration.

**Current integration state:** P3 is not runtime-dependent on P1. Its standalone host renders C01–C05 and typed numeric, categorical, defect-event, and missing observations. It displays sampling counts, limitations, provenance and read audits; users can inspect each capability and export a canonical evidence file with SHA-256. The P1 snapshot remains read-only and its converter still fails categorical/event preservation acceptance; therefore P1 integration is pending. A fresh standalone browser workflow and formal engineer study must be recorded separately.

## Independent P3 user journey
1. One wafer-centric workspace with actual measured points, wafer geometry/orientation and visible sampling mask. Legend separates observed vs inferred/unobserved values.
2. Overlay spatial features (ring, edge, gradient, localized cluster); inspect per-region counts and uncertainty.
3. Anomaly drawer shows baseline population, distance/score, false-alert calibration, spatial region and coverage.
4. Historical neighbors gallery shows same map convention, meaningful comparison metrics, associated verified history and distinct “similar shape is not same root cause” notice.
5. Cross-step before/after view with registration quality; disable when geometries are incomparable. Outcome pane shows only valid downstream links and observational language.
6. Keyboard and tabular text alternative, point selection, export with coordinate metadata and all exclusions/transformations.

The reference host implements source mode/plan selection, bounded MCP reads, C01–C05 execution, site coverage, typed site table, history/evolution and association detail, source audit inspection, cancellation, refusal/error recovery, and evidence export. The synthetic end-to-end path is qualified against a protocol-compatible peer; it is not evidence of company authorization.


## Actual interaction acceptance
- Using the input form or structured engineering request, user can choose/confirm exact scope and identify output in deterministic mode with an approved source context.
- Source inspector shows permission, semantic version, metric/unit, population count, join grain, sampling coverage and effective date; if invalid, the analysis cannot misrepresent it as verified.
- All charts provide accessible text/tabular data; keyboard navigation and screen-reader semantics are evaluated in the actual qualified browser.
- User can cancel a long-running bounded query without side effects; partial failures remain visible with precise retry and provenance boundaries.
- Export artifacts include exact data reference/query IDs, chosen evidence snapshot, input hash, method/software version, parameters, exclusions, uncertainty and timestamp. Repeat analysis matches within fixed deterministic numerical tolerance.
- Model offline/unavailable or hallucinated tool call: engine remains useful, forbids unauthorized source access, and either follows deterministic form controls or declines unsupported natural-language conversion safely.
- Empty data and conflicting source definitions result in an actionable state without replacing missing evidence with synthetic values.

## Avoid overbuilding
Reuse one existing approved engineering UI platform where compatible; otherwise one local/intranet host for all P1–P4. Keep JS/CSS bundled locally; no remote icons, fonts, scripts, license checks or telemetry. OpenCode MCP Apps rendering is optional and must be independently confirmed before relying on it.
