"""Measure bounded C05 build, repeated search, refresh and memory at 10k maps."""
from __future__ import annotations

import json
import gc
import math
import random
import statistics
import sys
import time
import tracemalloc
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    import resource
except ImportError:  # pragma: no cover - Windows does not expose the resource module.
    resource = None  # type: ignore[assignment]

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from products.p3.engine import SpatialSignatureIndex, search_history


def _map(wafer: str, lot: str, measured_at: str, regime: str, layout: int,
         rng: random.Random, *, product: str = "SYN-PRODUCT-A", layer: str = "L1",
         metric: str = "film_thickness", valid: bool = True) -> dict:
    hotspot_a = {(2, 1), (2, 2), (3, 1), (3, 2)}
    hotspot_b = {(1, 5), (1, 6), (2, 5), (2, 6)}
    points = []
    for radial, radius in enumerate((0.1, 0.4, 0.65, 0.9)):
        for sector in range(8):
            if layout == 1 and sector in {0, 4}:
                continue
            angle = 2 * math.pi * (sector + 0.2) / 8
            value = 100 + radial * 0.3 + rng.gauss(0, 0.04)
            if regime == "pattern-a" and (radial, sector) in hotspot_a:
                value += 2.0
            elif regime == "pattern-b" and (radial, sector) in hotspot_b:
                value += 2.0
            points.append({"site_id": f"R{radial}-S{sector}", "x": radius * math.cos(angle),
                           "y": radius * math.sin(angle), "value": round(value, 6)})
    result = {
        "coordinates_verified": True,
        "geometry": {"radius": 1, "origin": {"x": 0, "y": 0}, "orientation_deg": 0,
                     "coordinate_system": "wafer_xy_v1", "coordinate_unit": "mm"},
        "measurement": {"metric": metric, "unit": "nm" if metric == "film_thickness" else "nm/min",
                        "modality": "continuous", "definition_id": "SYN-MET-1" if metric == "film_thickness" else "SYN-ETCH-1",
                        "layer": layer},
        "product_id": product, "population_signature": "SYN-C05-POP-1",
        "sampling_mask_id": f"LAYOUT-{layout}-{wafer}", "wafer_id": wafer, "lot_id": lot,
        "measured_at": measured_at, "points": points,
    }
    if not valid:
        result["geometry"]["radius"] = 0
    return result


def build_population(count: int = 10_000, seed: int = 730_051):
    rng = random.Random(seed)
    history = []
    start = datetime(2022, 1, 1, tzinfo=timezone.utc)
    relevant = set()
    for index in range(count):
        incompatible = 1_060 <= index < 1_560
        if index < 60 or incompatible:
            regime = "pattern-a"
            if index < 60:
                relevant.add(f"SYN-HIST-{index:05d}")
        elif index < 1_060:
            regime = "pattern-b" if index % 2 else "normal"
        else:
            regime = "normal"
        layout = 1 if index % 3 == 0 else 0
        product = "SYN-PRODUCT-B" if incompatible and index % 3 == 0 else "SYN-PRODUCT-A"
        layer = "L2" if incompatible and index % 3 == 1 else "L1"
        metric = "etch_rate" if incompatible and index % 3 == 2 else "film_thickness"
        instant = start + timedelta(hours=index)
        item = _map(f"SYN-HIST-{index:05d}", f"SYN-LOT-{index:05d}",
                    instant.isoformat(), regime, layout, rng, product=product, layer=layer, metric=metric,
                    valid=index not in {2_111, 5_555, 8_888})
        history.append(item)
    current_time = (start + timedelta(hours=count + 24 * 30)).isoformat()
    queries = []
    for query_index in range(5):
        queries.append(_map(f"SYN-TARGET-{query_index}", f"SYN-TARGET-LOT-{query_index}",
                             current_time, "pattern-a", query_index % 2,
                             random.Random(seed + query_index + 1_000_000)))
    return history, queries, relevant


def _peak_rss_bytes() -> int | None:
    if resource is None:
        return None
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return int(value if sys.platform == "darwin" else value * 1024)


