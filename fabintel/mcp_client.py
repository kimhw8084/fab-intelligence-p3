"""Synchronous logical client facade backed by the official MCP Python SDK.

This module deliberately contains no MCP framing or transport implementation.
The SDK owns stdio and Streamable HTTP protocol behavior; P3's separate
``mcp_adapter`` retains the reviewed read-only semantic and authorization rules.
"""
from __future__ import annotations

import asyncio
from concurrent.futures import Future, TimeoutError as FutureTimeout
from dataclasses import dataclass
import ipaddress
import math
import os
import threading
import time
from typing import Any, Mapping, Sequence
from urllib.parse import urlsplit


class MCPClientError(RuntimeError):
    """Base class for an unavailable or unsuccessful SDK-backed MCP operation."""


class MCPProtocolError(MCPClientError):
    pass


class MCPTimeout(MCPClientError):
    pass


class MCPCancelled(MCPClientError):
    pass


class MCPRemoteError(MCPClientError):
    def __init__(self, code: int):
        super().__init__(f"MCP server returned protocol error {code}")
        self.code = code


class MCPToolError(MCPClientError):
    """A configured MCP tool reported an error; remote text is not exposed."""

    def __init__(self, tool_name: str):
        super().__init__(f"MCP tool {tool_name!r} reported an error")
        self.tool_name = tool_name


class MCPTransportError(MCPClientError):
    pass


class MCPDependencyError(MCPClientError):
    pass


@dataclass(frozen=True)
class MCPServerInfo:
    protocol_version: str
    era: str
    capabilities: Mapping[str, Any]
    server_info: Mapping[str, Any]


