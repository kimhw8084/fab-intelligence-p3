"""Deterministic, ground-truthed wafer investigation for P3 engineer review.

This generator is independent of the P3 analysis code. It creates correlated
metrology noise, a planted edge-ring shift, a localized sector cluster,
multi-step growth, historical decoys, and a lot-confounded downstream outcome.
All output is synthetic and is used only by the protocol-compatible test peer.
"""
from __future__ import annotations

from copy import deepcopy
from math import atan2, cos, hypot, pi, sin
import random
from typing import Any


PRODUCT = "SYN-PRODUCT-17"
LAYER = "ILD-3"
METRIC = "film_thickness"
DEFINITION = "SYN-ILD3-THICKNESS-7"
UNIT = "nm"
RADIUS_MM = 150.0
MASK_DENSE = "SYN-ENG-40-RADIAL-SECTOR"
POPULATION = "SYN-ENG-ILD3-THICKNESS-2026A"
GEOMETRY = {
    "radius": RADIUS_MM,
    "origin": {"x": 0.0, "y": 0.0},
    "orientation_deg": 0,
    "coordinate_system": "wafer_xy_v1",
    "coordinate_unit": "mm",
}
MEASUREMENT = {
    "metric": METRIC,
    "unit": UNIT,
    "modality": "continuous",
    "definition_id": DEFINITION,
    "layer": LAYER,
}


def _layout() -> list[tuple[str, float, float, int, int, float]]:
    """Five radial bands x eight sectors, alternating angular offsets."""
    radii = (0.12, 0.31, 0.53, 0.76, 0.94)
    output = []
    for ring, radius_fraction in enumerate(radii):
        offset = 22.5 if ring % 2 else 0.0
        for sector in range(8):
            angle_deg = (sector * 45.0 + offset) % 360.0
            angle = angle_deg * pi / 180.0
            output.append((f"S{ring}{sector}", RADIUS_MM * radius_fraction * cos(angle),
                           RADIUS_MM * radius_fraction * sin(angle), ring, sector, angle))
    # Add a compact, irregularly sampled group in one outer-middle neighborhood.
    # Its sites stay inside one 32x32 descriptor cell so the existing descriptive
    # cluster method has a fair opportunity to recover it.
    cluster_radius, cluster_angle = 0.64, 65.0 * pi / 180.0
    center_x, center_y = cluster_radius * cos(cluster_angle), cluster_radius * sin(cluster_angle)
    for index in range(8):
        local_angle = index * pi / 4
        x = center_x + 0.012 * cos(local_angle)
        y = center_y + 0.012 * sin(local_angle)
        output.append((f"LC{index}", RADIUS_MM * x, RADIUS_MM * y, 3, 1, atan2(y, x)))
    return output


LAYOUT = _layout()


def _base_profile(ring: int, radius_fraction: float, angle: float, wafer_offset: float,
                  ring_effects: list[float], sector_effects: list[float], site_noise: float) -> float:
    return (100.0 + wafer_offset + 1.4 * radius_fraction + 0.65 * cos(angle)
            + ring_effects[ring] + sector_effects[int(round(angle / (pi / 4))) % 8]
            + site_noise)


def _make_points(seed: int, *, edge_shift: float = 0.0, cluster_shift: float = 0.0,
                 cluster_sectors: tuple[int, ...] = (1, 2),
                 include_uncertainty: bool = True, omit_sites: set[str] | None = None) -> list[dict[str, Any]]:
    rng = random.Random(seed)
    wafer_offset = rng.gauss(0.0, 0.16)
    ring_effects = [rng.gauss(0.0, 0.07) for _ in range(5)]
    sector_effects = [rng.gauss(0.0, 0.10) for _ in range(8)]
    omitted = omit_sites or set()
    points = []
    for site_id, x, y, ring, sector, angle in LAYOUT:
        value = _base_profile(ring, hypot(x, y) / RADIUS_MM, angle, wafer_offset, ring_effects, sector_effects,
                              rng.gauss(0.0, 0.09))
        if ring == 4:
            value += edge_shift
        # A localized, physical-coordinate cluster near 0.76R in sectors 1–2.
        if ring == 3 and sector in cluster_sectors:
            value += cluster_shift
        point = {"site_id": site_id, "x": round(x, 9), "y": round(y, 9), "value": round(value, 5)}
        if include_uncertainty:
            point["standard_uncertainty"] = 0.18
        # Consume the same latent and site-noise stream even for an unsampled
        # site. Otherwise a changed mask would perturb every later site's
        # generated value and masquerade as process evolution.
        if site_id not in omitted:
            points.append(point)
    return points


