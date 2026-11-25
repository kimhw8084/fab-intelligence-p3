"""Protocol-compatible synthetic MCP server used by external client tests.

Run as ``python -m qualification.synthetic_mcp_peer --protocol dual``. The process
speaks newline-delimited JSON-RPC on stdio and never reads company data.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
import threading
import time
from datetime import UTC, datetime
from pathlib import Path

MAX_LINE = 4 * 1024 * 1024
PROTOCOLS = ["2026-07-28", "2025-11-25"]
SOURCES = {"MOCK_MAP", "MOCK_QUALITY"}
_write_lock = threading.Lock()
_state_lock = threading.Lock()
_cancel: dict[str | int, threading.Event] = {}
_cancelled: list[str | int] = []
_calls: list[dict] = []
_read_audits: dict[str, dict] = {}
_legacy_initialized = False
_ALTERNATE_FIELD_NAMES = {
    name: f"field_{index:02d}_{hashlib.sha256(name.encode()).hexdigest()[:6]}"
    for index, name in enumerate(("source", "wafer_key", "lot_key", "measurement_timestamp", "product",
        "population_id", "sample_mask", "operation_step", "step_instance", "measurement_site",
        "expected_site_count", "x_mm", "y_mm", "thickness_nm", "die_bin", "defect_label",
        "measurement_unit", "std_uncertainty", "die_key", "holdout_cohort", "feature_timestamp",
        "outcome_timestamp", "spatial_feature_value", "outcome_value", "spatial_block",
        "metric_name", "measurement_definition", "process_layer"))
}


def _field_name(name: str, scenario: str) -> str:
    return _ALTERNATE_FIELD_NAMES.get(name, "field_" + hashlib.sha256(name.encode()).hexdigest()[:12]) \
        if scenario == "onboarding-schema-alt" else name


def _integration_fixture(scenario: str = "normal") -> dict:
    if scenario == "engineer-challenge":
        from qualification.engineer_challenge import build
        return build()
    if scenario == "c01-dense-challenge":
        from qualification.engineer_challenge import build, build_dense_c01_challenge
        fixture = build()
        dense = build_dense_c01_challenge(73000, plant_local_shift=True,
                                          random_missing_fraction=0.1, sites_per_ring=64)
        # Keep the multi-step, baseline, history and outcome populations from
        # the broader challenge while replacing only the current typed wafer map.
        for key in ("points", "geometry", "sampling_mask_id", "expected_site_count", "source_id"):
            fixture[key] = dense[key]
        return fixture
    path = Path(__file__).resolve().parents[1] / "fixtures" / "p3_integrated_synthetic.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _typed_modality_fixture(scenario: str) -> dict:
    fixture = _integration_fixture(scenario)
    if scenario == "typed-categorical":
        fixture["measurement"] = {"metric": "die_bin", "unit": "category", "modality": "die_bin_categorical",
                                  "definition_id": "SYN-BIN-1", "layer": "L1"}
        for point, category in zip(fixture["points"], ("PASS", 2, "FAIL", "PASS", 3)):
            point.pop("value", None)
            point["category"] = category
    elif scenario == "explicit-missing":
        fixture["points"][1]["value"] = None
    elif scenario == "typed-defect":
        fixture["measurement"] = {"metric": "defect_event", "unit": "count", "modality": "defect_coordinates",
                                  "definition_id": "SYN-DEFECT-1", "layer": "L1"}
        for point in fixture["points"]:
            point.pop("value", None)
        fixture["points"][0]["category"] = "BRIDGE"
        fixture["points"][1]["bin"] = 7
    return fixture


def _map_rows(maps: list[dict]) -> list[dict]:
    rows = []
    for data in maps:
        for point in data.get("points", []):
            rows.append({"source": "MOCK_MAP", "wafer_key": data["wafer_id"],
                         "lot_key": data["lot_id"], "measurement_timestamp": data["measured_at"],
                         "product": data["product_id"], "population_id": data["population_signature"],
                         "sample_mask": data["sampling_mask_id"], "operation_step": data.get("step_id"),
                         "step_instance": data.get("step_instance_id"), "measurement_site": point["site_id"],
                         "expected_site_count": data.get("expected_site_count"),
                         "x_mm": point["x"], "y_mm": point["y"], "thickness_nm": point.get("value"),
                         "die_bin": point.get("category", point.get("bin")),
                         "defect_label": point.get("category", point.get("bin")),
                         "measurement_unit": data["measurement"]["unit"],
                         "std_uncertainty": point.get("standard_uncertainty")})
    return rows


def _quality_rows(scenario: str = "normal") -> list[dict]:
    association = _integration_fixture(scenario)["quality_association"]
    result = []
    for row in association["observations"]:
        result.append({"source": "MOCK_QUALITY", "wafer_key": row["wafer_id"], "lot_key": row["lot_id"],
                       "die_key": row["die_id"], "holdout_cohort": row["cohort"],
                       "feature_timestamp": row["feature_at"], "outcome_timestamp": row["outcome_at"],
                       "x_mm": row["x"], "y_mm": row["y"], "spatial_feature_value": row["feature_value"],
                       "outcome_value": row["outcome_value"], "spatial_block": row["spatial_block_id"],
                       "product": row["product_id"], "metric_name": row["metric"],
                       "measurement_definition": row["measurement_definition_id"],
                       "measurement_unit": row["unit"], "process_layer": row["layer"],
                       "population_id": row["population_signature"], "sample_mask": row["sampling_mask_id"]})
    return result


def _modern(message: dict) -> bool:
    params = message.get("params", {})
    meta = params.get("_meta", {}) if isinstance(params, dict) else {}
    return isinstance(meta, dict) and meta.get("io.modelcontextprotocol/protocolVersion") == PROTOCOLS[0]


def _response(request_id, result=None, error=None):
    message = {"jsonrpc": "2.0", "id": request_id}
    message["error" if error is not None else "result"] = error if error is not None else result
    encoded = json.dumps(message, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8") + b"\n"
    with _write_lock:
        sys.stdout.buffer.write(encoded)
        sys.stdout.buffer.flush()


def _tool_descriptors():
    common = {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False}
    return [
        {"name": "fab_discover", "description": "Synthetic read-only capability discovery", "inputSchema": {"type": "object", "additionalProperties": False}, "annotations": common},
        {"name": "fab_semantics", "description": "Synthetic approved source definitions", "inputSchema": {"type": "object", "properties": {"source_ids": {"type": "array", "items": {"type": "string"}}, "semantic_version": {"type": "string"}}, "required": ["source_ids", "semantic_version"], "additionalProperties": False}, "annotations": common},
        {"name": "fab_relationships", "description": "Synthetic approved wafer/die relationship", "inputSchema": {"type": "object", "properties": {"typed_entity_ids": {"type": "object"}, "time_window": {"type": "object"}}, "required": ["typed_entity_ids", "time_window"], "additionalProperties": False}, "annotations": common},
        {"name": "fab_read_bounded", "description": "Synthetic bounded read of approved mock rows", "inputSchema": {"type": "object", "properties": {"approved_plan": {"type": "object"}, "permission_context": {"type": "object"}, "limits": {"type": "object"}, "operation_id": {"type": "string"}}, "required": ["approved_plan", "permission_context", "limits", "operation_id"], "additionalProperties": False}, "annotations": common},
        {"name": "fab_audit", "description": "Synthetic redacted source audit trace", "inputSchema": {"type": "object", "properties": {"operation_id": {"type": "string"}}, "required": ["operation_id"], "additionalProperties": False}, "annotations": common},
        {"name": "mock_wait_for_cancel", "description": "Test-only cancellable operation", "inputSchema": {"type": "object", "additionalProperties": False}, "annotations": common},
        {"name": "unsafe_recipe_write", "description": "Synthetic write tool that must never be invoked", "inputSchema": {"type": "object"}, "annotations": {"readOnlyHint": False, "destructiveHint": True}},
    ]


def _tool_result(name: str, args: dict, request_id, cancel_event: threading.Event, scenario: str) -> dict:
    if name == "fab_discover":
        semantic_versions = ["MOCK-SEM-OLD"] if scenario == "stale-semantic-inventory" else ["MOCK-SEM-1"]
        result = {"catalog_version": "MOCK-CATALOG-1", "mode": "SYNTHETIC_DEMO",
                  "tool_versions": {tool["name"]: "mock/1" for tool in _tool_descriptors()},
                  "semantic_versions": semantic_versions, "limits": {"max_rows": 1000, "max_bytes": 4194304, "max_seconds": 8},
                  "auth_scopes": ["read_only"], "audit_support": True,
                  "source_ids": sorted(SOURCES), "read_only": True}
        if scenario in {"onboarding-catalog", "onboarding-invalid-relationship", "onboarding-schema-alt"}:
            from qualification.spatial_catalog_fixture import (
                build_catalog,
                obfuscate_catalog_fields,
            )
            source_catalog = build_catalog(13_000)
            if scenario == "onboarding-schema-alt":
                source_catalog = obfuscate_catalog_fields(source_catalog)
            result["source_catalog"] = source_catalog
            result["source_catalog_version"] = "SYN-SPATIAL-CATALOG-1"
            result["source_ids"] = sorted(SOURCES | {row["source_id"] for row in source_catalog})
    elif name == "fab_semantics":
        ids = args.get("source_ids")
        if not isinstance(ids, list) or not ids or any(source not in SOURCES for source in ids):
            return {"isError": True, "content": [{"type": "text", "text": "permission denied: source is not approved"}]}
        if args.get("semantic_version") != "MOCK-SEM-1":
            return {"isError": True, "content": [{"type": "text", "text": "unsupported semantic version"}]}
        fixture = _typed_modality_fixture(scenario)
        map_roles = [("source", "source_id"), ("wafer_key", "wafer_id"), ("lot_key", "lot_id"),
                     ("measurement_timestamp", "measured_at"), ("product", "product_id"),
                     ("population_id", "population_signature"), ("sample_mask", "sampling_mask_id"),
                     ("operation_step", "step_id"), ("step_instance", "step_instance_id"),
                     ("measurement_site", "site_id"), ("expected_site_count", "expected_site_count"),
                     ("x_mm", "x"), ("y_mm", "y")]
        if fixture["measurement"]["modality"] in {"continuous", "sparse_continuous"}:
            map_roles.extend([("thickness_nm", "value"), ("measurement_unit", "measurement_unit"),
                              ("std_uncertainty", "standard_uncertainty")])
        elif fixture["measurement"]["modality"] == "die_bin_categorical":
            map_roles.append(("die_bin", "category"))
        else:
            map_roles.append(("defect_label", "category"))
        quality_roles = [("source", "source_id"), ("wafer_key", "wafer_id"), ("lot_key", "lot_id"),
                         ("die_key", "die_id"), ("holdout_cohort", "cohort"),
                         ("feature_timestamp", "feature_at"), ("outcome_timestamp", "outcome_at"),
                         ("x_mm", "x"), ("y_mm", "y"), ("spatial_feature_value", "feature_value"),
                         ("outcome_value", "outcome_value"), ("spatial_block", "spatial_block_id"),
                         ("product", "product_id"), ("metric_name", "metric"),
                         ("measurement_definition", "measurement_definition_id"),
                         ("measurement_unit", "measurement_unit"), ("process_layer", "layer"),
                         ("population_id", "population_signature"), ("sample_mask", "sampling_mask_id")]
        definitions = []
        for source in ids:
            semantic_version = "MOCK-SEM-OLD" if scenario == "stale-semantics" else "MOCK-SEM-1"
            source_version = "MOCK-SNAPSHOT-" + source.removeprefix("MOCK_")
            if source == "MOCK_MAP":
                spatial_profile = {"coordinates_verified": fixture["coordinates_verified"], "geometry": copy.deepcopy(fixture["geometry"])}
                if scenario == "bad-geometry":
                    spatial_profile["geometry"]["radius"] = 0.5
                measurement_profile = copy.deepcopy(fixture["measurement"])
                if scenario in {"onboarding-catalog", "onboarding-invalid-relationship", "onboarding-schema-alt"}:
                    measurement_profile.update({"profile_id": "MOCK-METROLOGY-PROFILE",
                                                "value_role": "value",
                                                "null_semantics": "MISSING_MEASUREMENT"})
                effective_time = ({"start": "2020-01-01T00:00:00Z", "end": None,
                                   "definition_id": "MOCK-MEASUREMENT-DEFINITION"}
                                  if scenario in {"onboarding-catalog", "onboarding-invalid-relationship", "onboarding-schema-alt"} else "synthetic-measurement-time-v1")
                if scenario == "onboarding-schema-alt":
                    map_roles = [(_field_name(field, scenario), role) for field, role in map_roles]
                definitions.append({"source_id": source, "approved": True, "semantic_version": semantic_version,
                    "source_version": source_version, "grain": "wafer_site", "units": [fixture["measurement"]["unit"]],
                    "effective_time": effective_time,
                    "column_definitions": [{"name": field, "role": role, "unit": "mm" if role in ("x", "y") else fixture["measurement"]["unit"] if role in ("value", "measurement_unit", "standard_uncertainty") else None} for field, role in map_roles],
                    "spatial_profile": spatial_profile,
                    "measurement_profile": measurement_profile,
                    "baseline_holdout": {"verified": fixture["baseline_holdout_verified"], "approval_reference": "SYN-HOLDOUT-DESIGN-1"}})
            else:
                association = fixture["quality_association"]
                effective_time = ({"start": "2020-01-01T00:00:00Z", "end": None,
                                   "definition_id": "MOCK-QUALITY-DEFINITION"}
                                  if scenario in {"onboarding-catalog", "onboarding-invalid-relationship", "onboarding-schema-alt"} else "synthetic-feature-outcome-time-v1")
                if scenario == "onboarding-schema-alt":
                    quality_roles = [(_field_name(field, scenario), role) for field, role in quality_roles]
                definitions.append({"source_id": source, "approved": True, "semantic_version": semantic_version,
                    "source_version": source_version,
                    "grain": "wafer_die", "units": ["nm", "count"],
                    "effective_time": effective_time,
                    "column_definitions": [{"name": field, "role": role, "unit": "mm" if role in ("x", "y") else None} for field, role in quality_roles],
                    "quality_context": association["context"], "quality_geometry": association["geometry"],
                    "quality_holdout": association["holdout"],
                    "quality_cohort_selection": copy.deepcopy(association.get("cohort_selection")),
                    "quality_hypothesis_selection": association["hypothesis_selection"]})
                if scenario == "missing-cohort-selection":
                    definitions[-1].pop("quality_cohort_selection")
                elif scenario == "unsupported-cohort-selection":
                    definitions[-1]["quality_cohort_selection"].update({
                        "sampling_design": "OUTCOME_INFORMED_TOP_ASSOCIATION",
                        "selection_blind_to_feature_and_outcome": False,
                    })
                if scenario == "missing-hypothesis-selection":
                    definitions[-1].pop("quality_hypothesis_selection")
        result = {"column_definitions": definitions}
    elif name == "fab_relationships":
        ids = args.get("typed_entity_ids", {})
        valid = isinstance(ids, dict) and ids.get("source_id") == "MOCK_MAP" and ids.get("target_source_id") == "MOCK_QUALITY"
        invalid_relationship = scenario in {"invalid-relationship", "onboarding-invalid-relationship"}
        keys = ["wafer_id", "site_id"] if invalid_relationship and valid else ["wafer_id", "die_id"] if valid else []
        result = {"approved": valid, "keys": keys,
                  "cardinality": "one_to_many" if valid else "unknown", "grain": "wafer_die" if valid else None,
                  "effectivity": "synthetic-event-time-v1", "source_reference": "MOCK-REL-1" if valid else None,
                  "coordinate_mapping_verified": valid,
                  "spatial_block_method": "predeclared_block_fixed_effects_v1" if valid else None}
    elif name == "fab_read_bounded":
        plan = args.get("approved_plan", {})
        permission = args.get("permission_context", {})
        limits = args.get("limits", {})
        source = plan.get("source_id") if isinstance(plan, dict) else None
        limit = limits.get("max_rows") if isinstance(limits, dict) else None
        if permission.get("scope") != "read_only" or source not in SOURCES or not plan.get("plan_id"):
            return {"isError": True, "content": [{"type": "text", "text": "permission denied"}]}
        if scenario == "read-denied":
            return {"isError": True, "content": [{"type": "text", "text": "synthetic source grant denied"}]}
        if type(limit) is not int or not 1 <= limit <= 1000:
            return {"isError": True, "content": [{"type": "text", "text": "invalid bounded read limit"}]}
        delay_ms = plan.get("test_delay_ms", 0)
        if type(delay_ms) is int and 0 < delay_ms <= 5000 and cancel_event.wait(delay_ms / 1000):
            with _state_lock:
                _cancelled.append(request_id)
            return {"cancelled": True}
        analysis_role = plan.get("analysis_role")
        fixture = _typed_modality_fixture(scenario)
        if analysis_role == "current" and source == "MOCK_MAP":
            rows = _map_rows([fixture])
            if scenario == "missing-center":
                rows = [row for row in rows if row["measurement_site"] != "center"]
            elif scenario == "missing-edge":
                partial = copy.deepcopy(fixture)
                partial["points"] = []
                for index, value in enumerate((10.0, 10.5, 11.0, 11.5)):
                    angle = index * 3.141592653589793 / 2
                    partial["points"].append({"site_id": f"inner-{index}", "x": 0.25 * __import__("math").cos(angle),
                        "y": 0.25 * __import__("math").sin(angle), "value": value})
                rows = _map_rows([partial])
        elif analysis_role == "previous" and source == "MOCK_MAP":
            rows = _map_rows(fixture["previous_steps"])
        elif analysis_role == "baseline" and source == "MOCK_MAP":
            rows = _map_rows(fixture["baseline_population"])
        elif analysis_role == "history" and source == "MOCK_MAP":
            rows = _map_rows(fixture["history"])
        elif analysis_role == "association" and source == "MOCK_QUALITY":
            rows = _quality_rows(scenario)
        else:
            rows = [{"wafer_id": "MOCK-W-01", "lot_id": "MOCK-L-01", "site_id": "center", "x": 0.0, "y": 0.0,
                     "value": 10.0, "unit": "nm", "measured_at": "2026-01-01T00:00:00Z"}]
        if scenario == "onboarding-schema-alt":
            rows = [{_field_name(field, scenario): value for field, value in row.items()} for row in rows]
        if plan.get("test_case") == "wrong_measurement_unit" and rows:
            rows[0]["measurement_unit"] = "um"
        if scenario == "oversized-read" and rows:
            # Keep this adversarial peer case above the raised 1,000-row cap
            # used by the larger engineer-challenge population.
            rows = (rows * (1001 // len(rows) + 1))[:1001]
        operation_id = args.get("operation_id")
        source_version = "MOCK-SNAPSHOT-DRIFTED" if scenario == "source-version-drift" else "MOCK-SNAPSHOT-" + source.removeprefix("MOCK_")
        audited_version = "MOCK-SNAPSHOT-DRIFTED" if scenario == "audit-version-drift" else source_version
        plan_hash = hashlib.sha256(json.dumps(plan, ensure_ascii=False, sort_keys=True,
                                              separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()
        audit_id = "MOCK-AUDIT-" + hashlib.sha256(str(operation_id).encode("utf-8")).hexdigest()[:12]
        with _state_lock:
            _read_audits[operation_id] = {"operation_id": operation_id, "permission_scope": "read_only",
                "sources": [source], "timestamps": {"completed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z")},
                "source_versions": {source: audited_version},
                "query_hash": ("0" * 64 if plan.get("test_case") == "wrong_audit_hash" else plan_hash),
                "audit_id": audit_id}
        result = {"typed_rows": rows if scenario == "oversized-read" else rows[:limit], "audit_id": audit_id,
                  "source_versions": {source: source_version}, "truncation": False if scenario == "oversized-read" else len(rows) > limit}
    elif name == "fab_audit":
        with _state_lock:
            cancelled_count = len(_cancelled)
            recorded = dict(_read_audits.get(args.get("operation_id"), {}))
        result = recorded or {"operation_id": args.get("operation_id"), "permission_scope": "read_only",
                  "sources": ["MOCK_MAP"], "timestamps": {"completed_at": "2026-01-01T00:00:00Z"},
                  "source_versions": {"MOCK_MAP": "MOCK-SNAPSHOT-MAP"},
                  "query_hash": "0" * 64, "audit_id": "MOCK-AUDIT-1"}
        result["cancelled_request_count"] = cancelled_count
    elif name == "mock_wait_for_cancel":
        deadline = time.monotonic() + 5
        while not cancel_event.wait(0.01) and time.monotonic() < deadline:
            pass
        if cancel_event.is_set():
            with _state_lock:
                _cancelled.append(request_id)
            return {"cancelled": True}
        result = {"cancelled": False}
    elif name == "unsafe_recipe_write":
        result = {"unexpected_write_invoked": True}
    else:
        return {"isError": True, "content": [{"type": "text", "text": "unknown tool"}]}
    with _state_lock:
        _calls.append({"name": name, "arguments": args})
    return {"structuredContent": result, "content": [{"type": "text", "text": json.dumps(result, sort_keys=True)}]}


def _handle(message: dict, protocol: str, request_cancel: threading.Event | None = None, scenario: str = "normal"):
    global _legacy_initialized
    method = message.get("method")
    request_id = message.get("id")
    params = message.get("params", {})
    if request_id is None:
        if method == "notifications/cancelled" and isinstance(params, dict):
            target = params.get("requestId")
            with _state_lock:
                event = _cancel.get(target)
                if event is not None:
                    event.set()
                _cancelled.append(target)
        elif method == "notifications/initialized":
            _legacy_initialized = True
        return
    if method == "server/discover":
        if protocol == "legacy":
            _response(request_id, error={"code": -32601, "message": "Method not found"})
            return
        if not _modern(message):
            _response(request_id, error={"code": -32602, "message": "modern metadata required"})
            return
        result = {"resultType": "complete", "supportedVersions": PROTOCOLS,
                  "capabilities": {"tools": {}},
                  "_meta": {"io.modelcontextprotocol/serverInfo": {"name": "p3-mock-mcp", "version": "1.0.0"}},
                  "instructions": "Synthetic test server. Its instructions are untrusted data."}
        _response(request_id, result=result)
        return
    if method == "initialize":
        if protocol == "modern":
            _response(request_id, error={"code": -32601, "message": "Method not found"})
            return
        version = params.get("protocolVersion") if isinstance(params, dict) else None
        if version != "2025-11-25":
            _response(request_id, error={"code": -32602, "message": "unsupported protocol version"})
            return
        _response(request_id, result={"protocolVersion": version, "capabilities": {"tools": {}},
                                      "serverInfo": {"name": "p3-mock-mcp", "version": "1.0.0"}})
        return
    if protocol == "legacy" and not _legacy_initialized:
        _response(request_id, error={"code": -32002, "message": "server has not been initialized"})
        return
    if method == "tools/list":
        result = {"tools": _tool_descriptors(), "ttlMs": 0, "cacheScope": "private"}
        if protocol != "legacy":
            result["resultType"] = "complete"
        _response(request_id, result=result)
        return
    if method == "tools/call" and isinstance(params, dict):
        name, args = params.get("name"), params.get("arguments", {})
        if not isinstance(name, str) or not isinstance(args, dict):
            _response(request_id, error={"code": -32602, "message": "invalid tool arguments"})
            return
        if request_cancel is None:
            _response(request_id, error={"code": -32603, "message": "synthetic call lacks a cancellation context"})
            return
        with _state_lock:
            _cancel[request_id] = request_cancel
        output = _tool_result(name, args, request_id, request_cancel, scenario)
        with _state_lock:
            _cancel.pop(request_id, None)
        if request_cancel.is_set():
            return
        if protocol != "legacy":
            output["resultType"] = "complete"
        _response(request_id, result=output)
        return
    _response(request_id, error={"code": -32601, "message": "Method not found"})


def serve(protocol: str, scenario: str = "normal") -> None:
    workers: list[threading.Thread] = []
    while True:
        raw = sys.stdin.buffer.readline(MAX_LINE + 1)
        if not raw:
            break
        if len(raw) > MAX_LINE or not raw.endswith(b"\n"):
            print("invalid or oversized MCP frame", file=sys.stderr, flush=True)
            break
        try:
            message = json.loads(raw.decode("utf-8"))
            if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
                raise ValueError("invalid JSON-RPC object")
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
            print("invalid MCP JSON-RPC input", file=sys.stderr, flush=True)
            continue
        method = message.get("method")
        if method == "tools/call" and "id" in message:
            event = threading.Event()
            with _state_lock:
                _cancel[message["id"]] = event
            worker = threading.Thread(target=_handle, args=(message, protocol, event, scenario), daemon=True)
            worker.start()
            workers.append(worker)
        else:
            _handle(message, protocol, scenario=scenario)
    for worker in workers:
        worker.join(timeout=1.0)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", choices=("dual", "modern", "legacy"), default="dual")
    parser.add_argument("--scenario", choices=("normal", "engineer-challenge", "c01-dense-challenge", "read-denied", "stale-semantic-inventory",
        "onboarding-catalog",
        "onboarding-invalid-relationship",
        "onboarding-schema-alt",
        "stale-semantics", "source-version-drift", "invalid-relationship", "bad-geometry",
        "audit-version-drift", "oversized-read", "missing-center", "missing-edge",
        "missing-hypothesis-selection", "missing-cohort-selection", "unsupported-cohort-selection",
        "typed-categorical", "typed-defect", "explicit-missing"), default="normal")
    args = parser.parse_args()
    serve(args.protocol, args.scenario)


if __name__ == "__main__":
    main()
