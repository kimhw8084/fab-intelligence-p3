import copy
import importlib.util
import json
import os
import subprocess
import sys
import threading
import tempfile
import time
import unittest
from pathlib import Path
from http.server import ThreadingHTTPServer
from unittest.mock import patch

from fabintel.contracts import validate_envelope
from fabintel.mcp_adapter import (EnvironmentCredentialProvider, MCPDataError, MCPPolicyError,
                                  ReadOnlyMCPAdapter, approved_query_plan_sha256,
                                  tool_definition_sha256)
from fabintel.mcp_client import MCPClient, MCPCancelled
from fabintel.mcp_workflow import run_mcp_analysis
from tests.test_mcp_client import _HTTPMockHandler

ROOT = Path(__file__).resolve().parent.parent
SERVER = [sys.executable, "-S", "-m", "tests.fixtures.mcp_mock_server", "--protocol", "dual"]


def adapter_config(client):
    tools = {tool["name"]: tool for tool in client.list_tools()}
    fields = {
        "discover": {},
        "semantics": {"source_ids": "source_ids", "semantic_version": "semantic_version"},
        "relationships": {"typed_entity_ids": "typed_entity_ids", "time_window": "time_window"},
        "read_bounded": {"approved_plan": "approved_plan", "permission_context": "permission_context", "limits": "limits",
                         "operation_id": "operation_id"},
        "audit": {"operation_id": "operation_id"},
    }
    names = {"discover": "fab_discover", "semantics": "fab_semantics", "relationships": "fab_relationships",
             "read_bounded": "fab_read_bounded", "audit": "fab_audit"}
    operations = {}
    for logical, tool_name in names.items():
        operations[logical] = {"tool_name": tool_name,
            "approval": {"approved": True, "reference": "SYN-TOOL-APPROVAL-" + logical,
                         "tool_definition_sha256": tool_definition_sha256(tools[tool_name])},
            "argument_mapping": fields[logical]}
    plans = []
    workflow_plans = (("SYN-WF-CURRENT", "MOCK_MAP", "current"),
                      ("SYN-WF-PREVIOUS", "MOCK_MAP", "previous"),
                      ("SYN-WF-BASELINE", "MOCK_MAP", "baseline"),
                      ("SYN-WF-HISTORY", "MOCK_MAP", "history"),
                      ("SYN-WF-ASSOCIATION", "MOCK_QUALITY", "association"))
    for plan_id, delay in (("SYN-PLAN-1", 0), ("SYN-CANCEL", 700)):
        plan = {"plan_id": plan_id, "source_id": "MOCK_MAP", "semantic_version": "MOCK-SEM-1",
                "test_delay_ms": delay}
        plans.append({"approved": True, "approval_reference": "SYN-QUERY-" + plan_id,
                      "plan": plan, "plan_sha256": approved_query_plan_sha256(plan)})
    for plan_id, source_id, role in workflow_plans:
        plan = {"plan_id": plan_id, "source_id": source_id, "semantic_version": "MOCK-SEM-1",
                "analysis_role": role}
        plans.append({"approved": True, "approval_reference": "SYN-QUERY-" + plan_id,
                      "plan": plan, "plan_sha256": approved_query_plan_sha256(plan)})
    malformed_plan = {"plan_id": "SYN-WF-CURRENT-BAD-UNIT", "source_id": "MOCK_MAP",
                      "semantic_version": "MOCK-SEM-1", "analysis_role": "current",
                      "test_case": "wrong_measurement_unit"}
    plans.append({"approved": True, "approval_reference": "SYN-QUERY-" + malformed_plan["plan_id"],
                  "plan": malformed_plan, "plan_sha256": approved_query_plan_sha256(malformed_plan)})
    bad_audit_plan = {"plan_id": "SYN-WF-CURRENT-BAD-AUDIT", "source_id": "MOCK_MAP",
                      "semantic_version": "MOCK-SEM-1", "analysis_role": "current",
                      "test_case": "wrong_audit_hash"}
    plans.append({"approved": True, "approval_reference": "SYN-QUERY-" + bad_audit_plan["plan_id"],
                  "plan": bad_audit_plan, "plan_sha256": approved_query_plan_sha256(bad_audit_plan)})
    return {"schema_version": "p3-mcp-adapter-config-v1",
        "transport": {"type": "stdio", "command": SERVER},
        "read_only_approval": {"approved": True, "reference": "SYN-READ-ONLY-APPROVAL"},
        "approved_sources": [
            {"approved": True, "source_id": source, "semantic_version": "MOCK-SEM-1",
             "approval_reference": "SYN-SOURCE-" + source}
            for source in ("MOCK_MAP", "MOCK_QUALITY")
        ],
        "approved_plans": plans,
        "limits": {"max_rows": 100, "max_bytes": 1048576, "max_seconds": 5},
        "operations": operations}


