"""Test-only loopback API fixture for exercising the shared headless contract."""
from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import threading

from fabintel.project import analyze
from products.p3.engine import AnalysisCancelled
from fabintel.contracts import validate_envelope

BASE = Path(__file__).resolve().parents[2]
MAX_REQUEST_BYTES = 10 * 1024 * 1024
CANCEL_LOCK = threading.Lock()
ACTIVE_ANALYSES = {}
PENDING_CANCELS = set()
REQUEST_ID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")


class _Handler(BaseHTTPRequestHandler):
    server_version = "FabIntelLocal/0.2"

    def log_message(self, format, *args):
        # Request URLs and user supplied source identifiers are not written to logs.
        return

    def _send(self, status, body, content_type):
        encoded = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
        self.end_headers()
        try:
            self.wfile.write(encoded)
        except OSError:
            pass

    def do_GET(self):
        if self.path == "/api/example":
            body = (BASE / "fixtures" / "p3_integrated_synthetic.json").read_bytes()
            self._send(200, body, "application/json; charset=utf-8")
            return
        if self.path == "/api/health":
            self._send(200, '{"status":"local","network":"not used","mode":"SYNTHETIC_DEMO"}', "application/json; charset=utf-8")
            return
        self._send(404, '{"error":"not found"}', "application/json; charset=utf-8")

    def do_POST(self):
        if not self._same_origin_request():
            self._send(403, '{"error":"cross-origin requests are not accepted"}', "application/json; charset=utf-8")
            return
        if self.path == "/api/cancel":
            self._cancel_analysis()
            return
        if self.path != "/api/analyze":
            self._send(404, '{"error":"not found"}', "application/json; charset=utf-8")
            return
        raw_length = self.headers.get("Content-Length", "")
        if not raw_length.isdecimal() or len(raw_length) > 8:
            self._send(411, '{"error":"Content-Length is required"}', "application/json; charset=utf-8")
            return
        length = int(raw_length)
        if length <= 0 or length > MAX_REQUEST_BYTES:
            self._send(413, '{"error":"request must be between 1 byte and 10 MiB"}', "application/json; charset=utf-8")
            return
        try:
            data = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._send(400, '{"error":"request body must be valid UTF-8 JSON"}', "application/json; charset=utf-8")
            return
        if not isinstance(data, dict):
            self._send(400, '{"error":"request body must be a JSON object"}', "application/json; charset=utf-8")
            return
        request_id = self.headers.get("X-Analysis-Id", "")
        if request_id and not REQUEST_ID.fullmatch(request_id):
            self._send(400, '{"error":"X-Analysis-Id must be a UUID"}', "application/json; charset=utf-8")
            return
        cancel = threading.Event()
        if request_id:
            with CANCEL_LOCK:
                if request_id in PENDING_CANCELS:
                    PENDING_CANCELS.discard(request_id)
                    cancel.set()
                ACTIVE_ANALYSES[request_id] = cancel
        try:
            result = analyze(data, cancel)
            validate_envelope(result)
            body = json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            self._send(200, body, "application/json; charset=utf-8")
        except AnalysisCancelled:
            self._send(409, '{"status":"CANCELLED","reason":"local analysis was stopped"}', "application/json; charset=utf-8")
        except Exception:
            # Avoid leaking input fragments or stack traces into a browser response.
            self._send(500, '{"error":"analysis failed; input was not logged"}', "application/json; charset=utf-8")
        finally:
            if request_id:
                with CANCEL_LOCK:
                    ACTIVE_ANALYSES.pop(request_id, None)

    def _cancel_analysis(self):
        raw_length = self.headers.get("Content-Length", "")
        if not raw_length.isdecimal() or len(raw_length) > 4 or not 1 <= int(raw_length) <= 1024:
            self._send(411, '{"error":"a small Content-Length JSON body is required"}', "application/json; charset=utf-8")
            return
        try:
            request = json.loads(self.rfile.read(int(raw_length)).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._send(400, '{"error":"cancel body must be valid JSON"}', "application/json; charset=utf-8")
            return
        request_id = request.get("request_id") if isinstance(request, dict) else None
        if not isinstance(request_id, str) or not REQUEST_ID.fullmatch(request_id):
            self._send(400, '{"error":"request_id must be a UUID"}', "application/json; charset=utf-8")
            return
        with CANCEL_LOCK:
            cancel = ACTIVE_ANALYSES.get(request_id)
            if cancel:
                cancel.set()
            elif len(PENDING_CANCELS) < 32:
                PENDING_CANCELS.add(request_id)
        self._send(202, '{"status":"CANCEL_REQUESTED"}', "application/json; charset=utf-8")

    def _same_origin_request(self):
        expected_host = f"127.0.0.1:{self.server.server_port}"
        host = self.headers.get("Host", "").lower()
        if host != expected_host and host != f"localhost:{self.server.server_port}":
            return False
        origin = self.headers.get("Origin")
        if origin and origin not in (f"http://{expected_host}", f"http://localhost:{self.server.server_port}"):
            return False
        if self.headers.get("Sec-Fetch-Site", "").lower() == "cross-site":
            return False
        return True


def serve(port=8765):
    if type(port) is not int or not 1 <= port <= 65535:
        raise ValueError("port must be between 1 and 65535")
    server = ThreadingHTTPServer(("127.0.0.1", port), _Handler)
    server.daemon_threads = True
    try:
        print(f"P3 synthetic headless API: http://127.0.0.1:{port}/api/health (Ctrl-C to stop)")
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        pass
    finally:
        with CANCEL_LOCK:
            for cancel in ACTIVE_ANALYSES.values():
                cancel.set()
        server.server_close()

