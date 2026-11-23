"""Bounded, standard-library MCP client transports for explicitly configured servers.

The default transport is MCP stdio. No shell is involved and a server's stdout is
reserved for newline-delimited JSON-RPC. This module does not create or infer
company permissions; callers must supply an approved tool/source mapping.
"""
from __future__ import annotations

import json
import os
import queue
import re
import subprocess
import threading
import time
import ipaddress
from collections import deque
from dataclasses import dataclass
from typing import Any, Mapping, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

LATEST_PROTOCOL = "2026-07-28"
LEGACY_PROTOCOL = "2025-11-25"
SUPPORTED_PROTOCOLS = (LATEST_PROTOCOL, LEGACY_PROTOCOL)
MAX_MESSAGE_BYTES = 4 * 1024 * 1024
_MCP_META = "io.modelcontextprotocol/"


class MCPClientError(RuntimeError):
    """Base exception for a malformed, unavailable or unsafe MCP interaction."""


class MCPProtocolError(MCPClientError):
    pass


class MCPTimeout(MCPClientError):
    pass


class MCPCancelled(MCPClientError):
    pass


class MCPRemoteError(MCPClientError):
    def __init__(self, code: int, message: str, data: Any = None):
        super().__init__(f"MCP server returned JSON-RPC error {code}: {message}")
        self.code = code
        self.message = message
        self.data = data


class MCPToolError(MCPClientError):
    """A tool returned isError=true; untrusted server text is intentionally omitted."""

    def __init__(self, tool_name: str):
        super().__init__(f"MCP tool {tool_name!r} reported an error")
        self.tool_name = tool_name


class MCPTransportError(MCPClientError):
    pass


@dataclass(frozen=True)
class MCPServerInfo:
    protocol_version: str
    era: str
    capabilities: Mapping[str, Any]
    server_info: Mapping[str, Any]


def _valid_id(value: Any) -> bool:
    return (isinstance(value, (str, int)) and not isinstance(value, bool)
            and value is not None and (not isinstance(value, str) or bool(value)))


