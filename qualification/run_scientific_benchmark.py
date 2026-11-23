"""Run synthetic independent-oracle and timing benchmarks; writes no company data."""
from __future__ import annotations

import json
import math
import platform
import random
import statistics
import sys
import time
import tracemalloc
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tree_hash import current_git_commit, source_tree_sha256
from fabintel.catalog import synthetic_catalog
from products.p3.engine import SpatialSignatureIndex, detect_anomalies, fingerprint, search_history

SEED = 20261122
CASE_COUNT = 100
SITES_PER_CASE = 13


def make_case(seed):
    rng = random.Random(seed)
    points = []
    for i in range(3):
        points.append({"site_id": f"C{i}", "x": (i - 1) * 0.08, "y": 0.04, "value": rng.uniform(-8, 8)})
    for i in range(4):
        angle = i * math.pi / 2
        points.append({"site_id": f"E{i}", "x": math.cos(angle), "y": math.sin(angle), "value": rng.uniform(-8, 8) + 3})
    for i in range(6):
        angle = i * math.pi / 3
        radius = 0.35 + 0.25 * (i % 2)
        points.append({"site_id": f"M{i}", "x": radius * math.cos(angle), "y": radius * math.sin(angle), "value": rng.uniform(-8, 8)})
    return {
        "coordinates_verified": True,
        "geometry": {"radius": 1, "origin": {"x": 0, "y": 0}, "orientation_deg": 0, "coordinate_system": "wafer_xy_v1", "coordinate_unit": "mm"},
        "points": points,
        "measurement": {"metric": "m", "unit": "nm", "modality": "continuous", "definition_id": "D1", "layer": "L1"},
        "product_id": "P1", "sampling_mask_id": "M1", "population_signature": "S1",
    }


def make_dense_case(count=13_000):
    golden = math.pi * (3 - math.sqrt(5))
    points = []
    for i in range(count):
        radius = math.sqrt((i + 0.5) / count)
        angle = i * golden
        x, y = radius * math.cos(angle), radius * math.sin(angle)
        value = 10 + 1.75 * radius + 0.2 * math.sin(4 * angle)
        points.append({"site_id": f"D{i}", "x": x, "y": y, "value": value})
    return {
        "coordinates_verified": True,
        "geometry": {"radius": 1, "origin": {"x": 0, "y": 0}, "orientation_deg": 0, "coordinate_system": "wafer_xy_v1", "coordinate_unit": "mm"},
        "points": points,
        "measurement": {"metric": "m", "unit": "nm", "modality": "continuous", "definition_id": "D1", "layer": "L1"},
        "product_id": "P1", "sampling_mask_id": "M1", "population_signature": "S1",
    }


def oracle(data):
    center, edge = [], []
    for point in data["points"]:
        radius = math.sqrt(point["x"] ** 2 + point["y"] ** 2)
        if radius <= 0.2:
            center.append(point["value"])
        elif radius >= 0.8:
            edge.append(point["value"])
    return sum(edge) / len(edge) - sum(center) / len(center)


def percentile(values, q):
    values = sorted(values)
    return values[min(len(values) - 1, max(0, math.ceil(q * len(values)) - 1))]


RETRIEVAL_PATTERNS = ("uniform", "edge", "center", "gradient", "alternating-sectors")


def _retrieval_points(pattern, seed, *, partial=False):
    rng = random.Random(seed)
    coordinates = [(0.0, 0.0)]
    for radius in (0.18, 0.52, 0.92):
        for sector in range(8):
            angle = 2 * math.pi * (sector + 0.21) / 8
            coordinates.append((radius * math.cos(angle), radius * math.sin(angle)))
    scale = rng.uniform(0.97, 1.03)
    offset = rng.gauss(0, 2.0)
    result = []
    for index, (x, y) in enumerate(coordinates):
        radius = math.hypot(x, y)
        sector = int((math.atan2(y, x) + 2 * math.pi) / (math.pi / 4)) % 8
        if pattern == "edge":
            signal = 3.0 if radius >= 0.8 else 0.0
        elif pattern == "center":
            signal = 3.0 if radius <= 0.2 else 0.0
        elif pattern == "gradient":
            signal = 2.0 * x
        elif pattern == "alternating-sectors":
            signal = 2.0 if sector % 2 == 0 else -2.0
        else:
            signal = 0.0
        result.append({"site_id": f"R{index:02d}", "x": x, "y": y,
                       "value": offset + scale * signal + rng.gauss(0, 0.12)})
    if partial:
        # Keep the center and at least one site in every sector and radial band.
        result = [point for index, point in enumerate(result)
                  if index == 0 or index % 5 != 0]
    return result


