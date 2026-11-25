import json
import unittest
from pathlib import Path

from fabintel.contracts import validate_envelope
from fabintel.project import analyze
from qualification.engineer_challenge import build_dense_c01_challenge, dense_c01_ground_truth

BASE=Path(__file__).resolve().parent.parent
class EngineCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.positive=json.loads((BASE/'fixtures'/'case_positive.json').read_text())
        cls.negative=json.loads((BASE/'fixtures'/'case_negative.json').read_text())
        cls.oracle=json.loads((BASE/'fixtures'/'independent_oracle.json').read_text())
    def test_fixed_positive_oracle(self):
        result=analyze(self.positive); validate_envelope(result)
        self.assertEqual(result['status'],self.oracle['positive_status'])
        self.assertTrue(any(self.oracle['claim_contains'] in c['statement'] for c in result['claims']))
        self.assertEqual(result['mode'],'SYNTHETIC_DEMO')
    def test_fixed_negative_oracle(self):
        result=analyze(self.negative)
        self.assertEqual(result['status'],self.oracle['negative_status'])
        self.assertEqual(result['claims'],[])
        self.assertTrue(result['limitations'])
    def test_deterministic(self):
        self.assertEqual(analyze(self.positive),analyze(self.positive))
    def test_never_claim_caused_or_control(self):
        result=analyze(self.positive)
        self.assertTrue(all(c['category'] not in ('CAUSAL_ESTIMATE','INTERVENTION_VALIDATED') for c in result['claims']))

    def test_dense_c01_plane_adjustment_recovers_local_shift_without_null_candidates(self):
        from products.p3.engine import _local_clusters, _prepare_map, fingerprint

        for missing_fraction in (0.0, 0.4):
            with self.subTest(missing_fraction=missing_fraction):
                planted = build_dense_c01_challenge(73000, plant_local_shift=True,
                                                     random_missing_fraction=missing_fraction)
                truth = dense_c01_ground_truth(planted)
                prepared = _prepare_map(planted)
                frozen_style = _local_clusters(prepared["points"], prepared["radius"],
                                               prepared["orientation_deg"], grid_size=32)
                result = fingerprint(planted)["local_clusters"]
                self.assertEqual(frozen_style["clusters"], [],
                                 "the prior raw-value fixed-grid screen should expose the demonstrated miss")
                self.assertEqual(result["screening_adjustment"]["status"], "APPLIED")
                self.assertGreaterEqual(len(result["screening_adjustment"]["quadrant_site_counts"]), 4)
                self.assertGreater(len(result["clusters"]), 0)
                candidate_cells = {tuple(cell) for cluster in result["clusters"] for cell in cluster["grid_cells"]}
                grid_size = result["grid_size"]
                detected = set()
                for point in planted["points"]:
                    cell = (min(grid_size - 1, max(0, int((point["x"] / planted["geometry"]["radius"] + 1) * grid_size / 2))),
                            min(grid_size - 1, max(0, int((point["y"] / planted["geometry"]["radius"] + 1) * grid_size / 2))))
                    if cell in candidate_cells:
                        detected.add(point["site_id"])
                self.assertTrue(detected.intersection(truth["anomalous_site_ids"]))
                self.assertEqual(result["screening_adjustment"]["method"],
                                 "ordinary_least_squares_plane_residuals_before_same_radial_band_MAD")

        null_map = build_dense_c01_challenge(73000, plant_local_shift=False)
        null_result = fingerprint(null_map)["local_clusters"]
        self.assertEqual(null_result["clusters"], [],
                         "the independent smooth-gradient/no-local-shift control must remain unclassified")

if __name__=='__main__':unittest.main()
