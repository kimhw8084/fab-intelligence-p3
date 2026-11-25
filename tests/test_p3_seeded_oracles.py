import math
import random
import unittest

from products.p3.engine import fingerprint


def seeded_map(seed):
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


def independent_edge_center(data):
    center = []
    edge = []
    for point in data["points"]:
        radius = math.sqrt(point["x"] * point["x"] + point["y"] * point["y"])
        if radius <= 0.2:
            center.append(point["value"])
        elif radius >= 0.8:
            edge.append(point["value"])
    return sum(edge) / len(edge) - sum(center) / len(center), len(center), len(edge)


class SeededOracleTests(unittest.TestCase):
    def test_one_hundred_seeded_fingerprints_match_independent_arithmetic(self):
        for seed in range(100):
            with self.subTest(seed=seed):
                data = seeded_map(seed)
                expected_delta, center_count, edge_count = independent_edge_center(data)
                result = fingerprint(data)
                self.assertAlmostEqual(result["edge_minus_center"], expected_delta, places=12)
                self.assertEqual(result["regions"]["center"]["count"], center_count)
                self.assertEqual(result["regions"]["edge"]["count"], edge_count)
                self.assertFalse("estimated_sites" in result)

    def test_uniform_value_shift_does_not_change_spatial_difference(self):
        data = seeded_map(300)
        shifted = seeded_map(300)
        for point in shifted["points"]:
            point["value"] += 17.25
        self.assertAlmostEqual(fingerprint(data)["edge_minus_center"], fingerprint(shifted)["edge_minus_center"], places=12)


if __name__ == "__main__":
    unittest.main()
