import tempfile
import unittest
from pathlib import Path

from qualification.tree_hash import source_tree_sha256


class SourceTreeHashTests(unittest.TestCase):
    def test_hash_covers_source_but_ignores_execution_ledgers_and_generated_audits(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "fabintel" / "engine.py"
            progress = root / "progress" / "OVERNIGHT_EXECUTION.md"
            benchmark = root / "progress" / "C03_NESTED_LOT_BENCHMARK.json"
            audit = root / "release" / "PIP_AUDIT_OSV.json"
            version = root / "release" / "P3_WORKING_SOURCE_VERSION_20261124.json"
            installed_dependency = root / "node_modules" / "react" / "package.json"
            for path in (source, progress, benchmark, audit, version, installed_dependency):
                path.parent.mkdir(parents=True, exist_ok=True)
            source.write_text("value = 1\n", encoding="utf-8")
            progress.write_text("first execution state\n", encoding="utf-8")
            benchmark.write_text('{"replicates": 1}\n', encoding="utf-8")
            audit.write_text("first generated audit\n", encoding="utf-8")
            version.write_text('{"source_tree_sha256":"draft"}\n', encoding="utf-8")
            installed_dependency.write_text('{"version":"1.0.0"}\n', encoding="utf-8")
            baseline = source_tree_sha256(root)
            progress.write_text("updated execution state\n", encoding="utf-8")
            benchmark.write_text('{"replicates": 500}\n', encoding="utf-8")
            audit.write_text("updated generated audit\n", encoding="utf-8")
            version.write_text('{"source_tree_sha256":"final"}\n', encoding="utf-8")
            installed_dependency.write_text('{"version":"2.0.0"}\n', encoding="utf-8")
            self.assertEqual(source_tree_sha256(root), baseline)
            source.write_text("value = 2\n", encoding="utf-8")
            self.assertNotEqual(source_tree_sha256(root), baseline)


if __name__ == "__main__":
    unittest.main()
