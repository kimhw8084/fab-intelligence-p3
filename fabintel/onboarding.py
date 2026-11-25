"""Authorization-respecting P3 source discovery and mapping proposals.

This layer consumes metadata already exposed by the configured read-only MCP
adapter. It never reads manufacturing rows, grants permission, or approves a
logical mapping. Source names and column names are display fields only; role
classification uses explicit typed semantic metadata.
"""
from __future__ import annotations

import hashlib
import json
from bisect import bisect_right
from copy import deepcopy
from datetime import datetime
from time import perf_counter
from typing import Any

from fabintel.mcp_adapter import (
    MCPDataError,
    MCPPolicyError,
    ReadOnlyMCPAdapter,
    validate_config_before_start,
)

MAX_DISCOVERY_SOURCES = 20_000
MAX_PROPOSALS = 512
PHYSICAL_UNITS = {"mm", "cm", "m", "um", "µm"}
SUPPORTED_MODALITIES = {"continuous", "sparse_continuous", "die_bin_categorical", "defect_coordinates"}
METADATA_ACCESS = {"PERMITTED", "AUTHORIZED_SOURCE_METADATA", "CONFIGURED_SOURCE_METADATA"}


def canonical_sha256(value: Any) -> str:
    body = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _column_roles(source: dict[str, Any]) -> tuple[dict[str, list[dict[str, Any]]], dict[str, dict[str, Any]]]:
    roles: dict[str, list[dict[str, Any]]] = {}
    by_column: dict[str, dict[str, Any]] = {}
    columns = source.get("column_definitions")
    if not isinstance(columns, list):
        return roles, by_column
    for column in columns:
        if not isinstance(column, dict):
            continue
        role, name = column.get("role"), column.get("name")
        if isinstance(role, str) and role and isinstance(name, str) and name:
            roles.setdefault(role, []).append(column)
            by_column[name] = column
    return roles, by_column


def _time_status(effective_time: Any, as_of: datetime) -> tuple[str, str | None]:
    if not isinstance(effective_time, dict):
        return "UNVERIFIED", "effective-dated semantic definition is unavailable or not machine-readable"
    start, end = effective_time.get("start"), effective_time.get("end")
    try:
        lower = datetime.fromisoformat(str(start))
        upper = datetime.fromisoformat(str(end)) if end is not None else None
    except ValueError:
        return "UNVERIFIED", "effective-time boundaries could not be parsed"
    if lower.tzinfo is None or lower.utcoffset() is None or (upper is not None and (upper.tzinfo is None or upper.utcoffset() is None)):
        return "UNVERIFIED", "effective-time boundaries must include timezones"
    if lower > as_of or (upper is not None and as_of >= upper):
        return "NOT_EFFECTIVE", "semantic definition is outside the requested review time"
    return "EFFECTIVE", None


