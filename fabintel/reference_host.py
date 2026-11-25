"""Loopback reference host for independently operating and qualifying P3.

The host is a small HTTP boundary around the official MCP SDK adapter and the
P3 engine. It serves locally built, fully offline web assets and never binds to
a non-loopback address.
"""
from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import re
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

from fabintel.mcp_adapter import MCPDataError, MCPPolicyError, ReadOnlyMCPAdapter
from fabintel.mcp_client import MCPCancelled, MCPClient, MCPDependencyError
from fabintel.mcp_workflow import run_mcp_host_module
from fabintel.synthetic_mcp import synthetic_adapter_config
from products.p3.engine import AnalysisCancelled

ROOT = Path(__file__).resolve().parents[1]
STATIC_ROOT = ROOT / "products" / "p3" / "reference_host" / "static"
MAX_REQUEST_BYTES = 1024 * 1024
MAX_CANCEL_BYTES = 1024
PLAN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}$")
REQUEST_ID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
DEFAULT_PLANS = ["SYN-WF-CURRENT", "SYN-WF-PREVIOUS", "SYN-WF-BASELINE",
                 "SYN-WF-HISTORY", "SYN-WF-ASSOCIATION"]
_ACTIVE_LOCK = threading.Lock()
_ACTIVE: dict[str, threading.Event] = {}
_PENDING_CANCEL: set[str] = set()


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


def _create_adapter(mode: str) -> ReadOnlyMCPAdapter:
    if mode == "synthetic":
        scenario = os.environ.get("FABINTEL_SYNTHETIC_SCENARIO", "").strip() or None
        command = [os.sys.executable, "-S", "-m", "qualification.synthetic_mcp_peer", "--protocol", "dual"]
        if scenario:
            if not scenario.replace("-", "").isalnum() or len(scenario) > 48:
                raise ValueError("synthetic peer scenario is invalid")
            command.extend(("--scenario", scenario))
        transport = {"type": "stdio", "command": command, "cwd": str(ROOT)}
        client = MCPClient(transport, request_timeout=8)
        try:
            return ReadOnlyMCPAdapter(client, synthetic_adapter_config(client, ROOT, scenario))
        except BaseException:
            client.close()
            raise
    if mode == "configured":
        config_path = os.environ.get("FABINTEL_MCP_CONFIG", "").strip()
        if not config_path:
            raise PermissionError("configured MCP mode is not enabled")
        return ReadOnlyMCPAdapter.from_config(config_path)
    raise ValueError("source mode must be synthetic or configured")