def _json_line(message: Mapping[str, Any], max_bytes: int) -> bytes:
    try:
        payload = json.dumps(message, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise MCPProtocolError("MCP message is not finite JSON") from exc
    if len(payload) > max_bytes:
        raise MCPProtocolError("MCP message exceeds the configured byte limit")
    return payload + b"\n"


class StdioTransport:
    """MCP stdio transport with bounded JSONL framing and cooperative cancel."""

    def __init__(self, command: Sequence[str], *, cwd: str | None = None,
                 env: Mapping[str, str] | None = None, max_message_bytes: int = MAX_MESSAGE_BYTES):
        if not isinstance(command, (list, tuple)) or not command or len(command) > 64:
            raise ValueError("command must be a non-empty argument array")
        if any(not isinstance(part, str) or not part or "\x00" in part or len(part) > 4096 for part in command):
            raise ValueError("command arguments must be non-empty bounded strings without NUL")
        if not 1024 <= max_message_bytes <= MAX_MESSAGE_BYTES:
            raise ValueError("max_message_bytes must be between 1024 and 4 MiB")
        child_env = _minimal_environment()
        if env:
            for key, value in env.items():
                if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key) or not isinstance(value, str) or "\x00" in value:
                    raise ValueError("invalid child environment entry")
                child_env[key] = value
        self.max_message_bytes = max_message_bytes
        self._messages: queue.Queue[Any] = queue.Queue()
        self._write_lock = threading.Lock()
        self._request_lock = threading.Lock()
        self._closed = False
        self._stderr_tail: deque[str] = deque(maxlen=40)
        self.process = subprocess.Popen(list(command), cwd=cwd, env=child_env, stdin=subprocess.PIPE,
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0)
        self._reader = threading.Thread(target=self._read_stdout, name="mcp-stdio-reader", daemon=True)
        self._stderr_reader = threading.Thread(target=self._read_stderr, name="mcp-stdio-stderr", daemon=True)
        self._reader.start()
        self._stderr_reader.start()

    @property
    def stderr_tail(self) -> tuple[str, ...]:
        return tuple(self._stderr_tail)

    def _read_stdout(self) -> None:
        stream = self.process.stdout
        assert stream is not None
        while True:
            try:
                raw = stream.readline(self.max_message_bytes + 2)
                if not raw:
                    self._messages.put(MCPTransportError("MCP server closed stdout"))
                    return
                if len(raw) > self.max_message_bytes + 1 or not raw.endswith(b"\n"):
                    self._messages.put(MCPProtocolError("MCP stdio frame is oversized or not newline terminated"))
                    return
                if raw.endswith(b"\r\n"):
                    raw = raw[:-2] + b"\n"
                payload = raw[:-1]
                if not payload:
                    self._messages.put(MCPProtocolError("empty MCP stdio frame"))
                    return
                message = json.loads(payload.decode("utf-8"))
                if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
                    raise MCPProtocolError("MCP stdout must contain JSON-RPC 2.0 objects only")
                self._messages.put(message)
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                self._messages.put(MCPProtocolError("MCP server emitted invalid UTF-8 JSON"))
                return
            except OSError as exc:
                self._messages.put(MCPTransportError("MCP stdout read failed"))
                return

    def _read_stderr(self) -> None:
        stream = self.process.stderr
        assert stream is not None
        while True:
            try:
                raw = stream.readline(4097)
            except OSError:
                return
            if not raw:
                return
            self._stderr_tail.append(raw[:4096].decode("utf-8", errors="replace").rstrip())

    def send(self, message: Mapping[str, Any]) -> None:
        if self._closed or self.process.poll() is not None:
            raise MCPTransportError("MCP server process is not running")
        payload = _json_line(message, self.max_message_bytes)
        stream = self.process.stdin
        assert stream is not None
        try:
            with self._write_lock:
                stream.write(payload)
                stream.flush()
        except (BrokenPipeError, OSError) as exc:
            raise MCPTransportError("MCP server stdin is unavailable") from exc

    def notify(self, method: str, params: Mapping[str, Any] | None = None) -> None:
        if not isinstance(method, str) or not method:
            raise ValueError("notification method is required")
        message: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            message["params"] = dict(params)
        self.send(message)

    def request(self, message: Mapping[str, Any], *, timeout: float,
                cancel_event: threading.Event | None = None) -> dict[str, Any]:
        request_id = message.get("id")
        if not _valid_id(request_id):
            raise MCPProtocolError("MCP request ID must be a non-empty string or integer")
        with self._request_lock:
            self.send(message)
            deadline = time.monotonic() + timeout
            while True:
                if cancel_event is not None and cancel_event.is_set():
                    self._cancel(request_id, "client cancellation")
                    raise MCPCancelled("MCP request was cancelled")
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    self._cancel(request_id, "client timeout")
                    raise MCPTimeout("MCP request timed out")
                try:
                    item = self._messages.get(timeout=min(0.05, remaining))
                except queue.Empty:
                    if self.process.poll() is not None:
                        raise MCPTransportError("MCP server exited before replying")
                    continue
                if isinstance(item, BaseException):
                    raise item
                if "method" in item:
                    # Modern MCP servers cannot initiate requests to the client. Notifications
                    # are permissible, but are deliberately not used as data or instructions.
                    if "id" in item:
                        raise MCPProtocolError("server-initiated JSON-RPC requests are unsupported")
                    continue
                if (item.get("id") != request_id or type(item.get("id")) is not type(request_id)):
                    # A late response to a cancelled/timed-out request is discarded.
                    continue
                if "error" in item:
                    error = item["error"]
                    if not isinstance(error, dict) or type(error.get("code")) is not int or not isinstance(error.get("message"), str):
                        raise MCPProtocolError("MCP server returned a malformed JSON-RPC error")
                    raise MCPRemoteError(error["code"], error["message"], error.get("data"))
                result = item.get("result")
                if not isinstance(result, dict):
                    raise MCPProtocolError("MCP response result must be an object")
                return result

    def _cancel(self, request_id: Any, reason: str) -> None:
        try:
            self.notify("notifications/cancelled", {"requestId": request_id, "reason": reason})
        except MCPClientError:
            pass

    def close(self, *, wait_timeout: float = 1.0) -> None:
        if self._closed:
            return
        self._closed = True
        stream = self.process.stdin
        if stream is not None:
            try:
                stream.close()
            except OSError:
                pass
        try:
            self.process.wait(timeout=wait_timeout)
        except subprocess.TimeoutExpired:
            self.process.terminate()
            try:
                self.process.wait(timeout=wait_timeout)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=wait_timeout)
        for stream in (self.process.stdout, self.process.stderr):
            if stream is not None:
                try:
                    stream.close()
                except OSError:
                    pass

    def __enter__(self) -> "StdioTransport":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


