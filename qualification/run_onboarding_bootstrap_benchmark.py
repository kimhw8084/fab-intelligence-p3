"""Measure staged, metadata-only P3 onboarding with the official SDK peer."""
from __future__ import annotations

import json
from pathlib import Path

from qualification.onboarding_harness import run_protocol_onboarding

ROOT = Path(__file__).resolve().parents[1]
SCENARIOS = ("onboarding-catalog", "onboarding-schema-alt")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def main() -> int:
    runs = []
    for scenario in SCENARIOS:
        result = run_protocol_onboarding(scenario)
        statuses = {key: result["module"]["evidence"]["artifacts"][0]["result"][key]["status"]
                    for key in ("fingerprint", "evolution", "quality_association", "anomaly", "similarity")}
        require(set(statuses.values()) == {"VALID"}, f"capability failure: {statuses}")
        require(result["metadata_read_count"] == 0, "metadata capture performed a bounded read")
        require(result["read_count_before_analysis"] == 0, "a row read preceded analysis")
        require(result["bounded_read_count"] == 5, "analysis did not execute exactly five bounded plans")
        require(result["bootstrap_capture"]["configured_source_scopes"] == [], "bootstrap depended on preselected source IDs")
        require(result["bootstrap_capture"]["reads_performed"] == 0, "bootstrap discovery performed a row read")
        require(result["bootstrap_proposal"]["automatic_approvals"] == 0, "source proposals granted approval")
        require(result["tool_catalog"]["tool_invocations"] == 0, "tool catalog invoked a server tool")
        runs.append({
            "scenario": scenario,
            "initial_catalog_descriptors": result["bootstrap_capture"]["source_catalog_count"],
            "initial_ranked_source_proposals": len(result["bootstrap_proposal"]["source_proposals"]),
            "source_mapping_proposals": len(result["proposal"]["source_proposals"]),
            "initial_metadata_row_reads": result["bootstrap_capture"]["reads_performed"],
            "scoped_metadata_row_reads": result["metadata_read_count"],
            "bounded_analysis_reads": result["bounded_read_count"],
            "capabilities": statuses,
            "stage_timing_ms": result["stage_timing_ms"],
            "workflow_timing_ms": result["elapsed_ms"],
        })

    baseline_pre_discovery_approval_records = 1 + 5 + 1 + 1  # read-only scope, tools, one source, one plan minimum
    assisted_pre_discovery_approval_records = 1 + 1  # metadata-only scope and exact discovery tool
    report = {
        "schema": "p3-onboarding-bootstrap-benchmark/v1",
        "qualification": "PASS_SYNTHETIC_ONLY",
        "peer": "official MCP Python SDK against protocol-compatible synthetic stdio server",
        "scenarios": runs,
        "pre_discovery_configuration": {
            "baseline_minimum_approval_records": baseline_pre_discovery_approval_records,
            "metadata_only_minimum_approval_records": assisted_pre_discovery_approval_records,
            "reduction_percent": round((1 - assisted_pre_discovery_approval_records /
                                         baseline_pre_discovery_approval_records) * 100, 1),
            "meaning": "Fewer approval/configuration records are needed before source catalog review; final source, relationship, query-plan, and analysis approvals remain required.",
            "human_time_measured": False,
        },
        "limitations": [
            "Synthetic tool names, sources, review references and semantic truth are not company data or permissions.",
            "Timing measures local synthetic execution only, not engineer setup or company latency.",
            "Tool listing and metadata proposals never grant invocation or row-read permission.",
        ],
    }
    output = ROOT / "progress" / "ONBOARDING_BOOTSTRAP_BENCHMARK.json"
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
