# Start here · FAB Spatial & Yield Intelligence P3

This folder contains the P3 candidate source, offline local UI, standard-library CLI, synthetic fixtures, test suite, frozen v1 contract, and internal qualification template. It does not contain an approved Samsung MCP connection, real source mappings, corporate approval, or the authoritative literal R01–R53/Golden Standard documents.

## Run and inspect

1. Use Python 3.10+.
2. Run `python bootstrap_check.py` to verify the current manifest and full local test suite.
3. Run `python -m fabintel demo` for a synthetic evidence envelope exercising C01–C05; every result is labeled synthetic.
4. Run `python -m fabintel serve` for the loopback-only engineer UI at `http://127.0.0.1:8765/`; press Ctrl-C to stop it.
5. For an input JSON map, run `python -m fabintel analyze map.json --output evidence.json`.
6. Run `python -m fabintel qualify-internal` to see the internal gaps, or pass an authorized site-generated capture with `--capture`.

No product request reaches an external host. The UI clearly labels synthetic mode, draws only supplied measured points, shows capability-specific gaps, and exports the typed evidence envelope. Do not enter company data into this candidate build.

## Local verification

`python -m unittest discover -s tests -v` covers fixed independent numeric cases, refusal boundaries, all five P3 methods, the loopback HTTP flow, and internal qualification status handling. `release/GATE_REPORT.json` records which evidence still needs target hardware, independent review, license/security tooling, or authorized company access.

The shared schemas and `contracts/SHARED_ARCHITECTURE.md` remain v1.0.0. This P3 checkout owns `products/p3/`, its tests and product evidence only; shared contract changes require the documented RFC and compatibility process.
