"""Explicitly mapped, read-only logical adapter over MCP tool servers.

No production tool names or semantic mappings are built in. The server's tool
annotations are treated as untrusted hints; each exact descriptor must match a
site-supplied approval record before this adapter will call it.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import uuid
from datetime import datetime, timezone
from math import isfinite
from pathlib import Path
from typing import Any, Mapping

from fabintel.mcp_client import MCPClient, MCPToolError, StdioTransport, StreamableHTTPTransport

MAX_CONFIG_BYTES = 256 * 1024
DEFAULT_LIMITS = {"max_rows": 1000, "max_bytes": 4 * 1024 * 1024, "max_seconds": 30}
REQUIRED_OPERATIONS = ("discover", "semantics", "relationships", "read_bounded", "audit")
FORBIDDEN_QUERY_KEYS = {"sql", "query", "raw_sql", "statement", "table", "table_name", "query_string"}


class MCPPolicyError(PermissionError):
    pass


class MCPDataError(ValueError):
    pass


class CredentialProvider:
    """Authentication-provider interface. Credentials are resolved only at runtime."""

    def stdio_environment(self) -> dict[str, str]:
        return {}

    def http_headers(self) -> dict[str, str]:
        return {}


class EnvironmentCredentialProvider(CredentialProvider):
    """Map named secret-store environment references into child process variables."""

    def __init__(self, *, stdio_env: Mapping[str, str] | None = None,
                 http_headers: Mapping[str, str] | None = None):
        self.stdio_env = dict(stdio_env or {})
        self.http_header_refs = dict(http_headers or {})
        for target, reference in self.stdio_env.items():
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", target) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", reference):
                raise ValueError("credential references must be environment variable names")
        for target, reference in self.http_header_refs.items():
            if (not re.fullmatch(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+", target)
                    or target.lower() in {"host", "content-length", "content-type", "accept", "mcp-session-id", "mcp-protocol-version"}
                    or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", reference)):
                raise ValueError("HTTP credentials must map valid header names to environment variable references")

    def stdio_environment(self) -> dict[str, str]:
        result = {}
        for target, reference in self.stdio_env.items():
            value = os.environ.get(reference)
            if value is None:
                raise MCPPolicyError(f"required credential reference {reference!r} is unavailable")
            result[target] = value
        return result

    def http_headers(self) -> dict[str, str]:
        result = {}
        for target, reference in self.http_header_refs.items():
            value = os.environ.get(reference)
            if value is None:
                raise MCPPolicyError(f"required credential reference {reference!r} is unavailable")
            if any(char in value for char in "\r\n\x00"):
                raise MCPPolicyError("HTTP credential contains an invalid header value")
            result[target] = value
        return result


def tool_definition_sha256(tool: Mapping[str, Any]) -> str:
    canonical = json.dumps(dict(tool), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def approved_query_plan_sha256(plan: Mapping[str, Any]) -> str:
    canonical = json.dumps(dict(plan), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _json_size(value: Any) -> int:
    return len(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8"))


def _contains_forbidden_query_key(value: Any) -> bool:
    if isinstance(value, dict):
        return any((str(key).lower() in FORBIDDEN_QUERY_KEYS) or _contains_forbidden_query_key(item)
                   for key, item in value.items())
    if isinstance(value, list):
        return any(_contains_forbidden_query_key(item) for item in value)
    return False


def _structured_payload(result: Mapping[str, Any]) -> dict[str, Any]:
    structured = result.get("structuredContent")
    if isinstance(structured, dict):
        return structured
    content = result.get("content")
    if isinstance(content, list):
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text" and isinstance(item.get("text"), str):
                try:
                    parsed = json.loads(item["text"])
                except json.JSONDecodeError:
                    continue
                if isinstance(parsed, dict):
                    return parsed
    raise MCPDataError("MCP tool returned no structured object suitable for validated analysis")


def load_config(path: str | Path) -> dict[str, Any]:
    target = Path(path)
    if target.stat().st_size > MAX_CONFIG_BYTES:
        raise ValueError("MCP adapter config exceeds 256 KiB")
    try:
        config = json.loads(target.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("MCP adapter config must be UTF-8 JSON") from exc
    if not isinstance(config, dict) or config.get("schema_version") != "p3-mcp-adapter-config-v1":
        raise ValueError("unsupported MCP adapter config schema")
    validate_config_before_start(config)
    return config


def validate_config_before_start(config: Mapping[str, Any]) -> None:
    """Reject placeholders and unapproved configs before launching any MCP process."""
    approval = config.get("read_only_approval")
    if not isinstance(approval, dict) or approval.get("approved") is not True or not approval.get("reference"):
        raise MCPPolicyError("site read-only approval is missing; MCP process was not started")
    sources = config.get("approved_sources")
    if not isinstance(sources, list) or not sources:
        raise MCPPolicyError("approved source mappings are missing; MCP process was not started")
    for source in sources:
        if (not isinstance(source, dict) or source.get("approved") is not True
                or not isinstance(source.get("source_id"), str) or not source["source_id"]
                or not isinstance(source.get("semantic_version"), str) or not source["semantic_version"]
                or not source.get("approval_reference")):
            raise MCPPolicyError("approved source mapping is incomplete; MCP process was not started")
    plans = config.get("approved_plans")
    if not isinstance(plans, list) or not plans:
        raise MCPPolicyError("site-approved bounded read plans are missing; MCP process was not started")
    source_versions = {source["source_id"]: source["semantic_version"] for source in sources if isinstance(source, dict)}
    seen_plan_ids = set()
    for record in plans:
        plan = record.get("plan") if isinstance(record, dict) else None
        plan_id = plan.get("plan_id") if isinstance(plan, dict) else None
        source_id = plan.get("source_id") if isinstance(plan, dict) else None
        semantic_version = plan.get("semantic_version") if isinstance(plan, dict) else None
        if (not isinstance(record, dict) or record.get("approved") is not True
                or not isinstance(record.get("approval_reference"), str) or not record["approval_reference"].strip()
                or not isinstance(plan_id, str) or not plan_id.strip() or plan_id in seen_plan_ids
                or not isinstance(source_id, str) or source_versions.get(source_id) != semantic_version
                or not re.fullmatch(r"[a-f0-9]{64}", str(record.get("plan_sha256", "")))
                or approved_query_plan_sha256(plan) != record.get("plan_sha256")):
            raise MCPPolicyError("site-approved read plan is incomplete, mismatched or unapproved; MCP process was not started")
        seen_plan_ids.add(plan_id)
    operations = config.get("operations")
    if not isinstance(operations, dict):
        raise MCPPolicyError("logical operation mappings are missing; MCP process was not started")
    for name in REQUIRED_OPERATIONS:
        binding = operations.get(name)
        approval = binding.get("approval") if isinstance(binding, dict) else None
        argument_mapping = binding.get("argument_mapping") if isinstance(binding, dict) else None
        if (not isinstance(binding, dict) or not isinstance(binding.get("tool_name"), str) or not binding["tool_name"]
                or not isinstance(approval, dict) or approval.get("approved") is not True
                or not approval.get("reference") or not re.fullmatch(r"[a-f0-9]{64}", str(approval.get("tool_definition_sha256", "")))
                or not isinstance(argument_mapping, dict)
                or any(not isinstance(key, str) or not isinstance(value, str) or not value
                       or value.lower() in FORBIDDEN_QUERY_KEYS for key, value in (argument_mapping or {}).items())):
            raise MCPPolicyError(f"approved {name!r} tool mapping is incomplete; MCP process was not started")
    limits = config.get("limits")
    if not isinstance(limits, dict):
        raise ValueError("bounded MCP limits are required; MCP process was not started")
    for name in DEFAULT_LIMITS:
        _positive_int(limits.get(name), name)


class ReadOnlyMCPAdapter:
    """Maps approved logical read operations to exact site-configured MCP tools."""

    def __init__(self, client: MCPClient, config: Mapping[str, Any]):
        if not isinstance(config, Mapping) or config.get("schema_version") != "p3-mcp-adapter-config-v1":
            raise ValueError("unsupported MCP adapter config schema")
        validate_config_before_start(config)
        self.client = client
        self.config = dict(config)
        self.approval = self.config.get("read_only_approval")
        if (not isinstance(self.approval, dict) or self.approval.get("approved") is not True
                or not isinstance(self.approval.get("reference"), str) or not self.approval["reference"].strip()):
            raise MCPPolicyError("a site-provided read-only approval record is required")
        sources = self.config.get("approved_sources")
        if not isinstance(sources, list) or not sources:
            raise MCPPolicyError("explicit site-approved source IDs and semantic versions are required")
        self.sources: dict[str, dict[str, Any]] = {}
        for source in sources:
            if (not isinstance(source, dict) or source.get("approved") is not True
                    or not isinstance(source.get("source_id"), str) or not source["source_id"].strip()
                    or not isinstance(source.get("semantic_version"), str) or not source["semantic_version"].strip()
                    or not isinstance(source.get("approval_reference"), str) or not source["approval_reference"].strip()):
                raise MCPPolicyError("each approved source requires a source ID, semantic version and approval reference")
            source_id = source["source_id"]
            if source_id in self.sources:
                raise ValueError("approved source IDs must be unique")
            self.sources[source_id] = dict(source)
        self.plans: dict[str, dict[str, Any]] = {}
        for record in self.config.get("approved_plans", []):
            plan = dict(record["plan"])
            self.plans[plan["plan_id"]] = {"plan": plan, "approval_reference": record["approval_reference"],
                                            "plan_sha256": record["plan_sha256"]}
        limits = self.config.get("limits")
        if not isinstance(limits, dict):
            raise ValueError("bounded query limits are required")
        self.limits = {
            "max_rows": min(_positive_int(limits.get("max_rows"), "max_rows"), DEFAULT_LIMITS["max_rows"]),
            "max_bytes": min(_positive_int(limits.get("max_bytes"), "max_bytes"), DEFAULT_LIMITS["max_bytes"]),
            "max_seconds": min(_positive_int(limits.get("max_seconds"), "max_seconds"), DEFAULT_LIMITS["max_seconds"]),
        }
        bindings = self.config.get("operations")
        if not isinstance(bindings, dict) or any(not isinstance(bindings.get(name), dict) for name in REQUIRED_OPERATIONS):
            raise ValueError("explicit tool bindings for all logical read operations are required")
        self.bindings = bindings
        self._tool_inventory: dict[str, dict[str, Any]] | None = None
        self._active: dict[str, threading.Event] = {}
        self._lock = threading.RLock()
        self._audit: list[dict[str, Any]] = []
        self._discovery: dict[str, Any] | None = None

    @classmethod
    def from_config(cls, path: str | Path, *, request_timeout: float | None = None) -> "ReadOnlyMCPAdapter":
        config = load_config(path)
        if (request_timeout is not None
                and (type(request_timeout) not in (int, float) or not isfinite(request_timeout)
                     or not 0.05 <= request_timeout <= 300)):
            raise ValueError("request_timeout must be finite and between 0.05 and 300 seconds")
        transport_cfg = config.get("transport")
        if not isinstance(transport_cfg, dict) or transport_cfg.get("type") not in ("stdio", "streamable_http"):
            raise ValueError("transport must be configured as MCP stdio or Streamable HTTP")
        auth_cfg = config.get("auth_provider", {})
        if not isinstance(auth_cfg, dict) or auth_cfg.get("type", "none") not in ("none", "environment"):
            raise ValueError("unsupported MCP authentication provider")
        auth = (EnvironmentCredentialProvider(stdio_env=auth_cfg.get("stdio_env", {}),
                                              http_headers=auth_cfg.get("http_headers", {}))
                if auth_cfg.get("type") == "environment" else CredentialProvider())
        if transport_cfg["type"] == "stdio":
            cwd = transport_cfg.get("cwd")
            if cwd is not None and (not isinstance(cwd, str) or not Path(cwd).is_absolute()):
                raise ValueError("stdio server cwd must be an absolute path")
            transport = StdioTransport(transport_cfg.get("command"), cwd=cwd, env=auth.stdio_environment())
        else:
            endpoint = transport_cfg.get("endpoint")
            transport = StreamableHTTPTransport(endpoint, headers=auth.http_headers())
        try:
            timeout = float(request_timeout) if request_timeout is not None else float(min(30, config["limits"]["max_seconds"]))
            return cls(MCPClient(transport, request_timeout=timeout), config)
        except BaseException:
            transport.close()
            raise

    def _tools(self) -> dict[str, dict[str, Any]]:
        if self._tool_inventory is None:
            server = self.client.connect()
            if "tools" not in server.capabilities:
                raise MCPPolicyError("MCP server did not advertise the required tools capability")
            tools = self.client.list_tools()
            result = {}
            for tool in tools:
                if tool["name"] in result:
                    raise MCPDataError("MCP server advertised duplicate tool names")
                result[tool["name"]] = tool
            self._tool_inventory = result
        return self._tool_inventory

    def _tool_for(self, logical_name: str) -> tuple[str, dict[str, str]]:
        binding = self.bindings.get(logical_name)
        if not isinstance(binding, dict):
            raise MCPPolicyError(f"logical operation {logical_name!r} has no approved site binding")
        approval = binding.get("approval")
        tool_name = binding.get("tool_name")
        if (not isinstance(approval, dict) or approval.get("approved") is not True
                or not isinstance(approval.get("reference"), str) or not approval["reference"].strip()
                or not isinstance(approval.get("tool_definition_sha256"), str)
                or not isinstance(tool_name, str) or not tool_name):
            raise MCPPolicyError(f"logical operation {logical_name!r} lacks an exact reviewed tool approval")
        tool = self._tools().get(tool_name)
        if tool is None:
            raise MCPPolicyError(f"approved MCP tool {tool_name!r} is not currently advertised")
        if tool_definition_sha256(tool) != approval["tool_definition_sha256"]:
            raise MCPPolicyError(f"MCP tool definition for {logical_name!r} changed after review")
        annotations = tool.get("annotations", {})
        if (not isinstance(annotations, dict) or annotations.get("readOnlyHint") is not True
                or annotations.get("destructiveHint") is not False):
            raise MCPPolicyError(f"MCP tool {tool_name!r} is not explicitly marked read-only and non-destructive")
        mapping = binding.get("argument_mapping", {})
        if not isinstance(mapping, dict):
            raise MCPPolicyError("argument mapping must be a logical-field to MCP-field object")
        if any(not isinstance(source, str) or not source or not isinstance(target, str) or not target
               for source, target in mapping.items()):
            raise MCPPolicyError("argument mapping contains an invalid field name")
        return tool_name, mapping

    def _arguments(self, logical_name: str, values: Mapping[str, Any]) -> tuple[str, dict[str, Any]]:
        tool_name, mapping = self._tool_for(logical_name)
        args = {}
        for logical_key, tool_key in mapping.items():
            if logical_key not in values:
                raise MCPPolicyError(f"required mapped input {logical_key!r} is missing for {logical_name}")
            args[tool_key] = values[logical_key]
        return tool_name, args

    def _invoke(self, logical_name: str, values: Mapping[str, Any], *, cancel_event=None, timeout=None) -> dict[str, Any]:
        tool_name, args = self._arguments(logical_name, values)
        try:
            response = self.client.call_tool(tool_name, args, cancel_event=cancel_event, timeout=timeout)
        except MCPToolError as exc:
            raise MCPPolicyError(f"configured read operation {logical_name!r} was denied or failed by the MCP server") from exc
        payload = _structured_payload(response)
        if _json_size(payload) > self.limits["max_bytes"]:
            raise MCPDataError("MCP tool response exceeds the configured data limit")
        return payload

    def discover(self) -> dict[str, Any]:
        if self._discovery is not None:
            return self._discovery
        server = self.client.connect()
        payload = self._invoke("discover", {})
        for required in ("tool_versions", "semantic_versions", "limits", "auth_scopes", "audit_support", "source_ids", "read_only"):
            if required not in payload:
                raise MCPDataError(f"MCP capability discovery omitted {required}")
        if payload["read_only"] is not True or not isinstance(payload["auth_scopes"], list) or "read_only" not in payload["auth_scopes"]:
            raise MCPPolicyError("the active MCP principal did not establish read-only scope")
        if (not isinstance(payload["source_ids"], list)
                or any(not isinstance(source, str) or not source for source in payload["source_ids"])
                or len(payload["source_ids"]) != len(set(payload["source_ids"]))
                or not set(self.sources).issubset(set(payload["source_ids"]))):
            raise MCPPolicyError("the server does not expose all explicitly approved source IDs")
        if (not isinstance(payload["tool_versions"], dict) or not isinstance(payload["semantic_versions"], list)
                or not isinstance(payload["limits"], dict) or payload["audit_support"] is not True):
            raise MCPDataError("MCP discovery returned invalid tool, semantic, bounded-query, or audit capabilities")
        self._discovery = {
            "status": "CONFIGURED_READ_ONLY_UNQUALIFIED",
            "protocol_version": server.protocol_version,
            "protocol_era": server.era,
            "server_info": dict(server.server_info),
            "capabilities": sorted(server.capabilities),
            "tool_versions": payload["tool_versions"],
            "semantic_versions": payload["semantic_versions"],
            "limits": payload["limits"],
            "auth_scopes": ["read_only"],
            "audit_support": payload["audit_support"],
            "approved_source_ids": sorted(self.sources),
            "approval_reference": self.approval["reference"],
            "external_internal_qualification": "PENDING_INTERNAL",
        }
        return self._discovery

    def semantics(self, source_ids: list[str], semantic_version: str) -> dict[str, Any]:
        self.discover()
        if (not isinstance(source_ids, list) or not source_ids
                or any(not isinstance(source, str) or source not in self.sources for source in source_ids)
                or len(source_ids) != len(set(source_ids))):
            raise MCPPolicyError("semantics may be requested only for explicitly approved source IDs")
        if not isinstance(semantic_version, str) or not semantic_version:
            raise ValueError("semantic version is required")
        if any(self.sources[source]["semantic_version"] != semantic_version for source in source_ids):
            raise MCPPolicyError("requested semantic version differs from the reviewed source mappings")
        payload = self._invoke("semantics", {"source_ids": source_ids, "semantic_version": semantic_version})
        definitions = payload.get("column_definitions")
        if not isinstance(definitions, list) or len(definitions) != len(source_ids):
            raise MCPDataError("semantics response must define each requested source exactly once")
        seen = set()
        for item in definitions:
            if (not isinstance(item, dict) or item.get("approved") is not True
                    or item.get("source_id") not in source_ids or item.get("semantic_version") != semantic_version
                    or not item.get("grain") or not isinstance(item.get("units"), list)
                    or not item.get("effective_time") or not isinstance(item.get("column_definitions"), list)
                    or not item["column_definitions"]
                    or any(not isinstance(column, dict) or not isinstance(column.get("name"), str) or not column["name"]
                           for column in item["column_definitions"])):
                raise MCPDataError("semantics response is incomplete or unapproved")
            if item["source_id"] in seen:
                raise MCPDataError("semantics response repeats a source definition")
            seen.add(item["source_id"])
        return payload

    def relationships(self, typed_entity_ids: Mapping[str, Any], time_window: Mapping[str, Any]) -> dict[str, Any]:
        self.discover()
        if not isinstance(typed_entity_ids, Mapping) or not isinstance(time_window, Mapping):
            raise TypeError("typed entity identifiers and a bounded time window are required")
        source_id = typed_entity_ids.get("source_id")
        target_source_id = typed_entity_ids.get("target_source_id")
        if (not isinstance(source_id, str) or not source_id or not isinstance(target_source_id, str)
                or not target_source_id):
            raise MCPPolicyError("relationship source identifiers must be typed non-empty strings")
        if _contains_forbidden_query_key(typed_entity_ids):
            raise MCPPolicyError("relationship entity identifiers may not contain raw query fields")
        source_ids = {source_id, target_source_id}
        if None in source_ids or not source_ids.issubset(self.sources):
            raise MCPPolicyError("relationship discovery is restricted to explicitly approved sources")
        if _contains_forbidden_query_key(time_window) or not _valid_time_window(time_window):
            raise MCPPolicyError("relationship discovery requires a bounded timezone-aware time window without raw query fields")
        payload = self._invoke("relationships", {"typed_entity_ids": dict(typed_entity_ids), "time_window": dict(time_window)})
        if (payload.get("approved") is not True or not isinstance(payload.get("keys"), list) or not payload["keys"]
                or payload.get("cardinality") not in {"one_to_one", "one_to_many", "many_to_one"}
                or not payload.get("grain") or not payload.get("effectivity") or not payload.get("source_reference")):
            raise MCPPolicyError("MCP relationship is not an approved effective-time relationship")
        return payload

    def read_bounded(self, approved_plan: Mapping[str, Any], permission_context: Mapping[str, Any],
                     limits: Mapping[str, Any] | None = None, *, operation_id: str | None = None,
                     cancel_event: threading.Event | None = None) -> dict[str, Any]:
        self.discover()
        if not isinstance(approved_plan, Mapping) or not isinstance(permission_context, Mapping):
            raise TypeError("read requires an approved query plan and permission context")
        source_id = approved_plan.get("source_id")
        plan_id = approved_plan.get("plan_id")
        reviewed_plan = self.plans.get(plan_id) if isinstance(plan_id, str) else None
        if (not reviewed_plan or dict(approved_plan) != reviewed_plan["plan"]
                or approved_query_plan_sha256(approved_plan) != reviewed_plan["plan_sha256"]
                or source_id not in self.sources or _contains_forbidden_query_key(approved_plan)):
            raise MCPPolicyError("read requires an exact site-approved, source-scoped plan without raw query text")
        scoped_sources = permission_context.get("source_ids")
        if (permission_context.get("scope") != "read_only" or not isinstance(scoped_sources, list)
                or scoped_sources != [source_id]):
            raise MCPPolicyError("read permission context is not read-only and scoped to this source")
        requested = limits or {}
        if not isinstance(requested, Mapping):
            raise TypeError("read limits must be an object")
        effective = {
            "max_rows": min(_positive_int(requested.get("max_rows", self.limits["max_rows"]), "max_rows"), self.limits["max_rows"]),
            "max_bytes": min(_positive_int(requested.get("max_bytes", self.limits["max_bytes"]), "max_bytes"), self.limits["max_bytes"]),
            "max_seconds": min(_positive_int(requested.get("max_seconds", self.limits["max_seconds"]), "max_seconds"), self.limits["max_seconds"]),
        }
        operation_id = operation_id or str(uuid.uuid4())
        if not isinstance(operation_id, str) or not operation_id or len(operation_id) > 128:
            raise ValueError("operation_id must be a bounded non-empty string")
        cancel_event = cancel_event or threading.Event()
        with self._lock:
            if operation_id in self._active:
                raise ValueError("operation_id is already active")
            self._active[operation_id] = cancel_event
        started = _utc_now()
        plan_hash = approved_query_plan_sha256(approved_plan)
        try:
            payload = self._invoke("read_bounded", {"approved_plan": dict(approved_plan),
                "permission_context": {"scope": "read_only", "source_ids": [source_id]}, "limits": effective},
                cancel_event=cancel_event, timeout=effective["max_seconds"])
        finally:
            with self._lock:
                self._active.pop(operation_id, None)
        rows = payload.get("typed_rows")
        if not isinstance(rows, list) or len(rows) > effective["max_rows"]:
            raise MCPDataError("bounded MCP read returned missing or excessive typed rows")
        if any(not isinstance(row, dict) for row in rows):
            raise MCPDataError("bounded MCP read contains an untyped row")
        if _json_size(payload) > effective["max_bytes"]:
            raise MCPDataError("bounded MCP read exceeded the effective response byte limit")
        if not isinstance(payload.get("audit_id"), str) or not payload["audit_id"]:
            raise MCPDataError("bounded MCP read omitted its audit ID")
        if not isinstance(payload.get("source_versions"), dict) or payload.get("truncation") not in (True, False):
            raise MCPDataError("bounded MCP read omitted source versions or truncation status")
        if (not payload["source_versions"] or not set(payload["source_versions"]).issubset({source_id})
                or not isinstance(payload.get("audit_id"), str) or not payload["audit_id"]):
            raise MCPDataError("bounded MCP read source versions or audit record do not match the approved source")
        if any("source_id" in row and row["source_id"] != source_id for row in rows):
            raise MCPPolicyError("bounded MCP read returned a row from outside the selected source")
        trace = {"operation_id": operation_id, "permission_scope": "read_only",
                 "sources": [source_id], "started_at": started, "completed_at": _utc_now(),
                 "query_hash": plan_hash, "row_count": len(rows), "audit_id": payload["audit_id"],
                 "approval_reference": reviewed_plan["approval_reference"]}
        with self._lock:
            self._audit.append(trace)
        return {**payload, "audit_trace": trace, "external_internal_qualification": "PENDING_INTERNAL"}

    def cancel(self, operation_id: str) -> dict[str, Any]:
        with self._lock:
            event = self._active.get(operation_id)
            if event is None:
                return {"operation_id": operation_id, "cancellation_requested": False,
                        "confirmed_stopped": False, "reason": "operation is not active"}
            event.set()
        # MCP stdio cancellation is cooperative. A notification is not proof that
        # an untrusted remote process stopped, so never report confirmed_stopped.
        return {"operation_id": operation_id, "cancellation_requested": True,
                "confirmed_stopped": False, "reason": "cancellation notification sent; remote stop not acknowledged"}

    def audit(self, operation_id: str) -> dict[str, Any]:
        payload = self._invoke("audit", {"operation_id": operation_id})
        if (payload.get("permission_scope") != "read_only" or not isinstance(payload.get("sources"), list)
                or not isinstance(payload.get("timestamps"), dict) or not isinstance(payload.get("query_hash"), str)
                or not re.fullmatch(r"[a-fA-F0-9]{64}", payload.get("query_hash", ""))
                or not isinstance(payload.get("audit_id"), str) or not payload["audit_id"]
                or any(not isinstance(source, str) or source not in self.sources for source in payload.get("sources", []))):
            raise MCPDataError("MCP audit response is missing required lineage fields")
        return payload

    @property
    def local_audit_trace(self) -> tuple[dict[str, Any], ...]:
        with self._lock:
            return tuple(dict(item) for item in self._audit)


def _positive_int(value: Any, name: str) -> int:
    if type(value) is not int or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _valid_time_window(value: Mapping[str, Any]) -> bool:
    if set(value) != {"start", "end"}:
        return False
    try:
        start = datetime.fromisoformat(str(value["start"]).replace("Z", "+00:00"))
        end = datetime.fromisoformat(str(value["end"]).replace("Z", "+00:00"))
        return (start.tzinfo is not None and end.tzinfo is not None
                and start.utcoffset() is not None and end.utcoffset() is not None and end > start)
    except (TypeError, ValueError):
        return False
