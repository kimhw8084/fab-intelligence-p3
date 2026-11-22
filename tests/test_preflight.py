import json
from pathlib import Path
import unittest

from fabintel.preflight import evaluate

ROOT = Path(__file__).resolve().parent.parent


class InternalPreflightTests(unittest.TestCase):
    def test_empty_capture_stays_pending_internal(self):
        result = evaluate(None)
        self.assertEqual(result["state"], "PENDING_INTERNAL")
        self.assertFalse(result["internal_ready"])
        self.assertEqual(result["preflight_state"], "NO_CAPTURE")

    def test_template_lists_gaps_without_faking_readiness(self):
        template = json.loads((ROOT / "release" / "INTERNAL_QUALIFICATION_REPORT_TEMPLATE.json").read_text())
        result = evaluate(template)
        self.assertEqual(result["state"], "PENDING_INTERNAL")
        self.assertEqual(result["preflight_state"], "GAPS_REMAIN")
        self.assertFalse(result["internal_ready"])
        self.assertTrue(any("read-only" in gap for gap in result["gaps"]))

    def test_even_complete_capture_is_only_ready_for_review(self):
        template = json.loads((ROOT / "release" / "INTERNAL_QUALIFICATION_REPORT_TEMPLATE.json").read_text())
        template["captured_at"] = "2026-11-22T12:00:00Z"
        template["system"] = {"os": "test-os", "architecture": "test-arch", "python_version": "3.12", "public_egress_blocked": True}
        for binding in template["logical_operation_bindings"].values():
            binding.update({"supported": True, "discovered_name": "site-discovered-name", "version": "site-version"})
        template["logical_operation_bindings"]["discover"]["read_only"] = True
        template["approved_sources"] = [{"approved": True, "source_id": "approved-source", "semantic_version": "1", "grain": "wafer_site", "effective_time": "time-v1", "units": ["nm"]}]
        template["relationships"] = [{"approved": True, "source_reference": "approved-relationship", "keys": ["wafer_id"], "cardinality": "one_to_many", "grain": "wafer_site", "effective_time": "time-v1"}]
        template["security_checks"] = {key: True for key in template["security_checks"]}
        template["site_test_results"] = {key: "PASS" for key in template["site_test_results"]}
        template["approval_record"]["reference"] = "site-review-reference"
        result = evaluate(template)
        self.assertEqual(result["preflight_state"], "READY_FOR_AUTHORIZED_REVIEW")
        self.assertEqual(result["state"], "PENDING_INTERNAL")
        self.assertFalse(result["internal_ready"])
        self.assertIn("cannot authenticate", result["note"])


if __name__ == "__main__":
    unittest.main()
