import json
import unittest
from pathlib import Path

from products.p3.engine import analyze
from qualification.generate_synthetic_workflow import build

ROOT = Path(__file__).resolve().parents[1]


class SyntheticWorkflowTests(unittest.TestCase):
    def test_bundled_full_workflow_matches_generator_and_runs_all_capabilities(self):
        fixture = json.loads((ROOT / "fixtures" / "p3_integrated_synthetic.json").read_text(encoding="utf-8"))
        self.assertEqual(fixture, build())
        evidence = analyze(fixture)
        result = evidence["artifacts"][0]["result"]
        self.assertEqual(evidence["status"], "VALID")
        self.assertEqual([result[name]["status"] for name in
                          ("fingerprint", "anomaly", "similarity", "evolution", "quality_association")],
                         ["VALID"] * 5)
        self.assertEqual(result["fingerprint"]["reticle_periodicity"]["status"], "NOT_COMPUTED")
        self.assertEqual(result["quality_association"]["wafers"], 20)
        self.assertEqual(evidence["mode"], "SYNTHETIC_DEMO")


if __name__ == "__main__":
    unittest.main()
