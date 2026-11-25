"""Measure P3 source discovery and full synthetic MCP onboarding performance."""
from __future__ import annotations

import json
import statistics
import sys
from copy import deepcopy
from pathlib import Path
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fabintel.onboarding import candidate_relationship_pairs, propose_source_mappings
from qualification.onboarding_harness import PLAN_IDS, run_protocol_onboarding
from qualification.spatial_catalog_fixture import build_catalog
from qualification.tree_hash import source_tree_sha256

ORACLE_PATH = ROOT / "qualification" / "fixtures" / "spatial_catalog_oracle.json"
OUTPUT = ROOT / "progress" / "SPATIAL_ONBOARDING_BENCHMARK.json"


def _proposal(catalog: list[dict]) -> tuple[dict, float]:
    capture = {"schema": "p3-authorized-metadata-capture/v1", "source_descriptors": catalog,
               "configured_source_scopes": [], "source_catalog_count": len(catalog), "reads_performed": 0}
    began = perf_counter()
    report = propose_source_mappings(capture, as_of="2026-01-15T00:00:00Z")
    return report, (perf_counter() - began) * 1000


def run() -> dict:
    oracle = json.loads(ORACLE_PATH.read_text(encoding="utf-8"))
    began = perf_counter()
    catalog = build_catalog(oracle["catalog_count"])
    generation_ms = (perf_counter() - began) * 1000
    reports, classification_ms = zip(*(_proposal(catalog) for _ in range(5)))
    report = reports[-1]
    proposals = report["source_proposals"]
    by_source = {}
    for item in proposals:
        by_source.setdefault(item["source_id"], []).append(item)

    positive_expected = []
    negatives = []
    role_matches = []
    invalid_ready = []
    modality_mismatches = []
    geometry_mismatches = []
    correct_oracle_cases = 0
    expected_profile_count = 0
    recalled_profile_count = 0
    for expected in oracle["candidate_source_expectations"]:
        matches = by_source.get(expected["source_id"], [])
        if expected["role"] == "ABSTAIN":
            negatives.append(expected["source_id"])
            ready = [item for item in matches if item["proposal_status"] == "PROPOSED_REVIEW_REQUIRED"
                     and not item["gaps"] and item["geometry_status"] == "PHYSICAL_VERIFIED"]
            if ready:
                invalid_ready.extend(item["proposal_id"] for item in ready)
            else:
                correct_oracle_cases += 1
            continue
        expected_matches = [item for item in matches if item["role"] == expected["role"]]
        if expected.get("modality") is not None:
            expected_matches = [item for item in expected_matches if item["modality"] == expected["modality"]]
        expected_profiles = expected.get("measurement_profiles", 1)
        expected_profile_count += expected_profiles
        exact_case = (len(expected_matches) == expected_profiles
                      and ("geometry" not in expected or any(item["geometry_status"] == expected["geometry"]
                                                               for item in expected_matches)))
        if exact_case:
            positive_expected.append(expected["source_id"])
            role_matches.append(expected["source_id"])
            correct_oracle_cases += 1
            recalled_profile_count += expected_profiles
        else:
            role_matches.append(None)
            if expected.get("modality"):
                modality_mismatches.append(expected["source_id"])
        if "geometry" in expected and not any(item["geometry_status"] == expected["geometry"] for item in expected_matches):
            geometry_mismatches.append(expected["source_id"])

    # Names are intentionally deceptive; changing only display titles must not
    # alter the typed proposal decisions.
    renamed = deepcopy(catalog)
    for index, descriptor in enumerate(renamed):
        descriptor["source_name"] = f"misleading-{index:05d}-wafer-yield"
    renamed_report, name_invariance_ms = _proposal(renamed)
    semantic_view = lambda items: [(item["source_id"], item["role"], item["profile_id"],
                                    item["proposal_status"], item["geometry_status"], item["modality"],
                                    item["measurement_unit"], item["observation_semantics"])
                                   for item in items]
    name_invariant = semantic_view(proposals) == semantic_view(renamed_report["source_proposals"])

    unrelated_catalog = [{"source_id": f"UNRELATED-{index}", "metadata_access": "PERMITTED",
                          "grain": "wafer", "column_definitions": [{"name": "wafer", "role": "wafer_id"}]}
                         for index in range(oracle["catalog_count"])]
    relationship_started = perf_counter()
    unrelated_pairs = candidate_relationship_pairs(unrelated_catalog)
    unrelated_relationship_ms = (perf_counter() - relationship_started) * 1000

    e2e = run_protocol_onboarding()
    e2e_alt = run_protocol_onboarding("onboarding-schema-alt")
    active_plans = [record for record in e2e["reviewed_config"]["approved_plans"]
                    if record.get("plan", {}).get("plan_id") in PLAN_IDS]
    required_reference_slots = (1 + len(e2e["reviewed_config"]["approved_sources"])
                               + len(e2e["reviewed_config"]["operations"])
                               + len(active_plans) + 3)
    analysis = e2e["module"]["evidence"]["artifacts"][0]["result"]
    capability_statuses = {"C01": analysis["fingerprint"]["status"],
                           "C02": analysis["evolution"]["status"],
                           "C03": analysis["quality_association"]["status"],
                           "C04": analysis["anomaly"]["status"],
                           "C05": analysis["similarity"]["status"]}
    alternate_analysis = e2e_alt["module"]["evidence"]["artifacts"][0]["result"]
    alternate_capability_statuses = {"C01": alternate_analysis["fingerprint"]["status"],
                                     "C02": alternate_analysis["evolution"]["status"],
                                     "C03": alternate_analysis["quality_association"]["status"],
                                     "C04": alternate_analysis["anomaly"]["status"],
                                     "C05": alternate_analysis["similarity"]["status"]}
    pair_count = len(positive_expected) * len(negatives)
    rank_correct = sum(1 for pos in positive_expected for neg in negatives
                       if max((item["score"] for item in by_source.get(pos, [])), default=0)
                       > max((item["score"] for item in by_source.get(neg, [])), default=0))
    screening_reduction = 1 - len(proposals) / oracle["catalog_count"]
    result = {
        "schema": "p3-spatial-onboarding-benchmark/v1",
        "oracle": {"path": "qualification/fixtures/spatial_catalog_oracle.json",
                   "authored_before_candidate_evaluation": oracle["oracle_authored_before_candidate_evaluation"]},
        "catalog": {"independent_table_descriptors": len(catalog), "proposal_outcomes": len(proposals),
                    "restricted_descriptors": report["catalog"]["restricted_metadata_descriptors"],
                    "catalog_generation_ms": round(generation_ms, 3),
                    "classifier_ms_median_5": round(statistics.median(classification_ms), 3),
                    "classifier_ms_all": [round(value, 3) for value in classification_ms],
                    "source_title_invariance": name_invariant,
                    "renamed_catalog_classifier_ms": round(name_invariance_ms, 3)},
        "relationship_screening_stress": {
            "unrelated_wafer_id_descriptors": len(unrelated_catalog),
            "candidate_pairs": len(unrelated_pairs),
            "elapsed_ms": round(unrelated_relationship_ms, 3),
            "pair_output_cap": 200,
            "status": "PASS" if not unrelated_pairs and unrelated_relationship_ms < 2000 else "FAIL"},
        "oracle_quality": {"expected_source_cases": len(oracle["candidate_source_expectations"]),
                           "correct_candidate_role_or_abstention_cases": correct_oracle_cases,
                           "expected_actionable_roles_recalled": len(positive_expected),
                           "expected_actionable_roles": sum(1 for row in oracle["candidate_source_expectations"]
                               if row["role"] != "ABSTAIN"),
                           "expected_actionable_profiles_recalled": recalled_profile_count,
                           "expected_actionable_profiles": expected_profile_count,
                           "positive_negative_pairwise_ranking_accuracy": (rank_correct / pair_count if pair_count else None),
                           "positive_negative_pairs": pair_count,
                           "invalid_ready_mappings_accepted": len(invalid_ready),
                           "modality_mismatches": modality_mismatches,
                           "geometry_mismatches": geometry_mismatches,
                           "name_based_decision_changes": 0 if name_invariant else None},
        "matched_onboarding_effort_model": {
            "manual_baseline": {"descriptor_triage_decisions": oracle["catalog_count"],
                                "final_source_mapping_reviews": 2, "relationship_reviews": 1,
                                "required_authorization_reference_slots": required_reference_slots,
                                "human_time_seconds": None, "basis": "predeclared one triage decision per descriptor; not measured labor"},
            "assisted": {"descriptor_triage_decisions": len(proposals), "final_source_mapping_reviews": 2,
                         "relationship_reviews": 1, "required_authorization_reference_slots": required_reference_slots,
                         "human_time_seconds": None,
                         "local_candidate_screening_decision_reduction_fraction": round(screening_reduction, 6),
                         "automated_time_to_valid_module_ms": e2e["elapsed_ms"],
                         "mcp_metadata_capture_timing_ms": e2e["capture"]["timing_ms"],
                         "commands_for_cli_rollout": ["mcp-onboard", "mcp-onboard-validate", "mcp-analyze"]},
            "authorization_decisions_removed": 0,
            "approval_slots_include": {"site_read_only_scope": 1,
                                       "source_permissions": len(e2e["reviewed_config"]["approved_sources"]),
                                       "logical_tool_bindings": len(e2e["reviewed_config"]["operations"]),
                                       "server_query_plans": len(active_plans),
                                       "mapping_reviews": 2, "relationship_review": 1},
            "interpretation": "Synthetic workflow counts only. Human labor, productivity and company ROI were not measured."},
        "synthetic_sdk_e2e": {"scenario": "protocol-compatible 13k catalog MCP peer",
                              "catalog_descriptors": e2e["capture"]["source_catalog_count"],
                              "metadata_row_reads_before_review": e2e["metadata_read_count"],
                              "data_reads_before_reviewed_config": e2e["read_count_before_analysis"],
                              "bounded_data_reads_after_review": e2e["bounded_read_count"],
                              "simulated_review_only": e2e["reviewed_config"]["onboarding_review"]["source_mapping_status"],
                              "automatic_mapping_approvals": int(e2e["reviewed_config"]["onboarding_review"]["automatic_approval"]),
                              "module_contract": e2e["module"]["contract_version"],
                              "evidence_status": e2e["module"]["evidence"]["status"],
                              "capability_statuses": capability_statuses,
                              "observation_count": e2e["module"]["spatial_map"]["sampling"]["observation_count"],
                              "provenance_bounded_reads": len(e2e["module"]["evidence"]["provenance"]["mcp_workflow"]["bounded_reads"]),
                              "alternate_opaque_schema": {"metadata_row_reads_before_review": e2e_alt["metadata_read_count"],
                                  "reads_before_analysis": e2e_alt["read_count_before_analysis"],
                                  "evidence_status": e2e_alt["module"]["evidence"]["status"],
                                  "capability_statuses": alternate_capability_statuses,
                                  "bounded_read_count": e2e_alt["bounded_read_count"]}},
        "limits": ["Synthetic semantic roles and approval references do not establish internal authority or source meaning.",
                   "The one-descriptor-one-triage manual baseline is a workload rubric, not measured engineer time.",
                   "No company productivity, deployment, security or manufacturing validation is implied."],
        "status": "PASS" if (name_invariant and correct_oracle_cases == len(oracle["candidate_source_expectations"])
                              and not unrelated_pairs and unrelated_relationship_ms < 2000
                              and recalled_profile_count == expected_profile_count
                              and not invalid_ready and not modality_mismatches
                              and not geometry_mismatches and e2e["metadata_read_count"] == 0
                              and e2e["read_count_before_analysis"] == 0 and e2e["bounded_read_count"] == 5
                              and e2e["module"]["evidence"]["status"] == "VALID"
                              and set(capability_statuses.values()) == {"VALID"}
                              and e2e_alt["metadata_read_count"] == 0 and e2e_alt["read_count_before_analysis"] == 0
                              and e2e_alt["bounded_read_count"] == 5 and e2e_alt["module"]["evidence"]["status"] == "VALID"
                              and set(alternate_capability_statuses.values()) == {"VALID"}) else "FAIL",
    }
    result["source_tree_sha256"] = source_tree_sha256(ROOT)
    OUTPUT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "output": str(OUTPUT.relative_to(ROOT)),
                      "catalog_count": len(catalog), "proposal_count": len(proposals),
                      "median_classifier_ms": result["catalog"]["classifier_ms_median_5"],
                      "valid_e2e_ms": e2e["elapsed_ms"], "C01_C05": capability_statuses}, sort_keys=True))
    if result["status"] != "PASS":
        raise SystemExit(1)
    return result


if __name__ == "__main__":
    run()
