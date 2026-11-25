"""Explicit synthetic read-only MCP configuration for the P3 reference host.

The mock peer advertises these tool schemas and synthetic approval references;
none of the identifiers or approvals are company mappings or permissions.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from fabintel.mcp_adapter import approved_query_plan_sha256, tool_definition_sha256


def synthetic_adapter_config(client: Any, root: Path, scenario: str | None = None) -> dict[str, Any]:
    tools = {tool["name"]: tool for tool in client.list_tools()}
    argument_mappings = {
        "discover": {},
        "semantics": {"source_ids": "source_ids", "semantic_version": "semantic_version"},
        "relationships": {"typed_entity_ids": "typed_entity_ids", "time_window": "time_window"},
        "read_bounded": {"approved_plan": "approved_plan", "permission_context": "permission_context",
                         "limits": "limits", "operation_id": "operation_id"},
        "audit": {"operation_id": "operation_id"},
    }
    tool_names = {"discover": "fab_discover", "semantics": "fab_semantics",
                  "relationships": "fab_relationships", "read_bounded": "fab_read_bounded",
                  "audit": "fab_audit"}
    operations = {}
    for logical, tool_name in tool_names.items():
        if tool_name not in tools:
            raise ValueError(f"synthetic MCP peer omitted expected tool {tool_name}")
        operations[logical] = {
            "tool_name": tool_name,
            "approval": {"approved": True, "reference": "SYN-TOOL-APPROVAL-" + logical,
                         "tool_definition_sha256": tool_definition_sha256(tools[tool_name])},
            "argument_mapping": argument_mappings[logical],
        }

    plans = []
    workflow_plans = (("SYN-WF-CURRENT", "MOCK_MAP", "current"),
                      ("SYN-WF-PREVIOUS", "MOCK_MAP", "previous"),
                      ("SYN-WF-BASELINE", "MOCK_MAP", "baseline"),
                      ("SYN-WF-HISTORY", "MOCK_MAP", "history"),
                      ("SYN-WF-ASSOCIATION", "MOCK_QUALITY", "association"))
    special_plans = [("SYN-PLAN-1", "MOCK_MAP", None, 0), ("SYN-CANCEL", "MOCK_MAP", None, 700)]
    for plan_id, source_id, role in workflow_plans:
        special_plans.append((plan_id, source_id, role, 0))
    special_plans.extend([
        ("SYN-WF-CURRENT-BAD-UNIT", "MOCK_MAP", "current", 0),
        ("SYN-WF-CURRENT-BAD-AUDIT", "MOCK_MAP", "current", 0),
        # Long enough for a real browser operator to press Cancel after the
        # loading state appears; tests also exercise lower-level cancellation.
        ("SYN-WF-CURRENT-CANCEL", "MOCK_MAP", "current", 2500),
    ])
    for plan_id, source_id, role, delay in special_plans:
        plan = {"plan_id": plan_id, "source_id": source_id, "semantic_version": "MOCK-SEM-1"}
        if role:
            plan["analysis_role"] = role
        if delay:
            plan["test_delay_ms"] = delay
        if plan_id == "SYN-WF-CURRENT-BAD-UNIT":
            plan["test_case"] = "wrong_measurement_unit"
        elif plan_id == "SYN-WF-CURRENT-BAD-AUDIT":
            plan["test_case"] = "wrong_audit_hash"
        plans.append({"approved": True, "approval_reference": "SYN-QUERY-" + plan_id,
                      "plan": plan, "plan_sha256": approved_query_plan_sha256(plan)})

    peer_command = [sys.executable, "-S", "-m", "qualification.synthetic_mcp_peer", "--protocol", "dual"]
    if scenario:
        if not scenario.replace("-", "").isalnum() or len(scenario) > 48:
            raise ValueError("synthetic peer scenario is invalid")
        peer_command.extend(("--scenario", scenario))
    return {
        "schema_version": "p3-mcp-adapter-config-v1",
        "transport": {"type": "stdio", "command": peer_command, "cwd": str(root)},
        "read_only_approval": {"approved": True, "reference": "SYN-READ-ONLY-APPROVAL"},
        "approved_sources": [
            {"approved": True, "source_id": source, "semantic_version": "MOCK-SEM-1",
             "source_version": "MOCK-SNAPSHOT-" + source.removeprefix("MOCK_"),
             "approval_reference": "SYN-SOURCE-" + source}
            for source in ("MOCK_MAP", "MOCK_QUALITY")
        ],
        "approved_plans": plans,
        "limits": {"max_rows": 1000, "max_bytes": 4 * 1024 * 1024, "max_seconds": 8},
        **({"evolution_match_policy": {"predeclared": True, "method": "exact_common_site_v1",
                                        "minimum_sites": 40, "minimum_coverage_fraction": 0.85}}
           if scenario in {"engineer-challenge", "c01-dense-challenge"} else {}),
        "operations": operations,
    }


def synthetic_metadata_adapter_config(client: Any, root: Path, scenario: str | None = None,
                                      *, source_scopes: bool = False) -> dict[str, Any]:
    """Metadata-only review fixture with no row plans or bounded-read tool."""
    analysis = synthetic_adapter_config(client, root, scenario)
    operations = {name: analysis["operations"][name]
                  for name in (("discover", "semantics", "relationships") if source_scopes else ("discover",))}
    return {
        **analysis,
        "access_mode": "metadata_only",
        "read_only_approval": {"approved": True, "scope": "metadata_only",
                               "reference": "SYN-METADATA-ONLY-APPROVAL"},
        "approved_sources": [],
        "metadata_sources": ([{**source, "approval_reference": "SYN-METADATA-SCOPE-" + source["source_id"]}
                              for source in analysis["approved_sources"]] if source_scopes else []),
        "approved_plans": [],
        "operations": operations,
    }
