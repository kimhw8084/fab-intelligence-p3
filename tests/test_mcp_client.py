"""SDK integration checks use the pinned offline wheelhouse when available.

The stdlib MCP peer below is a synthetic test fixture only. Production transport
and protocol handling live in the official MCP Python SDK.
"""
from __future__ import annotations

import importlib.util
import json
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import ClassVar

from fabintel.mcp_client import MCPCancelled, MCPClient

ROOT = Path(__file__).resolve().parent.parent
SERVER = [sys.executable, "-S", "-m", "tests.fixtures.mcp_mock_server", "--protocol", "dual"]
HAS_MCP_SDK = importlib.util.find_spec("mcp") is not None


class MCPClientSDKTests(unittest.TestCase):
    @unittest.skipUnless(HAS_MCP_SDK, "install the local hash-locked MCP SDK candidate to run transport integration checks")
    def test_official_sdk_stdio_discovery_tool_listing_and_read_only_call(self):
        client = MCPClient({"type": "stdio", "command": SERVER, "cwd": str(ROOT)}, request_timeout=3)
        self.addCleanup(client.close)
        server = client.connect()
        self.assertEqual(server.era, "modern")
        self.assertEqual(server.protocol_version, "2026-07-28")
        tools = client.list_tools()
        self.assertIn("fab_read_bounded", {tool["name"] for tool in tools})
        result = client.call_tool("fab_discover", {})
        self.assertEqual(result["resultType"], "complete")
        self.assertEqual(result["structuredContent"]["mode"], "SYNTHETIC_DEMO")

    @unittest.skipUnless(HAS_MCP_SDK, "install the local hash-locked MCP SDK candidate to run transport integration checks")
    def test_official_sdk_uses_legacy_negotiation_when_server_requires_it(self):
        command = [*SERVER[:-1], "legacy"]
        client = MCPClient({"type": "stdio", "command": command, "cwd": str(ROOT)}, request_timeout=3)
        self.addCleanup(client.close)
        server = client.connect()
        self.assertEqual(server.era, "legacy")
        self.assertEqual(server.protocol_version, "2025-11-25")

    @unittest.skipUnless(HAS_MCP_SDK, "install the local hash-locked MCP SDK candidate to run transport integration checks")
    def test_official_sdk_cancellation_stops_waiting_without_claiming_remote_ack(self):
        client = MCPClient({"type": "stdio", "command": SERVER, "cwd": str(ROOT)}, request_timeout=3)
        self.addCleanup(client.close)
        client.connect()
        cancel = threading.Event()
        outcome = []

        def invoke():
            try:
                client.call_tool("mock_wait_for_cancel", {}, cancel_event=cancel, timeout=3)
            except BaseException as exc:  # noqa: BLE001 - surface worker cancellation/exception to the test thread.
                outcome.append(exc)

        worker = threading.Thread(target=invoke)
        worker.start()
        self.assertTrue(worker.is_alive())
        cancel.set()
        worker.join(2)
        self.assertFalse(worker.is_alive())
        self.assertEqual(len(outcome), 1)
        self.assertIsInstance(outcome[0], MCPCancelled)

    def test_cleartext_mcp_http_is_loopback_only(self):
        with self.assertRaisesRegex(ValueError, "loopback"):
            MCPClient({"type": "streamable_http", "endpoint": "http://example.invalid/mcp"})


class _HTTPMockHandler(BaseHTTPRequestHandler):
    requests: ClassVar[list] = []
    redirect = False

    def log_message(self, *_):
        return

    def do_POST(self):
        type(self).requests.append({"headers": dict(self.headers), "path": self.path})
        if type(self).redirect:
            self.send_response(307)
            self.send_header("Location", "/elsewhere")
            self.end_headers()
            return
        length = int(self.headers.get("Content-Length", "0"))
        message = json.loads(self.rfile.read(length).decode("utf-8"))
        request_id = message.get("id")
        method = message.get("method")
        params = message.get("params", {})
        if method == "server/discover":
            result = {"resultType": "complete", "supportedVersions": ["2026-07-28", "2025-11-25"],
                      "capabilities": {"tools": {}},
                      "_meta": {"io.modelcontextprotocol/serverInfo": {"name": "http-mock", "version": "1"}}}
        elif method == "tools/list":
            result = {"resultType": "complete", "ttlMs": 0, "cacheScope": "private",
                      "tools": [{"name": "read", "inputSchema": {"type": "object"},
                      "annotations": {"readOnlyHint": True, "destructiveHint": False}}]}
        elif method == "tools/call":
            arguments = params.get("arguments", {})
            structured = {"echo": arguments}
            if params.get("name") == "read" and not arguments:
                structured = {"tool_versions": {"read": "mock/1"}, "semantic_versions": ["MOCK-SEM-1"],
                              "limits": {"max_rows": 10, "max_bytes": 1024, "max_seconds": 3},
                              "auth_scopes": ["read_only"], "audit_support": True,
                              "source_ids": ["MOCK_MAP", "MOCK_QUALITY"], "read_only": True}
            result = {"resultType": "complete", "content": [], "structuredContent": structured}
        else:
            result = {"resultType": "complete"}
        if request_id is None:
            encoded = b""
            self.send_response(202)
        else:
            response = {"jsonrpc": "2.0", "id": request_id, "result": result}
            encoded = ("data: " + json.dumps(response) + "\n\n").encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("MCP-Session-Id", "SYN-HTTP-SESSION")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        if encoded:
            self.wfile.write(encoded)

    def do_GET(self):
        self.send_response(405)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_DELETE(self):
        self.send_response(204)
        self.send_header("Content-Length", "0")
        self.end_headers()


class MCPStreamableHTTPSDKTests(unittest.TestCase):
    @unittest.skipUnless(HAS_MCP_SDK, "install the local hash-locked MCP SDK candidate to run transport integration checks")
    def setUp(self):
        _HTTPMockHandler.requests = []
        _HTTPMockHandler.redirect = False
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _HTTPMockHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.thread.join, 2)
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.endpoint = f"http://127.0.0.1:{self.server.server_port}/mcp"

    @unittest.skipUnless(HAS_MCP_SDK, "install the local hash-locked MCP SDK candidate to run transport integration checks")
    def test_official_sdk_streamable_http_uses_scoped_auth(self):
        client = MCPClient({"type": "streamable_http", "endpoint": self.endpoint},
                           http_headers={"Authorization": "Bearer synthetic"}, request_timeout=3)
        self.addCleanup(client.close)
        self.assertEqual(client.connect().protocol_version, "2026-07-28")
        self.assertEqual(client.list_tools()[0]["name"], "read")
        self.assertEqual(client.call_tool("read", {"source_id": "MOCK_MAP"})["structuredContent"]["echo"],
                         {"source_id": "MOCK_MAP"})
        self.assertEqual(_HTTPMockHandler.requests[0]["headers"].get("Authorization"), "Bearer synthetic")