def _map(wafer: str, lot: str, timestamp: str, step: str, instance: str,
         source: str, seed: int, *, edge_shift: float = 0.0, cluster_shift: float = 0.0,
         mask: str = MASK_DENSE, omit_sites: set[str] | None = None,
         cluster_sectors: tuple[int, ...] = (1, 2),
         product: str = PRODUCT, population: str = POPULATION) -> dict[str, Any]:
    return {
        "coordinates_verified": True,
        "geometry": deepcopy(GEOMETRY),
        "points": _make_points(seed, edge_shift=edge_shift, cluster_shift=cluster_shift,
                               cluster_sectors=cluster_sectors,
                               omit_sites=omit_sites),
        "measurement": deepcopy(MEASUREMENT),
        "product_id": product,
        "wafer_id": wafer,
        "lot_id": lot,
        "measured_at": timestamp,
        "sampling_mask_id": mask,
        "population_signature": population,
        "step_id": step,
        "step_instance_id": instance,
        "source_id": source,
    }


def _quality_association(current_points: list[dict[str, Any]]) -> dict[str, Any]:
    """Make between-lot outcome differences, but no planted within-wafer link."""
    rng = random.Random(731_044)
    selected = LAYOUT
    value_by_site = {point["site_id"]: point["value"] for point in current_points}
    observations = []
    for wafer_index in range(20):
        lot_shift = rng.gauss(0.0, 3.0)
        for site_id, x, y, ring, sector, angle in selected:
            measured_feature = value_by_site[site_id] + lot_shift
            # Downstream outcomes share the lot-level offset (a confounder) but
            # their within-wafer site residuals are independently generated.
            outcome = 50.0 + 1.7 * lot_shift + rng.gauss(0.0, 2.0)
            observations.append({
                "wafer_id": f"SYN-W-Q{wafer_index:02d}",
                "lot_id": f"SYN-L-Q{wafer_index:02d}",
                "die_id": f"SYN-D-{site_id}",
                "x": round(x, 9), "y": round(y, 9),
                "feature_value": round(measured_feature, 5),
                "outcome_value": round(outcome, 5),
                "product_id": PRODUCT, "metric": METRIC,
                "measurement_definition_id": DEFINITION, "unit": UNIT, "layer": LAYER,
                "population_signature": POPULATION, "sampling_mask_id": MASK_DENSE,
                "spatial_block_id": "SYN-RADIAL-INNER" if ring < 2 else "SYN-RADIAL-OUTER",
                "cohort": "holdout",
                "feature_at": "2026-01-28T00:00:00Z",
                "outcome_at": "2026-01-29T00:00:00Z",
            })
    return {
        "relationship": {"approved": True, "source_id": "SYN-REL-WAFER-DIE",
                         "grain": "wafer_die", "coordinate_mapping_verified": True,
                         "spatial_block_method": "predeclared_block_fixed_effects_v1"},
        "context": {"product_id": PRODUCT, "metric": METRIC,
                    "measurement_definition_id": DEFINITION, "unit": UNIT, "layer": LAYER,
                    "population_signature": POPULATION, "sampling_mask_id": MASK_DENSE},
        "geometry": {**deepcopy(GEOMETRY), "verified": True},
        "holdout": {"verified": True, "split_method": "out_of_time_by_wafer_and_lot",
                    "grouped_by_wafer": True, "grouped_by_lot": True, "leakage_checked": True},
        "cohort_selection": {"verified": True, "sampling_design": "COMPLETE_ELIGIBLE_FRAME",
                             "frame_id": "SYN-ENG-C03-COMPLETE-FRAME",
                             "eligibility_rule_id": "SYN-ENG-C03-CONTEXT-ELIGIBILITY",
                             "eligibility_rule_predeclared": True,
                             "selection_blind_to_feature_and_outcome": True,
                             "eligible_wafer_count": 20, "selected_wafer_count": 20},
        "hypothesis_selection": {"hypothesis_id": "SYN-ENG-C03-NULL-1", "family_size": 1,
                                 "predeclared_before_holdout_outcomes": True, "family_complete": True},
        "observations": observations,
    }