class _NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class StreamableHTTPTransport:
    """Bounded MCP Streamable HTTP transport with session and cooperative cancel."""

    def __init__(self, endpoint: str, *, headers: Mapping[str, str] | None = None,
                 max_message_bytes: int = MAX_MESSAGE_BYTES):
        parsed = urlsplit(endpoint) if isinstance(endpoint, str) else None
        if (parsed is None or parsed.scheme not in ("https", "http") or not parsed.hostname
                or parsed.username is not None or parsed.password is not None
                or parsed.fragment or parsed.query):
            raise ValueError("MCP HTTP endpoint must be an HTTPS URL without credentials, query, or fragment")
        if parsed.scheme == "http":
            try:
                loopback = ipaddress.ip_address(parsed.hostname).is_loopback
            except ValueError:
                loopback = parsed.hostname.lower() == "localhost"
            if not loopback:
                raise ValueError("cleartext MCP HTTP is permitted only on loopback")
        if not 1024 <= max_message_bytes <= MAX_MESSAGE_BYTES:
            raise ValueError("max_message_bytes must be between 1024 and 4 MiB")
        if parsed.port is not None and not 1 <= parsed.port <= 65535:
            raise ValueError("MCP HTTP endpoint port is invalid")
        self.endpoint = endpoint
        self.max_message_bytes = max_message_bytes
        self._headers = dict(headers or {})
        for name, value in self._headers.items():
            if (not isinstance(name, str) or not re.fullmatch(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+", name)
                    or name.lower() in {"host", "content-length", "content-type", "accept", "mcp-session-id", "mcp-protocol-version"}
                    or not isinstance(value, str) or any(char in value for char in "\r\n\x00")):
                raise ValueError("MCP HTTP authentication headers contain an invalid or reserved field")
        self._opener = build_opener(_NoRedirectHandler)
        self._session_id: str | None = None
        self._protocol_version: str | None = None
        self._closed = False
        self._session_lock = threading.Lock()

    def set_protocol_version(self, version: str) -> None:
        if not isinstance(version, str) or not version or "\r" in version or "\n" in version:
            raise ValueError("MCP protocol version is invalid")
        self._protocol_version = version

    def _headers_for(self, message: Mapping[str, Any]) -> dict[str, str]:
        headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream",
                   **self._headers}
        params = message.get("params")
        meta = params.get("_meta") if isinstance(params, dict) else None
        version = meta.get(_MCP_META + "protocolVersion") if isinstance(meta, dict) else None
        if isinstance(version, str):
            headers["MCP-Protocol-Version"] = version
        elif self._protocol_version:
            headers["MCP-Protocol-Version"] = self._protocol_version
        with self._session_lock:
            if self._session_id:
                headers["MCP-Session-Id"] = self._session_id
        return headers

    def _post(self, message: Mapping[str, Any], timeout: float) -> dict[str, Any] | None:
        payload = _json_line(message, self.max_message_bytes)
        request = Request(self.endpoint, data=payload, headers=self._headers_for(message), method="POST")
        try:
            with self._opener.open(request, timeout=timeout) as response:
                status = response.status
                session_id = response.headers.get("MCP-Session-Id")
                if session_id is not None:
                    if not session_id or len(session_id) > 1024 or any(char in session_id for char in "\r\n\x00"):
                        raise MCPProtocolError("MCP server returned an invalid session identifier")
                    with self._session_lock:
                        self._session_id = session_id
                content_type = response.headers.get_content_type().lower()
                raw = response.read(self.max_message_bytes + 1)
        except HTTPError as exc:
            # Do not expose response bodies that might echo credentials or source data.
            if exc.code in (301, 302, 303, 307, 308):
                raise MCPTransportError("MCP HTTP redirects are rejected to protect configured credentials") from exc
            raise MCPTransportError(f"MCP HTTP endpoint returned status {exc.code}") from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise MCPTransportError("MCP HTTP request failed or timed out") from exc
        if len(raw) > self.max_message_bytes:
            raise MCPProtocolError("MCP HTTP response exceeds the configured byte limit")
        if status in (202, 204) and not raw:
            return None
        if not raw:
            raise MCPProtocolError("MCP HTTP request returned an empty response")
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise MCPProtocolError("MCP HTTP response is not valid UTF-8") from exc
        if content_type == "application/json":
            try:
                message_obj = json.loads(text)
            except json.JSONDecodeError as exc:
                raise MCPProtocolError("MCP HTTP response is not valid JSON") from exc
            if not isinstance(message_obj, dict) or message_obj.get("jsonrpc") != "2.0":
                raise MCPProtocolError("MCP HTTP JSON response must be a JSON-RPC 2.0 object")
            candidates = [message_obj]
        elif content_type == "text/event-stream":
            events: list[str] = []
            data_lines: list[str] = []
            for line in text.replace("\r\n", "\n").split("\n"):
                if line == "":
                    if data_lines:
                        events.append("\n".join(data_lines))
                        data_lines = []
                elif line.startswith(":"):
                    continue
                elif line.startswith("data:"):
                    data_lines.append(line[5:].lstrip(" "))
            if data_lines:
                events.append("\n".join(data_lines))
            candidates = []
            for event in events:
                try:
                    message_obj = json.loads(event)
                except json.JSONDecodeError as exc:
                    raise MCPProtocolError("MCP SSE event did not contain valid JSON") from exc
                if isinstance(message_obj, dict) and message_obj.get("jsonrpc") == "2.0":
                    candidates.append(message_obj)
        else:
            raise MCPProtocolError("MCP HTTP response content type must be JSON or text/event-stream")
        request_id = message.get("id")
        for candidate in candidates:
            if candidate.get("id") == request_id and type(candidate.get("id")) is type(request_id):
                return candidate
        if not candidates:
            raise MCPProtocolError("MCP HTTP response contained no JSON-RPC message")
        if request_id is None:
            return candidates[0]
        raise MCPProtocolError("MCP HTTP response did not match the request ID")

    def _bounded_request(self, message: Mapping[str, Any], timeout: float) -> dict[str, Any]:
        response = self._post(message, timeout)
        if not isinstance(response, dict):
            raise MCPProtocolError("MCP HTTP request returned no JSON-RPC response")
        if "error" in response:
            error = response["error"]
            if not isinstance(error, dict) or type(error.get("code")) is not int or not isinstance(error.get("message"), str):
                raise MCPProtocolError("MCP server returned a malformed JSON-RPC error")
            raise MCPRemoteError(error["code"], error["message"], error.get("data"))
        result = response.get("result")
        if not isinstance(result, dict):
            raise MCPProtocolError("MCP HTTP response result must be an object")
        return result

    def request(self, message: Mapping[str, Any], *, timeout: float,
                cancel_event: threading.Event | None = None) -> dict[str, Any]:
        if self._closed:
            raise MCPTransportError("MCP HTTP transport is closed")
        if not 0.05 <= timeout <= 300:
            raise ValueError("MCP HTTP timeout must be between 0.05 and 300 seconds")
        output: queue.Queue[Any] = queue.Queue(maxsize=1)
        def run_request():
            try:
                output.put(self._bounded_request(message, timeout))
            except BaseException as exc:
                output.put(exc)
        worker = threading.Thread(target=run_request, name="mcp-http-request", daemon=True)
        worker.start()
        deadline = time.monotonic() + timeout
        while True:
            if cancel_event is not None and cancel_event.is_set():
                request_id = message.get("id")
                if _valid_id(request_id):
                    cancellation = {"jsonrpc": "2.0", "method": "notifications/cancelled",
                                    "params": {"requestId": request_id, "reason": "client cancellation"}}
                    threading.Thread(target=self._send_cancellation, args=(cancellation,), daemon=True).start()
                raise MCPCancelled("MCP request was cancelled")
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                request_id = message.get("id")
                if _valid_id(request_id):
                    cancellation = {"jsonrpc": "2.0", "method": "notifications/cancelled",
                                    "params": {"requestId": request_id, "reason": "client timeout"}}
                    threading.Thread(target=self._send_cancellation, args=(cancellation,), daemon=True).start()
                raise MCPTimeout("MCP HTTP request timed out")
            try:
                result = output.get(timeout=min(0.05, remaining))
            except queue.Empty:
                continue
            if isinstance(result, BaseException):
                raise result
            return result

    def _send_cancellation(self, message: Mapping[str, Any]) -> None:
        try:
            self._post(message, 1.0)
        except MCPClientError:
            pass

    def notify(self, method: str, params: Mapping[str, Any] | None = None) -> None:
        if self._closed:
            raise MCPTransportError("MCP HTTP transport is closed")
        message: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            message["params"] = dict(params)
        self._post(message, 5.0)

    def close(self) -> None:
        self._closed = True
        with self._session_lock:
            session_id, self._session_id = self._session_id, None
        if session_id:
            try:
                request = Request(self.endpoint, headers={**self._headers, "MCP-Session-Id": session_id}, method="DELETE")
                with self._opener.open(request, timeout=1.0):
                    pass
            except (HTTPError, URLError, TimeoutError, OSError):
                pass

    def __enter__(self) -> "StreamableHTTPTransport":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