def _geometry_status(source: dict[str, Any]) -> tuple[str, list[str]]:
    if isinstance(source.get("reticle_profile"), dict):
        return "RETICLE_ONLY", ["reticle geometry cannot establish physical wafer geometry"]
    spatial = source.get("spatial_profile")
    geometry = spatial.get("geometry") if isinstance(spatial, dict) else None
    if not isinstance(geometry, dict):
        quality = source.get("quality_geometry")
        geometry = quality if isinstance(quality, dict) else None
    if not isinstance(geometry, dict):
        if isinstance(source.get("coordinate_reference"), dict):
            return "NEEDS_AUTHORIZED_METADATA_RELATION", ["physical wafer geometry must come from a separately authorized, effective-time join"]
        return "UNVERIFIED", ["verified wafer radius, origin, coordinate system, orientation and units are required"]
    coordinate_unit = geometry.get("coordinate_unit")
    coordinate_system = geometry.get("coordinate_system")
    unit_key = str(coordinate_unit).strip().lower() if isinstance(coordinate_unit, str) else ""
    system_key = str(coordinate_system).strip().lower() if isinstance(coordinate_system, str) else ""
    if "grid" in system_key or unit_key in {"die", "die_index", "grid_index", "index"}:
        return "DIE_GRID_ONLY_NO_PHYSICAL_RADIUS", ["integer die-grid coordinates are not physical wafer coordinates; no wafer map or physical-radius claim until a verified registration is supplied"]
    if "reticle" in system_key or isinstance(source.get("reticle_profile"), dict):
        return "RETICLE_ONLY", ["reticle geometry cannot support wafer-level periodicity without verified wafer registration and alias resolution"]
    radius, radius_unit = geometry.get("radius"), geometry.get("radius_unit", coordinate_unit)
    origin = geometry.get("origin")
    orientation = geometry.get("orientation_deg")
    verified = (spatial.get("coordinates_verified") is True if isinstance(spatial, dict)
                else geometry.get("verified") is True or source.get("coordinates_verified") is True)
    if (not isinstance(radius, (int, float)) or isinstance(radius, bool) or radius <= 0
            or not isinstance(origin, dict)
            or not all(isinstance(origin.get(axis), (int, float)) and not isinstance(origin.get(axis), bool)
                       for axis in ("x", "y"))):
        return "CONTRADICTORY", ["declared physical radius or coordinate origin is invalid"]
    if radius_unit != coordinate_unit:
        return "CONTRADICTORY", ["wafer radius unit conflicts with coordinate unit; no implicit unit conversion is allowed"]
    if (not isinstance(coordinate_system, str) or not coordinate_system
            or unit_key not in PHYSICAL_UNITS or not verified
            or not isinstance(orientation, (int, float)) or isinstance(orientation, bool)
            or not 0 <= orientation < 360):
        return "UNVERIFIED", ["verified physical radius, origin, orientation and declared physical coordinate units are required"]
    return "PHYSICAL_VERIFIED", []


def _measurement_profiles(source: dict[str, Any]) -> list[dict[str, Any]]:
    profiles = source.get("measurement_profiles")
    if isinstance(profiles, list):
        return [item for item in profiles if isinstance(item, dict)]
    profile = source.get("measurement_profile")
    return [profile] if isinstance(profile, dict) else []


def _proposal_body(proposal: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in proposal.items() if key != "proposal_sha256"}


def _proposal(source: dict[str, Any], role: str, profile: dict[str, Any] | None,
              status: str, score: float, geometry: str, gaps: list[str],
              effective_status: str) -> dict[str, Any]:
    profile_id = profile.get("profile_id") if profile else None
    identity = {"source_id": source["source_id"], "semantic_version": source.get("semantic_version"),
                "source_version": source.get("source_version"), "role": role, "profile_id": profile_id}
    return {
        "proposal_id": "P3MAP-" + canonical_sha256(identity)[:20],
        **identity,
        "source_name_display_only": source.get("source_name", ""),
        "source_grain": source.get("grain"),
        "proposal_status": status,
        "score": round(score, 4),
        "geometry_status": geometry,
        "effective_time_status": effective_status,
        "modality": profile.get("modality") if profile else None,
        "measurement_unit": profile.get("unit") if profile else None,
        "measurement_definition_id": profile.get("definition_id") if profile else None,
        "observation_semantics": ({key: deepcopy(profile[key]) for key in (
            "value_role", "null_semantics", "category_role", "category_primitive_types",
            "arithmetic_allowed", "event_semantics", "coordinate_mode") if key in profile}
            if profile else {}),
        "typed_role_columns": {column.get("role"): column.get("name")
                               for column in source.get("column_definitions", [])
                               if isinstance(column, dict) and column.get("role") and column.get("name")},
        "gaps": sorted(set(gaps)),
        "review_required": True,
        "approval_state": "NOT_APPROVED_BY_PROPOSAL",
        "data_read_permission": "NOT_GRANTED_BY_PROPOSAL",
    }


