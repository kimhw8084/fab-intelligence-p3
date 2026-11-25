"""Deterministic C04 challenge for a stable baseline containing target-like maps."""
from __future__ import annotations

import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from products.p3.engine import detect_anomalies
from qualification.tree_hash import source_tree_sha256

OUTPUT = ROOT / "progress" / "C04_BASELINE_CONTAMINATION_CHALLENGE.json"


def wafer(wafer_id: str, measured_at: str, *, lot_id: str, target_like: bool) -> dict:
    edge = 18.0 if target_like else 12.0
    return {
        "coordinates_verified": True,
        "geometry": {"radius": 1.0, "origin": {"x": 0.0, "y": 0.0}, "orientation_deg": 0,
                     "coordinate_system": "synthetic-wafer-xy", "coordinate_unit": "mm"},
        "measurement": {"metric": "edge_thickness", "unit": "nm", "modality": "continuous",
                        "definition_id": "SYN-THICKNESS-1", "layer": "SYN-L1"},
        "points": [{"site_id": "center", "x": 0.0, "y": 0.0, "value": 10.0},
                   {"site_id": "east", "x": 0.9, "y": 0.0, "value": edge},
                   {"site_id": "north", "x": 0.0, "y": 0.9, "value": edge},
                   {"site_id": "west", "x": -0.9, "y": 0.0, "value": edge}],
        "product_id": "SYN-PRODUCT", "wafer_id": wafer_id, "lot_id": lot_id,
        "measured_at": measured_at, "sampling_mask_id": "SYN-MASK-4",
        "population_signature": "SYN-POP-1", "step_id": "SYN-POST", "step_instance_id": wafer_id,
    }


def evaluate(contaminant_count: int) -> dict:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    baseline = [wafer(f"B-{contaminant_count}-{index}",
                      (start + timedelta(days=index)).isoformat().replace("+00:00", "Z"),
                      lot_id=f"L-{contaminant_count}-{index}", target_like=index < contaminant_count)
                for index in range(20)]
    target = wafer(f"T-{contaminant_count}", "2026-02-01T00:00:00Z",
                   lot_id=f"L-T-{contaminant_count}", target_like=True)
    result = detect_anomalies(target, baseline, holdout_verified=True)
    return {"target_like_baseline_maps": contaminant_count,
            "status": result["status"], "alpha": result.get("alpha"),
            "empirical_p": result.get("global_max_t_empirical_p"),
            "alert": (result.get("global_max_t_empirical_p", 1) <= result.get("alpha", 0)),
            "temporal_stability": result.get("baseline_temporal_stability", {}).get("status"),
            "baseline_cohort_assessment": result.get("baseline_cohort_assessment"),
            "reason": result.get("reason")}


def main() -> None:
    cases = [evaluate(count) for count in (0, 1, 2, 4)]
    clean, one_contaminant, two_contaminants, four_contaminants = cases
    if not (clean["status"] == "VALID" and clean["alert"] and clean["empirical_p"] == 1 / 21
            and one_contaminant["status"] == "VALID" and not one_contaminant["alert"]
            and one_contaminant["empirical_p"] == 2 / 21
            and one_contaminant["temporal_stability"] == "NO_SHIFT_DETECTED"
            and one_contaminant["baseline_cohort_assessment"]["status"] == "NOT_CERTIFIED_CLEAN"
            and not two_contaminants["alert"] and four_contaminants["status"] == "INCONCLUSIVE"):
        raise SystemExit("C04 stable-baseline contamination counterexample changed unexpectedly")
    report = {
        "schema": "p3-c04-baseline-contamination-challenge/v1",
        "status": "PASS_COUNTEREXAMPLE",
        "oracle_authored_before_run": True,
        "design": {"baseline_size": 20, "target_matches_contaminating_signature": True,
                   "baseline_contaminants_are_earliest_records": True,
                   "in_control_outer_site_value_nm": 12.0, "target_like_outer_site_value_nm": 18.0,
                   "center_value_nm": 10.0, "randomization": "none; deterministic falsification case"},
        "cases": cases,
        "finding": "One target-like historical map increased p from the clean-baseline rank floor 1/21 to 2/21 and removed the alert while the ordered temporal-stability test reported NO_SHIFT_DETECTED. P3 now identifies the baseline as NOT_CERTIFIED_CLEAN and requires source-approved eligibility review; it does not claim to automatically detect or remove contamination.",
        "scope": "Deterministic synthetic counterexample; not a false-alert rate, sensitivity estimate, manufacturing calibration, or evidence that a real baseline is contaminated.",
        "company_data_used": False,
        "source_tree_sha256": source_tree_sha256(ROOT),
    }
    OUTPUT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "cases": len(cases),
                      "clean_p": clean["empirical_p"], "one_contaminant_p": one_contaminant["empirical_p"],
                      "one_contaminant_temporal_status": one_contaminant["temporal_stability"],
                      "output": str(OUTPUT.relative_to(ROOT))}, sort_keys=True))


if __name__ == "__main__":
    main()
