import sys
import threading
import unittest
from pathlib import Path
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from fabintel.mcp_client import (MCPClient, MCPProtocolError, MCPCancelled,
                                 MCPTransportError, StdioTransport, StreamableHTTPTransport)

ROOT = Path(__file__).resolve().parent.parent
SERVER = [sys.executable, "-S", "-m", "fabintel.mcp_mock_server"]


class MCPStdioClientTests(unittest.TestCase):
    def open_client(self, protocol="dual", **kwargs):
        transport = StdioTransport(SERVER + ["--protocol", protocol], cwd=str(ROOT), **kwargs)
        self.addCleanup(transport.close)
        client = MCPClient(transport, request_timeout=3)
        return client, transport

    def test_modern_protocol_discovery_and_typed_mock_tools(self):
        client, _ = self.open_client("dual")
        server = client.connect()
        self.assertEqual(server.era, "modern")
        self.assertEqual(server.protocol_version, "2026-07-28")
        self.assertEqual(server.capabilities, {"tools": {}})
        tools = client.list_tools()
        by_name = {tool["name"]: tool for tool in tools}
        self.assertTrue(by_name["fab_read_bounded"]["annotations"]["readOnlyHint"])
        self.assertFalse(by_name["unsafe_recipe_write"]["annotations"]["readOnlyHint"])
        result = client.call_tool("fab_discover", {})
        self.assertEqual(result["structuredContent"]["auth_scopes"], ["read_only"])
        self.assertEqual(result["structuredContent"]["catalog_version"], "MOCK-CATALOG-1")

    def test_legacy_server_is_detected_and_initialized(self):
        client, _ = self.open_client("legacy")
        server = client.connect()
        self.assertEqual(server.era, "legacy")
        self.assertEqual(server.protocol_version, "2025-11-25")
        self.assertEqual(client.call_tool("fab_discover", {})["structuredContent"]["mode"], "SYNTHETIC_DEMO")

    def test_stdio_cancel_sends_notification_and_discards_late_response(self):
        client, _ = self.open_client("dual")
        client.connect()
        cancelled = threading.Event()
        timer = threading.Timer(0.1, cancelled.set)
        timer.start()
        self.addCleanup(timer.cancel)
        with self.assertRaises(MCPCancelled):
            client.call_tool("mock_wait_for_cancel", {}, cancel_event=cancelled, timeout=2)
        audit = client.call_tool("fab_audit", {"operation_id": "cancel-test"})["structuredContent"]
        self.assertGreaterEqual(audit.get("cancelled_request_count", 0), 1)

    def test_transport_bounds_outbound_frames(self):
        client, _ = self.open_client("dual", max_message_bytes=1024)
        with self.assertRaises(MCPProtocolError):
            client.transport.send({"jsonrpc": "2.0", "method": "x", "params": {"value": "x" * 2000}})

    def test_mock_server_uses_utf8_json_lines_only(self):
        client, transport = self.open_client("dual")
        client.connect()
        self.assertEqual(client.call_tool("fab_discover", {})["resultType"], "complete")
        self.assertEqual(transport.process.returncode, None)
        self.assertTrue(all(isinstance(line, str) for line in transport.stderr_tail))


class _HTTPMockHandler(BaseHTTPRequestHandler):
    requests = []
    redirect = False
    wrong_id = False

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
            result = {"resultType": "complete", "tools": [{"name": "read", "inputSchema": {"type": "object"},
                      "annotations": {"readOnlyHint": True, "destructiveHint": False}}]}
        elif method == "tools/call":
            arguments = params.get("arguments", {})
            structured = {"echo": arguments}
            if params.get("name") == "read" and not arguments:
                structured = {"tool_versions": {"read": "mock/1"}, "semantic_versions": ["MOCK-SEM-1"],
                              "limits": {"max_rows": 10, "max_bytes": 1024, "max_seconds": 3},
                              "auth_scopes": ["read_only"], "audit_support": True,
                              "source_ids": ["MOCK_MAP", "MOCK_QUALITY"], "read_only": True}
            result = {"resultType": "complete", "structuredContent": structured}
        elif method == "notifications/cancelled":
            result = None
        else:
            result = {"resultType": "complete"}
        if request_id is not None:
            response = {"jsonrpc": "2.0", "id": request_id + 100 if type(self).wrong_id else request_id,
                        "result": result}
            encoded = (": progress\n\n" + "data: " + json.dumps({"jsonrpc": "2.0", "method": "notifications/progress", "params": {}})
                       + "\n\n" + "data: " + json.dumps(response) + "\n\n").encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("MCP-Session-Id", "SYN-HTTP-SESSION")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)
        else:
            self.send_response(202)
            self.send_header("MCP-Session-Id", "SYN-HTTP-SESSION")
            self.send_header("Content-Length", "0")
            self.end_headers()

    def do_DELETE(self):
        self.send_response(204)
        self.send_header("Content-Length", "0")
        self.end_headers()


class MCPStreamableHTTPClientTests(unittest.TestCase):
    def setUp(self):
        _HTTPMockHandler.requests = []
        _HTTPMockHandler.redirect = False
        _HTTPMockHandler.wrong_id = False
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _HTTPMockHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.thread.join, 2)
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.endpoint = f"http://127.0.0.1:{self.server.server_port}/mcp"

    def test_http_transport_negotiates_session_auth_and_matches_sse_request_id(self):
        transport = StreamableHTTPTransport(self.endpoint, headers={"Authorization": "Bearer synthetic"})
        self.addCleanup(transport.close)
        client = MCPClient(transport, request_timeout=3)
        server = client.connect()
        self.assertEqual(server.protocol_version, "2026-07-28")
        tools = client.list_tools()
        self.assertEqual(tools[0]["name"], "read")
        result = client.call_tool("read", {"source_id": "MOCK_MAP"})
        self.assertEqual(result["structuredContent"]["echo"], {"source_id": "MOCK_MAP"})
        requests = _HTTPMockHandler.requests
        self.assertEqual(requests[0]["headers"].get("Mcp-Protocol-Version"), "2026-07-28")
        self.assertEqual(requests[0]["headers"].get("Authorization"), "Bearer synthetic")
        self.assertEqual(requests[1]["headers"].get("Mcp-Session-Id"), "SYN-HTTP-SESSION")
        self.assertEqual(requests[1]["headers"].get("Mcp-Protocol-Version"), "2026-07-28")

    def test_http_transport_rejects_cleartext_non_loopback_and_redirects(self):
        with self.assertRaises(ValueError):
            StreamableHTTPTransport("http://example.invalid/mcp")
        _HTTPMockHandler.redirect = True
        transport = StreamableHTTPTransport(self.endpoint, headers={"Authorization": "Bearer synthetic"})
        self.addCleanup(transport.close)
        with self.assertRaises(MCPTransportError):
            transport.request({"jsonrpc": "2.0", "id": 1, "method": "server/discover", "params": {}}, timeout=2)
        self.assertEqual(len(_HTTPMockHandler.requests), 1)

    def test_http_transport_rejects_mismatched_response_id(self):
        _HTTPMockHandler.wrong_id = True
        transport = StreamableHTTPTransport(self.endpoint)
        self.addCleanup(transport.close)
        with self.assertRaises(MCPProtocolError):
            transport.request({"jsonrpc": "2.0", "id": 1, "method": "server/discover", "params": {}}, timeout=2)


if __name__ == "__main__":
    unittest.main()