def _classify_source(source: dict[str, Any], as_of: datetime) -> list[dict[str, Any]]:
    if source.get("metadata_access") not in METADATA_ACCESS:
        return []
    source_id = source.get("source_id")
    if not isinstance(source_id, str) or not source_id:
        return []
    roles, by_column = _column_roles(source)
    effective_status, effective_gap = _time_status(source.get("effective_time"), as_of)
    geometry_status, geometry_gaps = _geometry_status(source)
    common_gaps = list(geometry_gaps)
    if effective_gap:
        common_gaps.append(effective_gap)
    if not source.get("semantic_version") or not source.get("source_version"):
        common_gaps.append("immutable semantic and source versions are required before analysis")
    proposals: list[dict[str, Any]] = []

    if isinstance(source.get("reticle_profile"), dict):
        gaps = list(common_gaps)
        if source["reticle_profile"].get("wafer_registration") != "VERIFIED":
            gaps.append("wafer registration and alias-resolvability evidence are absent")
        status = "ABSTAINED" if geometry_status == "CONTRADICTORY" or effective_status == "NOT_EFFECTIVE" else "PROPOSED_REVIEW_REQUIRED"
        proposals.append(_proposal(source, "reticle_geometry", None, status, 0.62,
                                   "RETICLE_ONLY", gaps, effective_status))

    if source.get("grain") == "wafer" and isinstance(source.get("spatial_profile"), dict):
        required_geometry_roles = {"wafer_id", "radius", "origin_x", "origin_y", "orientation_deg"}
        gaps = list(common_gaps)
        if not required_geometry_roles.issubset(roles):
            gaps.append("wafer identity and physical geometry role coverage is incomplete")
        status = "ABSTAINED" if geometry_status == "CONTRADICTORY" or effective_status == "NOT_EFFECTIVE" else "PROPOSED_REVIEW_REQUIRED"
        proposals.append(_proposal(source, "wafer_geometry", None, status, 0.74,
                                   geometry_status, gaps, effective_status))

    if source.get("grain") == "wafer_die":
        required = {"wafer_id", "lot_id", "die_id", "cohort", "feature_at", "outcome_at", "x", "y",
                    "feature_value", "outcome_value", "spatial_block_id", "product_id", "metric",
                    "measurement_definition_id", "layer", "population_signature", "sampling_mask_id"}
        gaps = list(common_gaps)
        missing = sorted(required - set(roles))
        if not (roles.get("unit") or roles.get("measurement_unit")):
            missing.append("unit")
        if missing:
            gaps.append("quality source lacks typed roles: " + ", ".join(missing))
        for key in ("quality_context", "quality_geometry", "quality_holdout", "quality_cohort_selection", "quality_hypothesis_selection"):
            if not isinstance(source.get(key), dict):
                gaps.append(key.replace("_", " ") + " metadata is unavailable")
        status = "ABSTAINED" if geometry_status == "CONTRADICTORY" or effective_status == "NOT_EFFECTIVE" else "PROPOSED_REVIEW_REQUIRED"
        score = 0.72 + 0.03 * (len(required - set(roles)) == 0)
        proposals.append(_proposal(source, "downstream_quality", None, status, score,
                                   geometry_status, gaps, effective_status))

    if source.get("grain") in {"wafer_site", "wafer_observation", "site_observation"}:
        required = {"wafer_id", "lot_id", "measured_at", "product_id", "population_signature",
                    "sampling_mask_id", "site_id", "x", "y"}
        base_gaps = list(common_gaps)
        missing = sorted(required - set(roles))
        if missing:
            base_gaps.append("spatial source lacks typed roles: " + ", ".join(missing))
        spatial_profile = source.get("spatial_profile")
        geometry = spatial_profile.get("geometry") if isinstance(spatial_profile, dict) else None
        coordinate_reference = source.get("coordinate_reference")
        declared_coordinate_unit = (geometry.get("coordinate_unit") if isinstance(geometry, dict)
                                    else coordinate_reference.get("coordinate_unit")
                                    if isinstance(coordinate_reference, dict) else None)
        for axis in ("x", "y"):
            if roles.get(axis) and any(column.get("unit") != declared_coordinate_unit for column in roles[axis]):
                base_gaps.append(f"{axis} column unit conflicts with the declared coordinate unit; conversion is not inferred")
        for profile in _measurement_profiles(source):
            modality = profile.get("modality")
            gaps = list(base_gaps)
            profile_id = profile.get("profile_id")
            unit = profile.get("unit")
            definition_id = profile.get("definition_id")
            if modality not in SUPPORTED_MODALITIES:
                gaps.append("measurement modality is undeclared or unsupported")
                modality_status = "ABSTAINED"
            elif not all(isinstance(item, str) and item for item in (profile_id, unit, definition_id, profile.get("layer"))):
                gaps.append("measurement profile must version its profile, unit, definition and layer")
                modality_status = "PROPOSED_REVIEW_REQUIRED"
            elif modality in {"continuous", "sparse_continuous"}:
                value_column_id = profile.get("value_column_id")
                column = (by_column.get(value_column_id) if value_column_id is not None
                          else roles.get(profile.get("value_role", "value"), [None])[0])
                if (not isinstance(column, dict) or column.get("role") != profile.get("value_role", "value")
                        or column.get("unit") != unit):
                    gaps.append("continuous value column role or unit conflicts with its measurement definition; conversion is not inferred")
                    modality_status = "ABSTAINED"
                else:
                    modality_status = "PROPOSED_REVIEW_REQUIRED"
                if profile.get("null_semantics") != "MISSING_MEASUREMENT":
                    gaps.append("explicit null meaning must be reviewed as missing measurement")
            elif modality == "die_bin_categorical":
                category_role = profile.get("category_role", "category")
                if not roles.get(category_role) and not roles.get("bin"):
                    gaps.append("categorical map lacks an explicit category/bin role")
                    modality_status = "ABSTAINED"
                else:
                    modality_status = "PROPOSED_REVIEW_REQUIRED"
                if profile.get("arithmetic_allowed") is True:
                    gaps.append("categorical arithmetic is explicitly disallowed; contradictory profile requires review")
                    modality_status = "ABSTAINED"
            else:
                event = profile.get("event_semantics")
                if (not isinstance(event, dict) or event.get("row_presence") != "DEFECT_EVENT"
                        or event.get("unlabeled_category_is_event") is not True or event.get("null_is_missing") is not False):
                    gaps.append("defect row presence and unlabeled-event semantics are not independently declared")
                    modality_status = "ABSTAINED"
                else:
                    modality_status = "PROPOSED_REVIEW_REQUIRED"
            status = modality_status
            if geometry_status == "CONTRADICTORY" or effective_status == "NOT_EFFECTIVE":
                status = "ABSTAINED"
            score = 0.83 if status == "PROPOSED_REVIEW_REQUIRED" else 0.55
            proposals.append(_proposal(source, "spatial_measurements", profile, status, score,
                                       geometry_status, gaps, effective_status))
    return proposals


