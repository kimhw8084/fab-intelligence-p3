"""Compare frozen and joint-profile C05 behavior on spatial marginal aliases.

The synthetic oracle includes a true same joint radial/sector pattern with a
changed sampling layout and a misleading pattern with identical separate radial
and sector marginals. Also reruns the fixed 1,000-map relevance fixture to guard
the established bounded index. No company data is used.
"""
from __future__ import annotations

import argparse
import json
import math
import random
import subprocess  # nosec B404 - explicit local Python and caller-selected source root
import sys
import time
import tracemalloc
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from products.p3.engine import SpatialSignatureIndex, search_history  # noqa: E402
from qualification.run_scientific_benchmark import retrieval_fixture  # noqa: E402

BASELINE_RUNNER = """
import json, sys
from products.p3.engine import search_history
payload = json.load(sys.stdin)
alias = []
for case in payload['alias_cases']:
    result = search_history(case['current'], case['history'], top_k=2)
    alias.append({'status': result.get('status'), 'top1': result.get('neighbors', [{}])[0].get('wafer_id'),
                  'distance': result.get('neighbors', [{}])[0].get('multiscale_rmse')})
retrieval = []
labels = {item['wafer_id']: item.get('oracle_regime') for item in payload['retrieval_history']}
for target in payload['retrieval_queries']:
    result = search_history(target, payload['retrieval_history'], top_k=5)
    retrieval.append({'status': result.get('status'),
                      'neighbors': [row.get('wafer_id') for row in result.get('neighbors', [])],
                      'regimes': [labels.get(row.get('wafer_id')) for row in result.get('neighbors', [])]})
json.dump({'alias': alias, 'retrieval': retrieval}, sys.stdout, allow_nan=False)
"""


def _map(wafer: str, high_cells: set[tuple[int, int]], offset_degrees: float,
         measured_at: str) -> dict[str, Any]:
    points = []
    for radial_bin, radius in enumerate((0.1, 0.4, 0.65, 0.9)):
        for sector in range(8):
            angle = (2 * math.pi * (sector + 0.21) / 8) + math.radians(offset_degrees)
            points.append({"site_id": f"{radial_bin}-{sector}",
                           "x": radius * math.cos(angle), "y": radius * math.sin(angle),
                           "value": 20 + 3 * radial_bin + (4 if (radial_bin, sector) in high_cells else 0)})
    return {
        "coordinates_verified": True,
        "geometry": {"radius": 1, "origin": {"x": 0, "y": 0}, "orientation_deg": 0,
                     "coordinate_system": "wafer_xy_v1", "coordinate_unit": "mm"},
        "measurement": {"metric": "film_thickness", "unit": "nm", "modality": "continuous",
                         "definition_id": "SYN-MET-1", "layer": "L1"},
        "product_id": "SYN-PRODUCT-1", "population_signature": "SYN-POP-1",
        "sampling_mask_id": "SYN-MASK-" + wafer, "wafer_id": wafer,
        "lot_id": "LOT-" + wafer, "measured_at": measured_at, "points": points,
    }


def _alias_cases(count: int, seed_start: int) -> list[dict[str, Any]]:
    cases = []
    for seed in range(seed_start, seed_start + count):
        rng = random.Random(seed)
        inner, outer = rng.sample(range(4), 2)
        first_sector = rng.randrange(4)
        second_sector = first_sector + 4
        true_pattern = {(inner, first_sector), (outer, second_sector)}
        marginal_alias = {(inner, second_sector), (outer, first_sector)}
        current = _map(f"SYN-CURRENT-{seed}", true_pattern, 0, "2026-03-01T00:00:00Z")
        wrong = _map(f"A-WRONG-{seed}", marginal_alias, 1.0, "2026-01-01T00:00:00Z")
        right = _map(f"Z-RIGHT-{seed}", true_pattern, 1.0, "2026-01-02T00:00:00Z")
        cases.append({"current": current, "history": [wrong, right]})
    return cases


