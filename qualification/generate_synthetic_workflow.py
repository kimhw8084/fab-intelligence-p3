"""Write a deterministic, company-free fixture that exercises all five P3 capabilities."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def make_map(wafer_id, lot_id, measured_at, values, step_id, step_instance_id, source_id):
    return {
        "coordinates_verified": True,
        "geometry": {"radius": 1.0, "origin": {"x": 0.0, "y": 0.0}, "orientation_deg": 0,
                     "coordinate_system": "wafer_xy_v1", "coordinate_unit": "mm"},
        "points": [
            {"site_id": "center", "x": 0.0, "y": 0.0, "value": values[0]},
            {"site_id": "east", "x": 1.0, "y": 0.0, "value": values[1]},
            {"site_id": "north", "x": 0.0, "y": 0.9, "value": values[2]},
            {"site_id": "west", "x": -0.8, "y": 0.0, "value": values[3]},
            {"site_id": "south", "x": 0.0, "y": -0.9, "value": values[4]},
        ],
        "measurement": {"metric": "film_thickness", "unit": "nm", "modality": "continuous",
                        "definition_id": "SYN-THICKNESS-1", "layer": "L1"},
        "product_id": "SYN-PRODUCT-1", "wafer_id": wafer_id, "lot_id": lot_id,
        "measured_at": measured_at, "sampling_mask_id": "SYN-CARDINAL-5",
        "population_signature": "SYN-POP-THICKNESS-L1", "step_id": step_id,
        "step_instance_id": step_instance_id, "source_id": source_id,
    }


def build():
    current = make_map("SYN-W-CURRENT", "SYN-L-CURRENT", "2026-02-01T00:00:00Z",
                       [10, 12, 12, 12, 12], "SYN-STEP-1", "SYN-INSTANCE-1", "SYN-MAP-CURRENT")
    current["mode"] = "SYNTHETIC_DEMO"
    current["requested_capabilities"] = ["C01", "C02", "C03", "C04", "C05"]
    current["baseline_holdout_verified"] = True
    current["baseline_population"] = [
        make_map(f"SYN-W-B{i:02d}", f"SYN-L-B{i:02d}", f"2026-01-{i + 1:02d}T00:00:00Z",
                 [10, 12, 12, 12, 12], "SYN-BASELINE", f"SYN-BI-{i:02d}", f"SYN-BASELINE-{i:02d}")
        for i in range(20)
    ]
    current["history"] = [make_map("SYN-W-HIST", "SYN-L-HIST", "2026-01-20T00:00:00Z",
                                   [20, 22, 22, 22, 22], "SYN-HISTORICAL", "SYN-HI-1", "SYN-MAP-HIST")]
    current["previous_steps"] = [make_map("SYN-W-CURRENT", "SYN-L-CURRENT", "2026-01-10T00:00:00Z",
                                          [9, 11, 11, 11, 11], "SYN-STEP-0", "SYN-INSTANCE-0", "SYN-MAP-PREVIOUS")]
    coordinates = [(0.0, 0.0), (1.0, 0.0), (0.0, 0.9), (-0.8, 0.0), (0.0, -0.9)]
    current["quality_association"] = {
        "relationship": {"approved": True, "source_id": "SYN-REL-WAFER-DIE", "grain": "wafer_die",
                         "coordinate_mapping_verified": True,
                         "spatial_block_method": "predeclared_block_fixed_effects_v1"},
        "context": {"product_id": "SYN-PRODUCT-1", "metric": "film_thickness",
                    "measurement_definition_id": "SYN-THICKNESS-1", "unit": "nm", "layer": "L1",
                    "population_signature": "SYN-POP-THICKNESS-L1", "sampling_mask_id": "SYN-CARDINAL-5"},
        "geometry": {"verified": True, "radius": 1.0, "origin": {"x": 0.0, "y": 0.0},
                     "orientation_deg": 0, "coordinate_system": "wafer_xy_v1", "coordinate_unit": "mm"},
        "holdout": {"verified": True, "split_method": "out_of_time_by_wafer_and_lot", "grouped_by_wafer": True,
                    "grouped_by_lot": True, "leakage_checked": True},
        "observations": [
            {"wafer_id": f"SYN-W-Q{wafer:02d}", "lot_id": f"SYN-L-Q{wafer:02d}", "die_id": f"SYN-D{site}",
             "x": coordinates[site][0], "y": coordinates[site][1],
             "feature_value": float(site), "outcome_value": float(site * 2),
             "product_id": "SYN-PRODUCT-1", "metric": "film_thickness",
             "measurement_definition_id": "SYN-THICKNESS-1", "unit": "nm", "layer": "L1",
             "population_signature": "SYN-POP-THICKNESS-L1", "sampling_mask_id": "SYN-CARDINAL-5",
             "spatial_block_id": "SYN-BLOCK-A" if site < 3 else "SYN-BLOCK-B", "cohort": "holdout",
             "feature_at": "2026-01-15T00:00:00Z", "outcome_at": "2026-01-16T00:00:00Z"}
            for wafer in range(20) for site in range(len(coordinates))
        ],
    }
    return current


if __name__ == "__main__":
    destination = ROOT / "fixtures" / "p3_integrated_synthetic.json"
    destination.write_text(json.dumps(build(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(destination)
