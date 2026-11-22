# FAB Spatial & Yield Intelligence · P3

P3 is an offline, standard-library candidate for inspecting measured wafer maps. It implements observed-site radial/sector summaries, a directional plane, exploratory spatial cell clusters, a matched-population anomaly screen, multiscale exact-site historical search, same-wafer cross-step deltas, and spatial-block-adjusted wafer/die quality association. The local UI and CLI operate on supplied JSON only.

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

## Scientific boundaries

- Fingerprints use measured sites only. Empty regions are left unknown; interpolation is not implemented. Local cell clusters are exploratory and uncalibrated; reticle periodicity is not computed.
- Anomaly candidates require a matched definition, product/population signature, sampling mask, 20 distinct historical lots, earlier measurement times, and an asserted wafer/lot/time holdout. Empirical site tails receive Benjamini-Hochberg correction. This screen is conditional and is not company-calibrated.
- Similarity requires an exact matched observed-site set, a distinct earlier lot and compatible definitions. It ranks centered site, radial-profile and sector-profile distances and is never a mechanism or root-cause finding.
- Evolution requires the same wafer and lot, distinct step instances, later measurement time, matching metric/unit/definition/layer, verified geometry, and exact observed-site alignment after the declared orientation transform.
- Quality association requires an approved wafer-to-die relationship, exact match to the selected map's observed sites, fixed spatial blocks, downstream outcomes, and a verified out-of-time wafer holdout. It estimates a block-adjusted within-wafer association with wafer-level uncertainty; it does not establish causation.

See `docs/P3_IMPLEMENTATION_DECISIONS.md`, `docs/TEST_AND_RELEASE_MATRIX.md`, and `release/GATE_REPORT.json` for methods, evidence and open gates.
