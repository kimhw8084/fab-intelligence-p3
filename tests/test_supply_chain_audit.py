import copy
import json
import unittest
from pathlib import Path

from qualification.supply_chain_audit import inspect_vendor_licenses


ROOT = Path(__file__).resolve().parents[1]
INVENTORY_PATH = ROOT / "vendor/mcp-sdk-2.3.0/macos-arm64-cp311/license-inventory.json"


class VendorLicenseAuditTests(unittest.TestCase):
    def setUp(self):
        self.inventory = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))

    def test_all_bundled_wheel_and_license_hashes_verify(self):
        result = inspect_vendor_licenses(ROOT, self.inventory)

        self.assertEqual(result["verified_wheels"], 28)
        self.assertEqual(result["verified_embedded_license_files"], 28)
        self.assertEqual(result["unresolved_packages"], [])
        self.assertEqual(
            {item["name"] for item in result["derived_expressions"]},
            {"h11", "mcp", "mcp-types"},
        )
        self.assertEqual(
            {name for name, expression in result["license_expressions"].items() if expression == "NOASSERTION"},
            set(),
        )

    def test_wheel_hash_mismatch_fails_closed(self):
        changed = copy.deepcopy(self.inventory)
        changed["packages"][0]["wheel_sha256"] = "0" * 64

        with self.assertRaisesRegex(ValueError, "wheel integrity mismatch"):
            inspect_vendor_licenses(ROOT, changed)


if __name__ == "__main__":
    unittest.main()
