"""Test-only synthetic authorization and MCP-to-P3 onboarding harness."""
from __future__ import annotations

import sys
from pathlib import Path
from time import perf_counter
from typing import Any

from fabintel.mcp_adapter import ReadOnlyMCPAdapter
from fabintel.mcp_adapter import capture_mcp_tool_catalog
from fabintel.mcp_client import MCPClient
from fabintel.mcp_workflow import run_mcp_host_module
from fabintel.onboarding import (
    build_reviewed_config,
    capture_authorized_metadata,
    propose_source_mappings,
)
from fabintel.synthetic_mcp import synthetic_adapter_config, synthetic_metadata_adapter_config

ROOT = Path(__file__).resolve().parents[1]
PLAN_IDS = ["SYN-WF-CURRENT", "SYN-WF-PREVIOUS", "SYN-WF-BASELINE",
            "SYN-WF-HISTORY", "SYN-WF-ASSOCIATION"]
TIME_WINDOW = {"start": "2026-01-01T00:00:00Z", "end": "2026-02-01T00:00:00Z"}


def run_protocol_onboarding(scenario: str = "onboarding-catalog") -> dict[str, Any]:
    """Discover metadata, propose roles, simulate named review, and execute C01-C05.

    Synthetic approval references exercise validation mechanics only. They do
    not represent or create a real source permission.
    """
    command = [sys.executable, "-S", "-m", "qualification.synthetic_mcp_peer",
               "--protocol", "dual", "--scenario", scenario]
    client = MCPClient({"type": "stdio", "command": command, "cwd": str(ROOT)}, request_timeout=20)
    started = perf_counter()
    try:
        catalog_started = perf_counter()
        tool_catalog = capture_mcp_tool_catalog(client)
        tool_catalog_ms = (perf_counter() - catalog_started) * 1000
        config = synthetic_adapter_config(client, ROOT, scenario)
        bootstrap_config = synthetic_metadata_adapter_config(client, ROOT, scenario)
        bootstrap_adapter = ReadOnlyMCPAdapter(client, bootstrap_config)
        bootstrap_started = perf_counter()
        bootstrap_capture = capture_authorized_metadata(bootstrap_adapter, time_window=TIME_WINDOW)
        bootstrap_proposal = propose_source_mappings(bootstrap_capture, as_of="2026-01-15T00:00:00Z")
        bootstrap_ms = (perf_counter() - bootstrap_started) * 1000
        if (bootstrap_config["approved_sources"] or bootstrap_config["approved_plans"]
                or set(bootstrap_config["operations"]) != {"discover"}
                or not bootstrap_proposal["source_proposals"]):
            raise AssertionError("metadata-only discovery failed without preconfigured row sources or plans")

        metadata_config = synthetic_metadata_adapter_config(client, ROOT, scenario, source_scopes=True)
        metadata_adapter = ReadOnlyMCPAdapter(client, metadata_config)
        source_metadata_started = perf_counter()
        capture = capture_authorized_metadata(metadata_adapter, time_window=TIME_WINDOW)
        metadata_reads = len(metadata_adapter.local_audit_trace)
        proposal = propose_source_mappings(capture, as_of="2026-01-15T00:00:00Z")
        source_metadata_ms = (perf_counter() - source_metadata_started) * 1000
        selected = []
        for source_id, role in (("MOCK_MAP", "spatial_measurements"),
                                ("MOCK_QUALITY", "downstream_quality")):
            candidate = next((item for item in proposal["source_proposals"]
                              if item["source_id"] == source_id and item["role"] == role
                              and item["proposal_status"] == "PROPOSED_REVIEW_REQUIRED"), None)
            if candidate is None:
                raise AssertionError(f"synthetic review fixture could not identify {source_id} as {role}")
            selected.append(candidate)
        relation = next((item for item in proposal["relationship_proposals"]
                         if item.get("source_id") == "MOCK_MAP"
                         and item.get("target_source_id") == "MOCK_QUALITY"
                         and item.get("proposal_status") == "AUTHORITY_REPORTED_REVIEW_REQUIRED"), None)
        if relation is None:
            raise AssertionError("synthetic peer did not report the expected wafer/die relationship")
        review = {
            "schema": "p3-onboarding-review/v1",
            "proposal_sha256": proposal["proposal_sha256"],
            "reviewer_id": "SYNTHETIC-REVIEWER-01",
            "authority_reference": "SYNTHETIC-AUTHORITY-ONLY",
            "synthetic_simulation": True,
            "selected_proposal_ids": [item["proposal_id"] for item in selected],
            "source_decisions": [{"proposal_id": item["proposal_id"], "decision": "APPROVE",
                                  "approval_reference": "SYNTHETIC-SOURCE-" + item["source_id"]}
                                 for item in selected],
            "selected_relationship_proposal_id": relation["relationship_proposal_id"],
            "relationship_decisions": [{"relationship_proposal_id": relation["relationship_proposal_id"],
                                         "decision": "APPROVE", "approval_reference": "SYNTHETIC-RELATIONSHIP-01"}],
        }
        reviewed = build_reviewed_config(config, proposal, review)
        adapter = ReadOnlyMCPAdapter(client, reviewed)
        reads_before_analysis = len(adapter.local_audit_trace)
        analysis_started = perf_counter()
        module = run_mcp_host_module(adapter, PLAN_IDS, time_window=TIME_WINDOW,
                                     operation_id="SYN-ONBOARDING-E2E")
        analysis_ms = (perf_counter() - analysis_started) * 1000
        elapsed_ms = (perf_counter() - started) * 1000
        return {"bootstrap_capture": bootstrap_capture, "bootstrap_proposal": bootstrap_proposal,
                "metadata_config": metadata_config, "capture": capture,
                "proposal": proposal, "reviewed_config": reviewed,
                "module": module, "metadata_read_count": metadata_reads,
                "read_count_before_analysis": reads_before_analysis,
                "bounded_read_count": len(adapter.local_audit_trace),
                "tool_catalog": tool_catalog,
                "stage_timing_ms": {"tool_catalog": round(tool_catalog_ms, 3),
                                     "initial_source_discovery": round(bootstrap_ms, 3),
                                     "scoped_semantics_and_relationships": round(source_metadata_ms, 3),
                                     "c01_c05_analysis": round(analysis_ms, 3)},
                "elapsed_ms": round(elapsed_ms, 3)}
    finally:
        client.close()
