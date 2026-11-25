import copy
import json
import tempfile
import unittest
from pathlib import Path

from qualification.supply_chain_audit import (
    inspect_npm_dependencies,
    inspect_runtime_references,
    inspect_vendor_licenses,
)

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

    def test_target_npm_inventory_reads_installed_license_metadata(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            packages = {
                "node_modules/chart": {"name": "chart", "license": "MIT", "version": "1.2.3"},
                "node_modules/@scope/util": {"name": "@scope/util", "license": {"type": "BSD-2-Clause"}, "version": "4.5.6"},
            }
            for lock_path, manifest in packages.items():
                path = root / lock_path / "package.json"
                path.parent.mkdir(parents=True)
                path.write_text(json.dumps(manifest), encoding="utf-8")
            lock = {"packages": {
                "": {},
                "node_modules/chart": {"version": "1.2.3", "resolved": "https://registry.example/chart.tgz", "integrity": "sha512-" + "A" * 86},
                "node_modules/@scope/util": {"version": "4.5.6"},
                "node_modules/other-platform": {"version": "7.8.9", "optional": True, "os": ["linux"]},
            }}

            result = inspect_npm_dependencies(root, lock)

        self.assertEqual(result["installed_package_count"], 2)
        self.assertEqual(result["license_summary"], {"MIT": 1, "BSD-2-Clause": 1})
        self.assertEqual(result["unresolved_installed_package_licenses"], [])
        self.assertEqual(result["locked_package_count"], 3)
        self.assertEqual(len(result["locked_but_not_installed"]), 1)

    def test_runtime_reference_scan_ignores_documentation_urls_but_detects_active_remote_calls(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            html = root / "index.html"
            js = root / "app.js"
            css = root / "app.css"
            html.write_text('<script src="/assets/app.js"></script>', encoding="utf-8")
            js.write_text('const docs="https://react.dev/errors/1"; const svg="http://www.w3.org/2000/svg"; fetch("/api/status");',
                          encoding="utf-8")
            css.write_text('body{background:url("/assets/pattern.svg")}', encoding="utf-8")
            result = inspect_runtime_references([html, js, css])
            self.assertFalse(result["remote_script_or_style_reference"])
            self.assertFalse(result["remote_font_or_image_reference"])
            self.assertFalse(result["remote_runtime_api_reference"])

            css.write_text('@import url("https://cdn.example/theme.css"); body{background:url("https://cdn.example/pattern.png")}',
                          encoding="utf-8")
            js.write_text('fetch("https://api.example.invalid/read");', encoding="utf-8")
            result = inspect_runtime_references([html, js, css])
            self.assertTrue(result["remote_script_or_style_reference"])
            self.assertTrue(result["remote_font_or_image_reference"])
            self.assertTrue(result["remote_runtime_api_reference"])


if __name__ == "__main__":
    unittest.main()
