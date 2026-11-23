import http.client
import json
from http.server import ThreadingHTTPServer
from pathlib import Path
import threading
import unittest

from tests.fixtures.headless_api import _Handler

ROOT = Path(__file__).resolve().parent.parent


class HeadlessApiContractFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.port = cls.server.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def request(self, method, path, body=None, extra_headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=3)
        payload = None if body is None else json.dumps(body)
        headers = {"Content-Type": "application/json"} if payload is not None else {}
        headers.update(extra_headers or {})
        connection.request(method, path, payload, headers)
        response = connection.getresponse()
        result = response.status, response.read(), dict(response.getheaders())
        connection.close()
        return result

    def test_headless_api_has_no_competing_product_shell(self):
        status, body, headers = self.request("GET", "/")
        self.assertEqual(status, 404)
        self.assertIn(b"not found", body)
        self.assertIn("no-store", headers["Cache-Control"])
        status, js, _ = self.request("GET", "/app.js")
        self.assertEqual(status, 404)
        status, example, _ = self.request("GET", "/api/example")
        self.assertEqual(status, 200)
        example_data = json.loads(example)
        self.assertTrue(example_data["coordinates_verified"])
        self.assertEqual(set(example_data["requested_capabilities"]), {"C01", "C02", "C03", "C04", "C05"})
        status, evidence, _ = self.request("POST", "/api/analyze", example_data)
        result = json.loads(evidence)["artifacts"][0]["result"]
        self.assertEqual(status, 200)
        self.assertEqual([result[key]["status"] for key in ("fingerprint", "anomaly", "similarity", "evolution", "quality_association")],
                         ["VALID"] * 5)

    def test_api_returns_deterministic_evidence_and_refuses_internal_mode(self):
        example = json.loads((ROOT / "fixtures" / "case_positive.json").read_text())
        status, first, _ = self.request("POST", "/api/analyze", example)
        status2, second, _ = self.request("POST", "/api/analyze", example)
        self.assertEqual((status, status2), (200, 200))
        first_obj, second_obj = json.loads(first), json.loads(second)
        self.assertEqual(first_obj, second_obj)
        self.assertEqual(first_obj["status"], "VALID")
        example["mode"] = "INTERNAL_AUTHORIZED"
        status, body, _ = self.request("POST", "/api/analyze", example)
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["status"], "REFUSED")

    def test_api_rejects_bad_json_shape_and_missing_route(self):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=3)
        connection.request("POST", "/api/analyze", "[]", {"Content-Type": "application/json"})
        response = connection.getresponse()
        self.assertEqual(response.status, 400)
        response.read()
        connection.close()
        status, _, _ = self.request("GET", "/does-not-exist")
        self.assertEqual(status, 404)

    def test_api_requires_utf8_json(self):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=3)
        connection.request("POST", "/api/analyze", b"\xff", {"Content-Type": "application/json"})
        response = connection.getresponse()
        self.assertEqual(response.status, 400)
        self.assertIn(b"valid UTF-8", response.read())
        connection.close()

    def test_cancel_request_is_bounded_and_stops_matching_analysis(self):
        request_id = "fb2a26c4-1a11-4a22-8d11-5c1ab7ad1111"
        status, body, _ = self.request("POST", "/api/cancel", {"request_id": request_id})
        self.assertEqual(status, 202)
        self.assertEqual(json.loads(body)["status"], "CANCEL_REQUESTED")
        example = json.loads((ROOT / "fixtures" / "case_positive.json").read_text())
        status, body, _ = self.request("POST", "/api/analyze", example, {"X-Analysis-Id": request_id})
        self.assertEqual(status, 409)
        self.assertEqual(json.loads(body)["status"], "CANCELLED")

    def test_api_rejects_cross_origin_posts(self):
        example = json.loads((ROOT / "fixtures" / "case_positive.json").read_text())
        status, body, _ = self.request("POST", "/api/analyze", example,
                                       {"Origin": "https://untrusted.example", "Sec-Fetch-Site": "cross-site"})
        self.assertEqual(status, 403)
        self.assertIn("cross-origin", json.loads(body)["error"])


if __name__ == "__main__":
    unittest.main()