def _retrieval_map(index, pattern, *, partial=False, timestamp=None):
    item = {
        "coordinates_verified": True,
        "geometry": {"radius": 1, "origin": {"x": 0, "y": 0}, "orientation_deg": 0,
                     "coordinate_system": "wafer_xy_v1", "coordinate_unit": "mm"},
        "measurement": {"metric": "film_thickness", "unit": "nm", "modality": "continuous",
                         "definition_id": "SYN-THICKNESS-1", "layer": "L1"},
        "product_id": "SYN-PRODUCT-1", "sampling_mask_id": "SYN-MASK-PARTIAL" if partial else "SYN-MASK-FULL",
        "population_signature": "SYN-POP-1", "wafer_id": f"W-INDEX-{index:05d}",
        "lot_id": f"LOT-INDEX-{index:05d}",
        "measured_at": timestamp or (datetime(2026, 11, 1, tzinfo=timezone.utc)
                                      - timedelta(minutes=index)).isoformat().replace("+00:00", "Z"),
        "points": _retrieval_points(pattern, SEED + 910_000 + index, partial=partial),
        "oracle_regime": pattern,
    }
    return item


def retrieval_fixture(map_count=1_000):
    """Fixed 1,000-record population with relevant and ineligible history rows."""
    if map_count != 1_000:
        raise ValueError("the locked historical benchmark contains exactly 1,000 maps")
    history = []
    # 850 independent records span five predeclared spatial regimes.
    for index in range(850):
        pattern = RETRIEVAL_PATTERNS[index % len(RETRIEVAL_PATTERNS)]
        history.append(_retrieval_map(index, pattern))
    next_index = 850
    # Context mismatch decoys verify product, measurement and population filters.
    for count, field, value in ((30, "measurement", {"metric": "roughness", "unit": "nm", "modality": "continuous",
                                                     "definition_id": "SYN-THICKNESS-1", "layer": "L1"}),
                               (25, "product_id", "SYN-OTHER-PRODUCT"),
                               (25, "population_signature", "SYN-OTHER-POPULATION")):
        for offset in range(count):
            item = _retrieval_map(next_index, RETRIEVAL_PATTERNS[offset % len(RETRIEVAL_PATTERNS)])
            item[field] = value
            history.append(item)
            next_index += 1
    # Future records and same-lot records are explicitly excluded by the retrieval contract.
    for offset in range(20):
        item = _retrieval_map(next_index, RETRIEVAL_PATTERNS[offset % len(RETRIEVAL_PATTERNS)],
                              timestamp=(datetime(2027, 1, 1, tzinfo=timezone.utc)
                                         + timedelta(minutes=offset)).isoformat().replace("+00:00", "Z"))
        history.append(item)
        next_index += 1
    for offset in range(20):
        pattern = RETRIEVAL_PATTERNS[offset % len(RETRIEVAL_PATTERNS)]
        item = _retrieval_map(next_index, pattern)
        query_class = RETRIEVAL_PATTERNS[offset % len(RETRIEVAL_PATTERNS)]
        item["lot_id"] = f"LOT-QUERY-{query_class}"
        history.append(item)
        next_index += 1
    # Missing identity prevents a candidate from entering an independent retrieval set.
    for offset in range(10):
        item = _retrieval_map(next_index, RETRIEVAL_PATTERNS[offset % len(RETRIEVAL_PATTERNS)])
        item["lot_id" if offset % 2 == 0 else "wafer_id"] = None
        history.append(item)
        next_index += 1
    # A realistic alternate sampling mask is retained and compared by shared profiles.
    for offset in range(20):
        item = _retrieval_map(next_index, RETRIEVAL_PATTERNS[offset % len(RETRIEVAL_PATTERNS)], partial=True)
        history.append(item)
        next_index += 1
    if len(history) != map_count:
        raise AssertionError("historical population fixture composition drifted")

    query_time = "2026-12-01T00:00:00Z"
    queries = []
    for index, pattern in enumerate(RETRIEVAL_PATTERNS):
        target = _retrieval_map(1_100 + index, pattern, partial=(index % 2 == 1), timestamp=query_time)
        target.update({"wafer_id": f"W-QUERY-{index}", "lot_id": f"LOT-QUERY-{pattern}"})
        queries.append(target)
    return queries, history