def run(baseline_root: Path, *, replicates: int = 40, seed_start: int = 95_000) -> dict[str, Any]:
    baseline_root = baseline_root.resolve()
    if not (baseline_root / "products/p3/engine.py").is_file():
        raise ValueError("--baseline-root must point to the frozen P3 source tree")
    if replicates < 1:
        raise ValueError("replicates must be positive")
    cases = _alias_cases(replicates, seed_start)
    queries, history = retrieval_fixture()
    payload = {"alias_cases": cases, "retrieval_queries": queries, "retrieval_history": history}
    completed = subprocess.run([sys.executable, "-c", BASELINE_RUNNER], cwd=baseline_root,
                               input=json.dumps(payload), text=True, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, check=True, timeout=90,
                               env={key: value for key, value in __import__("os").environ.items()
                                    if key != "PYTHONPATH"})  # nosec B603
    baseline = json.loads(completed.stdout)

    baseline_alias_correct = sum(row["top1"] == f"Z-RIGHT-{seed_start + index}"
                                 for index, row in enumerate(baseline["alias"]))
    candidate_alias = []
    for case in cases:
        result = search_history(case["current"], case["history"], top_k=2)
        candidate_alias.append(result)
    candidate_alias_correct = sum(result.get("neighbors", [{}])[0].get("wafer_id") == case["history"][1]["wafer_id"]
                                  for case, result in zip(cases, candidate_alias))

    labels = {item["wafer_id"]: item.get("oracle_regime") for item in history}
    tracemalloc.start()
    build_started = time.perf_counter_ns()
    index = SpatialSignatureIndex(history, max_maps=1_000, max_total_sites=30_000)
    index_build_ms = (time.perf_counter_ns() - build_started) / 1_000_000
    _, peak_bytes = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    candidate_relevance = []
    candidate_parity = True
    direct_ms = []
    indexed_ms = []
    for target in queries:
        start = time.perf_counter_ns()
        direct = search_history(target, history, top_k=5)
        direct_ms.append((time.perf_counter_ns() - start) / 1_000_000)
        start = time.perf_counter_ns()
        indexed = index.search(target, top_k=5)
        indexed_ms.append((time.perf_counter_ns() - start) / 1_000_000)
        direct_ids = [item["wafer_id"] for item in direct.get("neighbors", [])]
        indexed_ids = [item["wafer_id"] for item in indexed.get("neighbors", [])]
        candidate_parity = candidate_parity and direct_ids == indexed_ids
        regimes = [labels.get(identifier) for identifier in indexed_ids]
        candidate_relevance.append({"query": target["oracle_regime"], "top5_regimes": regimes,
                                    "precision_at_5": sum(item == target["oracle_regime"] for item in regimes) / max(1, len(regimes)),
                                    "all_top5_relevant": bool(regimes) and all(item == target["oracle_regime"] for item in regimes)})
    baseline_relevance = []
    for target, result in zip(queries, baseline["retrieval"]):
        regimes = result["regimes"]
        baseline_relevance.append({"query": target["oracle_regime"],
                                   "precision_at_5": sum(item == target["oracle_regime"] for item in regimes) / max(1, len(regimes)),
                                   "all_top5_relevant": bool(regimes) and all(item == target["oracle_regime"] for item in regimes)})

    candidate_pass = (candidate_alias_correct == replicates and candidate_parity
                      and all(row["all_top5_relevant"] for row in candidate_relevance)
                      and index.stats["indexed_maps"] == len(history))
    return {
        "scope": "independent synthetic C05 retrieval evaluation; no manufacturing validation",
        "spatial_alias_oracle": "true analog preserves planted radial-by-sector cells under a changed angular sampling offset; decoy swaps radial/sector assignments but exactly preserves separate radial and sector marginals",
        "seed_start": seed_start,
        "replicates": replicates,
        "frozen_baseline": {"correct_top1": baseline_alias_correct, "aliases_ranked_first": replicates - baseline_alias_correct,
                            "retrieval_all_top5_relevant": sum(row["all_top5_relevant"] for row in baseline_relevance),
                            "retrieval_mean_precision_at_5": sum(row["precision_at_5"] for row in baseline_relevance) / len(baseline_relevance)},
        "candidate": {"correct_top1": candidate_alias_correct, "aliases_ranked_first": replicates - candidate_alias_correct,
                      "retrieval_all_top5_relevant": sum(row["all_top5_relevant"] for row in candidate_relevance),
                      "retrieval_mean_precision_at_5": sum(row["precision_at_5"] for row in candidate_relevance) / len(candidate_relevance),
                      "direct_index_top5_parity": candidate_parity,
                      "index_build_ms": round(index_build_ms, 3), "index_peak_traced_bytes": peak_bytes,
                      "direct_query_ms": [round(value, 3) for value in direct_ms],
                      "indexed_query_ms": [round(value, 3) for value in indexed_ms],
                      "index_stats": index.stats},
        "retrieval_relevance_oracle": "independently generated five-regime labels from the existing locked 1,000-map fixture; each top five must match the predeclared target pattern; no cause labels",
        "candidate_relevance_detail": candidate_relevance,
        "status": "PASS" if candidate_pass else "FAIL",
        "interpretation": "The joint descriptor disambiguates a demonstrated radial/sector marginal alias across changed layouts. Eight-bin minimum support reduces but does not eliminate within-bin aliasing; resemblance is not cause and real historical relevance remains unvalidated.",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline-root", type=Path, required=True)
    parser.add_argument("--replicates", type=int, default=40)
    args = parser.parse_args()
    print(json.dumps(run(args.baseline_root, replicates=args.replicates), indent=2, sort_keys=True))