def build() -> dict[str, Any]:
    current = _map("SYN-W-ENG-TARGET", "SYN-L-ENG-TARGET", "2026-02-01T00:00:00Z",
                   "CMP-ILD3-POST", "SYN-STEP-ENG-03", "SYN-MAP-ENG-CURRENT", 91,
                   edge_shift=4.5, cluster_shift=3.8)
    current["mode"] = "SYNTHETIC_DEMO"
    current["requested_capabilities"] = ["C01", "C02", "C03", "C04", "C05"]
    current["baseline_holdout_verified"] = True
    current["expected_site_count"] = len(LAYOUT)
    current["baseline_population"] = [
        _map(f"SYN-W-ENG-B{i:02d}", f"SYN-L-ENG-B{i:02d}",
             f"2026-01-{i + 1:02d}T00:00:00Z", "CMP-ILD3-POST", f"SYN-B-ENG-{i:02d}",
             f"SYN-BASE-ENG-{i:02d}", 10_000 + i)
        for i in range(20)
    ]
    current["previous_steps"] = [
        _map("SYN-W-ENG-TARGET", "SYN-L-ENG-TARGET", "2026-01-28T00:00:00Z",
             "DEPOSITION-ILD3", "SYN-STEP-ENG-01", "SYN-MAP-ENG-STEP1", 91),
        _map("SYN-W-ENG-TARGET", "SYN-L-ENG-TARGET", "2026-01-30T00:00:00Z",
             "CMP-ILD3-PRE", "SYN-STEP-ENG-02", "SYN-MAP-ENG-STEP2", 91, edge_shift=2.5,
             mask="SYN-ENG-44-STEP-PRE", omit_sites={"S11", "S21", "S22", "S23"}),
    ]
    # C05 cases include a different angular signature, a changed dense mask, a
    # sparse stratified map, an incompatible product, and a future near-duplicate.
    sparse_omissions = {site_id for index, (site_id, *_rest) in enumerate(LAYOUT) if index % 2 == 1}
    current["history"] = [
        _map("SYN-W-ENG-HIST-MATCH", "SYN-L-ENG-HIST-MATCH", "2026-01-20T00:00:00Z",
             "CMP-ILD3-POST", "SYN-H-ENG-01", "SYN-HIST-ENG-01", 201, edge_shift=4.0,
             cluster_shift=3.4, mask="SYN-ENG-44-OMIT-EDGE", omit_sites={f"S4{i}" for i in (0, 2, 4, 6)}),
        _map("SYN-W-ENG-HIST-OPPOSITE", "SYN-L-ENG-HIST-OPPOSITE", "2026-01-19T00:00:00Z",
             "CMP-ILD3-POST", "SYN-H-ENG-02", "SYN-HIST-ENG-02", 202,
             edge_shift=4.5, cluster_shift=3.8, cluster_sectors=(5, 6)),
        _map("SYN-W-ENG-HIST-AVERAGE", "SYN-L-ENG-HIST-AVERAGE", "2026-01-18T00:00:00Z",
             "CMP-ILD3-POST", "SYN-H-ENG-03", "SYN-HIST-ENG-03", 203),
        _map("SYN-W-ENG-HIST-SPARSE", "SYN-L-ENG-HIST-SPARSE", "2026-01-16T00:00:00Z",
             "CMP-ILD3-POST", "SYN-H-ENG-06", "SYN-HIST-ENG-06", 206, mask="SYN-ENG-24-SPARSE",
             omit_sites=sparse_omissions),
        _map("SYN-W-ENG-WRONG-PRODUCT", "SYN-L-ENG-WRONG-PRODUCT", "2026-01-17T00:00:00Z",
             "CMP-ILD3-POST", "SYN-H-ENG-04", "SYN-HIST-ENG-04", 204,
             edge_shift=4.5, cluster_shift=3.8, product="SYN-PRODUCT-OTHER"),
        _map("SYN-W-ENG-FUTURE", "SYN-L-ENG-FUTURE", "2026-02-02T00:00:00Z",
             "CMP-ILD3-POST", "SYN-H-ENG-05", "SYN-HIST-ENG-05", 205,
             edge_shift=4.5, cluster_shift=3.8),
    ]
    current["quality_association"] = _quality_association(current["points"])
    return current