def _unit_student_t3(rng):
    numerator = rng.gauss(0, 1)
    denominator = math.sqrt(sum(rng.gauss(0, 1) ** 2 for _ in range(3)) / 3)
    return numerator / denominator / math.sqrt(3)


def _unit_skewed_lognormal(rng):
    sigma = 0.55
    variance = (math.exp(sigma * sigma) - 1) * math.exp(sigma * sigma)
    return (math.exp(sigma * rng.gauss(0, 1)) - math.exp(sigma * sigma / 2)) / math.sqrt(variance)


def _anomaly_map(replicate, index, family, rng, *, shifted=False):
    data = make_case(SEED + 1_200_000 + replicate * 32 + index)
    current = index == 20
    when = (datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(days=index)).isoformat().replace("+00:00", "Z")
    data.update({"wafer_id": f"CAL-{replicate}-{index}", "lot_id": f"CAL-LOT-{replicate}-{index}",
                 "measured_at": when, "product_id": "CAL-PRODUCT", "population_signature": "CAL-POP",
                 "sampling_mask_id": "CAL-MASK"})
    draw = {"gaussian": lambda random_source: random_source.gauss(0, 1), "student_t3": _unit_student_t3,
            "skewed_lognormal": _unit_skewed_lognormal}[family]
    wafer_effect = 0.7 * draw(rng)
    for point in data["points"]:
        radius = math.hypot(point["x"], point["y"])
        sector = math.atan2(point["y"], point["x"])
        fixed_spatial_effect = 0.35 * math.cos(2 * sector) + (0.5 if radius >= 0.8 else 0.0)
        value = 10 + fixed_spatial_effect + wafer_effect + 0.3 * draw(rng)
        if current and shifted and radius >= 0.8:
            value += 4.0
        point["value"] = value
    return data


def _wilson_interval(successes, count, z=1.959963984540054):
    proportion = successes / count
    denominator = 1 + z * z / count
    center = (proportion + z * z / (2 * count)) / denominator
    half_width = z * math.sqrt(proportion * (1 - proportion) / count + z * z / (4 * count * count)) / denominator
    return [max(0.0, center - half_width), min(1.0, center + half_width)]


