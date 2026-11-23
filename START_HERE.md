# Start here · FAB Spatial & Yield Intelligence P3

This folder contains the P3 candidate source, a headless suite panel, standard-library analysis engine, synthetic fixtures, test suite, frozen v1 contract, an offline candidate MCP SDK wheelhouse, and an internal qualification template. It does not contain company MCP credentials, approved source mappings, deployment approval, or real manufacturing data.

## Run and inspect

1. Use Python 3.10+.
2. Run `python bootstrap_check.py` to verify the current manifest and full local test suite.
3. Run `python -m fabintel demo` for a synthetic evidence envelope exercising C01–C05; every result is labeled synthetic.
4. Mount `products/p3/ui/P3Panel.tsx` through the P1-owned suite host; P3 ships no local route or server.
5. For an input JSON map, run `python -m fabintel analyze map.json --output evidence.json`.
6. Run `python -m fabintel qualify-internal` to see the internal gaps, or pass an authorized site-generated capture with `--capture`.

P3's analysis entrypoint is `products.p3.engine:analyze`; the former loopback API survives only as a test fixture. The P3 panel labels synthetic mode, draws only verified supplied measured points through the host renderer, shows capability-specific gaps, and keeps provenance and limitations visible. Do not enter company data into this candidate build.

## Local verification

`python -m unittest discover -s tests -v` covers fixed independent numeric cases, refusal boundaries, all five P3 methods, the headless API fixture, and internal qualification status handling. `python qualification/run_local_qualification.py` adds the P1-hosted React component/type checks and hash-locked offline MCP SDK install. `docs/GOLDEN_REUSE_MAPPING.md` maps P3 evidence to Golden's pilot rules and identifies deferred or unrun items; Golden remains a pre-qualification reference. `release/GATE_REPORT.json` records which evidence still needs target hardware, independent review, license/security tooling, suite-host integration, or authorized company access.

The shared schemas and `contracts/SHARED_ARCHITECTURE.md` remain v1.0.0. This P3 checkout owns `products/p3/`, its tests and product evidence only; shared contract changes require the documented RFC and compatibility process.