def build_dense_c01_challenge(seed: int, *, plant_local_shift: bool,
                              random_missing_fraction: float = 0.0,
                              sites_per_ring: int = 128) -> dict[str, Any]:
    """Create an independent dense-wafer C01 challenge with known local ground truth.

    The smooth directional field, ring-correlated offset, angular artifact and
    site noise compete with a small local shift. Optional missingness is applied
    after values are generated so it cannot alter the underlying process field.
    """
    if not 0 <= random_missing_fraction < 0.8:
        raise ValueError("random_missing_fraction must be in [0, 0.8)")
    if type(sites_per_ring) is not int or sites_per_ring < 32:
        raise ValueError("sites_per_ring must be an integer of at least 32")
    rng = random.Random(seed)
    ring_count = 12
    ring_effects = [rng.gauss(0.0, 0.18) for _ in range(ring_count)]
    wafer_offset = rng.gauss(0.0, 0.15)
    points = []
    for ring in range(ring_count):
        radius_fraction = 0.08 + ring * (0.90 / (ring_count - 1))
        for angular_index in range(sites_per_ring):
            angle = 2 * pi * (angular_index + (ring % 2) * 0.5) / sites_per_ring
            x, y = RADIUS_MM * radius_fraction * cos(angle), RADIUS_MM * radius_fraction * sin(angle)
            planted = plant_local_shift and 0.55 < radius_fraction < 0.78 and 0.65 < angle < 1.35
            value = (100.0 + wafer_offset + ring_effects[ring] + 3.0 * x / RADIUS_MM
                     + 0.4 * sin(3 * angle) + rng.gauss(0.0, 0.12) + (1.5 if planted else 0.0))
            points.append({"site_id": f"D{ring:02d}-{angular_index:03d}", "x": round(x, 9), "y": round(y, 9),
                           "value": round(value, 6), "ground_truth_anomaly": bool(planted)})
    if random_missing_fraction:
        mask_rng = random.Random(seed + 900_000)
        points = [point for point in points if mask_rng.random() >= random_missing_fraction]
    return {
        "coordinates_verified": True,
        "geometry": deepcopy(GEOMETRY),
        "points": points,
        "measurement": deepcopy(MEASUREMENT),
        "product_id": PRODUCT,
        "wafer_id": f"SYN-W-C01-DENSE-{seed}",
        "lot_id": f"SYN-L-C01-DENSE-{seed}",
        "measured_at": "2026-02-03T00:00:00Z",
        "sampling_mask_id": f"SYN-C01-DENSE-{random_missing_fraction:.2f}",
        "population_signature": POPULATION,
        "step_id": "CMP-ILD3-POST",
        "step_instance_id": f"SYN-C01-DENSE-I-{seed}",
        "source_id": f"SYN-C01-DENSE-S-{seed}",
        "expected_site_count": ring_count * sites_per_ring,
    }


def dense_c01_ground_truth(data: dict[str, Any]) -> dict[str, Any]:
    """Return expected sites directly from the generator's planted coordinates."""
    return {
        "scope": "synthetic-only; not manufacturing validation",
        "anomalous_site_ids": [point["site_id"] for point in data["points"] if point["ground_truth_anomaly"]],
        "observed_site_count": len(data["points"]),
        "expected_site_count": data["expected_site_count"],
        "planted_directional_gradient_nm_per_radius": 3.0,
        "planted_local_shift_nm": 1.5 if any(point["ground_truth_anomaly"] for point in data["points"]) else 0.0,
        "missing_fraction": 1 - len(data["points"]) / data["expected_site_count"],
    }