def _plain(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json", by_alias=True, exclude_none=True, exclude_unset=True)
    if isinstance(value, dict):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def _safe_endpoint(endpoint: Any) -> str:
    if not isinstance(endpoint, str) or len(endpoint) > 4096:
        raise ValueError("Streamable HTTP endpoint must be a bounded URL")
    parsed = urlsplit(endpoint)
    if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Streamable HTTP endpoint must use HTTPS or loopback HTTP without URL credentials")
    if parsed.query or parsed.fragment:
        raise ValueError("Streamable HTTP endpoint cannot contain a query or fragment")
    if parsed.scheme == "http":
        host = parsed.hostname.lower()
        loopback = host == "localhost"
        try:
            loopback = loopback or ipaddress.ip_address(host).is_loopback
        except ValueError:
            pass
        if not loopback:
            raise ValueError("cleartext MCP HTTP is restricted to loopback")
    try:
        _ = parsed.port
    except ValueError as exc:
        raise ValueError("Streamable HTTP endpoint has an invalid port") from exc
    return endpoint


class MCPClient:
    """Small synchronous facade over the official asynchronous MCP SDK."""

    def __init__(self, transport: Mapping[str, Any], *, stdio_env: Mapping[str, str] | None = None,
                 http_headers: Mapping[str, str] | None = None, request_timeout: float = 30.0):
        if not isinstance(transport, Mapping) or transport.get("type") not in ("stdio", "streamable_http"):
            raise ValueError("transport must be explicitly configured as stdio or Streamable HTTP")
        if type(request_timeout) not in (int, float) or not math.isfinite(request_timeout) or not 0.05 <= request_timeout <= 300:
            raise ValueError("request_timeout must be finite and between 0.05 and 300 seconds")
        self.transport_type = str(transport["type"])
        self.request_timeout = float(request_timeout)
        self.stdio_env = dict(stdio_env or {})
        self.http_headers = dict(http_headers or {})
        self.command: tuple[str, ...] = ()
        self.cwd: str | None = None
        self.endpoint: str | None = None
        if self.transport_type == "stdio":
            command = transport.get("command")
            if not isinstance(command, (list, tuple)) or not command or len(command) > 64:
                raise ValueError("stdio command must be a non-empty argument array")
            if any(not isinstance(part, str) or not part or "\x00" in part or len(part) > 4096 for part in command):
                raise ValueError("stdio command arguments must be non-empty bounded strings without NUL")
            cwd = transport.get("cwd")
            if cwd is not None and (not isinstance(cwd, str) or not os.path.isabs(cwd)):
                raise ValueError("stdio server cwd must be an absolute path")
            self.command, self.cwd = tuple(command), cwd
            for key, value in self.stdio_env.items():
                if not isinstance(key, str) or not key.replace("_", "a").isalnum() or not isinstance(value, str) or "\x00" in value:
                    raise ValueError("stdio environment must contain valid string values")
        else:
            self.endpoint = _safe_endpoint(transport.get("endpoint"))
            if any(not isinstance(k, str) or not isinstance(v, str) or "\r" in k + v or "\n" in k + v for k, v in self.http_headers.items()):
                raise ValueError("HTTP authentication headers must be valid strings")

        self.server: MCPServerInfo | None = None
        self._sdk_session: Any = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._ready = threading.Event()
        self._close_event: asyncio.Event | None = None
        self._startup_error: BaseException | None = None
        self._closed = False
        self._state_lock = threading.Lock()

    def _run_thread(self) -> None:
        loop = asyncio.new_event_loop()
        self._loop = loop
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._session_lifecycle())
        except BaseException as exc:
            self._startup_error = exc
            self._ready.set()
        finally:
            pending = asyncio.all_tasks(loop)
            for task in pending:
                task.cancel()
            if pending:
                loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            loop.close()

    async def _session_lifecycle(self) -> None:
        try:
            try:
                from mcp import ClientSession
                from mcp.shared.exceptions import MCPError
            except ImportError as exc:
                raise MCPDependencyError("the pinned official MCP Python SDK is not installed; use the local offline wheelhouse") from exc

            self._close_event = asyncio.Event()
            if self.transport_type == "stdio":
                from mcp.client.stdio import StdioServerParameters, stdio_client
                import contextlib
                with open(os.devnull, "w", encoding="utf-8") as server_stderr:
                    server = StdioServerParameters(command=self.command[0], args=list(self.command[1:]),
                                                   env=self.stdio_env or None, cwd=self.cwd)
                    async with stdio_client(server, errlog=server_stderr) as (read_stream, write_stream):
                        async with ClientSession(read_stream, write_stream, read_timeout_seconds=self.request_timeout) as session:
                            await self._negotiate(session, MCPError)
                            self._sdk_session = session
                            self._ready.set()
                            await self._close_event.wait()
            else:
                import httpx2
                from mcp.client.streamable_http import streamable_http_client
                async with httpx2.AsyncClient(headers=self.http_headers, timeout=self.request_timeout,
                                              follow_redirects=False, trust_env=False) as http_client:
                    async with streamable_http_client(self.endpoint or "", http_client=http_client) as streams:
                        read_stream, write_stream = streams[0], streams[1]
                        async with ClientSession(read_stream, write_stream, read_timeout_seconds=self.request_timeout) as session:
                            await self._negotiate(session, MCPError)
                            self._sdk_session = session
                            self._ready.set()
                            await self._close_event.wait()
        except BaseException as exc:
            self._startup_error = exc
            self._ready.set()

    async def _negotiate(self, session: Any, mcp_error_type: type[BaseException]) -> None:
        try:
            await session.discover()
            era = "modern"
        except mcp_error_type as exc:
            error = getattr(exc, "error", None)
            if getattr(error, "code", None) != -32601:
                raise
            await session.initialize()
            era = "legacy"
        server_info = _plain(getattr(session, "server_info", None)) or {}
        capabilities = _plain(getattr(session, "server_capabilities", None)) or {}
        self.server = MCPServerInfo(str(getattr(session, "protocol_version", "unknown")), era,
                                    capabilities if isinstance(capabilities, dict) else {},
                                    server_info if isinstance(server_info, dict) else {})

    def connect(self) -> MCPServerInfo:
        with self._state_lock:
            if self._closed:
                raise MCPTransportError("MCP client is closed")
            if self._thread is None:
                self._thread = threading.Thread(target=self._run_thread, name="p3-mcp-sdk", daemon=True)
                self._thread.start()
        if not self._ready.wait(self.request_timeout + 1):
            raise MCPTimeout("MCP SDK connection exceeded its configured startup timeout")
        if self._startup_error is not None:
            error = self._startup_error
            if isinstance(error, MCPClientError):
                raise error
            code = getattr(getattr(error, "error", None), "code", None)
            if code is not None:
                raise MCPRemoteError(code) from None
            raise MCPTransportError("MCP SDK connection or protocol negotiation failed") from None
        if self.server is None:
            raise MCPProtocolError("MCP SDK completed without a negotiated server session")
        return self.server

    def _submit(self, coroutine: Any, *, timeout: float, cancel_event: threading.Event | None = None) -> Any:
        self.connect()
        if cancel_event is not None and cancel_event.is_set():
            raise MCPCancelled("MCP operation was cancelled before dispatch")
        loop = self._loop
        if loop is None or not loop.is_running():
            raise MCPTransportError("MCP SDK event loop is not running")
        future: Future[Any] = asyncio.run_coroutine_threadsafe(coroutine, loop)
        deadline = time.monotonic() + timeout
        while True:
            if cancel_event is not None and cancel_event.is_set():
                future.cancel()
                raise MCPCancelled("MCP operation cancellation was requested")
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                future.cancel()
                raise MCPTimeout("MCP SDK operation exceeded its configured timeout")
            try:
                return future.result(timeout=min(0.05, remaining))
            except FutureTimeout:
                continue
            except BaseException as exc:
                code = getattr(getattr(exc, "error", None), "code", None)
                if code is not None:
                    raise MCPRemoteError(code) from None
                raise MCPTransportError(f"MCP SDK operation failed ({type(exc).__name__})") from None

    def list_tools(self) -> list[dict[str, Any]]:
        async def fetch() -> list[dict[str, Any]]:
            from mcp_types import PaginatedRequestParams
            result: list[dict[str, Any]] = []
            cursor = None
            seen: set[str] = set()
            for _ in range(100):
                page = await self._sdk_session.list_tools(params=PaginatedRequestParams(cursor=cursor) if cursor else None)
                result.extend(_plain(tool) for tool in page.tools)
                if len(result) > 5000:
                    raise MCPProtocolError("MCP tool inventory exceeds the configured limit")
                cursor = page.next_cursor
                if cursor is None:
                    return result
                if not isinstance(cursor, str) or not cursor or cursor in seen:
                    raise MCPProtocolError("MCP tool inventory contains an invalid or repeated cursor")
                seen.add(cursor)
            raise MCPProtocolError("MCP tool inventory exceeded the configured page limit")

        return self._submit(fetch(), timeout=self.request_timeout)

    def call_tool(self, name: str, arguments: Mapping[str, Any], *, cancel_event: threading.Event | None = None,
                  timeout: float | None = None) -> dict[str, Any]:
        duration = self.request_timeout if timeout is None else timeout
        if type(duration) not in (int, float) or not math.isfinite(duration) or not 0.05 <= duration <= 300:
            raise ValueError("tool timeout must be finite and between 0.05 and 300 seconds")
        if not isinstance(name, str) or not name or not isinstance(arguments, Mapping):
            raise ValueError("MCP tool name and object arguments are required")

        async def invoke() -> dict[str, Any]:
            result = await self._sdk_session.call_tool(name, arguments=dict(arguments), read_timeout_seconds=float(duration))
            payload = _plain(result)
            if not isinstance(payload, dict):
                raise MCPProtocolError("MCP SDK returned an invalid tool result")
            if payload.get("isError") is True:
                raise MCPToolError(name)
            return payload

        try:
            return self._submit(invoke(), timeout=float(duration), cancel_event=cancel_event)
        except MCPToolError:
            raise

    def close(self) -> None:
        with self._state_lock:
            if self._closed:
                return
            self._closed = True
            loop, closing, thread = self._loop, self._close_event, self._thread
        if loop is not None and loop.is_running() and closing is not None:
            loop.call_soon_threadsafe(closing.set)
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=min(self.request_timeout + 2, 10))

    def __enter__(self) -> "MCPClient":
        self.connect()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
