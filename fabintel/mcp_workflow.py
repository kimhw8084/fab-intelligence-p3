"""P3-specific MCP-to-spatial-analysis workflow.

The official MCP SDK owns protocol transport. This module composes the existing
read-only adapter with the deterministic P3 engine; it does not add a second
semantic authority, transport, or suite API.
"""
from __future__ import annotations

import hashlib
import json
import math
import uuid
from collections import defaultdict
from collections.abc import Mapping
from copy import deepcopy
from threading import Event
from typing import Any

from fabintel.contracts import validate_envelope
from fabintel.mcp_adapter import MCPDataError, MCPPolicyError, ReadOnlyMCPAdapter
from fabintel.mcp_client import MCPCancelled
from fabintel.spatial_observations import (
    SpatialContractError,
    make_spatial_map,
    to_suite_spatial_map_v1,
)
from products.p3.engine import analyze

CAPABILITIES = ["C01", "C02", "C03", "C04", "C05"]
ANALYSIS_ROLES = {"current", "previous", "baseline", "history", "association"}


def _canonical_sha256(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _finite_number(value: Any) -> bool:
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(float(value)))


def _role_columns(definition: Mapping[str, Any]) -> dict[str, str]:
    columns = definition.get("column_definitions")
    if not isinstance(columns, list) or not columns:
        raise MCPDataError("approved semantics contain no column-to-role mapping")
    result: dict[str, str] = {}
    names = set()
    for column in columns:
        if (not isinstance(column, dict) or not isinstance(column.get("name"), str)
                or not column["name"] or not isinstance(column.get("role"), str)
                or not column["role"] or column["role"] in result or column["name"] in names):
            raise MCPDataError("semantic column names and roles must be nonempty and unique")
        result[column["role"]] = column["name"]
        names.add(column["name"])
    return result


def _require_role_unit(definition: Mapping[str, Any], role: str, expected: str) -> None:
    columns = definition.get("column_definitions", [])
    column = next((item for item in columns if item.get("role") == role), None)
    if column is None or column.get("unit") != expected:
        raise MCPDataError(f"approved semantic role {role!r} must declare unit {expected!r}")


def _value(row: Mapping[str, Any], roles: Mapping[str, str], role: str,
           *, required: bool = True) -> Any:
    field = roles.get(role)
    if field is None:
        if required:
            raise MCPDataError(f"approved semantics do not map required P3 field {role!r}")
        return None
    if field not in row:
        raise MCPDataError(f"bounded MCP row omitted semantically mapped field {field!r}")
    return row[field]


