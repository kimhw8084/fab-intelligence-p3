"""Protocol-compatible synthetic MCP server used by external client tests.

Run as ``python -m fabintel.mcp_mock_server --protocol dual``. The process
speaks newline-delimited JSON-RPC on stdio and never reads company data.
"""
from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from datetime import datetime, timezone

MAX_LINE = 4 * 1024 * 1024
PROTOCOLS = ["2026-07-28", "2025-11-25"]
SOURCES = {"MOCK_MAP", "MOCK_QUALITY"}
_write_lock = threading.Lock()
_state_lock = threading.Lock()
_cancel: dict[str | int, threading.Event] = {}
_cancelled: list[str | int] = []
_calls: list[dict] = []
_legacy_initialized = False


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
        {"name": "fab_read_bounded", "description": "Synthetic bounded read of approved mock rows", "inputSchema": {"type": "object", "properties": {"approved_plan": {"type": "object"}, "permission_context": {"type": "object"}, "limits": {"type": "object"}}, "required": ["approved_plan", "permission_context", "limits"], "additionalProperties": False}, "annotations": common},
        {"name": "fab_audit", "description": "Synthetic redacted source audit trace", "inputSchema": {"type": "object", "properties": {"operation_id": {"type": "string"}}, "required": ["operation_id"], "additionalProperties": False}, "annotations": common},
        {"name": "mock_wait_for_cancel", "description": "Test-only cancellable operation", "inputSchema": {"type": "object", "additionalProperties": False}, "annotations": common},
        {"name": "unsafe_recipe_write", "description": "Synthetic write tool that must never be invoked", "inputSchema": {"type": "object"}, "annotations": {"readOnlyHint": False, "destructiveHint": True}},
    ]


def _tool_result(name: str, args: dict, request_id, cancel_event: threading.Event) -> dict:
    if name == "fab_discover":
        result = {"catalog_version": "MOCK-CATALOG-1", "mode": "SYNTHETIC_DEMO",
                  "tool_versions": {tool["name"]: "mock/1" for tool in _tool_descriptors()},
                  "semantic_versions": ["MOCK-SEM-1"], "limits": {"max_rows": 100, "max_bytes": 1048576, "max_seconds": 5},
                  "auth_scopes": ["read_only"], "audit_support": True,
                  "source_ids": sorted(SOURCES), "read_only": True}
    elif name == "fab_semantics":
        ids = args.get("source_ids")
        if not isinstance(ids, list) or not ids or any(source not in SOURCES for source in ids):
            return {"isError": True, "content": [{"type": "text", "text": "permission denied: source is not approved"}]}
        if args.get("semantic_version") != "MOCK-SEM-1":
            return {"isError": True, "content": [{"type": "text", "text": "unsupported semantic version"}]}
        result = {"column_definitions": [{"source_id": source, "approved": True, "semantic_version": "MOCK-SEM-1",
                    "grain": "wafer_site" if source == "MOCK_MAP" else "wafer_die",
                    "units": ["nm"] if source == "MOCK_MAP" else ["count"],
                    "effective_time": "synthetic-event-time-v1",
                    "column_definitions": [{"name": "value", "unit": "nm", "role": "measurement"}]} for source in ids]}
    elif name == "fab_relationships":
        ids = args.get("typed_entity_ids", {})
        valid = isinstance(ids, dict) and ids.get("source_id") == "MOCK_MAP" and ids.get("target_source_id") == "MOCK_QUALITY"
        result = {"approved": valid, "keys": ["wafer_id", "die_id"] if valid else [],
                  "cardinality": "one_to_many" if valid else "unknown", "grain": "wafer_die" if valid else None,
                  "effectivity": "synthetic-event-time-v1", "source_reference": "MOCK-REL-1" if valid else None}
    elif name == "fab_read_bounded":
        plan = args.get("approved_plan", {})
        permission = args.get("permission_context", {})
        limits = args.get("limits", {})
        source = plan.get("source_id") if isinstance(plan, dict) else None
        limit = limits.get("max_rows") if isinstance(limits, dict) else None
        if permission.get("scope") != "read_only" or source not in SOURCES or not plan.get("plan_id"):
            return {"isError": True, "content": [{"type": "text", "text": "permission denied"}]}
        if type(limit) is not int or not 1 <= limit <= 100:
            return {"isError": True, "content": [{"type": "text", "text": "invalid bounded read limit"}]}
        delay_ms = plan.get("test_delay_ms", 0)
        if type(delay_ms) is int and 0 < delay_ms <= 1000:
            if cancel_event.wait(delay_ms / 1000):
                with _state_lock:
                    _cancelled.append(request_id)
                return {"cancelled": True}
        rows = [{"wafer_id": "MOCK-W-01", "lot_id": "MOCK-L-01", "site_id": "center", "x": 0.0, "y": 0.0,
                 "value": 10.0, "unit": "nm", "measured_at": "2026-01-01T00:00:00Z"}]
        result = {"typed_rows": rows[:limit], "audit_id": "MOCK-AUDIT-READ-1",
                  "source_versions": {source: "mock/1"}, "truncation": False}
    elif name == "fab_audit":
        with _state_lock:
            cancelled_count = len(_cancelled)
        result = {"operation_id": args.get("operation_id"), "permission_scope": "read_only",
                  "sources": sorted(SOURCES), "timestamps": {"completed_at": "2026-01-01T00:00:00Z"},
                  "query_hash": "0" * 64, "audit_id": "MOCK-AUDIT-1",
                  "cancelled_request_count": cancelled_count}
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


def _handle(message: dict, protocol: str, request_cancel: threading.Event | None = None):
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
        assert request_cancel is not None
        with _state_lock:
            _cancel[request_id] = request_cancel
        output = _tool_result(name, args, request_id, request_cancel)
        with _state_lock:
            _cancel.pop(request_id, None)
        if request_cancel.is_set():
            return
        if protocol != "legacy":
            output["resultType"] = "complete"
        _response(request_id, result=output)
        return
    _response(request_id, error={"code": -32601, "message": "Method not found"})


def serve(protocol: str) -> None:
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
            worker = threading.Thread(target=_handle, args=(message, protocol, event), daemon=True)
            worker.start()
            workers.append(worker)
        else:
            _handle(message, protocol)
    for worker in workers:
        worker.join(timeout=1.0)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", choices=("dual", "modern", "legacy"), default="dual")
    args = parser.parse_args()
    serve(args.protocol)


if __name__ == "__main__":
    main()