def candidate_relationship_pairs(sources: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Use declared role overlap to rank metadata queries; this never validates a join."""
    eligible = []
    for source in sources:
        if source.get("metadata_access") not in METADATA_ACCESS:
            continue
        roles, _ = _column_roles(source)
        if "wafer_id" in roles:
            eligible.append((source, roles))
    # Index only descriptors that can satisfy one of the two declared join
    # shapes. A catalog full of unrelated wafer identifiers must stay linear.
    spatial: list[int] = []
    geometry: list[int] = []
    site: list[int] = []
    die: list[int] = []
    for index, (source, _) in enumerate(eligible):
        if isinstance(source.get("spatial_profile"), dict):
            spatial.append(index)
        coordinate_reference = source.get("coordinate_reference")
        if (isinstance(coordinate_reference, dict)
                and coordinate_reference.get("geometry_source_required") is True):
            geometry.append(index)
        if source.get("grain") == "wafer_site":
            site.append(index)
        elif source.get("grain") == "wafer_die":
            die.append(index)
    pairs = []
    for left_index, (left, left_roles) in enumerate(eligible):
        candidate_indexes = set()
        coordinate_reference = left.get("coordinate_reference")
        needs_geometry = (isinstance(coordinate_reference, dict)
                          and coordinate_reference.get("geometry_source_required") is True)
        if isinstance(left.get("spatial_profile"), dict):
            candidate_indexes.update(geometry[bisect_right(geometry, left_index):])
        if needs_geometry:
            candidate_indexes.update(spatial[bisect_right(spatial, left_index):])
        if left.get("grain") == "wafer_site":
            candidate_indexes.update(die[bisect_right(die, left_index):])
        if left.get("grain") == "wafer_die":
            candidate_indexes.update(site[bisect_right(site, left_index):])
        for right_index in sorted(candidate_indexes):
            right, right_roles = eligible[right_index]
            shared = sorted(set(left_roles) & set(right_roles))
            geometry_join = ((isinstance(left.get("spatial_profile"), dict)
                              and isinstance(right.get("coordinate_reference"), dict)
                              and right["coordinate_reference"].get("geometry_source_required") is True)
                             or (isinstance(right.get("spatial_profile"), dict)
                                 and isinstance(left.get("coordinate_reference"), dict)
                                 and left["coordinate_reference"].get("geometry_source_required") is True))
            quality_join = ((left.get("grain") == "wafer_site" and right.get("grain") == "wafer_die")
                            or (right.get("grain") == "wafer_site" and left.get("grain") == "wafer_die"))
            if "wafer_id" in shared and (geometry_join or quality_join):
                pairs.append({"source_id": left["source_id"], "target_source_id": right["source_id"],
                              "shared_typed_roles": shared[:8],
                              "state": "CANDIDATE_ROLE_OVERLAP_ONLY_NOT_A_RELATIONSHIP"})
                if len(pairs) >= 200:
                    return pairs
    return pairs


def capture_authorized_metadata(adapter: ReadOnlyMCPAdapter, *,
                                time_window: dict[str, str]) -> dict[str, Any]:
    """Capture only configured metadata through the SDK adapter; performs no row reads."""
    if not isinstance(time_window, dict) or set(time_window) != {"start", "end"}:
        raise ValueError("metadata relationship discovery requires one explicit bounded time window")
    try:
        lower = datetime.fromisoformat(time_window["start"])
        upper = datetime.fromisoformat(time_window["end"])
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError("metadata relationship bounds must be ISO-8601 timestamps") from exc
    if (lower.tzinfo is None or upper.tzinfo is None or lower.utcoffset() is None
            or upper.utcoffset() is None or upper <= lower):
        raise ValueError("metadata relationship bounds must be increasing timezone-aware timestamps")
    start = perf_counter()
    discovery = adapter.discover()
    discovery_ms = (perf_counter() - start) * 1000
    tools = adapter.tool_catalog()
    descriptors = deepcopy(discovery.get("source_catalog", []))
    if not isinstance(descriptors, list) or len(descriptors) > MAX_DISCOVERY_SOURCES:
        raise MCPDataError("onboarding source catalog exceeds the 20,000-descriptor bound")
    by_source = {item.get("source_id"): item for item in descriptors if isinstance(item, dict)}
    semantic_defs: list[dict[str, Any]] = []
    semantics_ms = 0.0
    versions: dict[str, list[str]] = {}
    for source_id, record in adapter.sources.items():
        versions.setdefault(record["semantic_version"], []).append(source_id)
    for version, source_ids in sorted(versions.items()):
        began = perf_counter()
        payload = adapter.semantics(sorted(source_ids), version)
        semantics_ms += (perf_counter() - began) * 1000
        for definition in payload["column_definitions"]:
            descriptor = deepcopy(definition)
            descriptor["metadata_access"] = "AUTHORIZED_SOURCE_METADATA"
            by_source[descriptor["source_id"]] = descriptor
            semantic_defs.append(descriptor)

    relation_candidates = candidate_relationship_pairs(list(by_source.values()))
    configured_ids = set(adapter.sources)
    relation_results = []
    relationship_ms = 0.0
    for pair in relation_candidates:
        if pair["source_id"] not in configured_ids or pair["target_source_id"] not in configured_ids:
            continue
        began = perf_counter()
        try:
            result = adapter.relationships({"source_id": pair["source_id"],
                                            "target_source_id": pair["target_source_id"]}, time_window)
            relation_results.append({**pair, **result, "discovery_state": "AUTHORITY_REPORTED_REVIEW_REQUIRED"})
        except (MCPPolicyError, MCPDataError, ValueError):
            relation_results.append({**pair, "discovery_state": "UNAVAILABLE_OR_DENIED",
                                     "approved": False, "review_required": True})
        relationship_ms += (perf_counter() - began) * 1000
    sources = sorted(by_source.values(), key=lambda item: str(item.get("source_id", "")))
    return {
        "schema": "p3-authorized-metadata-capture/v1",
        "capture_status": "METADATA_ONLY_REVIEW_REQUIRED",
        "adapter_access_mode": adapter.access_mode,
        "server": deepcopy(discovery.get("server_info", {})),
        "protocol_version": discovery.get("protocol_version"),
        "relationship_time_window": deepcopy(time_window),
        "source_catalog_version": discovery.get("source_catalog_version"),
        "source_catalog_count": discovery.get("source_catalog_count",
                                               discovery.get("discovered_source_count", len(sources))),
        "tool_catalog": tools,
        "source_descriptors": sources,
        "authority_relationships": relation_results,
        "configured_source_scopes": [
            {"scope_type": ("metadata_only" if adapter.access_mode == "metadata_only" else "analysis_source"),
             "source_id": source, "semantic_version": record["semantic_version"],
             "source_version": record.get("source_version"),
             "approval_reference": record.get("approval_reference")}
            for source, record in sorted(adapter.sources.items())
        ],
        "configured_operation_scopes": [
            {"logical_operation": name, "tool_name": binding.get("tool_name"),
             "tool_definition_sha256": binding.get("approval", {}).get("tool_definition_sha256"),
             "approval_reference": binding.get("approval", {}).get("reference")}
            for name, binding in sorted(adapter.bindings.items())
        ],
        "reads_performed": 0,
        "data_read_permission": "NOT_GRANTED_BY_METADATA_DISCOVERY",
        "timing_ms": {"mcp_discovery": round(discovery_ms, 3),
                      "semantics": round(semantics_ms, 3),
                      "relationship_metadata": round(relationship_ms, 3)},
    }


def propose_source_mappings(capture: dict[str, Any], *, as_of: str) -> dict[str, Any]:
    if not isinstance(capture, dict) or capture.get("schema") != "p3-authorized-metadata-capture/v1":
        raise ValueError("unsupported P3 metadata capture")
    descriptors = capture.get("source_descriptors")
    if not isinstance(descriptors, list) or len(descriptors) > MAX_DISCOVERY_SOURCES:
        raise MCPDataError("P3 onboarding accepts at most 20,000 source descriptors")
    parsed_as_of = datetime.fromisoformat(as_of)
    if parsed_as_of.tzinfo is None or parsed_as_of.utcoffset() is None:
        raise ValueError("mapping review time must be timezone-aware")
    ids = [item.get("source_id") if isinstance(item, dict) else None for item in descriptors]
    if any(not isinstance(item, str) or not item for item in ids) or len(ids) != len(set(ids)):
        raise MCPDataError("P3 source descriptors require unique nonempty source IDs")
    proposals = []
    for source in descriptors:
        proposals.extend(_classify_source(source, parsed_as_of))
        if len(proposals) > MAX_PROPOSALS:
            raise MCPDataError("P3 source-role candidate count exceeds the 512-proposal bound")
    proposals.sort(key=lambda item: (-item["score"], item["proposal_id"]))
    configured_ids = {item.get("source_id") for item in capture.get("configured_source_scopes", [])}
    approved_relationships = []
    for edge in capture.get("authority_relationships", []):
        if not isinstance(edge, dict):
            continue
        good = (edge.get("approved") is True and set(edge.get("keys", [])) == {"wafer_id", "die_id"}
                and edge.get("cardinality") == "one_to_many" and edge.get("grain") == "wafer_die"
                and bool(edge.get("effectivity")) and edge.get("coordinate_mapping_verified") is True
                and edge.get("spatial_block_method") == "predeclared_block_fixed_effects_v1")
        approved_relationships.append({
            "relationship_proposal_id": "P3REL-" + canonical_sha256({
                "source_id": edge.get("source_id"), "target_source_id": edge.get("target_source_id"),
                "keys": edge.get("keys")})[:20],
            "source_id": edge.get("source_id"), "target_source_id": edge.get("target_source_id"),
            "authority_reported_approved": edge.get("approved") is True,
            "proposal_status": "AUTHORITY_REPORTED_REVIEW_REQUIRED" if good else "ABSTAIN_INVALID_OR_INCOMPLETE",
            "keys": edge.get("keys", []), "cardinality": edge.get("cardinality"),
            "grain": edge.get("grain"), "effectivity": edge.get("effectivity"),
            "coordinate_mapping_verified": edge.get("coordinate_mapping_verified") is True,
            "spatial_block_method": edge.get("spatial_block_method"),
            "approval_state": "NOT_APPROVED_BY_PROPOSAL",
        })
    role_pairs = candidate_relationship_pairs(descriptors)
    relationship_candidates = []
    seen_pairs = set()
    for pair in role_pairs:
        key = (pair["source_id"], pair["target_source_id"])
        if key in seen_pairs:
            continue
        seen_pairs.add(key)
        relationship_candidates.append({**pair,
            "source_ids_configured_for_metadata_review": set(key).issubset(configured_ids),
            "proposal_status": "CANDIDATE_ONLY_REQUIRES_AUTHORITY_RELATIONSHIP_REVIEW"})
    plan_requirements = []
    for proposal in proposals:
        if proposal["proposal_status"] != "PROPOSED_REVIEW_REQUIRED" or proposal["source_id"] not in configured_ids:
            continue
        roles = ({"spatial_measurements": ["current", "previous", "baseline", "history"],
                  "downstream_quality": ["association"]}.get(proposal["role"], []))
        for analysis_role in roles:
            plan_requirements.append({"analysis_role": analysis_role, "source_id": proposal["source_id"],
                                      "semantic_version": proposal.get("semantic_version"),
                                      "time_window": deepcopy(capture.get("relationship_time_window")),
                                      "permission_scope": "READ_ONLY_SOURCE_SCOPED",
                                      "time_bound_required": True, "maximum_rows": 1000,
                                      "maximum_bytes": 4 * 1024 * 1024, "maximum_seconds": 30,
                                      "top_k": 5 if analysis_role == "history" else None,
                                      "raw_query_text": None,
                                      "approved": False, "approval_reference": None,
                                      "state": "DRAFT_REQUIRES_SERVER_PLAN_AND_AUTHORIZED_REVIEW"})
    report = {
        "schema": "p3-source-mapping-proposals/v1",
        "created_as_of": as_of,
        "metadata_capture_sha256": canonical_sha256(capture),
        "scope": "Metadata-only candidate ranking. Names are display-only. No source, relationship, query plan, permission or data read is approved.",
        "catalog": {"discovered_descriptors": capture.get("source_catalog_count", len(descriptors)),
                    "descriptors_received": len(descriptors),
                    "restricted_metadata_descriptors": sum(item.get("metadata_access") not in METADATA_ACCESS for item in descriptors)},
        "tool_review": [{"name": item["name"], "tool_definition_sha256": item["tool_definition_sha256"],
                         "read_only_hint": item["read_only_hint"], "destructive_hint": item["destructive_hint"],
                         "invocation_authorized": False, "review_required": True}
                        for item in capture.get("tool_catalog", [])],
        "source_proposals": proposals,
        "relationship_proposals": approved_relationships + relationship_candidates,
        "bounded_plan_requirements": plan_requirements,
        "human_review_decisions_required": len(proposals) + len(approved_relationships) + len(relationship_candidates),
        "automatic_approvals": 0,
        "reads_performed": capture.get("reads_performed", 0),
    }
    report["proposal_sha256"] = canonical_sha256(_proposal_body(report))
    return report


def build_reviewed_config(config: dict[str, Any], proposal: dict[str, Any], review: dict[str, Any]) -> dict[str, Any]:
    """Bind explicit review records to an already source/plan-approved adapter config."""
    validate_config_before_start(config)
    if (proposal.get("schema") != "p3-source-mapping-proposals/v1"
            or review.get("schema") != "p3-onboarding-review/v1"
            or review.get("proposal_sha256") != proposal.get("proposal_sha256")
            or proposal.get("proposal_sha256") != canonical_sha256(_proposal_body(proposal))):
        raise MCPPolicyError("review must target the exact current P3 mapping proposal digest")
    reviewer = review.get("reviewer_id")
    authority = review.get("authority_reference")
    if not isinstance(reviewer, str) or not reviewer.strip() or not isinstance(authority, str) or not authority.strip():
        raise MCPPolicyError("mapping review requires an identified reviewer and authority reference")
    selected = review.get("selected_proposal_ids")
    relation_id = review.get("selected_relationship_proposal_id")
    if not isinstance(selected, list) or len(selected) != len(set(selected)) or len(selected) < 2:
        raise MCPPolicyError("review must explicitly select the spatial and downstream quality proposals")
    source_proposals = {item["proposal_id"]: item for item in proposal["source_proposals"]}
    chosen = []
    for proposal_id in selected:
        item = source_proposals.get(proposal_id)
        if (not item or item.get("proposal_status") != "PROPOSED_REVIEW_REQUIRED"
                or not item.get("review_required") or item.get("geometry_status") in {"CONTRADICTORY", "UNVERIFIED"}
                or item.get("effective_time_status") != "EFFECTIVE"):
            raise MCPPolicyError("selected source proposal is incomplete, refused, or not effective")
        chosen.append(item)
    chosen_map = [item for item in chosen if item["role"] == "spatial_measurements"]
    chosen_quality = [item for item in chosen if item["role"] == "downstream_quality"]
    if len(chosen_map) != 1 or len(chosen_quality) != 1:
        raise MCPPolicyError("review must choose exactly one spatial source and one downstream quality source")
    if chosen_map[0].get("geometry_status") != "PHYSICAL_VERIFIED" or chosen_quality[0].get("geometry_status") != "PHYSICAL_VERIFIED":
        raise MCPPolicyError("the selected map and quality source both require verified physical wafer geometry")
    if chosen_map[0].get("gaps") or chosen_quality[0].get("gaps"):
        raise MCPPolicyError("selected sources retain unresolved typed, modality, effectivity, geometry or unit gaps")
    source_decisions = review.get("source_decisions")
    decision_by_id = ({item.get("proposal_id"): item for item in source_decisions if isinstance(item, dict)}
                      if isinstance(source_decisions, list) else {})
    if any(decision_by_id.get(item["proposal_id"], {}).get("decision") != "APPROVE"
           or not decision_by_id.get(item["proposal_id"], {}).get("approval_reference") for item in chosen):
        raise MCPPolicyError("each selected source mapping requires a separate authorized review reference")
    approved_ids = {item["source_id"] for item in config["approved_sources"]}
    if any(item["source_id"] not in approved_ids for item in chosen):
        raise MCPPolicyError("mapping review cannot grant source permission; selected source lacks explicit adapter approval")
    relationship = next((item for item in proposal["relationship_proposals"]
                         if item.get("relationship_proposal_id") == relation_id), None)
    if (not relationship or relationship.get("proposal_status") != "AUTHORITY_REPORTED_REVIEW_REQUIRED"
            or relationship.get("source_id") != chosen_map[0]["source_id"]
            or relationship.get("target_source_id") != chosen_quality[0]["source_id"]):
        raise MCPPolicyError("review requires a matching authority-reported wafer/die relationship")
    relation_decisions = review.get("relationship_decisions")
    relation_decision = (next((item for item in relation_decisions if isinstance(item, dict)
                               and item.get("relationship_proposal_id") == relation_id), None)
                         if isinstance(relation_decisions, list) else None)
    if (not relation_decision or relation_decision.get("decision") != "APPROVE"
            or not relation_decision.get("approval_reference")):
        raise MCPPolicyError("wafer/die relationship requires its own authorized review reference")
    roles = {plan["plan"].get("analysis_role"): plan["plan"].get("source_id")
             for plan in config["approved_plans"] if isinstance(plan.get("plan"), dict)}
    expected = {"current": chosen_map[0]["source_id"], "previous": chosen_map[0]["source_id"],
                "baseline": chosen_map[0]["source_id"], "history": chosen_map[0]["source_id"],
                "association": chosen_quality[0]["source_id"]}
    if any(roles.get(role) != source_id for role, source_id in expected.items()):
        raise MCPPolicyError("approved bounded plans do not match the reviewed P3 source-role mapping")
    reviewed = deepcopy(config)
    reviewed["onboarding_review"] = {
        "schema": "p3-reviewed-source-mapping/v1", "proposal_sha256": proposal["proposal_sha256"],
        "reviewer_id": reviewer, "authority_reference": authority,
        "selected_proposal_ids": selected, "selected_relationship_proposal_id": relation_id,
        "source_approval_references": {item["proposal_id"]: decision_by_id[item["proposal_id"]]["approval_reference"]
                                       for item in chosen},
        "relationship_approval_reference": relation_decision["approval_reference"],
        "source_mapping_status": "SYNTHETIC_REVIEW_ONLY" if review.get("synthetic_simulation") is True else "SITE_REVIEW_RECORDED_NOT_INTERNALLY_QUALIFIED",
        "automatic_approval": False,
    }
    validate_config_before_start(reviewed)
    return reviewed
