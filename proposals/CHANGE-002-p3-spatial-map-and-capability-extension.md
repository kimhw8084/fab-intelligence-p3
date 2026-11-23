# CHANGE-002: P3 spatial map and capability IDs in suite UI contracts

Date: 2026-11-22  
Status: Request for P1 suite-contract owner; no shared contract modified by P3.

## Observed compatibility gaps

The P1-owned `suite-ui-module.v1` schema currently permits only `A01`-style capability IDs. P3's frozen product manifest identifies its five capabilities as `C01`–`C05`. The P3 module contribution manifest therefore keeps the schema-valid capability list empty and exposes the product capability states from validated evidence. This is truthful but loses suite-level capability metadata.

The current `suite-chart.v1` schema supports only line and scatter data. A wafer map needs two measured coordinates, a measured value, verified wafer geometry/orientation, and observed-site-only semantics. Encoding it as a line/scatter chart would discard required fields or invite false geometry. P3 therefore supplies a typed `p3-wafer-map.v1` model to the host through `renderWaferMap`; it does not ship a chart renderer.

## Requested additive host change

1. Widen module capability identifiers to accept namespaced product codes (`A01`–`A99`, `C01`–`C99`) or add a generic capability-ID pattern without changing existing IDs.
2. Add a versioned `suite-spatial-map.v1` model with coordinate system, orientation, radius, coordinate and measurement units, verified-coordinate flag, and exact observed points. Keep geometry interpolation disabled by default.
3. Extend the one shared suite renderer with this model; keep the product module callback injectable and keep a complete semantic data table in the product module.

## Migration checks

- Existing P1 A-code manifests and `suite-chart.v1` consumers continue to validate unchanged.
- P3 C01–C05 manifest validates without aliases or silent remapping.
- Verified spatial fixtures render through the host renderer; unverified-coordinate fixtures do not render a map.
- Rendered point counts and table rows equal the input observations; no interpolated points appear.
- Missing renderer leaves the accessible table and a pending message.

The local P3 module and tests implement the product-side behavior. P1 schema approval and suite-host rendering remain integration gates; no host behavior is claimed here.

## Current integration inventory

The available P1 checkout was inspected on 2026-11-22. It contains the P1 headless product panel, the `suite-ui-module.v1` and `suite-chart.v1` contracts, and a React/TypeScript/Vite component toolchain. Its package scripts run type checking, component tests and a module build; the checkout has no shared application shell, product route, or running suite host. The local snapshot has no Git revision metadata. P3 records this observation in `release/P1_HOST_INTEGRATION_AUDIT.json`.

P3 retains its headless panel and typed `p3-wafer-map.v1` callback model. P1 remains the owner for additive C01–C05 capability metadata and a versioned spatial-map renderer contract. CHANGE-002 has no P1 owner approval or merged contract migration yet; interactive host rendering and browser accessibility remain pending that shared integration point.
