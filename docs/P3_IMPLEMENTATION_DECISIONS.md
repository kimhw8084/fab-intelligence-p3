# P3 implementation decisions

## D-001 · Keep the first qualified path standard-library only

Use Python's standard library for the deterministic P3 baseline, JSON interface and loopback UI. The current methods operate on measured points and exact coordinate matches; they do not need image interpolation, model training, a database, or a service framework. A third-party library would add offline packaging, maintenance and license work without a demonstrated result-quality gain. Reopen the choice only if the frozen challenge suite identifies a concrete capability or performance gap.

## D-002 · Treat the measured-site mask as part of the data

Every numeric fingerprint is computed from supplied observations only. Missing center/edge coverage produces an inconclusive edge-center measure. C02 and C05 require exact matched observed coordinates after the declared rotation; the engine does not interpolate or register arbitrary transforms. C01 reports robust radial regions and orientation-aware sectors, a least-squares directional plane, and exploratory fixed-grid local-cell clusters where geometry is known. The local-cell threshold is not calibrated. Reticle periodicity stays `NOT_COMPUTED` until reticle geometry and sampling-alias checks exist.

## D-003 · C04 is a conditional matched-population screen

C04 compares each measured site with a per-site empirical distribution from at least 20 distinct prior lots. Metric definition, layer, product, population signature, wafer geometry and sampling mask must match; target lot must be held out; baseline timestamps must precede the target. It reports median/MAD robust scores and applies Benjamini-Hochberg correction to empirical two-sided site-tail values at 0.05. This does not calibrate a production false-alert rate and is not a causal explanation.

## D-004 · C05 ranks multiscale shape without claiming mechanism

C05 combines centered exact-site RMSE with radial-profile and sector-profile distances over exactly matching observed coordinates. It separately reports raw RMSE and mean-level difference. It excludes the target wafer and lot, future records, incompatible definitions, geometry, coordinate frames and masks. Retrieval quality and useful-neighbor relevance still need independent blinded fab review.

## D-005 · C02 requires same-wafer temporal evidence

C02 requires same wafer and lot, distinct step instances, increasing timezone-aware measurement times, equal product/metric/definition/unit/layer, matching population and sampling metadata, verified orientation, and identical observed coordinate sets after rotation. It accepts an ordered series of steps, reports signed site deltas and same-direction persistence, records missing repeatability/transform uncertainty, and emits no unobserved values.

## D-006 · C03 uses wafer as the independent unit

C03 pairs the feature and later outcome at the selected map's exact observed die coordinates, applies fixed spatial-block centering within each wafer, then summarizes wafer-level correlations across holdout wafers with an equal-wafer Fisher-z interval. It requires at least 20 holdout wafers from distinct lots and five matched die sites per wafer, including at least two observations in each of two predeclared spatial blocks. The relation, block mapping, time ordering and out-of-time split grouped by both wafer and lot must be verified at the site. Where the selected map carries recipe, tool, chamber, or route identifiers, the downstream context and rows must match those identifiers. It reports association only; product mix, selection and other confounding remain.

## D-007 · No external adapter or model is simulated

This package has no Samsung MCP client and no model path. JSON inputs that request `INTERNAL_AUTHORIZED` are refused. The internal preflight consumes a site-generated logical-operation capture using the packaged contract names, lists missing evidence, and always retains `PENDING_INTERNAL`; it cannot authenticate company authority or grant approval.

## Known work still open

The algorithm thresholds and population assumptions require holdout qualification on representative approved data. Reticle periodicity scores require a traceable alias review and remain exploratory; local-cell clusters are not calibrated for alerting. Arbitrary registration, confound adjustment beyond the predeclared block effect, independent retrieval relevance, real task-study thresholds, company source discovery, target-OS air-gap install, license/rights approval, and signed independent audit remain release gates.