def anomaly_calibration(repetitions=400):
    """Independent seeded null/shift experiment for the wafer-level max-T rank screen."""
    families = ("gaussian", "student_t3", "skewed_lognormal")
    rows = []
    for family_index, family in enumerate(families):
        rng = random.Random(SEED + 1_300_000 + family_index)
        false_alerts = 0
        detections = 0
        for replicate in range(repetitions):
            null_maps = [_anomaly_map(replicate, index, family, rng) for index in range(21)]
            null_result = detect_anomalies(null_maps[-1], null_maps[:-1], holdout_verified=True)
            if null_result.get("status") != "VALID":
                raise AssertionError(f"C04 null calibration refused an eligible generated case: {family}")
            false_alerts += null_result["global_max_t_empirical_p"] <= null_result["alpha"]

            shifted_maps = [_anomaly_map(repetitions + replicate, index, family, rng,
                                         shifted=(index == 20)) for index in range(21)]
            shifted_result = detect_anomalies(shifted_maps[-1], shifted_maps[:-1], holdout_verified=True)
            if shifted_result.get("status") != "VALID":
                raise AssertionError(f"C04 positive calibration refused an eligible generated case: {family}")
            detections += shifted_result["global_max_t_empirical_p"] <= shifted_result["alpha"]
        rows.append({"noise_family": family, "replicates_per_condition": repetitions,
                     "null_false_alerts": false_alerts, "null_rate": false_alerts / repetitions,
                     "null_wilson_95_interval": _wilson_interval(false_alerts, repetitions),
                     "alternative_detections": detections, "alternative_rate": detections / repetitions,
                     "alternative_wilson_95_interval": _wilson_interval(detections, repetitions),
                     "alternative": "predeclared +4 nm edge-site shift; wafer-level max-T decision"})
    # These are broad experiment-sanity bounds, not release or fab thresholds.
    passed = all(row["null_rate"] <= 0.12 and row["alternative_rate"] >= 0.80 for row in rows)
    return {"method": "leave_one_wafer_out_spatial_maxT_rank_v1", "nominal_alpha": 0.05,
            "independent_unit": "wafer; 20 distinct baseline lots and one target lot per replicate",
            "families": rows, "experiment_sanity_bounds": {"maximum_null_false_alert_rate": 0.12,
                "minimum_detection_rate_for_strong_synthetic_edge_shift": 0.80},
            "sanity_bounds_are_product_thresholds": False,
            "status": "PASS" if passed else "FAIL",
            "qualification_boundary": "synthetic exchangeable populations only; no production calibration or company alert threshold"}