@unittest.skipUnless(importlib.util.find_spec("mcp"), "install the local hash-locked MCP SDK candidate to run adapter integration checks")
class MCPReadOnlyAdapterTests(unittest.TestCase):
    def open_adapter(self):
        client = MCPClient({"type": "stdio", "command": SERVER, "cwd": str(ROOT)}, request_timeout=3)
        self.addCleanup(client.close)
        config = adapter_config(client)
        return ReadOnlyMCPAdapter(client, config), client, config

    def test_discovery_semantics_relationship_read_and_audit_use_exact_bindings(self):
        adapter, _, _ = self.open_adapter()
        discovery = adapter.discover()
        self.assertEqual(discovery["status"], "CONFIGURED_READ_ONLY_UNQUALIFIED")
        self.assertEqual(discovery["approved_source_ids"], ["MOCK_MAP", "MOCK_QUALITY"])
        semantics = adapter.semantics(["MOCK_MAP"], "MOCK-SEM-1")
        self.assertEqual(semantics["column_definitions"][0]["source_id"], "MOCK_MAP")
        relation = adapter.relationships({"source_id": "MOCK_MAP", "target_source_id": "MOCK_QUALITY"},
                                         {"start": "2026-01-01T00:00:00Z", "end": "2026-02-01T00:00:00Z"})
        self.assertTrue(relation["approved"])
        result = adapter.read_bounded(adapter.plans["SYN-PLAN-1"]["plan"],
            {"scope": "read_only", "source_ids": ["MOCK_MAP"]}, {"max_rows": 5}, operation_id="SYN-OP-1")
        self.assertEqual(len(result["typed_rows"]), 1)
        self.assertEqual(result["audit_trace"]["permission_scope"], "read_only")
        self.assertEqual(result["audit_trace"]["query_hash"], adapter.local_audit_trace[0]["query_hash"])
        self.assertEqual(adapter.audit("SYN-OP-1")["permission_scope"], "read_only")
        self.assertEqual(result["external_internal_qualification"], "PENDING_INTERNAL")

    def test_protocol_to_approved_semantics_to_bounded_map_to_c01_c05_evidence(self):
        adapter, _, _ = self.open_adapter()
        evidence = run_mcp_analysis(adapter,
            ["SYN-WF-CURRENT", "SYN-WF-PREVIOUS", "SYN-WF-BASELINE", "SYN-WF-HISTORY", "SYN-WF-ASSOCIATION"],
            time_window={"start": "2026-01-01T00:00:00Z", "end": "2026-02-01T00:00:00Z"},
            operation_id="SYN-WORKFLOW")
        self.assertTrue(validate_envelope(evidence))
        self.assertEqual(evidence["mode"], "SYNTHETIC_DEMO")
        self.assertEqual(evidence["status"], "VALID")
        result = evidence["artifacts"][0]["result"]
        self.assertEqual({key: result[key]["status"] for key in
                          ("fingerprint", "evolution", "quality_association", "anomaly", "similarity")},
                         {"fingerprint": "VALID", "evolution": "VALID", "quality_association": "VALID",
                          "anomaly": "VALID", "similarity": "VALID"})
        trace = evidence["provenance"]["mcp_workflow"]
        self.assertEqual(trace["permission_scope"], "read_only")
        self.assertEqual(len(trace["bounded_reads"]), 5)
        self.assertTrue(all(read["audit_id"] and read["query_hash"] for read in trace["bounded_reads"]))
        self.assertEqual({source["id"] for source in evidence["sources"]}, {"MOCK_MAP", "MOCK_QUALITY"})
        self.assertTrue(all(source["approved_semantic_version"] == "MOCK-SEM-1" for source in evidence["sources"]))
        self.assertEqual(trace["internal_qualification"], "PENDING_INTERNAL")

    def test_mcp_workflow_keeps_missing_support_data_as_capability_abstentions(self):
        adapter, _, _ = self.open_adapter()
        evidence = run_mcp_analysis(adapter, ["SYN-WF-CURRENT"],
            time_window={"start": "2026-01-01T00:00:00Z", "end": "2026-02-01T00:00:00Z"},
            operation_id="SYN-WORKFLOW-MISSING")
        result = evidence["artifacts"][0]["result"]
        self.assertEqual(result["fingerprint"]["status"], "VALID")
        self.assertEqual(result["evolution"]["status"], "INCONCLUSIVE")
        self.assertEqual(result["quality_association"]["status"], "INCONCLUSIVE")
        self.assertEqual(result["anomaly"]["status"], "INCONCLUSIVE")
        self.assertEqual(result["similarity"]["status"], "INCONCLUSIVE")

    def test_mcp_workflow_rejects_measurement_values_outside_approved_semantic_units(self):
        adapter, _, _ = self.open_adapter()
        with self.assertRaisesRegex(MCPDataError, "unit differs"):
            run_mcp_analysis(adapter, ["SYN-WF-CURRENT-BAD-UNIT"],
                time_window={"start": "2026-01-01T00:00:00Z", "end": "2026-02-01T00:00:00Z"},
                operation_id="SYN-WORKFLOW-BAD-UNIT")

    def test_mcp_workflow_rejects_an_audit_not_correlated_to_its_exact_read(self):
        adapter, _, _ = self.open_adapter()
        with self.assertRaisesRegex(MCPDataError, "audit does not correlate"):
            run_mcp_analysis(adapter, ["SYN-WF-CURRENT-BAD-AUDIT"],
                time_window={"start": "2026-01-01T00:00:00Z", "end": "2026-02-01T00:00:00Z"},
                operation_id="SYN-WORKFLOW-BAD-AUDIT")

    def test_mcp_workflow_rejects_unbounded_historical_top_k(self):
        adapter, _, _ = self.open_adapter()
        with self.assertRaisesRegex(MCPPolicyError, "top_k must be between 1 and 50"):
            run_mcp_analysis(adapter, ["SYN-WF-CURRENT"],
                time_window={"start": "2026-01-01T00:00:00Z", "end": "2026-02-01T00:00:00Z"},
                top_k=100_000, operation_id="SYN-WORKFLOW-TOP-K")

    def test_cli_runs_full_mcp_workflow_and_writes_evidence(self):
        _, client, config = self.open_adapter()
        client.close()
        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory) / "approved-mock.json"
            output_path = Path(directory) / "evidence.json"
            config_path.write_text(json.dumps(config), encoding="utf-8")
            plan_ids = ["SYN-WF-CURRENT", "SYN-WF-PREVIOUS", "SYN-WF-BASELINE",
                        "SYN-WF-HISTORY", "SYN-WF-ASSOCIATION"]
            command = [sys.executable, "-m", "fabintel", "mcp-analyze", "--config", str(config_path),
                       "--time-start", "2026-01-01T00:00:00Z", "--time-end", "2026-02-01T00:00:00Z",
                       "--output", str(output_path)]
            for plan_id in plan_ids:
                command.extend(("--plan-id", plan_id))
            result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=20)
            evidence = json.loads(output_path.read_text(encoding="utf-8")) if output_path.exists() else None
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIsInstance(evidence, dict)
        self.assertTrue(validate_envelope(evidence))
        self.assertEqual(evidence["status"], "VALID")
        self.assertEqual(len(evidence["provenance"]["mcp_workflow"]["bounded_reads"]), 5)

    def test_unapproved_sources_and_non_read_only_tools_are_denied(self):
        adapter, _, config = self.open_adapter()
        with self.assertRaises(MCPPolicyError):
            adapter.semantics(["UNAPPROVED"], "MOCK-SEM-1")
        unsafe = copy.deepcopy(config)
        unsafe_tool = {item["name"]: item for item in adapter.client.list_tools()}["unsafe_recipe_write"]
        unsafe["operations"]["read_bounded"]["tool_name"] = "unsafe_recipe_write"
        unsafe["operations"]["read_bounded"]["approval"]["tool_definition_sha256"] = tool_definition_sha256(unsafe_tool)
        denied = ReadOnlyMCPAdapter(adapter.client, unsafe)
        with self.assertRaises(MCPPolicyError):
            denied.read_bounded(adapter.plans["SYN-PLAN-1"]["plan"],
                                {"scope": "read_only", "source_ids": ["MOCK_MAP"]})

    def test_tool_schema_change_after_review_fails_closed(self):
        adapter, _, config = self.open_adapter()
        changed = copy.deepcopy(config)
        changed["operations"]["discover"]["approval"]["tool_definition_sha256"] = "f" * 64
        client = adapter.client
        altered = ReadOnlyMCPAdapter(client, changed)
        with self.assertRaises(MCPPolicyError):
            altered.discover()

    def test_raw_sql_and_broader_permission_context_are_rejected(self):
        adapter, _, _ = self.open_adapter()
        with self.assertRaises(MCPPolicyError):
            unsafe = dict(adapter.plans["SYN-PLAN-1"]["plan"], sql="select *")
            adapter.read_bounded(unsafe,
                                 {"scope": "read_only", "source_ids": ["MOCK_MAP"]})
        with self.assertRaises(MCPPolicyError):
            adapter.read_bounded(adapter.plans["SYN-PLAN-1"]["plan"],
                                 {"scope": "read_write", "source_ids": ["MOCK_MAP"]})
        with self.assertRaises(MCPPolicyError):
            adapter.read_bounded(adapter.plans["SYN-PLAN-1"]["plan"] | {"filter": "different"},
                                 {"scope": "read_only", "source_ids": ["MOCK_MAP"]})
        with self.assertRaises(MCPPolicyError):
            adapter.relationships({"source_id": "MOCK_MAP", "target_source_id": "MOCK_QUALITY", "sql": "select *"},
                                  {"start": "2026-01-01T00:00:00Z", "end": "2026-02-01T00:00:00Z"})
        unsafe_mapping = copy.deepcopy(adapter.config)
        unsafe_mapping["operations"]["read_bounded"]["argument_mapping"]["approved_plan"] = "sql"
        with self.assertRaises(MCPPolicyError):
            ReadOnlyMCPAdapter(adapter.client, unsafe_mapping)

    def test_adapter_cancellation_is_cooperative_and_does_not_fake_acknowledgement(self):
        adapter, client, _ = self.open_adapter()
        results = []
        errors = []
        def read():
            try:
                results.append(adapter.read_bounded(
                    adapter.plans["SYN-CANCEL"]["plan"],
                    {"scope": "read_only", "source_ids": ["MOCK_MAP"]}, operation_id="SYN-CANCEL-OP"))
            except BaseException as exc:
                errors.append(exc)
        worker = threading.Thread(target=read)
        worker.start()
        deadline = time.monotonic() + 2
        while "SYN-CANCEL-OP" not in adapter._active and time.monotonic() < deadline:
            time.sleep(0.01)
        outcome = adapter.cancel("SYN-CANCEL-OP")
        worker.join(timeout=3)
        self.assertFalse(worker.is_alive())
        self.assertTrue(outcome["cancellation_requested"])
        self.assertFalse(outcome["confirmed_stopped"])
        self.assertEqual(results, [])
        self.assertTrue(any(isinstance(error, MCPCancelled) for error in errors))
        self.assertEqual(client.call_tool("fab_audit", {"operation_id": "cancel-check"})["structuredContent"]["cancelled_request_count"] > 0, True)

    def test_environment_auth_is_resolved_without_configuring_secret_values(self):
        provider = EnvironmentCredentialProvider(stdio_env={"MCP_ACCESS_TOKEN": "P3_TEST_TOKEN"})
        with patch.dict(os.environ, {"P3_TEST_TOKEN": "test-secret-value"}):
            self.assertEqual(provider.stdio_environment(), {"MCP_ACCESS_TOKEN": "test-secret-value"})
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(MCPPolicyError):
                provider.stdio_environment()
        http_provider = EnvironmentCredentialProvider(http_headers={"Authorization": "P3_TEST_HTTP_TOKEN"})
        with patch.dict(os.environ, {"P3_TEST_HTTP_TOKEN": "Bearer http-test-secret"}):
            self.assertEqual(http_provider.http_headers(), {"Authorization": "Bearer http-test-secret"})
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(MCPPolicyError):
                http_provider.http_headers()

    def test_site_config_can_run_read_only_discovery_over_streamable_http(self):
        _HTTPMockHandler.requests = []
        _HTTPMockHandler.redirect = False
        _HTTPMockHandler.wrong_id = False
        server = ThreadingHTTPServer(("127.0.0.1", 0), _HTTPMockHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(thread.join, 2)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        config = {"schema_version": "p3-mcp-adapter-config-v1",
            "transport": {"type": "streamable_http", "endpoint": f"http://127.0.0.1:{server.server_port}/mcp"},
            "auth_provider": {"type": "environment", "http_headers": {"Authorization": "P3_HTTP_TOKEN"}},
            "read_only_approval": {"approved": True, "reference": "SYN-HTTP-APPROVAL"},
            "approved_sources": [{"approved": True, "source_id": "MOCK_MAP", "semantic_version": "MOCK-SEM-1",
                                  "approval_reference": "SYN-MOCK-SEMANTICS"}],
            "limits": {"max_rows": 10, "max_bytes": 1024, "max_seconds": 3},
            "operations": {}}
        plan = {"plan_id": "SYN-HTTP-PLAN", "source_id": "MOCK_MAP", "semantic_version": "MOCK-SEM-1"}
        config["approved_plans"] = [{"approved": True, "approval_reference": "SYN-HTTP-PLAN-APPROVAL",
                                     "plan": plan, "plan_sha256": approved_query_plan_sha256(plan)}]
        descriptor = {"name": "read", "inputSchema": {"type": "object"},
                      "annotations": {"readOnlyHint": True, "destructiveHint": False}}
        for operation in ("discover", "semantics", "relationships", "read_bounded", "audit"):
            config["operations"][operation] = {"tool_name": "read",
                "approval": {"approved": True, "reference": f"SYN-HTTP-{operation}",
                             "tool_definition_sha256": tool_definition_sha256(descriptor)},
                "argument_mapping": {}}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "approved-http-mock.json"
            path.write_text(json.dumps(config), encoding="utf-8")
            with patch.dict(os.environ, {"P3_HTTP_TOKEN": "Bearer synthetic-http-secret"}):
                adapter = ReadOnlyMCPAdapter.from_config(path)
                self.addCleanup(adapter.client.close)
                discovery = adapter.discover()
        self.assertEqual(discovery["status"], "CONFIGURED_READ_ONLY_UNQUALIFIED")
        self.assertEqual(discovery["approved_source_ids"], ["MOCK_MAP"])
        self.assertEqual(_HTTPMockHandler.requests[0]["headers"].get("Authorization"), "Bearer synthetic-http-secret")

    def test_cli_can_discover_a_configured_mock_server(self):
        _, client, config = self.open_adapter()
        client.close()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "approved-mock.json"
            path.write_text(json.dumps(config), encoding="utf-8")
            result = subprocess.run([sys.executable, "-m", "fabintel", "mcp-discover", "--config", str(path)],
                                    cwd=ROOT, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"], "CONFIGURED_READ_ONLY_UNQUALIFIED")

    def test_template_is_rejected_before_server_process_launch(self):
        template = json.loads((ROOT / "requirements" / "mcp-adapter.template.json").read_text())
        template["transport"]["command"] = ["/no/such/server-must-not-be-launched"]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "template.json"
            path.write_text(json.dumps(template), encoding="utf-8")
            with self.assertRaises(MCPPolicyError):
                ReadOnlyMCPAdapter.from_config(path)

    def test_invalid_limits_are_rejected_before_stdio_process_launch(self):
        _, client, config = self.open_adapter()
        client.close()
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / "server-was-launched"
            config["transport"] = {"type": "stdio", "cwd": directory,
                "command": [sys.executable, "-c", f"from pathlib import Path; Path({str(marker)!r}).write_text('started')"]}
            config["limits"]["max_seconds"] = 0
            path = Path(directory) / "invalid-limits.json"
            path.write_text(json.dumps(config), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "max_seconds"):
                ReadOnlyMCPAdapter.from_config(path)
            self.assertFalse(marker.exists())
            config["limits"]["max_seconds"] = 5
            path.write_text(json.dumps(config), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "request_timeout"):
                ReadOnlyMCPAdapter.from_config(path, request_timeout=0)
            self.assertFalse(marker.exists())


if __name__ == "__main__":
    unittest.main()
