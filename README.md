# FAB Spatial & Yield Intelligence · P3

P3's analysis core implements observed-site radial/sector summaries, a directional plane, exploratory spatial cell clusters, a matched-population wafer-level anomaly screen, multiscale historical search across compatible measured profiles, same-wafer cross-step deltas, and spatial-block-adjusted wafer/die quality association. P3 includes an independently executable loopback reference host that runs the official MCP SDK through reviewed read-only mappings, executes C01–C05, renders the typed spatial observation contract, and exports provenance-bound evidence. The headless React panel remains available for future shared-suite integration.

For internal OpenCode onboarding, extract this candidate, open the extracted folder as the workspace, and invoke @p3-spatial-onboarding. The skill orchestrates discovery, deterministic proposals, validation, and analysis; only company authorization and semantic approvals require an authorized engineer.

**Release state: CANDIDATE.** The product has not passed target-OS offline installation, independent full qualification, licensing/security review, or authorized internal MCP/data/engineer checks. It is not approved for Samsung data or production use. The provided example is synthetic.

## Run locally

Use Python 3.10 or later for the analysis core. The MCP host requires the bundled, hash-locked SDK. The current offline SDK wheelhouse is qualified only for macOS arm64 with CPython 3.11; other target platforms remain pending. Use the installed environment's Python for every host command so the MCP SDK is available.

The candidate contains the already-built React/ECharts browser assets. They are served locally; no Node.js install, npm cache, CDN, or network is needed to run the product.

Before extraction, verify the archive SHA-256 against the value delivered through the approved transfer channel. The detached checksum file produced beside a locally built candidate uses `shasum -a 256 -c <candidate>.zip.sha256` on macOS.

```sh
python3.11 -m venv .venv
.venv/bin/python -m pip install --no-index --disable-pip-version-check \
  --find-links vendor/mcp-sdk-2.3.0/macos-arm64-cp311/wheelhouse \
  --require-hashes -r vendor/mcp-sdk-2.3.0/macos-arm64-cp311/requirements.lock
.venv/bin/python -m pip check
.venv/bin/python bootstrap_check.py
.venv/bin/python -m fabintel demo
.venv/bin/python -m fabintel analyze fixtures/case_positive.json --output evidence.json
.venv/bin/python -m fabintel reference-host --port 8765
```

Rebuilding or running React tests is development-only. The ZIP carries package.json and the pinned lockfile but not node_modules or an npm cache. Run npm ci --offline --ignore-scripts and npm run build only in an approved development environment with the locked package cache already available; these steps are not required for offline runtime.

Open `http://127.0.0.1:8765/`, select the synthetic source, and run the supplied plans. The host binds only to loopback. Configured mode is enabled only by an operator-set `FABINTEL_MCP_CONFIG` path, and source credentials remain in named environment variables resolved by the adapter. Synthetic MCP permissions are test evidence, never company authorization. Do not paste company data into this candidate build.

P3's authoritative typed map contract is [`products/p3/contracts/spatial-map.v2.schema.json`](products/p3/contracts/spatial-map.v2.schema.json) with TypeScript types alongside it. The module response includes an explicit v1 compatibility adapter only if it can preserve data meaning; it refuses v1 conversion of defect events. P1's v1 categorical converter issue is a separate shared-host compatibility defect and does not block P3 operation.

`python -m fabintel qualify-internal --capture <site-capture.json>` checks the shape and coverage of a site-generated qualification report. It never authenticates a report or changes `PENDING_INTERNAL` to ready. Use the local template at `release/INTERNAL_QUALIFICATION_REPORT_TEMPLATE.json` only through an authorized site-side adapter.

The `mcp-discover` and `mcp-analyze` commands use the official Python MCP SDK 2.3.0 through the logical read-only adapter to inspect an explicitly approved server. The local hash-locked macOS CPython 3.11 wheelhouse is a candidate, not company-cleared; target OS and internal protocol compatibility are pending. Exact source scopes, tool descriptor hashes, and pre-registered query plans are required before bounded reads; no production names, endpoints, mappings, or credentials are supplied here. See [the MCP adapter guide](docs/MCP_ADAPTER.md), [the reference host guide](docs/P3_REFERENCE_HOST.md), and [the placeholder config](requirements/mcp-adapter.template.json).

## Scientific boundaries

- Fingerprints use measured sites only. Empty regions are left unknown; interpolation is not implemented. Sparse local screening uses raw measured values; a dense-only plane-residual screen reduces broad-gradient masking after orientation and coverage gates. All local groups remain exploratory and uncalibrated; reticle periodicity is not computed.
- Anomaly screening requires a matched definition, product/population signature, sampling mask, 20 distinct historical lots, earlier measurement times, and a target holdout. A leave-one-wafer-out spatial max-T rank test preserves within-wafer dependence; localized sites are not individually significant. This screen is conditional and is not company-calibrated.
- Similarity excludes the target wafer and lot and requires a distinct earlier lot and compatible definitions. It uses exact site values where layouts match, otherwise compares sufficiently covered shared radial/sector profile bins without interpolation. It is never a mechanism or root-cause finding.
- Evolution requires the same wafer and lot, distinct step instances, later measurement time, matching metric/unit/definition/layer, verified geometry, and exact observed-site alignment after the declared orientation transform. Different sampling masks can be compared only with a predeclared exact common-site policy and sufficient overlap.
- Quality association requires an approved wafer-to-die relationship, exact match to the selected map's observed sites, fixed spatial blocks, downstream outcomes, a verified out-of-time wafer holdout, and a complete predeclared outcome-blind eligible-wafer frame. Unsupported or unreconciled selection designs abstain. It estimates a block-adjusted within-wafer association with wafer-level uncertainty; it does not establish causation, and P3 does not independently audit the source registry attestation.

See `docs/P3_IMPLEMENTATION_DECISIONS.md`, `docs/TEST_AND_RELEASE_MATRIX.md`, and `release/GATE_REPORT.json` for methods, evidence and open gates.