def main():
    dataset = [make_case(SEED + i) for i in range(CASE_COUNT)]
    cases = []
    durations = []
    for index, data in enumerate(dataset):
        expected = oracle(data)
        start = time.perf_counter_ns()
        result = fingerprint(data)
        durations.append((time.perf_counter_ns() - start) / 1_000_000)
        passed = math.isclose(result["edge_minus_center"], expected, rel_tol=1e-12, abs_tol=1e-12)
        cases.append({"case": index, "seed": SEED + index, "expected_edge_minus_center": expected,
                      "actual_edge_minus_center": result["edge_minus_center"], "status": "PASS" if passed else "FAIL"})
    tracemalloc.start()
    catalog = synthetic_catalog(13_000)
    _, catalog_peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    catalog_pass = len(catalog) == 13_000 and len({item["id"] for item in catalog}) == 13_000
    dense = make_dense_case()
    dense_expected = oracle(dense)
    dense_durations = []
    for _ in range(50):
        start = time.perf_counter_ns()
        dense_result = fingerprint(dense)
        dense_durations.append((time.perf_counter_ns() - start) / 1_000_000)
    tracemalloc.start()
    fingerprint(dense)
    _, dense_peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    dense_pass = math.isclose(dense_result["edge_minus_center"], dense_expected, rel_tol=1e-12, abs_tol=1e-12)
    retrieval_queries, retrieval_history = retrieval_fixture()
    retrieval_target = retrieval_queries[0]
    direct_result = search_history(retrieval_target, retrieval_history, top_k=5)
    tracemalloc.start()
    index_build_start = time.perf_counter_ns()
    retrieval_index = SpatialSignatureIndex(retrieval_history, max_maps=1_000, max_total_sites=30_000)
    index_build_ms = (time.perf_counter_ns() - index_build_start) / 1_000_000
    _, index_build_peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    direct_query_ms = []
    indexed_query_ms = []
    retrieval_parity = True
    retrieval_oracles = []
    retrieval_repeats = 10
    labels = {item["wafer_id"]: item.get("oracle_regime") for item in retrieval_history}
    for repeat in range(retrieval_repeats):
        for target in retrieval_queries:
            start = time.perf_counter_ns()
            direct = search_history(target, retrieval_history, top_k=5)
            direct_query_ms.append((time.perf_counter_ns() - start) / 1_000_000)
            start = time.perf_counter_ns()
            indexed = retrieval_index.search(target, top_k=5)
            indexed_query_ms.append((time.perf_counter_ns() - start) / 1_000_000)
            same = (direct.get("status") == "VALID" and indexed.get("status") == "VALID"
                    and direct.get("neighbors") == indexed.get("neighbors"))
            retrieval_parity = retrieval_parity and same
            if repeat == 0:
                regime = target["oracle_regime"]
                top_labels = [labels.get(row["wafer_id"]) for row in indexed.get("neighbors", [])]
                precision = sum(label == regime for label in top_labels) / len(top_labels) if top_labels else 0.0
                retrieval_oracles.append({"query_regime": regime, "top_k": 5,
                                          "relevant_top_k": sum(label == regime for label in top_labels),
                                          "precision_at_5": precision,
                                          "all_top_k_relevant": bool(top_labels) and all(label == regime for label in top_labels),
                                          "status": indexed.get("status")})
    # The index is a deep-copied snapshot. Callers must invalidate before applying
    # source updates, then build and publish a new bounded generation.
    update_history = history_before_update = retrieval_history
    update_target = next(target for target in retrieval_queries if target["oracle_regime"] == "uniform")
    old_query = retrieval_index.search(update_target, top_k=5)
    update_candidate = next(item for item in update_history
                            if item.get("oracle_regime") != "uniform"
                            and item.get("lot_id") != update_target["lot_id"]
                            and item.get("product_id") == update_target["product_id"]
                            and item.get("measurement", {}).get("metric") == "film_thickness"
                            and item.get("population_signature") == update_target["population_signature"]
                            and item.get("measured_at", "") < update_target["measured_at"])
    update_candidate["points"] = deepcopy(update_target["points"])
    stale_snapshot_result = retrieval_index.search(update_target, top_k=5)
    snapshot_unchanged_after_source_update = stale_snapshot_result.get("neighbors") == old_query.get("neighbors")
    invalidated_state = retrieval_index.invalidate()
    invalidated_search = retrieval_index.search(update_target, top_k=5)
    refreshed_state = retrieval_index.refresh(history_before_update)
    direct_after_update = search_history(update_target, history_before_update, top_k=5)
    refreshed_after_update = retrieval_index.search(update_target, top_k=5)
    update_rebuild_parity = (direct_after_update.get("neighbors") == refreshed_after_update.get("neighbors"))
    memory_cap_bytes = 64 * 1024 * 1024
    relevance_pass = all(item["all_top_k_relevant"] for item in retrieval_oracles)
    retrieval_pass = (retrieval_parity and relevance_pass and retrieval_index.stats["indexed_maps"] == len(retrieval_history)
                      and index_build_peak <= memory_cap_bytes and snapshot_unchanged_after_source_update
                      and invalidated_search.get("status") == "INCONCLUSIVE" and update_rebuild_parity
                      and refreshed_state["generation"] == 2 and invalidated_state["invalidated"]
                      and not refreshed_state["invalidated"])
    anomaly_result = anomaly_calibration()
    report = {
        "scope": "synthetic external baseline only",
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "environment": {"os": platform.platform(), "architecture": platform.machine(), "python": sys.version,
                        "cpu_count": __import__("os").cpu_count(), "processor": platform.processor()},
        "seed": SEED,
        "fixed_cases": CASE_COUNT,
        "sites_per_case": SITES_PER_CASE,
        "numeric_oracle": {"method": "independent measured-point center/edge arithmetic", "passed": sum(c["status"] == "PASS" for c in cases),
                           "failed": sum(c["status"] == "FAIL" for c in cases), "cases": cases},
        "latency_ms": {"p50": statistics.median(durations), "p95": percentile(durations, 0.95), "samples": len(durations)},
        "synthetic_catalog": {"requested_tables": 13000, "actual_tables": len(catalog), "unique_ids": len({item["id"] for item in catalog}),
                              "peak_traced_bytes": catalog_peak, "status": "PASS" if catalog_pass else "FAIL"},
        "dense_wafer_measurement": {"measured_sites": len(dense["points"]), "p50_ms": statistics.median(dense_durations),
                                     "p95_ms": percentile(dense_durations, 0.95), "peak_traced_bytes": dense_peak,
                                     "expected_edge_minus_center": dense_expected, "actual_edge_minus_center": dense_result["edge_minus_center"],
                                     "status": "PASS" if dense_pass else "FAIL"},
        "c05_history_index_benchmark": {
            "scope": "synthetic 1,000-map historical population with context/time/identity exclusions, alternate sampling and relevance labels; no company data",
            "historical_maps": len(retrieval_history), "measured_sites_per_map": len(retrieval_history[0]["points"]),
            "population_composition": {"relevant_context_independent_maps": 850, "metric_mismatch": 30,
                "product_mismatch": 25, "population_mismatch": 25, "future_records": 20,
                "same_lot_records": 20, "missing_identity_records": 10, "alternate_partial_sampling_maps": 20},
            "query_regimes": len(retrieval_queries), "repeated_queries_per_regime": retrieval_repeats,
            "index_build_ms": index_build_ms, "index_build_peak_traced_bytes_incremental": index_build_peak,
            "direct_query_ms": {"p50": statistics.median(direct_query_ms), "p95": percentile(direct_query_ms, 0.95), "samples": len(direct_query_ms)},
            "indexed_query_ms": {"p50": statistics.median(indexed_query_ms), "p95": percentile(indexed_query_ms, 0.95), "samples": len(indexed_query_ms)},
            "memory_cap_bytes": memory_cap_bytes, "within_memory_cap": index_build_peak <= memory_cap_bytes,
            "result_parity_all_repeats": retrieval_parity,
            "relevance_oracle": {"oracle": "independent generator regime labels; all top-5 must share the query's predeclared spatial regime",
                "mean_precision_at_5": statistics.mean(item["precision_at_5"] for item in retrieval_oracles),
                "queries": retrieval_oracles, "pass": relevance_pass},
            "update_invalidation": {"snapshot_immutable_after_source_mutation": snapshot_unchanged_after_source_update,
                "invalidation_blocks_search": invalidated_search.get("status") == "INCONCLUSIVE",
                "invalidation_reason": invalidated_search.get("reason"),
                "refresh_generation": refreshed_state["generation"],
                "refreshed_matches_direct_after_update": update_rebuild_parity,
                "updated_top1": refreshed_after_update.get("neighbors", [{}])[0].get("wafer_id")},
            "index_stats": retrieval_index.stats,
            "status": "PASS" if retrieval_pass else "FAIL",
        },
        "c04_anomaly_calibration": anomaly_result,
        "thresholds": "No absolute latency, memory, ROI or user-time target was invented; set thresholds after target-hardware and real analyst baseline measurement.",
        "company_data_used": False,
        "source_commit": current_git_commit(ROOT),
        "source_tree_sha256": source_tree_sha256(ROOT),
        "overall": "PASS" if all(c["status"] == "PASS" for c in cases) and catalog_pass and dense_pass
                   and retrieval_pass and anomaly_result["status"] == "PASS" else "FAIL",
    }
    out = ROOT / "release" / "SCIENTIFIC_PERFORMANCE_BENCHMARK.json"
    out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"{report['overall']}: {report['numeric_oracle']['passed']}/{CASE_COUNT} numeric oracle cases; "
          f"catalog {len(catalog)}; p50 {report['latency_ms']['p50']:.3f} ms; p95 {report['latency_ms']['p95']:.3f} ms")
    print(f"Wrote {out.relative_to(ROOT)}")
    print("C04 synthetic calibration: " + ", ".join(
        f"{row['noise_family']} null={row['null_rate']:.3f}, shift_detection={row['alternative_rate']:.3f}"
        for row in anomaly_result["families"]))


if __name__ == "__main__":
    main()
