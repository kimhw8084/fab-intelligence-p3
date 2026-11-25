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
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tree_hash import current_git_commit, source_tree_sha256

from fabintel.catalog import synthetic_catalog
from products.p3.engine import (
    SpatialSignatureIndex,
    associate_quality,
    detect_anomalies,
    fingerprint,
    search_history,
)

SEED = 20261122
CASE_COUNT = 100
SITES_PER_CASE = 13


def make_case(seed):
    rng = random.Random(seed)  # nosec B311
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
    rng = random.Random(seed)  # nosec B311
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
        "measured_at": timestamp or (datetime(2026, 11, 1, tzinfo=UTC)
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
                              timestamp=(datetime(2027, 1, 1, tzinfo=UTC)
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
    when = (datetime(2026, 1, 1, tzinfo=UTC) + timedelta(days=index)).isoformat().replace("+00:00", "Z")
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
        rng = random.Random(SEED + 1_300_000 + family_index)  # nosec B311
        false_alerts = 0
        detections = 0
        null_stability_abstentions = 0
        alternative_stability_abstentions = 0
        for replicate in range(repetitions):
            null_maps = [_anomaly_map(replicate, index, family, rng) for index in range(21)]
            null_result = detect_anomalies(null_maps[-1], null_maps[:-1], holdout_verified=True)
            if null_result.get("status") == "INCONCLUSIVE" and null_result.get("baseline_temporal_stability", {}).get("status") == "INCONCLUSIVE":
                null_stability_abstentions += 1
            elif null_result.get("status") == "VALID":
                false_alerts += null_result["global_max_t_empirical_p"] <= null_result["alpha"]
            else:
                raise AssertionError(f"C04 null calibration refused an eligible generated case: {family}")

            shifted_maps = [_anomaly_map(repetitions + replicate, index, family, rng,
                                         shifted=(index == 20)) for index in range(21)]
            shifted_result = detect_anomalies(shifted_maps[-1], shifted_maps[:-1], holdout_verified=True)
            if shifted_result.get("status") == "INCONCLUSIVE" and shifted_result.get("baseline_temporal_stability", {}).get("status") == "INCONCLUSIVE":
                alternative_stability_abstentions += 1
            elif shifted_result.get("status") == "VALID":
                detections += shifted_result["global_max_t_empirical_p"] <= shifted_result["alpha"]
            else:
                raise AssertionError(f"C04 positive calibration refused an eligible generated case: {family}")
        rows.append({"noise_family": family, "replicates_per_condition": repetitions,
                     "null_false_alerts": false_alerts, "null_rate": false_alerts / repetitions,
                     "null_wilson_95_interval": _wilson_interval(false_alerts, repetitions),
                     "null_baseline_shift_abstentions": null_stability_abstentions,
                     "null_baseline_shift_abstention_rate": null_stability_abstentions / repetitions,
                     "null_alert_rate_conditional_on_stability_pass": false_alerts / max(1, repetitions - null_stability_abstentions),
                     "alternative_detections": detections, "alternative_rate": detections / repetitions,
                     "alternative_wilson_95_interval": _wilson_interval(detections, repetitions),
                     "alternative_baseline_shift_abstentions": alternative_stability_abstentions,
                     "alternative_baseline_shift_abstention_rate": alternative_stability_abstentions / repetitions,
                     "alternative_detection_rate_conditional_on_stability_pass": detections / max(1, repetitions - alternative_stability_abstentions),
                     "alternative": "predeclared +4 nm edge-site shift; wafer-level max-T decision"})
    # These are broad experiment-sanity bounds, not release or fab thresholds.
    passed = all(row["null_rate"] <= 0.12 and row["alternative_rate"] >= 0.80 for row in rows)
    shift_result = baseline_shift_challenge()
    pattern_result = anomaly_pattern_calibration()
    size_result = baseline_size_calibration()
    passed = (passed and shift_result["status"] == "PASS"
              and pattern_result["status"] == "PASS" and size_result["status"] == "PASS")
    return {"method": "leave_one_wafer_out_spatial_maxT_rank_v1",
            "baseline_shift_screen": {"method": "whole_wafer_max_split_spatial_profile_permutation_v1",
                                      "alpha": 0.01, "permutations": 499,
                                      "interpretation": "screen for an ordered shift in global, radial, sector and populated radial-sector profiles; NO_SHIFT_DETECTED is not proof of stationarity"},
            "baseline_shift_challenge": shift_result,
            "site_pattern_challenge": pattern_result,
            "baseline_size_challenge": size_result, "nominal_alpha": 0.05,
            "independent_unit": "wafer; 20 distinct baseline lots and one target lot per replicate",
            "families": rows, "experiment_sanity_bounds": {"maximum_null_false_alert_rate": 0.12,
                "minimum_detection_rate_for_strong_synthetic_edge_shift": 0.80},
            "sanity_bounds_are_product_thresholds": False,
            "status": "PASS" if passed else "FAIL",
            "qualification_boundary": "synthetic exchangeable populations only; no production calibration or company alert threshold"}


def baseline_shift_challenge(repetitions=200):
    """Test C04 abstention under synthetic global, radial and abrupt baseline drift."""
    scenarios = {
        "subtle_global_linear_0.1_per_wafer": lambda index, point: 0.1 * index,
        "strong_global_linear_0.2_per_wafer": lambda index, point: 0.2 * index,
        "subtle_edge_linear_0.1_per_wafer": lambda index, point: 0.1 * index if math.hypot(point["x"], point["y"]) >= 0.8 else 0.0,
        "strong_edge_linear_0.2_per_wafer": lambda index, point: 0.2 * index if math.hypot(point["x"], point["y"]) >= 0.8 else 0.0,
        "subtle_abrupt_edge_shift_last_10_wafer_1.5": lambda index, point: 1.5 if index >= 10 and math.hypot(point["x"], point["y"]) >= 0.8 else 0.0,
        "strong_abrupt_edge_shift_last_10_wafer_2.0": lambda index, point: 2.0 if index >= 10 and math.hypot(point["x"], point["y"]) >= 0.8 else 0.0,
    }
    rows = []
    for scenario_index, (name, shift) in enumerate(scenarios.items()):
        refusals = 0
        for replicate in range(repetitions):
            rng = random.Random(SEED + 1_450_000 + scenario_index * repetitions + replicate)  # nosec B311
            maps = [_anomaly_map(replicate, index, "gaussian", rng) for index in range(21)]
            for index, item in enumerate(maps[:-1]):
                for point in item["points"]:
                    point["value"] += shift(index, point)
            result = detect_anomalies(maps[-1], maps[:-1], holdout_verified=True)
            if result.get("status") == "INCONCLUSIVE" and result.get("baseline_temporal_stability", {}).get("status") == "INCONCLUSIVE":
                refusals += 1
            elif result.get("status") != "VALID":
                raise AssertionError(f"C04 drift fixture failed for an unrelated reason: {name}")
        rate = refusals / repetitions
        rows.append({"scenario": name, "replicates": repetitions, "baseline_shift_abstentions": refusals,
                     "abstention_rate": rate, "wilson_95_interval": _wilson_interval(refusals, repetitions),
                     "synthetic_only": True})
    strong_scenarios = [row for row in rows if row["scenario"].startswith("strong_")]
    passed = all(row["abstention_rate"] >= 0.80 for row in strong_scenarios)
    return {"scenarios": rows,
            "experiment_sanity_bounds": {"minimum_abstention_rate_for_declared_strong_drift": 0.80,
                                          "sanity_bound_is_company_threshold": False},
            "status": "PASS" if passed else "FAIL",
            "boundary": "generated independent-lot populations only; weaker shifts are reported without a pass threshold"}


def anomaly_pattern_calibration(repetitions=200):
    """Calibrate global, center, sector, edge and single-site target alternatives."""
    cases = {
        "strong_global_shift_4": (lambda point: True, 4.0),
        "strong_center_shift_4": (lambda point: math.hypot(point["x"], point["y"]) <= 0.2, 4.0),
        "strong_sector0_shift_4": (lambda point: (int(((math.atan2(point["y"], point["x"]) + 2 * math.pi) % (2 * math.pi) / (math.pi / 4)) % 8) == 0
                                                     and math.hypot(point["x"], point["y"]) > 0.2), 4.0),
        "strong_edge_shift_4": (lambda point: math.hypot(point["x"], point["y"]) >= 0.8, 4.0),
        "probe_single_edge_site_shift_4": (lambda point: point["site_id"] == "E0", 4.0),
        "subtle_global_shift_1": (lambda point: True, 1.0),
        "subtle_edge_shift_1": (lambda point: math.hypot(point["x"], point["y"]) >= 0.8, 1.0),
    }
    rows = []
    for scenario_index, (name, (select, magnitude)) in enumerate(cases.items()):
        detections = 0
        abstentions = 0
        for replicate in range(repetitions):
            rng = random.Random(SEED + 1_500_000 + scenario_index * repetitions + replicate)  # nosec B311
            maps = [_anomaly_map(replicate, index, "gaussian", rng) for index in range(21)]
            for point in maps[-1]["points"]:
                if select(point):
                    point["value"] += magnitude
            result = detect_anomalies(maps[-1], maps[:-1], holdout_verified=True)
            if result.get("status") == "INCONCLUSIVE" and result.get("baseline_temporal_stability", {}).get("status") == "INCONCLUSIVE":
                abstentions += 1
            elif result.get("status") == "VALID":
                detections += result["global_max_t_empirical_p"] <= result["alpha"]
            else:
                raise AssertionError(f"C04 site-pattern fixture failed for an unrelated reason: {name}")
        rows.append({"scenario": name, "replicates": repetitions,
                     "detections": detections, "unconditional_detection_rate": detections / repetitions,
                     "detection_wilson_95_interval": _wilson_interval(detections, repetitions),
                     "baseline_stability_abstentions": abstentions,
                     "baseline_stability_abstention_rate": abstentions / repetitions,
                     "synthetic_only": True})
    required = [row for row in rows if row["scenario"].startswith("strong_")]
    passed = all(row["unconditional_detection_rate"] >= 0.80 for row in required)
    return {"scenarios": rows,
            "experiment_sanity_bounds": {"minimum_detection_for_declared_strong_multi_site_patterns": 0.80,
                                          "sanity_bound_is_company_threshold": False},
            "status": "PASS" if passed else "FAIL",
            "boundary": "one-site and subtle-shift probes have no pass threshold and do not imply site-level significance"}


def baseline_size_calibration(repetitions=100):
    """Compare max-T p-value resolution, null alerts and edge detection at 20/40 lots."""
    rows = []
    for baseline_count in (20, 40):
        null_alerts = detections = stability_abstentions = 0
        for replicate in range(repetitions):
            rng = random.Random(SEED + 1_600_000 + baseline_count * repetitions + replicate)  # nosec B311
            baseline = [_anomaly_map(replicate, index, "gaussian", rng)
                        for index in range(baseline_count)]
            null_target = _anomaly_map(repetitions + replicate, baseline_count, "gaussian", rng)
            null_result = detect_anomalies(null_target, baseline, holdout_verified=True)
            shifted_target = _anomaly_map(repetitions + replicate, baseline_count, "gaussian", rng)
            for point in shifted_target["points"]:
                if math.hypot(point["x"], point["y"]) >= 0.8:
                    point["value"] += 4.0
            shifted_result = detect_anomalies(shifted_target, baseline, holdout_verified=True)
            if null_result.get("status") == "INCONCLUSIVE" and null_result.get("baseline_temporal_stability", {}).get("status") == "INCONCLUSIVE":
                stability_abstentions += 1
            elif null_result.get("status") == "VALID":
                null_alerts += null_result["global_max_t_empirical_p"] <= null_result["alpha"]
            else:
                raise AssertionError("C04 baseline-size null fixture failed for an unrelated reason")
            if shifted_result.get("status") == "INCONCLUSIVE" and shifted_result.get("baseline_temporal_stability", {}).get("status") == "INCONCLUSIVE":
                stability_abstentions += 1
            elif shifted_result.get("status") == "VALID":
                detections += shifted_result["global_max_t_empirical_p"] <= shifted_result["alpha"]
            else:
                raise AssertionError("C04 baseline-size positive fixture failed for an unrelated reason")
        rows.append({"baseline_wafers": baseline_count, "independent_lots": baseline_count,
                     "minimum_attainable_empirical_p": 1 / (baseline_count + 1),
                     "null_false_alerts": null_alerts, "null_false_alert_rate": null_alerts / repetitions,
                     "edge_shift_detections": detections, "edge_shift_detection_rate": detections / repetitions,
                     "baseline_stability_abstentions_out_of_2_conditions": stability_abstentions,
                     "replicates_per_condition": repetitions})
    passed = all(row["null_false_alert_rate"] <= 0.12 and row["edge_shift_detection_rate"] >= 0.80 for row in rows)
    return {"rows": rows,
            "experiment_sanity_bounds": {"maximum_null_false_alert_rate": 0.12,
                                          "minimum_detection_for_strong_synthetic_edge_shift": 0.80,
                                          "sanity_bounds_are_company_thresholds": False},
            "status": "PASS" if passed else "FAIL",
            "boundary": "exchangeable synthetic populations; no production sample size recommendation"}


def c03_selection_bias_challenge(repetitions=80, family_size=20):
    """Show how selecting the largest null association changes nominal interval behavior."""
    coordinates = [(0.0, 0.0), (1.0, 0.0), (0.0, 0.9), (-0.8, 0.0), (0.0, -0.9)]
    expected_coordinates = {(round(x, 8), round(y, 8)) for x, y in coordinates}
    expected_context = {"product_id": "SYN-PRODUCT", "metric": "synthetic_metric",
                        "measurement_definition_id": "SYN-DEF", "unit": "nm", "layer": "L1",
                        "population_signature": "SYN-POP", "sampling_mask_id": "SYN-MASK",
                        "coordinate_system": "wafer_xy_v1", "coordinate_unit": "mm",
                        "radius": 1.0, "orientation_deg": 0}
    relationship = {"approved": True, "source_id": "SYN-REL", "grain": "wafer_die",
                    "coordinate_mapping_verified": True,
                    "spatial_block_method": "predeclared_block_fixed_effects_v1"}
    geometry = {"verified": True, "radius": 1.0, "origin": {"x": 0, "y": 0},
                "orientation_deg": 0, "coordinate_system": "wafer_xy_v1", "coordinate_unit": "mm"}
    holdout = {"verified": True, "split_method": "out_of_time_by_wafer_and_lot",
               "grouped_by_wafer": True, "grouped_by_lot": True, "leakage_checked": True}
    rng = random.Random(SEED + 1_700_000)  # nosec B311
    all_interval_exclusions = selected_interval_exclusions = posthoc_refusals = 0
    selected_effects = []
    for replicate in range(repetitions):
        outcomes = [[rng.gauss(0, 1) for _ in coordinates] for _ in range(20)]
        candidates = []
        for hypothesis in range(family_size):
            rows = []
            for wafer in range(20):
                for site, (x, y) in enumerate(coordinates):
                    rows.append({"wafer_id": f"W-{replicate}-{wafer}", "lot_id": f"L-{replicate}-{wafer}",
                                 "die_id": f"D{site}", "cohort": "holdout",
                                 "feature_at": "2026-01-01T00:00:00Z", "outcome_at": "2026-01-02T00:00:00Z",
                                 "x": x, "y": y, "spatial_block_id": "A" if site < 3 else "B",
                                 "feature_value": rng.gauss(0, 1), "outcome_value": outcomes[wafer][site],
                                 "product_id": expected_context["product_id"], "metric": expected_context["metric"],
                                 "measurement_definition_id": expected_context["measurement_definition_id"],
                                 "unit": expected_context["unit"], "layer": expected_context["layer"],
                                 "population_signature": expected_context["population_signature"],
                                 "sampling_mask_id": expected_context["sampling_mask_id"]})
            association = {"relationship": relationship, "context": expected_context, "geometry": geometry,
                           "holdout": holdout,
                           "cohort_selection": {"verified": True, "sampling_design": "COMPLETE_ELIGIBLE_FRAME",
                                                "frame_id": f"SYN-C03-FRAME-{replicate}",
                                                "eligibility_rule_id": "SYN-C03-CONTEXT-ELIGIBILITY",
                                                "eligibility_rule_predeclared": True,
                                                "selection_blind_to_feature_and_outcome": True,
                                                "eligible_wafer_count": 20, "selected_wafer_count": 20},
                           "hypothesis_selection": {"hypothesis_id": f"SYN-H{hypothesis}",
                               "family_size": family_size, "predeclared_before_holdout_outcomes": True,
                               "family_complete": True},
                           "observations": rows}
            result = associate_quality(association, expected_context, expected_coordinates)
            if result.get("status") != "VALID":
                raise AssertionError(f"C03 independent-null association failed: {result.get('reason')}")
            if result["hypothesis_selection"]["confirmatory_single_hypothesis_scope"]:
                raise AssertionError("C03 multiple-hypothesis family was incorrectly labeled confirmatory")
            low, high = result["fisher_wafer_95_ci"]
            interval_excludes_zero = low > 0 or high < 0
            all_interval_exclusions += interval_excludes_zero
            candidates.append((abs(result["mean_within_wafer_r"]), result, association))
        _, winner, winner_input = max(candidates, key=lambda item: item[0])
        low, high = winner["fisher_wafer_95_ci"]
        selected_interval_exclusions += low > 0 or high < 0
        selected_effects.append(abs(winner["mean_within_wafer_r"]))
        posthoc_input = deepcopy(winner_input)
        posthoc_input["hypothesis_selection"]["predeclared_before_holdout_outcomes"] = False
        refused = associate_quality(posthoc_input, expected_context, expected_coordinates)
        posthoc_refusals += refused.get("status") == "INCONCLUSIVE"
    candidate_count = repetitions * family_size
    passed = posthoc_refusals == repetitions
    return {"method": "independent_wafer_die_null_with_posthoc_max_abs_association_selection_v1",
            "replicates": repetitions, "family_size": family_size,
            "candidate_associations": candidate_count,
            "data_generation": "feature and downstream outcome values are generated independently for every die and wafer; holdout outcomes are then used to select the largest absolute mean association",
            "per_hypothesis_nominal_95_interval_exclusion_rate": all_interval_exclusions / candidate_count,
            "selected_max_abs_r_nominal_95_interval_exclusion_rate": selected_interval_exclusions / repetitions,
            "selected_abs_r_median": statistics.median(selected_effects),
            "posthoc_selection_refusals": posthoc_refusals,
            "family_interval_adjustment": "NONE; multi-hypothesis results are explicitly exploratory",
            "product_sanity_bound": "unadjusted selection rate is reported without a pass threshold; all posthoc-selected associations must abstain",
            "status": "PASS" if passed else "FAIL",
            "boundary": "synthetic independent-null challenge only; does not calibrate real yield association or establish causality"}


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
    search_history(retrieval_target, retrieval_history, top_k=5)
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
    c03_selection = c03_selection_bias_challenge()
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
        "c03_multiple_hypothesis_selection_challenge": c03_selection,
        "c04_anomaly_calibration": anomaly_result,
        "thresholds": "No absolute latency, memory, ROI or user-time target was invented; set thresholds after target-hardware and real analyst baseline measurement.",
        "company_data_used": False,
        "source_commit": current_git_commit(ROOT),
        "source_tree_sha256": source_tree_sha256(ROOT),
        "overall": "PASS" if all(c["status"] == "PASS" for c in cases) and catalog_pass and dense_pass
                   and retrieval_pass and c03_selection["status"] == "PASS"
                   and anomaly_result["status"] == "PASS" else "FAIL",
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