def _validate_spatial_profile(definition: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    geometry_profile = definition.get("spatial_profile")
    measurement = definition.get("measurement_profile")
    if not isinstance(geometry_profile, dict) or not isinstance(measurement, dict):
        raise MCPDataError("approved semantics must include spatial and measurement profiles")
    geometry = geometry_profile.get("geometry")
    if not isinstance(geometry, dict):
        raise MCPDataError("approved spatial semantics omitted wafer geometry")
    radius = geometry.get("radius")
    origin = geometry.get("origin")
    if (not _finite_number(radius) or radius <= 0 or not isinstance(origin, dict)
            or not _finite_number(origin.get("x")) or not _finite_number(origin.get("y"))
            or not isinstance(geometry.get("coordinate_system"), str) or not geometry["coordinate_system"]
            or not isinstance(geometry.get("coordinate_unit"), str) or not geometry["coordinate_unit"]):
        raise MCPDataError("approved geometry must provide a finite radius, origin, coordinate system and unit")
    orientation = geometry.get("orientation_deg")
    if orientation is not None and (not _finite_number(orientation) or not 0 <= orientation < 360):
        raise MCPDataError("approved wafer orientation must be a finite angle in [0, 360)")
    if (not isinstance(measurement.get("metric"), str) or not measurement["metric"]
            or not isinstance(measurement.get("unit"), str) or not measurement["unit"]
            or not isinstance(measurement.get("modality"), str)
            or not isinstance(measurement.get("definition_id"), str) or not measurement["definition_id"]
            or not isinstance(measurement.get("layer"), str) or not measurement["layer"]):
        raise MCPDataError("approved measurement semantics must identify metric, unit, modality, definition and layer")
    declared_units = definition.get("units")
    if not isinstance(declared_units, list) or measurement["unit"] not in declared_units:
        raise MCPDataError("measurement unit is absent from the approved semantic unit set")
    return deepcopy(geometry_profile), deepcopy(measurement)


def _build_maps(rows: list[dict[str, Any]], definition: Mapping[str, Any], source_id: str,
                role: str) -> list[dict[str, Any]]:
    if not rows:
        return []
    roles = _role_columns(definition)
    geometry_profile, measurement = _validate_spatial_profile(definition)
    geometry = geometry_profile["geometry"]
    coordinate_unit = geometry["coordinate_unit"]
    _require_role_unit(definition, "x", coordinate_unit)
    _require_role_unit(definition, "y", coordinate_unit)
    modality = measurement["modality"]
    if modality not in {"continuous", "sparse_continuous", "die_bin_categorical", "defect_coordinates"}:
        raise MCPDataError("MCP semantic modality is not supported by the P3 spatial contract")
    mandatory = {"wafer_id", "lot_id", "measured_at", "product_id",
                 "population_signature", "sampling_mask_id", "site_id", "x", "y"}
    if modality in {"continuous", "sparse_continuous"}:
        mandatory.add("value")
    if modality == "die_bin_categorical":
        mandatory.add("category")
    if not mandatory.issubset(roles):
        missing = ", ".join(sorted(mandatory - set(roles)))
        raise MCPDataError("approved semantic mapping is missing required P3 roles: " + missing)
    if modality in {"continuous", "sparse_continuous"}:
        _require_role_unit(definition, "value", measurement["unit"])
        if "standard_uncertainty" in roles:
            _require_role_unit(definition, "standard_uncertainty", measurement["unit"])

    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if not isinstance(row, dict):
            raise MCPDataError("bounded MCP result contains a non-object spatial row")
        row_source = _value(row, roles, "source_id", required=False)
        row_source = source_id if row_source is None else row_source
        wafer = _value(row, roles, "wafer_id")
        lot = _value(row, roles, "lot_id")
        timestamp = _value(row, roles, "measured_at")
        if row_source != source_id:
            raise MCPPolicyError("semantic row source does not match the approved read source")
        if not all(isinstance(item, str) and item.strip() for item in (wafer, lot, timestamp)):
            raise MCPDataError("spatial rows require nonempty wafer, lot and measured-time identities")
        step = _value(row, roles, "step_instance_id", required=False) or _value(row, roles, "step_id", required=False) or "map"
        if not isinstance(step, str):
            raise MCPDataError("spatial step identity must be a string")
        grouped[(wafer, step)].append(row)

    maps = []
    for (wafer, step), members in grouped.items():
        first = members[0]
        stable_roles = ("lot_id", "measured_at", "product_id", "population_signature",
                        "sampling_mask_id", "step_id", "step_instance_id", "expected_site_count")
        context = {name: _value(first, roles, name, required=False) for name in stable_roles}
        points = []
        seen_sites = set()
        seen_coordinates = set()
        for row in members:
            for name in stable_roles:
                if _value(row, roles, name, required=False) != context[name]:
                    raise MCPDataError(f"one wafer map contains inconsistent {name} values")
            observed_unit = _value(row, roles, "measurement_unit", required=False)
            if observed_unit is not None and observed_unit != measurement["unit"]:
                raise MCPDataError("measured-site unit differs from the approved measurement semantics")
            x, y = _value(row, roles, "x"), _value(row, roles, "y")
            if not _finite_number(x) or not _finite_number(y):
                raise MCPDataError("measured-site coordinates must be finite numeric values")
            site_id = _value(row, roles, "site_id")
            if not isinstance(site_id, str) or not site_id.strip() or site_id in seen_sites:
                raise MCPDataError("measured-site identities must be nonempty and unique within a wafer map")
            seen_sites.add(site_id)
            relative_x = float(x) - float(geometry["origin"]["x"])
            relative_y = float(y) - float(geometry["origin"]["y"])
            tolerance = max(float(geometry["radius"]) * 1e-9, 1e-12)
            if math.hypot(relative_x, relative_y) > float(geometry["radius"]) + tolerance:
                raise MCPDataError("measured-site coordinate lies outside the approved wafer geometry")
            coordinate_key = (round(relative_x / tolerance), round(relative_y / tolerance))
            if coordinate_key in seen_coordinates:
                raise MCPDataError("wafer map contains duplicate measured coordinates")
            seen_coordinates.add(coordinate_key)
            point = {"site_id": site_id, "x": x, "y": y}
            if modality in {"continuous", "sparse_continuous"}:
                value = _value(row, roles, "value")
                if value is not None and not _finite_number(value):
                    raise MCPDataError("measured-site values must be finite numeric values or explicit null")
                point["value"] = value
                uncertainty = _value(row, roles, "standard_uncertainty", required=False)
                if uncertainty is not None:
                    if not _finite_number(uncertainty) or uncertainty < 0:
                        raise MCPDataError("site standard uncertainty must be finite and nonnegative")
                    point["standard_uncertainty"] = uncertainty
                    point["standard_uncertainty_unit"] = measurement["unit"]
            elif modality == "die_bin_categorical":
                category = _value(row, roles, "category")
                if category is not None and not ((isinstance(category, str) and bool(category.strip())) or _finite_number(category)):
                    raise MCPDataError("categorical measured sites require a nonempty string or finite numeric bin identifier")
                point["category"] = category
            else:
                category_column = roles.get("category", roles.get("bin"))
                category = row.get(category_column) if category_column else None
                if category is not None:
                    if not ((isinstance(category, str) and bool(category.strip())) or _finite_number(category)):
                        raise MCPDataError("defect category must be a nonempty string or finite numeric label")
                    point["category"] = category
            points.append(point)
        if any(not isinstance(context[key], str) or not context[key].strip()
               for key in ("product_id", "population_signature", "sampling_mask_id")):
            raise MCPDataError("spatial map context is missing product, population or sampling identity")
        expected_site_count = context["expected_site_count"]
        if expected_site_count is not None and (type(expected_site_count) is not int or expected_site_count < len(points)):
            raise MCPDataError("expected site count must be an integer no smaller than the bounded observation set")
        maps.append({
            "mode": "SYNTHETIC_DEMO",
            "coordinates_verified": geometry_profile.get("coordinates_verified") is True,
            "geometry": deepcopy(geometry_profile["geometry"]),
            "measurement": deepcopy(measurement),
            "wafer_id": wafer,
            "lot_id": context["lot_id"],
            "measured_at": context["measured_at"],
            "product_id": context["product_id"],
            "population_signature": context["population_signature"],
            "sampling_mask_id": context["sampling_mask_id"],
            "step_id": context["step_id"],
            "step_instance_id": context["step_instance_id"],
            **({"expected_site_count": expected_site_count} if expected_site_count is not None else {}),
            "source_id": source_id,
            "points": points,
        })
    maps.sort(key=lambda item: (item.get("measured_at") or "", item.get("step_id") or "", item["wafer_id"]))
    return maps


def _build_association(rows: list[dict[str, Any]], definition: Mapping[str, Any],
                       relationship: Mapping[str, Any], source_id: str) -> dict[str, Any]:
    roles = _role_columns(definition)
    required = {"wafer_id", "lot_id", "die_id", "cohort", "feature_at", "outcome_at",
                "x", "y", "feature_value", "outcome_value", "spatial_block_id", "product_id", "metric",
                "measurement_definition_id", "layer", "population_signature", "sampling_mask_id"}
    if not required.issubset(roles):
        raise MCPDataError("approved quality semantics omit required wafer/die outcome roles")
    context = definition.get("quality_context")
    geometry = definition.get("quality_geometry")
    holdout = definition.get("quality_holdout")
    cohort_selection = definition.get("quality_cohort_selection")
    hypothesis_selection = definition.get("quality_hypothesis_selection")
    if not all(isinstance(value, dict) for value in (context, geometry, holdout)):
        raise MCPDataError("approved quality semantics must include context, geometry and holdout design")
    if (geometry.get("verified") is not True or not isinstance(geometry.get("coordinate_system"), str)
            or not geometry.get("coordinate_system") or not isinstance(geometry.get("coordinate_unit"), str)
            or not geometry.get("coordinate_unit") or not _finite_number(geometry.get("radius"))
            or geometry["radius"] <= 0 or not isinstance(geometry.get("origin"), dict)
            or not _finite_number(geometry["origin"].get("x"))
            or not _finite_number(geometry["origin"].get("y"))):
        raise MCPDataError("approved quality geometry must be verified and physically bounded")
    _require_role_unit(definition, "x", geometry["coordinate_unit"])
    _require_role_unit(definition, "y", geometry["coordinate_unit"])
    if not isinstance(definition.get("units"), list) or context.get("unit") not in definition["units"]:
        raise MCPDataError("quality context unit is absent from the approved semantic unit set")
    observations = []
    for row in rows:
        if (not isinstance(row, dict)
                or _value(row, roles, "source_id", required=False) not in (None, source_id)):
            raise MCPPolicyError("quality row source does not match the approved read source")
        item = {role: _value(row, roles, role) for role in required if role != "source_id"}
        observed_unit = _value(row, roles, "measurement_unit", required=False)
        item["unit"] = observed_unit if observed_unit is not None else context.get("unit")
        observations.append(item)
    if (relationship.get("approved") is not True or relationship.get("grain") != "wafer_die"
            or set(relationship.get("keys", [])) != {"wafer_id", "die_id"}
            or relationship.get("cardinality") != "one_to_many"
            or relationship.get("coordinate_mapping_verified") is not True
            or relationship.get("spatial_block_method") != "predeclared_block_fixed_effects_v1"):
        raise MCPPolicyError("approved MCP relationship does not satisfy P3 wafer/die spatial matching semantics")
    relation = deepcopy(dict(relationship))
    relation["source_id"] = source_id
    return {"context": deepcopy(context), "geometry": deepcopy(geometry),
            "holdout": deepcopy(holdout),
            "cohort_selection": deepcopy(cohort_selection) if isinstance(cohort_selection, dict) else None,
            "hypothesis_selection": deepcopy(hypothesis_selection) if isinstance(hypothesis_selection, dict) else None,
            "relationship": relation,
            "observations": observations}


def _run_mcp_workflow(adapter: ReadOnlyMCPAdapter, plan_ids: list[str], *,
                      time_window: Mapping[str, Any], top_k: int = 5,
                      anomaly_target_family: Mapping[str, Any] | None = None,
                      cancel: Event | None = None, operation_id: str | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    """Read approved P3 datasets through MCP and return a validated evidence envelope.

    Plan metadata must contain an exact approved ``analysis_role`` chosen from
    current, previous, baseline, history or association. Missing auxiliary roles
    remain visible as P3 capability abstentions in the resulting evidence.
    """
    if adapter.access_mode != "analysis":
        raise MCPPolicyError("C01-C05 execution requires a site-approved analysis access profile")
    if not isinstance(plan_ids, list) or not plan_ids or any(not isinstance(item, str) for item in plan_ids):
        raise MCPPolicyError("at least one site-approved bounded analysis plan ID is required")
    if not isinstance(time_window, Mapping):
        raise MCPPolicyError("a bounded time window is required for MCP relationship discovery")
    if type(top_k) is not int or not 1 <= top_k <= 50:
        raise MCPPolicyError("P3 historical retrieval top_k must be between 1 and 50")
    discovery = adapter.discover()
    plans: list[dict[str, Any]] = []
    seen_plan_ids = set()
    seen_roles = set()
    semantic_versions: dict[str, str] = {}
    for plan_id in plan_ids:
        if plan_id in seen_plan_ids:
            raise MCPPolicyError("analysis plan IDs must be unique")
        seen_plan_ids.add(plan_id)
        plan = adapter.approved_plan(plan_id)
        role = plan.get("analysis_role")
        source_id = plan.get("source_id")
        if role not in ANALYSIS_ROLES or not isinstance(source_id, str):
            raise MCPPolicyError("an approved P3 plan must identify one supported analysis role and source")
        if role in {"current", "association"} and role in seen_roles:
            raise MCPPolicyError(f"only one approved {role} plan is supported per workflow")
        seen_roles.add(role)
        source = adapter.sources.get(source_id)
        if source is None:
            raise MCPPolicyError("analysis plan source is not an explicitly approved source")
        if not isinstance(source.get("source_version"), str) or not source["source_version"].strip():
            raise MCPPolicyError("an approved source snapshot version is required for integrated analysis")
        semantic_versions[source_id] = source["semantic_version"]
        plans.append({"plan_id": plan_id, "plan": plan, "role": role, "source_id": source_id,
                      "approval_reference": adapter.plans[plan_id]["approval_reference"]})
    if "current" not in seen_roles:
        raise MCPPolicyError("one approved current wafer-map plan is required")

    definitions: dict[str, dict[str, Any]] = {}
    for source_id, version in sorted(semantic_versions.items()):
        response = adapter.semantics([source_id], version)
        definition = response["column_definitions"][0]
        definitions[source_id] = definition

    relation = None
    association_plan = next((item for item in plans if item["role"] == "association"), None)
    current_plan = next(item for item in plans if item["role"] == "current")
    if association_plan is not None:
        relation = adapter.relationships(
            {"source_id": current_plan["source_id"], "target_source_id": association_plan["source_id"]},
            time_window,
        )

    operation_root = operation_id or ("P3-MCP-" + uuid.uuid4().hex)
    if not isinstance(operation_root, str) or not operation_root or len(operation_root) > 80:
        raise ValueError("operation_id must be a nonempty string of at most 80 characters")
    rows_by_role: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    source_reads: dict[str, list[dict[str, Any]]] = defaultdict(list)
    read_evidence = []
    for index, item in enumerate(plans):
        if cancel is not None and cancel.is_set():
            raise MCPCancelled("MCP analysis was cancelled before the next bounded read")
        op = f"{operation_root}-{index + 1}"
        read = adapter.read_bounded(
            item["plan"], {"scope": "read_only", "source_ids": [item["source_id"]]},
            operation_id=op, cancel_event=cancel,
        )
        if read.get("truncation") is not False:
            raise MCPDataError("P3 analysis requires a complete, non-truncated approved read")
        audit = adapter.audit(op)
        trace = read["audit_trace"]
        if (audit.get("operation_id") != op or audit.get("permission_scope") != "read_only"
                or audit.get("sources") != [item["source_id"]]
                or audit.get("source_versions") != read.get("source_versions")
                or audit.get("query_hash") != trace.get("query_hash")
                or audit.get("audit_id") != read.get("audit_id")):
            raise MCPDataError("remote MCP audit does not correlate to the exact bounded P3 read")
        rows = read["typed_rows"]
        rows_by_role[item["role"]][item["source_id"]].extend(rows)
        source_reads[item["source_id"]].append({"plan_id": item["plan_id"], "rows": rows,
                                                 "query_hash": trace["query_hash"],
                                                 "audit_id": read["audit_id"]})
        read_evidence.append({"analysis_role": item["role"], "source_id": item["source_id"],
                              "plan_id": item["plan_id"], "plan_approval_reference": item["approval_reference"],
                              "operation_id": op, "permission_scope": "read_only",
                              "row_count": len(rows), "query_hash": trace["query_hash"],
                              "audit_id": read["audit_id"], "source_versions": read["source_versions"],
                              "source_version": read["source_versions"][item["source_id"]],
                              "completed_at": trace["completed_at"]})

    map_source_ids = {item["source_id"] for item in plans if item["role"] != "association"}
    maps_by_role: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for role in ("current", "previous", "baseline", "history"):
        for source_id in sorted(map_source_ids):
            selected_plans = [item for item in plans if item["role"] == role and item["source_id"] == source_id]
            if selected_plans:
                maps_by_role[role].extend(_build_maps(rows_by_role[role][source_id], definitions[source_id], source_id, role))
    if len(maps_by_role["current"]) != 1:
        raise MCPDataError("the approved current-map read must resolve to exactly one wafer map")
    current = maps_by_role["current"][0]
    current["source_ids"] = [current["source_id"]]
    data: dict[str, Any] = {**current, "requested_capabilities": CAPABILITIES, "top_k": top_k}
    # Analysis policies are local administrator configuration. Never accept a
    # policy from source rows, where it could silently relax comparison gates.
    if anomaly_target_family is not None:
        data["anomaly_target_family"] = deepcopy(dict(anomaly_target_family))
    evolution_policy = adapter.config.get("evolution_match_policy")
    if evolution_policy is not None:
        data["evolution_match_policy"] = deepcopy(evolution_policy)
    if maps_by_role["previous"]:
        data["previous_steps"] = maps_by_role["previous"]
    if maps_by_role["baseline"]:
        data["baseline_population"] = maps_by_role["baseline"]
        baseline_sources = sorted({item["source_id"] for item in plans if item["role"] == "baseline"})
        holdout_reviews = {source_id: definitions[source_id].get("baseline_holdout")
                           for source_id in baseline_sources}
        data["baseline_holdout_verified"] = bool(holdout_reviews) and all(
            isinstance(review, dict) and review.get("verified") is True
            and isinstance(review.get("approval_reference"), str) and bool(review["approval_reference"].strip())
            for review in holdout_reviews.values()
        )
    else:
        holdout_reviews = {}
    if maps_by_role["history"]:
        data["history"] = maps_by_role["history"]
    if association_plan is not None and relation is not None:
        quality_definition = definitions[association_plan["source_id"]]
        data["quality_association"] = _build_association(
            rows_by_role["association"][association_plan["source_id"]], quality_definition, relation,
            association_plan["source_id"]
        )
    evidence = analyze(data, cancel)
    validate_envelope(evidence)

    source_manifest = []
    for source_id in sorted(source_reads):
        source = adapter.sources[source_id]
        definition = definitions[source_id]
        all_rows = [{"plan_id": read["plan_id"], "rows": read["rows"]}
                    for read in source_reads[source_id]]
        completed = next((row["completed_at"] for row in read_evidence
                          if row["source_id"] == source_id), None)
        source_manifest.append({"id": source_id,
                                "approved_semantic_version": definition["semantic_version"],
                                "grain": definition["grain"],
                                "source_hash": _canonical_sha256(all_rows),
                                "source_version": adapter.sources[source_id]["source_version"],
                                "permissions_ref": source["approval_reference"],
                                "observed_at": completed})
    evidence["sources"] = source_manifest
    evidence["assumptions"] = [
        "The official MCP SDK reached a protocol-compatible synthetic peer; site-reviewed tool hashes, semantic roles, read plans, bounded read limits and correlated audit records were checked.",
        "Synthetic approvals and source metadata do not qualify a company MCP deployment; INTERNAL_QUALIFICATION_PENDING.",
    ]
    evidence["provenance"]["mcp_workflow"] = {
        "workflow_version": "p3-mcp-spatial-analysis.v1",
        "protocol_version": discovery["protocol_version"],
        "server_info": discovery["server_info"],
        "permission_scope": "read_only",
        "adapter_approval_reference": adapter.approval["reference"],
        "tool_approvals": [{"logical_operation": name, "tool_name": binding["tool_name"],
                             "approval_reference": binding["approval"]["reference"],
                             "tool_definition_sha256": binding["approval"]["tool_definition_sha256"]}
                            for name, binding in sorted(adapter.bindings.items())],
        "semantic_mappings": [{"source_id": source_id,
                                "semantic_version": definitions[source_id]["semantic_version"],
                                "grain": definitions[source_id]["grain"],
                                "mapping_sha256": _canonical_sha256(definitions[source_id]),
                                "approval_reference": adapter.sources[source_id]["approval_reference"]}
                               for source_id in sorted(definitions)],
        "bounded_reads": read_evidence,
        "relationship": (None if relation is None else {
            "approved": relation["approved"], "source_reference": relation["source_reference"],
            "source_id": association_plan["source_id"], "grain": relation["grain"],
            "keys": relation["keys"], "effectivity": relation["effectivity"]}),
        "baseline_holdout_reviews": [{"source_id": source_id,
                                       "verified": review.get("verified") is True,
                                       "approval_reference": review.get("approval_reference")}
                                      for source_id, review in sorted(holdout_reviews.items())],
        "internal_qualification": "PENDING_INTERNAL",
    }
    validate_envelope(evidence)
    return evidence, current, maps_by_role["history"]


def run_mcp_analysis(adapter: ReadOnlyMCPAdapter, plan_ids: list[str], *,
                     time_window: Mapping[str, Any], top_k: int = 5,
                     anomaly_target_family: Mapping[str, Any] | None = None,
                     cancel: Event | None = None, operation_id: str | None = None) -> dict[str, Any]:
    """Return the validated evidence envelope for an approved synthetic/authorized MCP workflow."""
    evidence, _, _ = _run_mcp_workflow(adapter, plan_ids, time_window=time_window, top_k=top_k,
                                       anomaly_target_family=anomaly_target_family,
                                       cancel=cancel, operation_id=operation_id)
    return evidence


def run_mcp_host_module(adapter: ReadOnlyMCPAdapter, plan_ids: list[str], *,
                        time_window: Mapping[str, Any], top_k: int = 5,
                        anomaly_target_family: Mapping[str, Any] | None = None,
                        cancel: Event | None = None, operation_id: str | None = None) -> dict[str, Any]:
    """Run MCP→C01–C05 and produce P3's versioned typed module contract."""
    evidence, current, history = _run_mcp_workflow(adapter, plan_ids, time_window=time_window, top_k=top_k,
                                                   anomaly_target_family=anomaly_target_family,
                                                   cancel=cancel, operation_id=operation_id)
    current_source = next((source for source in evidence["sources"] if source["id"] == current["source_id"]), None)
    if current_source is None:
        raise MCPDataError("host module result has no source manifest for the current wafer map")
    spatial_map = make_spatial_map(current, current_source)
    analysis = next(item["result"] for item in evidence["artifacts"] if item.get("kind") == "p3_analysis")
    neighbors = analysis.get("similarity", {}).get("neighbors", [])
    historical_spatial_map = None
    if neighbors:
        closest = neighbors[0]
        candidate = next((item for item in history
                          if item.get("wafer_id") == closest.get("wafer_id")
                          and item.get("lot_id") == closest.get("candidate_lot_id")
                          and item.get("product_id") == closest.get("candidate_product_id")
                          and item.get("step_id") == closest.get("candidate_step_id")
                          and item.get("step_instance_id") == closest.get("candidate_step_instance_id")
                          and item.get("measured_at") == closest.get("candidate_measured_at")
                          and item.get("measurement", {}).get("metric") == closest.get("candidate_metric")
                          and item.get("measurement", {}).get("definition_id") == closest.get("candidate_measurement_definition_id")
                          and item.get("sampling_mask_id") == closest.get("candidate_sampling_mask_id")
                          and item.get("source_id") in closest.get("source_ids", [])), None)
        if candidate is not None:
            candidate_source = next((source for source in evidence["sources"]
                                     if source["id"] == candidate["source_id"]), None)
            if candidate_source is not None:
                historical_spatial_map = make_spatial_map(candidate, candidate_source)
    try:
        suite_map = to_suite_spatial_map_v1(spatial_map)
        suite_status = "COMPATIBLE"
        suite_reason = None
    except SpatialContractError as exc:
        suite_map = None
        suite_status = "UNREPRESENTABLE_WITHOUT_LOSS"
        suite_reason = str(exc)
    preview = {
        "status": "SYNTHETIC_ONLY" if evidence["mode"] == "SYNTHETIC_DEMO" else "READ_ONLY_UNQUALIFIED",
        "permission": "Read-only MCP plan approved in this configuration; company authorization remains pending.",
        "semantic_version": current_source["approved_semantic_version"],
        "grain": current_source["grain"],
        "metric": current["measurement"]["metric"],
        "unit": current["measurement"]["unit"],
        "scope": " · ".join(str(current.get(key)) for key in ("wafer_id", "product_id", "step_id") if current.get(key)),
        "time_window": str(current.get("measured_at", "not supplied")),
        "modality": current["measurement"]["modality"],
        "coverage": {"observations": len(spatial_map["observations"]),
                     "numeric_measurements": spatial_map["sampling"]["numeric_measurement_count"],
                     "categorical_measurements": spatial_map["sampling"]["categorical_measurement_count"],
                     "defect_events": spatial_map["sampling"]["defect_event_count"],
                     "explicit_missing_values": spatial_map["sampling"]["explicit_missing_value_count"],
                     **({"expected_sites": spatial_map["sampling"]["expected_site_count"],
                         "coverage_fraction": spatial_map["sampling"]["coverage_fraction"]}
                        if "expected_site_count" in spatial_map["sampling"] else {})},
    }
    validate_envelope(evidence)
    return {
        "contract_version": "p3-reference-module.v2",
        "product_id": "p3",
        "capabilities": list(CAPABILITIES),
        "source_preview": preview,
        "evidence": evidence,
        "spatial_map": spatial_map,
        "historical_spatial_map": historical_spatial_map,
        "suite_compatibility": {"contract_version": "suite-ui-module.v1", "status": suite_status,
                                "reason": suite_reason, "spatial_map": suite_map},
    }
