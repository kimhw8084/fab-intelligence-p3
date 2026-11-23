# FAB Spatial & Yield Intelligence · P3

P3 is an offline, standard-library candidate for inspecting measured wafer maps. It implements observed-site radial/sector summaries, a directional plane, exploratory spatial cell clusters, a matched-population wafer-level anomaly screen, multiscale historical search across compatible measured profiles, same-wafer cross-step deltas, and spatial-block-adjusted wafer/die quality association. The local UI and deterministic analysis operate on supplied JSON; the separately configured MCP tool supports bounded read-only discovery and data access.

**Release state: CANDIDATE.** The product has not passed target-OS offline installation, independent full qualification, licensing/security review, or authorized internal MCP/data/engineer checks. It is not approved for Samsung data or production use. The provided example is synthetic.

## Run locally

Use Python 3.10 or later; there are no third-party Python or browser dependencies.

```sh
python bootstrap_check.py
python -m fabintel demo
python -m fabintel analyze fixtures/case_positive.json --output evidence.json
python -m fabintel serve
```

The UI listens on `127.0.0.1:8765`; stop it with Ctrl-C. It rejects internal-authorized mode and makes no network calls. Do not paste company data into this candidate build.

`python -m fabintel qualify-internal --capture <site-capture.json>` checks the shape and coverage of a site-generated qualification report. It never authenticates a report or changes `PENDING_INTERNAL` to ready. Use the local template at `release/INTERNAL_QUALIFICATION_REPORT_TEMPLATE.json` only through an authorized site-side adapter.

The optional `mcp-discover` command uses configured stdio or Streamable HTTP transport to inspect a site-approved read-only MCP server. Exact source scopes, tool descriptor hashes, and pre-registered query plans are required before bounded reads; no production names, endpoints, mappings, or credentials are supplied here. See [the MCP adapter guide](docs/MCP_ADAPTER.md) and [the placeholder config](requirements/mcp-adapter.template.json).

## Scientific boundaries

- Fingerprints use measured sites only. Empty regions are left unknown; interpolation is not implemented. Local cell clusters are exploratory and uncalibrated; reticle periodicity is not computed.
- Anomaly screening requires a matched definition, product/population signature, sampling mask, 20 distinct historical lots, earlier measurement times, and a target holdout. A leave-one-wafer-out spatial max-T rank test preserves within-wafer dependence; localized sites are not individually significant. This screen is conditional and is not company-calibrated.
- Similarity excludes the target wafer and lot and requires a distinct earlier lot and compatible definitions. It uses exact site values where layouts match, otherwise compares sufficiently covered shared radial/sector profile bins without interpolation. It is never a mechanism or root-cause finding.
- Evolution requires the same wafer and lot, distinct step instances, later measurement time, matching metric/unit/definition/layer, verified geometry, and exact observed-site alignment after the declared orientation transform. Different sampling masks can be compared only with a predeclared exact common-site policy and sufficient overlap.
- Quality association requires an approved wafer-to-die relationship, exact match to the selected map's observed sites, fixed spatial blocks, downstream outcomes, and a verified out-of-time wafer holdout. It estimates a block-adjusted within-wafer association with wafer-level uncertainty; it does not establish causation.

See `docs/P3_IMPLEMENTATION_DECISIONS.md`, `docs/TEST_AND_RELEASE_MATRIX.md`, and `release/GATE_REPORT.json` for methods, evidence and open gates.