def ground_truth(bundle: dict[str, Any] | None = None) -> dict[str, Any]:
    """Independent expected facts from generation parameters, not engine output."""
    data = bundle or build()
    current = data["points"]
    edge = [point["value"] for point, (_, _, _, ring, _, _) in zip(current, LAYOUT) if ring == 4]
    center = [point["value"] for point, (_, _, _, ring, _, _) in zip(current, LAYOUT) if ring == 0]
    edge_sites = sum(ring == 4 for _, _, _, ring, _, _ in LAYOUT)
    cluster_sites = sum(ring == 3 and sector in (1, 2) for _, _, _, ring, sector, _ in LAYOUT)
    layout_by_site = {site_id: (ring, sector) for site_id, _, _, ring, sector, _ in LAYOUT}
    process_effects = ((0.0, 0.0), (2.5, 0.0), (4.5, 3.8))
    step_maps = data["previous_steps"] + [data]
    expected_step_changes = []
    common_counts = []
    for index, (before, after) in enumerate(zip(step_maps, step_maps[1:])):
        before_ids = {point["site_id"] for point in before["points"]}
        after_ids = {point["site_id"] for point in after["points"]}
        common_ids = before_ids & after_ids
        common_counts.append(len(common_ids))
        edge_before, cluster_before = process_effects[index]
        edge_after, cluster_after = process_effects[index + 1]
        changes = []
        for site_id in common_ids:
            ring, sector = layout_by_site[site_id]
            delta = ((edge_after - edge_before) if ring == 4 else 0.0)
            if ring == 3 and sector in (1, 2):
                delta += cluster_after - cluster_before
            changes.append(delta)
        expected_step_changes.append(round(sum(changes) / len(changes), 6) if changes else None)
    return {
        "scope": "synthetic-only; not manufacturing validation",
        "target": {"wafer_id": data["wafer_id"], "observed_sites": len(data["points"]),
                   "physical_radius_mm": RADIUS_MM},
        "planted_signatures": {"edge_ring_shift_nm": 4.5, "cluster_shift_nm": 3.8,
                               "cluster_region": "outer-middle sectors 1 and 2",
                               "edge_center_delta_nm": round(sum(edge) / len(edge) - sum(center) / len(center), 4)},
        "evolution": {"steps": [row["step_id"] for row in data["previous_steps"]] + [data["step_id"]],
                      "edge_shift_by_step_nm": [0.0, 2.5, 4.5], "site_masks_identical": False,
                      "common_sites_by_transition": common_counts,
                      "expected_mean_change_nm": expected_step_changes,
                      "planted_changed_sites_per_step": [edge_sites, edge_sites + cluster_sites]},
        "anomaly": {"baseline_wafers": 20, "baseline_lots": 20,
                    "expected_target_outlier": True, "minimum_rank_p": 1.0 / 21.0},
        "historical": {"eligible_same_signature": 4, "matching_neighbor_has_changed_sampling_mask": True,
                       "sparse_analog_observed_sites": len(next(
                           item for item in data["history"] if item["wafer_id"] == "SYN-W-ENG-HIST-SPARSE")["points"]),
                       "exclude_wrong_product": True, "exclude_future_record": True},
        "quality": {"holdout_wafers": 20, "distinct_lots": 20,
                    "between_lot_common_cause_is_planted": True,
                    "within_wafer_spatial_association_is_null_by_generation": True,
                    "causal_claim_permitted": False},
    }


if __name__ == "__main__":
    import json
    from pathlib import Path

    destination = Path(__file__).resolve().parents[1] / "fixtures" / "p3_engineer_challenge.json"
    challenge = build()
    destination.write_text(json.dumps(challenge, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"fixture": str(destination), "bytes": destination.stat().st_size,
                      "ground_truth": ground_truth(challenge)}, indent=2, sort_keys=True))