def _minimal_environment() -> dict[str, str]:
    allowed = ("PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "TMPDIR", "LANG", "LC_ALL")
    return {key: os.environ[key] for key in allowed if key in os.environ}


class MCPClient:
    """Version-negotiating MCP client without implicit tool execution."""

    def __init__(self, transport: Any, *, client_name: str = "fab-intelligence-p3",
                 client_version: str = "0.2.0", request_timeout: float = 30.0):
        if not 0.05 <= request_timeout <= 300:
            raise ValueError("request_timeout must be between 0.05 and 300 seconds")
        self.transport = transport
        self.client_name = client_name
        self.client_version = client_version
        self.request_timeout = request_timeout
        self.server: MCPServerInfo | None = None
        self._next_id = 1
        self._lock = threading.RLock()

    def _id(self) -> int:
        value = self._next_id
        self._next_id += 1
        return value

    def _meta(self, version: str) -> dict[str, Any]:
        return {
            _MCP_META + "protocolVersion": version,
            _MCP_META + "clientInfo": {"name": self.client_name, "version": self.client_version},
            _MCP_META + "clientCapabilities": {},
        }

    def _modern_request(self, method: str, params: Mapping[str, Any], version: str,
                        *, cancel_event: threading.Event | None = None, timeout: float | None = None) -> dict[str, Any]:
        merged = dict(params)
        merged["_meta"] = self._meta(version)
        message = {"jsonrpc": "2.0", "id": self._id(), "method": method, "params": merged}
        result = self.transport.request(message, timeout=timeout or self.request_timeout, cancel_event=cancel_event)
        result_type = result.get("resultType")
        if result_type not in ("complete", "input_required"):
            raise MCPProtocolError("modern MCP result has an unsupported or missing resultType")
        return result

    def connect(self, *, timeout: float = 5.0) -> MCPServerInfo:
        with self._lock:
            if self.server is not None:
                return self.server
            discovery: dict[str, Any] | None = None
            try:
                raw = self._modern_request("server/discover", {}, LATEST_PROTOCOL, timeout=timeout)
                discovery = raw
            except MCPRemoteError as exc:
                # -32022 identifies a modern server that supports another protocol version.
                if exc.code == -32022 and isinstance(exc.data, dict):
                    supported = exc.data.get("supported") or exc.data.get("supportedVersions")
                    if isinstance(supported, list):
                        discovery = {"supportedVersions": supported, "capabilities": {}, "_meta": {}}
                if discovery is None:
                    if exc.code == -32601:
                        return self._initialize_legacy(timeout=timeout)
                    raise

            supported = discovery.get("supportedVersions")
            if not isinstance(supported, list) or any(not isinstance(item, str) for item in supported):
                # A legacy server commonly answers this probe with an implementation-specific error;
                # a malformed successful discovery is not treated as permission to call tools.
                raise MCPProtocolError("server/discover returned an invalid supportedVersions list")
            selected = next((version for version in SUPPORTED_PROTOCOLS if version in supported), None)
            if selected is None:
                raise MCPProtocolError("MCP server and client have no mutually supported protocol version")
            if selected == LEGACY_PROTOCOL:
                return self._initialize_legacy(timeout=timeout)
            if not isinstance(discovery.get("capabilities"), dict):
                raise MCPProtocolError("server/discover capabilities must be an object")
            meta = discovery.get("_meta", {})
            server_info = meta.get(_MCP_META + "serverInfo", {}) if isinstance(meta, dict) else {}
            self.server = MCPServerInfo(selected, "modern", discovery["capabilities"],
                                        server_info if isinstance(server_info, dict) else {})
            setter = getattr(self.transport, "set_protocol_version", None)
            if callable(setter):
                setter(selected)
            return self.server

    def _initialize_legacy(self, *, timeout: float) -> MCPServerInfo:
        message = {"jsonrpc": "2.0", "id": self._id(), "method": "initialize", "params": {
            "protocolVersion": LEGACY_PROTOCOL,
            "capabilities": {},
            "clientInfo": {"name": self.client_name, "version": self.client_version},
        }}
        result = self.transport.request(message, timeout=timeout)
        version = result.get("protocolVersion")
        if version != LEGACY_PROTOCOL or not isinstance(result.get("capabilities"), dict):
            raise MCPProtocolError("legacy initialize returned an unsupported version or invalid capabilities")
        server_info = result.get("serverInfo", {})
        if not isinstance(server_info, dict):
            raise MCPProtocolError("legacy serverInfo must be an object")
        setter = getattr(self.transport, "set_protocol_version", None)
        if callable(setter):
            setter(version)
        self.transport.notify("notifications/initialized")
        self.server = MCPServerInfo(version, "legacy", result["capabilities"], server_info)
        return self.server

    def request(self, method: str, params: Mapping[str, Any] | None = None, *,
                cancel_event: threading.Event | None = None, timeout: float | None = None) -> dict[str, Any]:
        with self._lock:
            server = self.connect()
            params = params or {}
            if not isinstance(params, Mapping):
                raise TypeError("MCP params must be an object")
            if server.era == "modern":
                return self._modern_request(method, params, server.protocol_version,
                                            cancel_event=cancel_event, timeout=timeout)
            message = {"jsonrpc": "2.0", "id": self._id(), "method": method, "params": dict(params)}
            return self.transport.request(message, timeout=timeout or self.request_timeout,
                                          cancel_event=cancel_event)

    def notify(self, method: str, params: Mapping[str, Any] | None = None) -> None:
        self.connect()
        self.transport.notify(method, params)

    def list_tools(self, *, max_tools: int = 1000, max_pages: int = 100) -> list[dict[str, Any]]:
        if type(max_tools) is not int or not 1 <= max_tools <= 10000 or type(max_pages) is not int or not 1 <= max_pages <= 100:
            raise ValueError("tool listing limits are invalid")
        tools: list[dict[str, Any]] = []
        cursor = None
        seen_cursors: set[str] = set()
        for _ in range(max_pages):
            params = {"cursor": cursor} if cursor is not None else {}
            result = self.request("tools/list", params)
            page = result.get("tools")
            if not isinstance(page, list):
                raise MCPProtocolError("tools/list did not return a tools array")
            for tool in page:
                if not isinstance(tool, dict) or not isinstance(tool.get("name"), str) or not tool["name"]:
                    raise MCPProtocolError("tools/list contains an invalid tool descriptor")
            tools.extend(page)
            if len(tools) > max_tools:
                raise MCPProtocolError("MCP tool inventory exceeds the configured limit")
            next_cursor = result.get("nextCursor")
            if next_cursor is None:
                return tools
            if not isinstance(next_cursor, str) or not next_cursor or next_cursor in seen_cursors:
                raise MCPProtocolError("tools/list returned an invalid or repeated pagination cursor")
            seen_cursors.add(next_cursor)
            cursor = next_cursor
        raise MCPProtocolError("tools/list exceeded the configured page limit")

    def call_tool(self, name: str, arguments: Mapping[str, Any], *,
                  cancel_event: threading.Event | None = None, timeout: float | None = None) -> dict[str, Any]:
        if not isinstance(name, str) or not name or len(name) > 256:
            raise ValueError("MCP tool name is invalid")
        if not isinstance(arguments, Mapping):
            raise TypeError("MCP tool arguments must be an object")
        result = self.request("tools/call", {"name": name, "arguments": dict(arguments)},
                              cancel_event=cancel_event, timeout=timeout)
        if result.get("resultType", "complete") != "complete":
            raise MCPProtocolError("MCP tool requested additional input; unattended execution is refused")
        if result.get("isError") is True:
            raise MCPToolError(name)
        return result

    def close(self) -> None:
        self.transport.close()

    def __enter__(self) -> "MCPClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
