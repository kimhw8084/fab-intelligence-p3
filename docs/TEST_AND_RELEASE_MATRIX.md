# Release-blocking scientific and implementation qualification — FAB Spatial & Yield Intelligence

## Critical independently checked case catalog
The following describe expected behaviors **to be implemented and actually executed by Codex**. The bootstrap supplies only a tiny fixed subset, intentionally insufficient for a product-ready claim. Expand to at least the full catalog with richer parameter sweeps, property/metamorphic tests and correctly sequestered holdouts.

| ID | Input challenge | Required behavior | Independent expected-answer source |
|---|---|---|---|
| P3-01 | center=10 edge=12 measured sites | **edge-center=+2 nm; no interpolated fill** | fixed measured-point arithmetic |
| P3-02 | unknown orientation/coordinate metadata | **REFUSED on spatial conclusion** | missing-coordinates fixture |
| P3-03 | wafer with no center sampling | **INCONCLUSIVE for center-edge metric** | coverage oracle |
| P3-04 | edge ring with same global average as uniform | **distinguish spatial signatures** | ring signature oracle |
| P3-05 | rotated wafer map | **validate orientation before temporal comparison** | rotation transform fixture |
| P3-06 | sparse sites but image interpolation plausible | **observed vs predicted visibly distinct** | measured mask oracle |
| P3-07 | die-map vs continuous nm map | **reject direct pixel arithmetic** | modality mismatch oracle |
| P3-08 | reticle-pattern confounded by sampling grid | **no unsupported periodicity inference** | sampling artifact oracle |
| P3-09 | same-looking wafers different historical causes | **do not assert shared cause from neighbor retrieval** | negative similarity oracle |
| P3-10 | different layer/metric in cross-step records | **no meaningless subtraction** | measurement type oracle |
| P3-11 | invalid die-to-wafer outcome identity | **disable yield association** | join approval oracle |
| P3-12 | train/validation maps share wafer family | **holdout grouped by wafer/lot/time** | leakage fixture |

## Cross-product external release gates
| ID | Check | Evidence required |
|---|---|---|
| E01 | Full integrated scientific workflow, all features | Functional E2E cases, no placeholder critical paths |
| E02 | Independent positive and numeric oracle | Independent fixed expected outputs + held-out cases |
| E03 | Adversarial false claim / refusal | All critical negative examples blocked |
| E04 | Frozen schema, APIs and compatibility | Schema validation + contract fingerprints |
| E05 | Actual read-only authorization + provenance | Denial tests, audit + source lineage |
| E06 | LLM optional + prompt injection boundary | Mock invalid model output, deterministic fallback |
| E07 | Engineer UX and accessibility | Keyboard, errors, chart/table alternatives, recovery |
| E08 | No-network platform install/runtime | Fresh matched OS/arch install with network isolation |
| E09 | Supply-chain/license/security scan | SBOM, license approvals, time-stamped CVE DB |
| E10 | Archive reproducibility, rollback, stop | Hashes, rerun unpack tests, kill switch |
| E11 | Performance, resource and user work | Pre-set baseline comparisons, p95 and user effort |
| E12 | Minimal authorized internal adaptation | Qualify-internal real MCP checklist + guided first result |

## Precommit benchmark method
- Record target OS/architecture CPU/memory, Python/JS/runtime versions, analysis task sizes, expected task mix, correctness oracle, baseline method and threshold BEFORE final holdout scoring.
- Benchmark representative small/medium/13,000-schema source discovery and dense golden event/measurement cases; do not allocate 13,000 fully populated relational tables unless benchmark calls for it.
- Measure source-selection recall and false joins, scientific validity, false positives/abstentions, p50/p95 latency, peak memory, model calls/tokens, full user-review duration and dependency/install cost.
- Noncompensatory safety/false-causal/false-join cases require zero escape in defined critical suite. No percentile score compensates for an invented manufacturing fact.
- A baseline may legitimately outperform a sophisticated model; remove components without justified incremental gain.
- Record failures and retry evidence. A unit test that merely asserts an output exists is not an independent scientific oracle.

## Evidence policy
Every external gate must map to actual test command and artifact path. The supplied `bootstrap_check.py` validates only starter file integrity and a few sanity tests. `EXTERNAL_TRANSFER_READY` is forbidden until code, offline target installation, security/license review, full user path and complete independent science tests exist. Internal readiness is separate and can never be certified using synthetic cases.
