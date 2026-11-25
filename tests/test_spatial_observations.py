import copy
import json
import unittest
from pathlib import Path

from fabintel.spatial_observations import (
    SpatialContractError,
    make_spatial_map,
    to_suite_spatial_map_v1,
    validate_spatial_map,
)


def source_map(modality="continuous", points=None):
    measurement = {"metric": "film_thickness", "unit": "nm", "modality": modality}
    return {
        "wafer_id": "SYN-W-01", "lot_id": "SYN-L-01", "product_id": "SYN-P-01",
        "step_id": "ETCH", "step_instance_id": "ETCH-7", "measured_at": "2026-01-10T00:00:00Z",
        "coordinates_verified": True, "sampling_mask_id": "MASK-01",
        "expected_site_count": len(points) if points is not None else 1,
        "geometry": {"coordinate_system": "wafer_xy_v1", "coordinate_unit": "mm",
                     "origin": {"x": 0, "y": 0}, "radius": 1.0, "orientation_deg": 0},
        "measurement": measurement,
        "points": points if points is not None else [{"site_id": "s1", "x": 0.1, "y": 0.2, "value": 42.5}],
    }


SOURCE = {"id": "SYN-METROLOGY", "source_version": "SNAP-1", "approved_semantic_version": "SEM-1",
          "source_hash": "a" * 64, "grain": "wafer site"}


class SpatialObservationContractTests(unittest.TestCase):
    def test_shared_fixture_cases_preserve_all_eight_observations_and_refuse_invalid_inputs(self):
        fixture_path = Path(__file__).parent / "fixtures" / "spatial_value_contract.json"
        fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
        observed = []
        for modality in sorted({row["modality"] for row in fixture["points"]}):
            rows = []
            for row in fixture["points"]:
                if row["modality"] != modality:
                    continue
                point = {"site_id": row["site_id"], "x": 0.1 + len(rows) * 0.1, "y": 0.1}
                if modality in {"continuous", "sparse_continuous"} and "value" in row:
                    point["value"] = row["value"]
                if "category" in row:
                    point["category"] = row["category"]
                if "bin" in row:
                    point["bin"] = row["bin"]
                rows.append(point)
            current = source_map(modality, rows)
            model = make_spatial_map(current, SOURCE)
            observed.extend(model["observations"])
        self.assertEqual(len(observed), fixture["invariants"]["input_point_count"])
        event = next(row for row in observed if row["site_id"] == "defect-unlabeled")
        self.assertEqual((event["observation_kind"], event["value_type"], event["value"]), ("DEFECT_EVENT", "null", None))
        for refusal in fixture["refusal_cases"]:
            point = {"site_id": refusal["site_id"], "x": 0.1, "y": 0.1}
            point.update({key: refusal[key] for key in ("value", "category", "bin") if key in refusal})
            with self.assertRaises(SpatialContractError):
                make_spatial_map(source_map(refusal["modality"], [point]), SOURCE)

    def test_continuous_numeric_value_remains_a_number_and_numeric_text_is_refused(self):
        model = make_spatial_map(source_map(), SOURCE)
        self.assertEqual(model["observations"][0]["value"], 42.5)
        self.assertIs(type(model["observations"][0]["value"]), float)
        with self.assertRaisesRegex(SpatialContractError, "numeric strings are refused"):
            make_spatial_map(source_map(points=[{"site_id": "s1", "x": 0.1, "y": 0.2, "value": "42.5"}]), SOURCE)

    def test_categorical_numbers_and_strings_keep_original_types(self):
        current = source_map("die_bin_categorical", [
            {"site_id": "s1", "x": 0.1, "y": 0.1, "category": 2},
            {"site_id": "s2", "x": 0.2, "y": 0.1, "category": "BIN-A"},
        ])
        model = make_spatial_map(current, SOURCE)
        self.assertEqual([row["value"] for row in model["observations"]], [2, "BIN-A"])
        self.assertEqual([row["value_type"] for row in model["observations"]], ["number", "string"])
        self.assertEqual(model["sampling"]["categorical_measurement_count"], 2)
        self.assertEqual(model["sampling"]["explicit_missing_value_count"], 0)

    def test_missing_measurement_and_unlabeled_defect_event_are_distinct(self):
        missing = make_spatial_map(source_map(points=[{"site_id": "s1", "x": 0.1, "y": 0.1, "value": None}]), SOURCE)
        self.assertEqual(missing["observations"][0]["observation_kind"], "MISSING_MEASUREMENT")
        self.assertEqual(missing["sampling"]["explicit_missing_value_count"], 1)
        defect = make_spatial_map(source_map("defect_coordinates", [{"site_id": "e1", "x": 0.1, "y": 0.1}]), SOURCE)
        self.assertEqual(defect["observations"][0]["observation_kind"], "DEFECT_EVENT")
        self.assertEqual(defect["sampling"]["defect_event_count"], 1)
        self.assertEqual(defect["sampling"]["explicit_missing_value_count"], 0)
        self.assertEqual(defect["sampling"]["coverage_basis"], "EVENT_COUNTS_ARE_NOT_SITE_COVERAGE")
        with self.assertRaisesRegex(SpatialContractError, "cannot represent defect events"):
            to_suite_spatial_map_v1(defect)

    def test_count_mismatch_geometry_and_declared_type_are_rejected(self):
        model = make_spatial_map(source_map(), SOURCE)
        wrong_count = copy.deepcopy(model)
        wrong_count["sampling"]["numeric_measurement_count"] = 0
        with self.assertRaisesRegex(SpatialContractError, "counts do not reconcile"):
            validate_spatial_map(wrong_count)
        wrong_geometry = copy.deepcopy(model)
        wrong_geometry["observations"][0]["x"] = 2
        with self.assertRaisesRegex(SpatialContractError, "outside the declared wafer geometry"):
            validate_spatial_map(wrong_geometry)
        wrong_type = copy.deepcopy(model)
        wrong_type["observations"][0]["value_type"] = "string"
        with self.assertRaisesRegex(SpatialContractError, "declared value type"):
            validate_spatial_map(wrong_type)

    def test_v1_compatibility_adapter_does_not_change_numeric_or_category_values(self):
        model = make_spatial_map(source_map("die_bin_categorical", [
            {"site_id": "s1", "x": 0.1, "y": 0.1, "category": 4},
            {"site_id": "s2", "x": 0.2, "y": 0.1, "category": "PASS"},
        ]), SOURCE)
        suite = to_suite_spatial_map_v1(model)
        self.assertEqual([row["value"] for row in suite["points"]], [4, "PASS"])
        self.assertIs(type(suite["points"][0]["value"]), int)
        self.assertEqual(len(suite["points"]), model["sampling"]["observation_count"])


if __name__ == "__main__":
    unittest.main()
