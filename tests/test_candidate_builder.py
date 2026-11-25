"""Ensure the candidate does not embed a circular archive gate report."""
from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from bootstrap_check import package_files as bootstrap_check_files
from qualification.supply_chain_audit import ROOT as audit_root
from qualification.supply_chain_audit import source_files as audit_source_files
from qualification.write_bootstrap_manifest import package_files as manifest_files
from release.build_candidate import candidate_output_paths, package_files


class CandidateBuilderTests(unittest.TestCase):
    def test_new_candidate_path_is_versioned_and_never_overwrites_frozen_archive(self):
        with TemporaryDirectory() as directory:
            release = Path(directory)
            frozen = release / "p3-candidate-20261123.zip"
            frozen.write_bytes(b"frozen")
            archive, sidecar, report = candidate_output_paths(release, "p3-candidate-20261124-onboarding.zip")
            self.assertNotEqual(archive, frozen)
            self.assertEqual(frozen.read_bytes(), b"frozen")
            self.assertEqual(sidecar.name, archive.name + ".sha256")
            self.assertEqual(report.name, "p3-candidate-20261124-onboarding.qualification.json")
            archive.write_bytes(b"new candidate")
            with self.assertRaises(FileExistsError):
                candidate_output_paths(release, archive.name)
            with self.assertRaises(ValueError):
                candidate_output_paths(release, "../p3-candidate-escape.zip")

    def test_generated_gate_report_stays_adjacent_to_archive(self):
        members = {relative for relative, _ in package_files()}
        self.assertNotIn("release/GATE_REPORT.json", members)
        self.assertNotIn("progress/OVERNIGHT_EXECUTION.md", members)
        self.assertIn("release/CRITICAL_CASE_EVIDENCE.json", members)
        self.assertIn("release/THIRD_PARTY_NOTICES.md", members)
        self.assertIn("release/P3_CURRENT_SOURCE_BANDIT_20261124.json", members)
        self.assertIn("release/P3_FINAL_SECURITY_REVIEW_20261124.json", members)
        self.assertIn("release/P3_FINAL_QUALIFICATION_REPORT.json", members)
        self.assertIn("release/P3_STANDALONE_BROWSER_EVIDENCE.json", members)
        self.assertIn("release/MCP_SDK_OFFLINE_QUALIFICATION.json", members)
        self.assertIn(".opencode/skills/p3-spatial-onboarding/SKILL.md", members)
        self.assertIn("release/RUNBOOK_ROLLBACK_KILL_SWITCH.md", members)
        self.assertIn("requirements/mcp-onboarding-metadata.template.json", members)
        self.assertFalse(any(path.startswith("release/p3-candidate-") for path in members))

    def test_archive_dependent_report_is_not_hashed_into_bootstrap_manifest(self):
        members = {relative for relative, _ in manifest_files()}
        self.assertNotIn("release/GATE_REPORT.json", members)
        self.assertNotIn("progress/NEXT_ACTIONS.json", members)
        self.assertIn("release/CRITICAL_CASE_EVIDENCE.json", members)
        self.assertFalse(any(path.relative_to(audit_root).as_posix().startswith("progress/")
                             for path in audit_source_files()))

    def test_installed_tool_caches_are_excluded_from_transfer_members_and_hashes(self):
        archive_members = {relative for relative, _ in package_files()}
        bootstrap_members = {relative for relative, _ in manifest_files()}
        integrity_members = bootstrap_check_files()
        for members in (archive_members, bootstrap_members, integrity_members):
            self.assertFalse(any(path.startswith("node_modules/") or "/node_modules/" in path for path in members))
            self.assertFalse(any(path.startswith((".ruff_cache/", ".pytest_cache/")) or
                                 "/.ruff_cache/" in path or "/.pytest_cache/" in path for path in members))
        self.assertIn("products/p3/reference_host/static/index.html", archive_members)
        self.assertIn("products/p3/reference_host/static/index.html", bootstrap_members)
        self.assertIn("bootstrap_check.py", archive_members)


if __name__ == "__main__":
    unittest.main()