class _ReferenceHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class _Handler(BaseHTTPRequestHandler):
    server_version = "P3ReferenceHost/1.0"
    sys_version = ""

    def log_message(self, _format: str, *_args: Any) -> None:
        # Do not write query parameters, user source identifiers, or request bodies.
        return

    def _headers(self, status: int, content_type: str, length: int) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(length))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
        self.end_headers()

    def _send(self, status: int, value: Any, content_type: str = "application/json; charset=utf-8") -> None:
        body = value if isinstance(value, bytes) else value.encode("utf-8")
        self._headers(status, content_type, len(body))
        try:
            self.wfile.write(body)
        except OSError:
            pass

    def do_GET(self) -> None:
        path = unquote(urlsplit(self.path).path)
        if path == "/api/health":
            self._send(200, json.dumps({"status": "local", "network": "not used for synthetic mode",
                                        "synthetic_mcp": "official-sdk-stdio-peer",
                                        "configured_source_available": bool(os.environ.get("FABINTEL_MCP_CONFIG"))}))
            return
        if path == "/api/status":
            self._send(200, json.dumps({"product_id": "p3", "capabilities": ["C01", "C02", "C03", "C04", "C05"],
                                        "internal_qualification": "PENDING_INTERNAL",
                                        "source_modes": ["synthetic"] + (["configured"] if os.environ.get("FABINTEL_MCP_CONFIG") else [])}))
            return
        if path.startswith("/api/"):
            self._send(404, '{"error":"not found"}')
            return
        relative = "index.html" if path in {"", "/"} else path.lstrip("/")
        candidate = (STATIC_ROOT / relative).resolve()
        try:
            candidate.relative_to(STATIC_ROOT.resolve())
        except ValueError:
            self._send(404, '{"error":"not found"}')
            return
        if not candidate.is_file():
            self._send(404, '{"error":"built reference-host assets are unavailable; run the offline build"}')
            return
        body = candidate.read_bytes()
        content_type = mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
        if content_type.startswith("text/") or content_type in {"application/javascript", "application/json"}:
            content_type += "; charset=utf-8"
        self._send(200, body, content_type)

    def do_POST(self) -> None:
        if not self._same_origin_request():
            self._send(403, '{"error":"cross-origin requests are not accepted"}')
            return
        if self.path == "/api/cancel":
            self._cancel()
            return
        if self.path != "/api/investigate":
            self._send(404, '{"error":"not found"}')
            return
        data = self._read_json(MAX_REQUEST_BYTES)
        if data is None:
            return
        mode = data.get("source_mode", "synthetic")
        plans = data.get("plan_ids", DEFAULT_PLANS if mode == "synthetic" else None)
        time_window = {"start": data.get("time_start", "2026-01-01T00:00:00Z"),
                       "end": data.get("time_end", "2026-02-01T00:00:00Z")}
        top_k = data.get("top_k", 5)
        target_family = data.get("anomaly_target_family")
        if (mode not in {"synthetic", "configured"} or not isinstance(plans, list) or not plans or len(plans) > 10
                or any(not isinstance(item, str) or not PLAN_ID.fullmatch(item) for item in plans)
                or type(top_k) is not int or not 1 <= top_k <= 50
                or (target_family is not None and not isinstance(target_family, dict))
                or not all(isinstance(time_window[key], str) and len(time_window[key]) <= 64 for key in ("start", "end"))):
            self._send(400, '{"error":"investigation request is invalid or exceeds its bounded limits"}')
            return
        request_id = self.headers.get("X-Analysis-Id", "")
        if request_id and not REQUEST_ID.fullmatch(request_id):
            self._send(400, '{"error":"X-Analysis-Id must be a UUID"}')
            return
        cancel = threading.Event()
        if request_id:
            with _ACTIVE_LOCK:
                if request_id in _ACTIVE:
                    self._send(409, '{"status":"REFUSED","reason":"This request identifier is already active."}')
                    return
                if len(_ACTIVE) >= 4:
                    self._send(429, '{"status":"REFUSED","reason":"The local host has reached its bounded active-request limit."}')
                    return
                if request_id in _PENDING_CANCEL:
                    _PENDING_CANCEL.discard(request_id)
                    cancel.set()
                _ACTIVE[request_id] = cancel
        adapter = None
        try:
            if cancel.is_set():
                raise MCPCancelled("analysis was cancelled before source discovery")
            adapter = _create_adapter(mode)
            result = run_mcp_host_module(adapter, plans, time_window=time_window, top_k=top_k,
                                         anomaly_target_family=target_family,
                                         cancel=cancel, operation_id="P3-REF-" + uuid.uuid4().hex[:16])
            export_content = {key: result[key] for key in ("contract_version", "product_id", "capabilities",
                                                              "source_preview", "evidence", "spatial_map",
                                                              "historical_spatial_map",
                                                              "suite_compatibility")}
            canonical_export = _canonical_bytes(export_content)
            result["export"] = {"format": "fab-intelligence-investigation.v1",
                                "sha256": hashlib.sha256(canonical_export).hexdigest(),
                                "canonicalization": "UTF-8 JSON; sorted keys; compact separators; no NaN",
                                "canonical_json": canonical_export.decode("utf-8")}
            result["export_content"] = export_content
            self._send(200, _canonical_bytes(result).decode("utf-8"))
        except (MCPCancelled, AnalysisCancelled):
            self._send(409, '{"status":"CANCELLED","reason":"Investigation cancelled. No partial analysis was accepted; you can correct the request or retry."}')
        except PermissionError:
            self._send(403, '{"status":"REFUSED","reason":"Configured source permission is unavailable."}')
        except MCPPolicyError:
            self._send(403, '{"status":"REFUSED","reason":"Source permissions or reviewed tool bindings did not pass validation."}')
        except MCPDependencyError:
            self._send(503, '{"status":"ERROR","reason":"The pinned MCP SDK is missing from this Python environment. Install the hash-locked bundle from vendor/mcp-sdk-2.3.0/ and start the host with that environment’s Python."}')
        except (MCPDataError, ValueError, OSError, RuntimeError):
            self._send(422, '{"status":"REFUSED","reason":"Source semantics, schema, units, geometry, or bounded read validation failed."}')
        except Exception:  # noqa: BLE001 - keep raw source and process details out of browser responses.
            self._send(502, '{"status":"ERROR","reason":"The source workflow failed. Correct the configuration or retry."}')
        finally:
            if adapter is not None:
                adapter.client.close()
            if request_id:
                with _ACTIVE_LOCK:
                    _ACTIVE.pop(request_id, None)

    def _read_json(self, maximum: int) -> dict[str, Any] | None:
        raw_length = self.headers.get("Content-Length", "")
        if not raw_length.isdecimal() or len(raw_length) > 8:
            self._send(411, '{"error":"Content-Length is required"}')
            return None
        length = int(raw_length)
        if not 1 <= length <= maximum:
            self._send(413, '{"error":"request body exceeds the bounded size limit"}')
            return None
        try:
            value = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._send(400, '{"error":"request body must be valid UTF-8 JSON"}')
            return None
        if not isinstance(value, dict):
            self._send(400, '{"error":"request body must be a JSON object"}')
            return None
        return value

    def _cancel(self) -> None:
        request = self._read_json(MAX_CANCEL_BYTES)
        if request is None:
            return
        request_id = request.get("request_id")
        if not isinstance(request_id, str) or not REQUEST_ID.fullmatch(request_id):
            self._send(400, '{"error":"request_id must be a UUID"}')
            return
        with _ACTIVE_LOCK:
            if request_id in _ACTIVE:
                _ACTIVE[request_id].set()
            elif len(_PENDING_CANCEL) < 32:
                _PENDING_CANCEL.add(request_id)
        self._send(202, '{"status":"CANCEL_REQUESTED"}')

    def _same_origin_request(self) -> bool:
        expected_host = f"127.0.0.1:{self.server.server_port}"
        host = self.headers.get("Host", "").lower()
        if host not in {expected_host, f"localhost:{self.server.server_port}"}:
            return False
        origin = self.headers.get("Origin")
        allowed = {f"http://{expected_host}", f"http://localhost:{self.server.server_port}"}
        return (origin is None or origin in allowed) and self.headers.get("Sec-Fetch-Site", "").lower() != "cross-site"


def serve(port: int = 8765) -> None:
    if type(port) is not int or not 1 <= port <= 65535:
        raise ValueError("port must be between 1 and 65535")
    server = _ReferenceHTTPServer(("127.0.0.1", port), _Handler)
    try:
        print(f"P3 Reference Host: http://127.0.0.1:{port}/ (Ctrl-C to stop)", flush=True)
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        pass
    finally:
        with _ACTIVE_LOCK:
            for event in _ACTIVE.values():
                event.set()
        server.server_close()
