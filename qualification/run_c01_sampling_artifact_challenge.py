"""Independent C01 challenge for sampling-density confounding and attribution limits."""
from __future__ import annotations

import copy
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from products.p3.engine import analyze, fingerprint
from qualification.tree_hash import source_tree_sha256


def make_map(edge_radius: float) -> dict:
    points = [{"site_id": "center", "x": 0.1, "y": 0.0, "value": 10.2}]
    points.extend({
        "site_id": f"edge-{index}",
        "x": edge_radius * math.cos(index * math.pi / 4),
        "y": edge_radius * math.sin(index * math.pi / 4),
        "value": 10 + 2 * edge_radius,
    } for index in range(8))
    return {
        "coordinates_verified": True,
        "geometry": {"radius": 1.0, "origin": {"x": 0.0, "y": 0.0}, "orientation_deg": 0,
                     "coordinate_system": "wafer_xy_v1", "coordinate_unit": "mm"},
        "measurement": {"metric": "thickness", "unit": "nm", "modality": "continuous",
                         "definition_id": "SYN-MET-1", "layer": "SYN-L1"},
        "points": points, "product_id": "SYN-P1", "wafer_id": f"SYN-W-{edge_radius}",
        "sampling_mask_id": f"SYN-MASK-{edge_radius}",
    }


def main() -> None:
    inner_layout = make_map(0.81)
    outer_layout = make_map(0.99)
    inner = fingerprint(inner_layout)
    outer = fingerprint(outer_layout)

    # Same exact observed payload admits two distinct latent explanations.
    physical_world = {"latent_truth": "physical thickness field", "observations": copy.deepcopy(inner_layout)}
    artifact_world = {"latent_truth": "flat material plus metrology radial bias", "observations": copy.deepcopy(inner_layout)}
    physical_result = fingerprint(physical_world["observations"])
    artifact_result = fingerprint(artifact_world["observations"])
    limitations = analyze(inner_layout)["limitations"]

    passed = (
        abs(inner["edge_minus_center"] - 1.42) < 1e-12
        and abs(outer["edge_minus_center"] - 1.78) < 1e-12
        and physical_result == artifact_result
        and inner["interpretation_limits"]["sampling"]["area_weighted_estimate"] == "NOT_COMPUTED"
        and inner["interpretation_limits"]["measurement_attribution"]["status"]
        == "NOT_IDENTIFIABLE_FROM_A_SINGLE_SPATIAL_MAP"
        and any("not area-weighted" in item for item in limitations)
    )
    evidence = {
        "schema": "p3-c01-sampling-artifact-challenge/v1",
        "status": "PASS" if passed else "FAIL",
        "oracle_authored_before_run": True,
        "company_data_used": False,
        "independent_design": {
            "true_field": "value(r) = 10 + 2*r nm for every world",
            "center_sample_radius_fraction": 0.1,
            "edge_sampling_layouts": [0.81, 0.99],
            "expected_observation_weighted_contrasts_nm": [1.42, 1.78],
            "latent_worlds_with_identical_observations": [
                "physical thickness field", "flat material plus metrology radial bias"
            ],
        },
        "results": {
            "inner_layout_edge_minus_center_nm": inner["edge_minus_center"],
            "outer_layout_edge_minus_center_nm": outer["edge_minus_center"],
            "layout_induced_contrast_change_nm": outer["edge_minus_center"] - inner["edge_minus_center"],
            "observed_payload_identical_between_latent_worlds": True,
            "analysis_equal_between_latent_worlds": physical_result == artifact_result,
            "sampling_assessment": inner["interpretation_limits"]["sampling"],
            "measurement_attribution_assessment": inner["interpretation_limits"]["measurement_attribution"],
            "exported_limitations_include_sampling_warning": any("not area-weighted" in item for item in limitations),
        },
        "scope": "Deterministic identifiability counterexample. It does not estimate manufacturing bias, sampling error, or production accuracy.",
        "source_tree_sha256": source_tree_sha256(ROOT),
    }
    output = ROOT / "progress" / "C01_SAMPLING_AND_ARTIFACT_CHALLENGE.json"
    output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(evidence, indent=2, sort_keys=True))
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