def run(count: int = 10_000, seed: int = 730_051) -> dict:
    if type(count) is not int or not 1_000 <= count <= 15_000:
        raise ValueError("count must be in the bounded 1,000..15,000 range")
    history, queries, relevant = build_population(count, seed)
    total_sites = sum(len(item["points"]) for item in history)
    population_peak_rss_bytes = _peak_rss_bytes()

    build_start = time.perf_counter_ns()
    timed_index = SpatialSignatureIndex(history, max_maps=15_000, max_total_sites=500_000)
    build_ms = (time.perf_counter_ns() - build_start) / 1_000_000
    post_index_peak_rss_bytes = _peak_rss_bytes()
    del timed_index
    gc.collect()

    # Trace only index-owned allocations; keep the measured query path uninstrumented.
    tracemalloc.start()
    index = SpatialSignatureIndex(history, max_maps=15_000, max_total_sites=500_000)
    _, build_peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    direct_times = []
    indexed_times = []
    direct_ids = []
    indexed_ids = []
    relevance = []
    first_excluded = []
    for query in queries:
        started = time.perf_counter_ns()
        direct = search_history(query, history, top_k=5)
        direct_times.append((time.perf_counter_ns() - started) / 1_000_000)
        started = time.perf_counter_ns()
        indexed = index.search(query, top_k=5)
        indexed_times.append((time.perf_counter_ns() - started) / 1_000_000)
        direct_ids.append([row["wafer_id"] for row in direct.get("neighbors", [])])
        if not first_excluded:
            first_excluded = direct.get("excluded", [])
        indexed_ids.append([row["wafer_id"] for row in indexed.get("neighbors", [])])
        relevance.append(sum(identifier in relevant for identifier in indexed_ids[-1]) / 5)

    invalidated = index.invalidate()
    invalidated_search = index.search(queries[0], top_k=5)
    updated_history = list(history)
    updated_history[-1] = _map("SYN-HIST-UPDATED", "SYN-LOT-UPDATED",
                               (datetime(2022, 1, 1, tzinfo=timezone.utc)
                                + timedelta(hours=count)).isoformat(), "normal", 0,
                               random.Random(seed + 2_000_000))
    refresh_start = time.perf_counter_ns()
    refreshed = index.refresh(updated_history)
    refresh_ms = (time.perf_counter_ns() - refresh_start) / 1_000_000
    post_refresh = index.search(queries[0], top_k=5)
    excluded_ids = {row.get("wafer_id") for row in first_excluded}
    incompatible_ids = {item["wafer_id"] for item in history if item["product_id"] != "SYN-PRODUCT-A"
                        or item["measurement"]["layer"] != "L1"
                        or item["measurement"]["metric"] != "film_thickness"}
    invalid_ids = {"SYN-HIST-02111", "SYN-HIST-05555", "SYN-HIST-08888"}

    return {
        "scope": "deterministic synthetic C05 scale qualification; no manufacturing validation",
        "seed": seed, "historical_maps": count, "historical_sites": total_sites,
        "map_layouts": {"complete": sum(len(item["points"]) == 32 for item in history),
                         "sparse_24_site": sum(len(item["points"]) == 24 for item in history)},
        "incompatible_context_decoys": 500, "invalid_geometry_records": 3,
        "relevant_pattern_analogs": len(relevant), "query_count": len(queries),
        "resource_bounds": {"max_maps": 15_000, "max_total_sites": 500_000,
                            "population_within_site_bound": total_sites <= 500_000},
        "index": {"build_ms": round(build_ms, 3), "build_peak_traced_bytes": build_peak,
                  "process_peak_rss_after_index_bytes": post_index_peak_rss_bytes,
                  "estimated_index_incremental_peak_rss_bytes": (
                      max(0, post_index_peak_rss_bytes - population_peak_rss_bytes)
                      if post_index_peak_rss_bytes is not None and population_peak_rss_bytes is not None else None),
                  "refresh_full_snapshot_ms": round(refresh_ms, 3),
                  "invalidation_status": invalidated["invalidated"],
                  "invalidated_search_status": invalidated_search["status"],
                  "invalidated_search_reason": invalidated_search.get("reason"),
                  "generation_after_refresh": refreshed["generation"],
                  "post_refresh_status": post_refresh["status"],
                  "indexed_maps": refreshed["indexed_maps"], "excluded_maps": refreshed["excluded_maps"],
                  "indexed_sites": refreshed["indexed_sites"]},
        "search": {"direct_query_ms": [round(value, 3) for value in direct_times],
                   "indexed_query_ms": [round(value, 3) for value in indexed_times],
                   "direct_median_ms": round(statistics.median(direct_times), 3),
                   "indexed_median_ms": round(statistics.median(indexed_times), 3),
                   "direct_index_top5_parity": direct_ids == indexed_ids,
                   "top5_relevance_by_query": relevance,
                   "mean_precision_at_5": round(statistics.mean(relevance), 4)},
        "exclusion_oracle": {"incompatible_context_records": len(incompatible_ids),
                             "incompatible_context_records_excluded": len(incompatible_ids & excluded_ids),
                             "invalid_geometry_records": len(invalid_ids),
                             "invalid_geometry_records_excluded": len(invalid_ids & excluded_ids)},
        "independent_relevance_oracle": "60 prior records share the planted radial-sector signature, including changed 24-site masks; 500 product/layer/metric-incompatible records contain the same target signature; 500 same-context decoys contain an opposite radial-sector signature with the same number of elevated cells; all remaining records are null spatial backgrounds",
        "assumptions_and_limits": ["synthetic labels are independent ground truth, not production relevance",
                                   "profile resemblance is not common root cause",
                                   "this is one local process, not a fleet-memory service benchmark"],
        "status": ("PASS" if total_sites <= 500_000 and refreshed["indexed_maps"] == count - 3
                  and refreshed["excluded_maps"] == 3 and direct_ids == indexed_ids
                  and all(value == 1.0 for value in relevance)
                  and len(incompatible_ids & excluded_ids) == len(incompatible_ids)
                  and len(invalid_ids & excluded_ids) == len(invalid_ids)
                  and invalidated_search["status"] == "INCONCLUSIVE" and post_refresh["status"] == "VALID"
                  else "FAIL"),
    }


if __name__ == "__main__":
    print(json.dumps(run(), indent=2, sort_keys=True))
