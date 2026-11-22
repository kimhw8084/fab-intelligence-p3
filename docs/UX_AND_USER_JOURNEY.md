# Concrete engineer experience and acceptance walkthrough — FAB Spatial & Yield Intelligence

The UI in `ui/index.html` is a *noninteractive bootstrap layout reference*, not the finished app. Build one working product panel in the shared authenticated workspace and qualify the actual approved UI host. No duplicate standalone site without justification.

## Minimum user journey
1. One wafer-centric workspace with actual measured points, wafer geometry/orientation and visible sampling mask. Legend separates observed vs inferred/unobserved values.
2. Overlay spatial features (ring, edge, gradient, localized cluster); inspect per-region counts and uncertainty.
3. Anomaly drawer shows baseline population, distance/score, false-alert calibration, spatial region and coverage.
4. Historical neighbors gallery shows same map convention, meaningful comparison metrics, associated verified history and distinct “similar shape is not same root cause” notice.
5. Cross-step before/after view with registration quality; disable when geometries are incomparable. Outcome pane shows only valid downstream links and observational language.
6. Keyboard and tabular text alternative, point selection, export with coordinate metadata and all exclusions/transformations.


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
