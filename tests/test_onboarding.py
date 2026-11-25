import importlib.util
import json
import subprocess  # nosec B404 - launches the tested local P3 CLI with a test-only synthetic peer.
import sys
import tempfile
import unittest
from pathlib import Path
from time import perf_counter

from fabintel.mcp_adapter import MCPPolicyError, ReadOnlyMCPAdapter
from fabintel.mcp_client import MCPClient
from fabintel.mcp_workflow import run_mcp_analysis
from fabintel.onboarding import (
    candidate_relationship_pairs,
    capture_authorized_metadata,
    propose_source_mappings,
)
from fabintel.synthetic_mcp import synthetic_adapter_config, synthetic_metadata_adapter_config
from qualification.onboarding_harness import (
    PLAN_IDS,
    TIME_WINDOW,
    run_protocol_onboarding,
)
from qualification.spatial_catalog_fixture import (
    build_catalog,
    obfuscate_catalog_fields,
)

ROOT = Path(__file__).resolve().parents[1]
ORACLE = json.loads((ROOT / "qualification" / "fixtures" / "spatial_catalog_oracle.json").read_text())


def catalog_proposals(catalog):
    capture = {"schema": "p3-authorized-metadata-capture/v1", "source_descriptors": catalog,
               "configured_source_scopes": [], "reads_performed": 0,
               "source_catalog_count": len(catalog)}
    return propose_source_mappings(capture, as_of="2026-01-15T00:00:00Z")


@unittest.skipUnless(importlib.util.find_spec("mcp"), "install the local hash-locked MCP SDK to run onboarding integration checks")
class SpatialOnboardingTests(unittest.TestCase):
    def test_transport_only_tool_catalog_produces_exact_hashes_without_tool_invocation(self):
        transport_config = {"schema_version": "p3-mcp-transport-config-v1",
                            "transport": {"type": "stdio", "command": [sys.executable, "-S", "-m",
                                "qualification.synthetic_mcp_peer", "--protocol", "dual"],
                                          "cwd": str(ROOT)}, "limits": {"max_seconds": 20}}
        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory) / "transport.json"
            output_path = Path(directory) / "catalog.json"
            config_path.write_text(json.dumps(transport_config), encoding="utf-8")
            subprocess.run([sys.executable, "-m", "fabintel", "mcp-tool-catalog", "--config", str(config_path),
                            "--output", str(output_path)], cwd=ROOT, check=True, capture_output=True, text=True)
            catalog = json.loads(output_path.read_text(encoding="utf-8"))
        self.assertEqual(catalog["schema"], "p3-mcp-tool-catalog/v1")
        self.assertEqual(catalog["tool_invocations"], 0)
        self.assertEqual(catalog["invocation_authorization"], "NOT_INFERRED_FROM_LISTING_OR_ANNOTATIONS")
        tools = {item["name"]: item for item in catalog["tool_catalog"]}
        self.assertRegex(tools["fab_discover"]["tool_definition_sha256"], r"^[a-f0-9]{64}$")
        self.assertFalse(tools["fab_discover"]["invocation_authorized"])
        self.assertTrue(tools["unsafe_recipe_write"]["destructive_hint"])
        self.assertFalse(tools["unsafe_recipe_write"]["invocation_authorized"])

    def test_metadata_only_discovery_needs_no_source_ids_or_bounded_plans(self):
        command = [sys.executable, "-S", "-m", "qualification.synthetic_mcp_peer", "--protocol", "dual",
                   "--scenario", "onboarding-catalog"]
        client = MCPClient({"type": "stdio", "command": command, "cwd": str(ROOT)}, request_timeout=20)
        try:
            config = synthetic_metadata_adapter_config(client, ROOT, "onboarding-catalog")
            self.assertEqual(config["approved_sources"], [])
            self.assertEqual(config["approved_plans"], [])
            self.assertEqual(set(config["operations"]), {"discover"})
            adapter = ReadOnlyMCPAdapter(client, config)
            capture = capture_authorized_metadata(adapter, time_window=TIME_WINDOW)
            proposal = propose_source_mappings(capture, as_of="2026-01-15T00:00:00Z")
            self.assertEqual(capture["adapter_access_mode"], "metadata_only")
            self.assertEqual(capture["data_read_permission"], "NOT_GRANTED_BY_METADATA_DISCOVERY")
            self.assertEqual(capture["reads_performed"], 0)
            self.assertEqual(capture["configured_source_scopes"], [])
            self.assertGreater(proposal["catalog"]["descriptors_received"], 10_000)
            self.assertEqual(proposal["automatic_approvals"], 0)
            self.assertTrue(all(item["invocation_authorized"] is False for item in proposal["tool_review"]))
            with self.assertRaisesRegex(MCPPolicyError, "metadata-only adapter cannot perform"):
                adapter.read_bounded({}, {"scope": "read_only", "source_ids": ["MOCK_MAP"]})
            with self.assertRaisesRegex(MCPPolicyError, "requires a site-approved analysis access profile"):
                run_mcp_analysis(adapter, ["SYNTHETIC-PLAN"], time_window=TIME_WINDOW)
            self.assertEqual(adapter.local_audit_trace, ())
        finally:
            client.close()

    def test_metadata_only_profile_rejects_data_plans_and_row_tools(self):
        command = [sys.executable, "-S", "-m", "qualification.synthetic_mcp_peer", "--protocol", "dual"]
        client = MCPClient({"type": "stdio", "command": command, "cwd": str(ROOT)}, request_timeout=20)
        try:
            config = synthetic_metadata_adapter_config(client, ROOT)
            config["operations"]["read_bounded"] = synthetic_adapter_config(client, ROOT)["operations"]["read_bounded"]
            with self.assertRaisesRegex(MCPPolicyError, "operation mappings exceed"):
                ReadOnlyMCPAdapter(client, config)
            config = synthetic_metadata_adapter_config(client, ROOT)
            config["approved_plans"] = synthetic_adapter_config(client, ROOT)["approved_plans"]
            with self.assertRaisesRegex(MCPPolicyError, "site-approved bounded read plans"):
                ReadOnlyMCPAdapter(client, config)
        finally:
            client.close()

    def test_relationship_discovery_is_bounded_for_unrelated_large_catalogs(self):
        catalog = [{"source_id": f"S{index}", "metadata_access": "PERMITTED", "grain": "wafer",
                    "column_definitions": [{"name": "wafer", "role": "wafer_id"}]}
                   for index in range(13_000)]
        started = perf_counter()
        pairs = candidate_relationship_pairs(catalog)
        elapsed = perf_counter() - started
        self.assertEqual(pairs, [])
        self.assertLess(elapsed, 2.0, f"13K non-joinable descriptors took {elapsed:.3f}s")

    def test_independent_13k_catalog_matches_role_geometry_modality_and_abstention_oracle(self):
        report = catalog_proposals(build_catalog(ORACLE["catalog_count"]))
        self.assertEqual(report["catalog"]["descriptors_received"], ORACLE["catalog_count"])
        self.assertEqual(report["reads_performed"], 0)
        self.assertEqual(report["automatic_approvals"], 0)
        proposals = report["source_proposals"]
        for expected in ORACLE["candidate_source_expectations"]:
            matches = [item for item in proposals if item["source_id"] == expected["source_id"]]
            if expected["role"] == "ABSTAIN":
                self.assertFalse(any(item["proposal_status"] == "PROPOSED_REVIEW_REQUIRED"
                                     and not item["gaps"] for item in matches), expected["source_id"])
                if expected["source_id"] not in {"SYN-SP-12417", "SYN-SP-12517"}:
                    self.assertTrue(matches, expected["source_id"])
                continue
            matches = [item for item in matches if item["role"] == expected["role"]]
            self.assertTrue(matches, expected["source_id"])
            if "geometry" in expected:
                self.assertEqual(matches[0]["geometry_status"], expected["geometry"])
            if "modality" in expected:
                self.assertTrue(any(item["modality"] == expected["modality"] for item in matches))
            if expected["source_id"] == "SYN-SP-01317":
                self.assertEqual(len(matches), expected["measurement_profiles"])
            if expected.get("arithmetic") == "REFUSED":
                self.assertIs(matches[0]["observation_semantics"]["arithmetic_allowed"], False)
            if expected.get("null_label") == "DEFECT_EVENT_NOT_MISSING":
                semantics = matches[0]["observation_semantics"]["event_semantics"]
                self.assertIs(semantics["unlabeled_category_is_event"], True)
                self.assertIs(semantics["null_is_missing"], False)
        self.assertTrue(all(item["approved"] is False for item in report["bounded_plan_requirements"]))

    def test_source_titles_do_not_change_semantic_proposals(self):
        catalog = build_catalog(ORACLE["catalog_count"])
        renamed = obfuscate_catalog_fields(catalog)
        def summary(report):
            return [(item["source_id"], item["role"], item["profile_id"], item["proposal_status"],
                     item["geometry_status"], item["modality"], item["measurement_unit"],
                     item["observation_semantics"]) for item in report["source_proposals"]]
        self.assertEqual(summary(catalog_proposals(catalog)), summary(catalog_proposals(renamed)))

    def test_invalid_authority_relationship_is_not_reviewable(self):
        command = [sys.executable, "-S", "-m", "qualification.synthetic_mcp_peer", "--protocol", "dual",
                   "--scenario", "onboarding-invalid-relationship"]
        client = MCPClient({"type": "stdio", "command": command, "cwd": str(ROOT)}, request_timeout=20)
        try:
            config = synthetic_adapter_config(client, ROOT, "onboarding-invalid-relationship")
            adapter = ReadOnlyMCPAdapter(client, config)
            capture = capture_authorized_metadata(adapter, time_window=TIME_WINDOW)
            report = propose_source_mappings(capture, as_of="2026-01-15T00:00:00Z")
            self.assertEqual(len(adapter.local_audit_trace), 0)
            invalid = [item for item in report["relationship_proposals"]
                       if item.get("relationship_proposal_id")
                       and item.get("source_id") == "MOCK_MAP" and item.get("target_source_id") == "MOCK_QUALITY"]
            self.assertTrue(invalid)
            self.assertTrue(all(item["proposal_status"] == "ABSTAIN_INVALID_OR_INCOMPLETE" for item in invalid))
            selected = [next(item for item in report["source_proposals"]
                             if item["source_id"] == source and item["role"] == role)
                        for source, role in (("MOCK_MAP", "spatial_measurements"),
                                             ("MOCK_QUALITY", "downstream_quality"))]
            with self.assertRaisesRegex(MCPPolicyError, "matching authority-reported wafer/die relationship"):
                from fabintel.onboarding import build_reviewed_config
                build_reviewed_config(config, report, {
                    "schema": "p3-onboarding-review/v1", "proposal_sha256": report["proposal_sha256"],
                    "reviewer_id": "SYNTHETIC-REVIEWER", "authority_reference": "SYNTHETIC-ONLY",
                    "synthetic_simulation": True, "selected_proposal_ids": [item["proposal_id"] for item in selected],
                    "source_decisions": [{"proposal_id": item["proposal_id"], "decision": "APPROVE",
                                          "approval_reference": "SYNTHETIC-SOURCE"} for item in selected],
                    "selected_relationship_proposal_id": invalid[0]["relationship_proposal_id"],
                    "relationship_decisions": [{"relationship_proposal_id": invalid[0]["relationship_proposal_id"],
                                                 "decision": "APPROVE", "approval_reference": "SYNTHETIC-RELATIONSHIP"}]})
            self.assertEqual(len(adapter.local_audit_trace), 0)
        finally:
            client.close()

    def test_protocol_discovery_to_reviewed_c01_c05_module_is_read_only_until_review(self):
        result = run_protocol_onboarding()
        self.assertEqual(result["bootstrap_capture"]["configured_source_scopes"], [])
        self.assertEqual(result["bootstrap_proposal"]["automatic_approvals"], 0)
        self.assertEqual(result["bootstrap_capture"]["reads_performed"], 0)
        self.assertEqual(result["metadata_config"]["approved_plans"], [])
        self.assertEqual(result["capture"]["source_catalog_count"], 13_000)
        self.assertEqual(result["metadata_read_count"], 0)
        self.assertEqual(result["read_count_before_analysis"], 0)
        self.assertEqual(result["reviewed_config"]["onboarding_review"]["source_mapping_status"], "SYNTHETIC_REVIEW_ONLY")
        self.assertFalse(result["reviewed_config"]["onboarding_review"]["automatic_approval"])
        self.assertEqual(result["bounded_read_count"], 5)
        module = result["module"]
        self.assertEqual(module["capabilities"], ["C01", "C02", "C03", "C04", "C05"])
        self.assertEqual(module["evidence"]["status"], "VALID")
        analysis = module["evidence"]["artifacts"][0]["result"]
        self.assertEqual({key: analysis[key]["status"] for key in
                          ("fingerprint", "evolution", "quality_association", "anomaly", "similarity")},
                         {key: "VALID" for key in
                          ("fingerprint", "evolution", "quality_association", "anomaly", "similarity")})
        spatial_map = module["spatial_map"]
        self.assertEqual(spatial_map["sampling"]["observation_count"], len(spatial_map["observations"]))
        self.assertEqual(len(module["evidence"]["provenance"]["mcp_workflow"]["bounded_reads"]), 5)

    def test_alternate_opaque_mcp_schema_runs_the_same_reviewed_science(self):
        result = run_protocol_onboarding("onboarding-schema-alt")
        self.assertEqual(result["capture"]["source_catalog_count"], 13_000)
        self.assertEqual(result["metadata_read_count"], 0)
        self.assertEqual(result["read_count_before_analysis"], 0)
        module = result["module"]
        self.assertEqual(module["evidence"]["status"], "VALID")
        analysis = module["evidence"]["artifacts"][0]["result"]
        self.assertEqual({key: analysis[key]["status"] for key in
                          ("fingerprint", "evolution", "quality_association", "anomaly", "similarity")},
                         {key: "VALID" for key in
                          ("fingerprint", "evolution", "quality_association", "anomaly", "similarity")})
        self.assertEqual(result["bounded_read_count"], 5)

    def test_cli_onboard_review_validate_and_analyze(self):
        command = [sys.executable, "-S", "-m", "qualification.synthetic_mcp_peer",
                   "--protocol", "dual", "--scenario", "onboarding-catalog"]
        client = MCPClient({"type": "stdio", "command": command, "cwd": str(ROOT)}, request_timeout=20)
        try:
            config = synthetic_adapter_config(client, ROOT, "onboarding-catalog")
            bootstrap_config = synthetic_metadata_adapter_config(client, ROOT, "onboarding-catalog")
            metadata_config = synthetic_metadata_adapter_config(client, ROOT, "onboarding-catalog", source_scopes=True)
        finally:
            client.close()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config_path, bootstrap_config_path = root / "config.json", root / "bootstrap.json"
            metadata_config_path, bootstrap_proposal_path = root / "metadata.json", root / "bootstrap-proposal.json"
            proposal_path = root / "proposal.json"
            review_path, reviewed_path, evidence_path = root / "review.json", root / "reviewed.json", root / "evidence.json"
            config_path.write_text(json.dumps(config), encoding="utf-8")
            bootstrap_config_path.write_text(json.dumps(bootstrap_config), encoding="utf-8")
            metadata_config_path.write_text(json.dumps(metadata_config), encoding="utf-8")
            common = [sys.executable, "-m", "fabintel"]
            bootstrap = subprocess.run(common + ["mcp-onboard", "--config", str(bootstrap_config_path),
                "--time-start", TIME_WINDOW["start"], "--time-end", TIME_WINDOW["end"],
                "--as-of", "2026-01-15T00:00:00Z", "--output", str(bootstrap_proposal_path)],
                cwd=ROOT, capture_output=True, text=True, timeout=30, check=False)  # nosec B603
            self.assertEqual(bootstrap.returncode, 0, bootstrap.stderr)
            bootstrap_proposal = json.loads(bootstrap_proposal_path.read_text(encoding="utf-8"))
            onboard = subprocess.run(common + ["mcp-onboard", "--config", str(metadata_config_path),
                "--time-start", TIME_WINDOW["start"], "--time-end", TIME_WINDOW["end"],
                "--as-of", "2026-01-15T00:00:00Z", "--output", str(proposal_path)],
                cwd=ROOT, capture_output=True, text=True, timeout=30, check=False)  # nosec B603
            self.assertEqual(onboard.returncode, 0, onboard.stderr)
            proposal = json.loads(proposal_path.read_text(encoding="utf-8"))
            selected = [next(item for item in proposal["source_proposals"]
                             if item["source_id"] == source_id and item["role"] == role)
                        for source_id, role in (("MOCK_MAP", "spatial_measurements"),
                                                ("MOCK_QUALITY", "downstream_quality"))]
            relationship = next(item for item in proposal["relationship_proposals"]
                                if item.get("source_id") == "MOCK_MAP"
                                and item.get("target_source_id") == "MOCK_QUALITY"
                                and item.get("proposal_status") == "AUTHORITY_REPORTED_REVIEW_REQUIRED")
            review_path.write_text(json.dumps({
                "schema": "p3-onboarding-review/v1", "proposal_sha256": proposal["proposal_sha256"],
                "reviewer_id": "SYNTHETIC-CLI-REVIEWER", "authority_reference": "SYNTHETIC-ONLY",
                "synthetic_simulation": True, "selected_proposal_ids": [item["proposal_id"] for item in selected],
                "source_decisions": [{"proposal_id": item["proposal_id"], "decision": "APPROVE",
                                      "approval_reference": "SYN-CLI-SOURCE-" + item["source_id"]} for item in selected],
                "selected_relationship_proposal_id": relationship["relationship_proposal_id"],
                "relationship_decisions": [{"relationship_proposal_id": relationship["relationship_proposal_id"],
                    "decision": "APPROVE", "approval_reference": "SYN-CLI-RELATIONSHIP"}]}), encoding="utf-8")
            validate = subprocess.run(common + ["mcp-onboard-validate", "--config", str(config_path),
                "--proposal", str(proposal_path), "--review", str(review_path), "--output", str(reviewed_path)],
                cwd=ROOT, capture_output=True, text=True, timeout=30, check=False)  # nosec B603
            self.assertEqual(validate.returncode, 0, validate.stderr)
            analyze = subprocess.run(common + ["mcp-analyze", "--config", str(reviewed_path),
                "--time-start", TIME_WINDOW["start"], "--time-end", TIME_WINDOW["end"],
                "--output", str(evidence_path)] + [arg for plan_id in PLAN_IDS for arg in ("--plan-id", plan_id)],
                cwd=ROOT, capture_output=True, text=True, timeout=30, check=False)  # nosec B603
            self.assertEqual(analyze.returncode, 0, analyze.stderr)
            evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        self.assertGreater(bootstrap_proposal["catalog"]["descriptors_received"], 10_000)
        self.assertEqual(bootstrap_proposal["automatic_approvals"], 0)
        self.assertEqual(bootstrap_proposal["reads_performed"], 0)
        self.assertEqual(proposal["catalog"]["descriptors_received"], 13_002)
        self.assertEqual(proposal["reads_performed"], 0)
        self.assertEqual(evidence["mode"], "SYNTHETIC_DEMO")
        self.assertEqual(evidence["status"], "VALID")
        self.assertEqual(len(evidence["provenance"]["mcp_workflow"]["bounded_reads"]), 5)


if __name__ == "__main__":
    unittest.main()
