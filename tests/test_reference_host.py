import hashlib
import importlib.util
import json
import os
import re
import threading
import time
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from fabintel.mcp_client import MCPDependencyError
from fabintel.reference_host import _Handler


@unittest.skipUnless(importlib.util.find_spec("mcp"), "install the local hash-locked MCP SDK candidate to run host acceptance")
class ReferenceHostAcceptanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        cls.server.daemon_threads = True
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.port = cls.server.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def request(self, method, path, body=None, headers=None, timeout=20):
        connection = HTTPConnection("127.0.0.1", self.port, timeout=timeout)
        payload = None if body is None else json.dumps(body)
        request_headers = {"Content-Type": "application/json"} if payload is not None else {}
        request_headers.update(headers or {})
        connection.request(method, path, payload, request_headers)
        response = connection.getresponse()
        result = response.status, response.read(), dict(response.getheaders())
        connection.close()
        return result

    def test_host_serves_local_assets_and_health_without_remote_resources(self):
        status, body, headers = self.request("GET", "/api/health")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["network"], "not used for synthetic mode")
        self.assertIn("no-store", headers["Cache-Control"])
        status, html, _headers = self.request("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn(b"Spatial &amp; Yield", html)
        status, _js, js_headers = self.request("GET", "/assets/placeholder.js")
        self.assertEqual(status, 404)
        self.assertIn("default-src 'self'", js_headers["Content-Security-Policy"])

    def test_full_sdk_workflow_returns_typed_map_c01_to_c05_and_hashable_evidence(self):
        status, body, headers = self.request("POST", "/api/investigate", {
            "source_mode": "synthetic", "plan_ids": ["SYN-WF-CURRENT", "SYN-WF-PREVIOUS", "SYN-WF-BASELINE",
                                                          "SYN-WF-HISTORY", "SYN-WF-ASSOCIATION"],
            "time_start": "2026-01-01T00:00:00Z", "time_end": "2026-02-01T00:00:00Z", "top_k": 5,
        }, {"X-Analysis-Id": "624b7a32-a9c9-46c5-8745-818d2f000001"})
        self.assertEqual(status, 200, body.decode())
        self.assertIn("no-store", headers["Cache-Control"])
        module = json.loads(body)
        self.assertEqual(module["contract_version"], "p3-reference-module.v2")
        self.assertEqual(module["capabilities"], ["C01", "C02", "C03", "C04", "C05"])
        self.assertEqual(module["evidence"]["mode"], "SYNTHETIC_DEMO")
        result = module["evidence"]["artifacts"][0]["result"]
        self.assertEqual({key: result[key]["status"] for key in
                          ("fingerprint", "evolution", "quality_association", "anomaly", "similarity")},
                         {"fingerprint": "VALID", "evolution": "VALID", "quality_association": "VALID",
                          "anomaly": "VALID", "similarity": "VALID"})
        spatial = module["spatial_map"]
        import jsonschema
        schema = json.loads((Path(__file__).resolve().parents[1] / "products" / "p3" / "contracts" / "spatial-map.v2.schema.json").read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator(schema).validate(spatial)
        self.assertEqual(spatial["schema_version"], "fab-spatial-map.v2")
        self.assertEqual(spatial["sampling"]["observation_count"], len(spatial["observations"]))
        self.assertEqual([row["value"] for row in spatial["observations"]], [10, 12, 12, 12, 12])
        historical = module["historical_spatial_map"]
        self.assertEqual(historical["wafer_id"], "SYN-W-HIST")
        self.assertEqual(historical["schema_version"], "fab-spatial-map.v2")
        self.assertEqual(historical["sampling"]["observation_count"], 5)
        self.assertEqual(historical["interpolation"], "none")
        self.assertEqual(module["export_content"]["historical_spatial_map"], historical)
        self.assertEqual(len(module["evidence"]["provenance"]["mcp_workflow"]["bounded_reads"]), 5)
        canonical = module["export"]["canonical_json"].encode("utf-8")
        self.assertEqual(hashlib.sha256(canonical).hexdigest(), module["export"]["sha256"])
        self.assertEqual(json.loads(canonical)["contract_version"], "p3-reference-module.v2")

    def test_engineer_challenge_runs_all_capabilities_against_independent_ground_truth(self):
        from qualification.engineer_challenge import build, ground_truth
        truth = ground_truth(build())
        request = {"source_mode": "synthetic", "plan_ids": ["SYN-WF-CURRENT", "SYN-WF-PREVIOUS",
                    "SYN-WF-BASELINE", "SYN-WF-HISTORY", "SYN-WF-ASSOCIATION"],
                   "time_start": "2026-01-01T00:00:00Z", "time_end": "2026-02-01T00:00:00Z",
                   "top_k": 5}
        with patch.dict(os.environ, {"FABINTEL_SYNTHETIC_SCENARIO": "engineer-challenge"}):
            status, body, _headers = self.request("POST", "/api/investigate", request)
        self.assertEqual(status, 200, body.decode())
        module = json.loads(body)
        self.assertEqual(module["evidence"]["status"], "VALID")
        self.assertEqual(module["spatial_map"]["geometry"]["radius"], truth["target"]["physical_radius_mm"])
        self.assertEqual(module["spatial_map"]["sampling"]["observation_count"], truth["target"]["observed_sites"])
        self.assertEqual(len(module["evidence"]["provenance"]["mcp_workflow"]["bounded_reads"]), 5)
        analysis = module["evidence"]["artifacts"][0]["result"]
        self.assertEqual([analysis[key]["status"] for key in
                          ("fingerprint", "evolution", "quality_association", "anomaly", "similarity")],
                         ["VALID"] * 5)
        fingerprint = analysis["fingerprint"]
        self.assertAlmostEqual(fingerprint["edge_center"]["difference"],
                               truth["planted_signatures"]["edge_center_delta_nm"], delta=0.01)
        clusters = fingerprint["local_clusters"]["clusters"]
        self.assertEqual(len(clusters), 1)
        self.assertEqual(clusters[0]["observed_site_count"], 8)
        self.assertEqual(fingerprint["local_clusters"]["reference_method"], "same_radial_band_median_and_MAD")
        target_cell = next(row for row in fingerprint["local_clusters"]["cells"] if row["count"] == 8)
        self.assertLess(abs(target_cell["robust_z_vs_global_median"]), 3.5,
                        "the frozen global scale would have screened out the planted local signature")
        self.assertGreater(abs(target_cell["robust_z_vs_radial_reference"]), 3.5)
        from products.p3.engine import fingerprint as calculate_fingerprint
        normal_candidates = [calculate_fingerprint(baseline)["local_clusters"]["clusters"]
                             for baseline in build()["baseline_population"]]
        self.assertEqual(sum(bool(rows) for rows in normal_candidates), 0,
                         "the planted target improvement should not mark these 20 synthetic null maps")
        self.assertEqual(len(analysis["evolution"]["step_sequence"]), 3)
        comparisons = analysis["evolution"]["comparisons"]
        self.assertEqual([row["matched_sites"] for row in comparisons],
                         truth["evolution"]["common_sites_by_transition"])
        self.assertEqual([round(row["mean_delta"], 6) for row in analysis["evolution"]["comparisons"]],
                         truth["evolution"]["expected_mean_change_nm"])
        self.assertAlmostEqual(comparisons[0]["coverage"]["previous"], 44 / 48)
        self.assertAlmostEqual(comparisons[1]["coverage"]["current"], 44 / 48)
        association = analysis["quality_association"]
        low, high = association["fisher_wafer_95_ci"]
        self.assertLessEqual(low, 0)
        self.assertGreaterEqual(high, 0)
        self.assertEqual(association["independent_lots"], truth["quality"]["distinct_lots"])
        self.assertAlmostEqual(analysis["anomaly"]["global_max_t_empirical_p"],
                               truth["anomaly"]["minimum_rank_p"])
        match = analysis["similarity"]["neighbors"][0]
        self.assertEqual(match["wafer_id"], "SYN-W-ENG-HIST-MATCH")
        self.assertTrue(match["sampling_mask_changed"])
        self.assertEqual(match["target_observed_site_count"], 48)
        self.assertEqual(match["candidate_observed_site_count"], 44)
        sparse_analog = next(row for row in analysis["similarity"]["neighbors"]
                             if row["wafer_id"] == "SYN-W-ENG-HIST-SPARSE")
        self.assertEqual(sparse_analog["candidate_observed_site_count"],
                         truth["historical"]["sparse_analog_observed_sites"])
        self.assertEqual(sparse_analog["alignment"], "common radial/sector/radial-sector profile descriptors; no reconstruction")
        excluded = {row.get("wafer_id") for row in analysis["similarity"].get("excluded", [])}
        self.assertTrue(any("WRONG-PRODUCT" in str(value) for value in excluded))
        self.assertTrue(any("FUTURE" in str(value) for value in excluded))

        family_request = {**request, "anomaly_target_family": {
            "family_id": "SYN-C04-FAMILY-2", "family_size": 2,
            "selection_rule_id": "SYN-FIXED-TARGET-ROSTER", "predeclared": True, "complete": True}}
        with patch.dict(os.environ, {"FABINTEL_SYNTHETIC_SCENARIO": "engineer-challenge"}):
            family_status, family_body, _headers = self.request("POST", "/api/investigate", family_request)
        self.assertEqual(family_status, 200, family_body.decode())
        family_module = json.loads(family_body)
        family_analysis = family_module["evidence"]["artifacts"][0]["result"]
        self.assertEqual(family_module["evidence"]["status"], "PARTIAL")
        self.assertEqual(family_analysis["anomaly"]["status"], "INCONCLUSIVE")
        self.assertEqual(family_analysis["anomaly"]["repeated_target_adjustment"], "BONFERRONI")
        self.assertAlmostEqual(family_analysis["anomaly"]["alpha"], 0.025)
        self.assertEqual([family_analysis[key]["status"] for key in
                          ("fingerprint", "evolution", "quality_association", "similarity")], ["VALID"] * 4)

    def test_dense_c01_challenge_crosses_the_synthetic_mcp_boundary(self):
        request = {"source_mode": "synthetic", "plan_ids": ["SYN-WF-CURRENT", "SYN-WF-PREVIOUS",
                    "SYN-WF-BASELINE", "SYN-WF-HISTORY", "SYN-WF-ASSOCIATION"],
                   "time_start": "2026-01-01T00:00:00Z", "time_end": "2026-02-01T00:00:00Z",
                   "top_k": 5}
        with patch.dict(os.environ, {"FABINTEL_SYNTHETIC_SCENARIO": "c01-dense-challenge"}):
            status, body, _headers = self.request("POST", "/api/investigate", request)
        self.assertEqual(status, 200, body.decode())
        module = json.loads(body)
        spatial_map = module["spatial_map"]
        self.assertGreater(spatial_map["sampling"]["observation_count"], 600)
        self.assertLess(spatial_map["sampling"]["observation_count"], spatial_map["sampling"]["expected_site_count"])
        self.assertEqual(len(module["evidence"]["provenance"]["mcp_workflow"]["bounded_reads"]), 5)
        fingerprint = module["evidence"]["artifacts"][0]["result"]["fingerprint"]
        self.assertEqual(fingerprint["local_clusters"]["screening_adjustment"]["status"], "APPLIED")
        self.assertEqual(fingerprint["local_clusters"]["grid_size"], 16)
        self.assertGreater(len(fingerprint["local_clusters"]["clusters"]), 0)

    def test_categorical_missing_and_defect_modalities_survive_the_host_and_v2_schema(self):
        import jsonschema
        schema = json.loads((Path(__file__).resolve().parents[1] / "products" / "p3" / "contracts" / "spatial-map.v2.schema.json").read_text(encoding="utf-8"))
        request = {"source_mode": "synthetic", "plan_ids": ["SYN-WF-CURRENT"]}
        cases = (("typed-categorical", ["PASS", 2, "FAIL", "PASS", 3]),
                 ("explicit-missing", [10, None, 12, 12, 12]),
                 ("typed-defect", ["BRIDGE", 7, None, None, None]))
        for scenario, expected_values in cases:
            with self.subTest(scenario=scenario), patch.dict(os.environ, {"FABINTEL_SYNTHETIC_SCENARIO": scenario}):
                status, body, _headers = self.request("POST", "/api/investigate", request)
            self.assertEqual(status, 200, body.decode())
            module = json.loads(body)
            spatial = module["spatial_map"]
            jsonschema.Draft202012Validator(schema).validate(spatial)
            observations = spatial["observations"]
            self.assertEqual([item["value"] for item in observations], expected_values)
            self.assertEqual(len(observations), spatial["sampling"]["observation_count"])
            if scenario == "typed-categorical":
                self.assertEqual(spatial["sampling"]["categorical_measurement_count"], 5)
                self.assertEqual(type(observations[1]["value"]), int)
                self.assertEqual(module["suite_compatibility"]["status"], "COMPATIBLE")
            elif scenario == "explicit-missing":
                self.assertEqual(spatial["sampling"]["explicit_missing_value_count"], 1)
                self.assertEqual(observations[1]["observation_kind"], "MISSING_MEASUREMENT")
            else:
                self.assertEqual(spatial["sampling"]["defect_event_count"], 5)
                self.assertEqual(spatial["sampling"]["explicit_missing_value_count"], 0)
                self.assertEqual(observations[2]["observation_kind"], "DEFECT_EVENT")
                self.assertEqual(module["suite_compatibility"]["status"], "UNREPRESENTABLE_WITHOUT_LOSS")

    def test_configured_mode_without_site_configuration_is_refused(self):
        with patch.dict(os.environ, {"FABINTEL_MCP_CONFIG": ""}):
            status, body, _headers = self.request("POST", "/api/investigate", {
                "source_mode": "configured", "plan_ids": ["SITE-APPROVED-PLAN"],
            })
        self.assertEqual(status, 403)
        self.assertEqual(json.loads(body)["status"], "REFUSED")

    def test_peer_permission_denial_and_stale_semantics_fail_closed(self):
        request = {"source_mode": "synthetic", "plan_ids": ["SYN-WF-CURRENT"]}
        with patch.dict(os.environ, {"FABINTEL_SYNTHETIC_SCENARIO": "read-denied"}):
            status, body, _headers = self.request("POST", "/api/investigate", request)
        self.assertEqual(status, 403)
        self.assertEqual(json.loads(body)["status"], "REFUSED")
        with patch.dict(os.environ, {"FABINTEL_SYNTHETIC_SCENARIO": "stale-semantics"}):
            status, body, _headers = self.request("POST", "/api/investigate", request)
        self.assertEqual(status, 422)
        self.assertEqual(json.loads(body)["status"], "REFUSED")

    def test_http_cancellation_stops_the_sdk_read_without_partial_success(self):
        request_id = "6c8690f0-906d-46a5-a63f-e380a8b00002"
        result = []
        worker = threading.Thread(target=lambda: result.append(self.request("POST", "/api/investigate", {
            "source_mode": "synthetic", "plan_ids": ["SYN-WF-CURRENT-CANCEL"],
        }, {"X-Analysis-Id": request_id}, timeout=8)))
        worker.start()
        deadline = time.monotonic() + 3
        from fabintel import reference_host
        while request_id not in reference_host._ACTIVE and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertIn(request_id, reference_host._ACTIVE)
        status, body, _headers = self.request("POST", "/api/cancel", {"request_id": request_id})
        self.assertEqual(status, 202)
        self.assertEqual(json.loads(body)["status"], "CANCEL_REQUESTED")
        worker.join(timeout=9)
        self.assertFalse(worker.is_alive())
        self.assertEqual(result[0][0], 409)
        self.assertEqual(json.loads(result[0][1])["status"], "CANCELLED")

    def test_cross_origin_and_unbounded_requests_are_rejected(self):
        request = {"source_mode": "synthetic", "plan_ids": ["SYN-WF-CURRENT"]}
        status, body, _headers = self.request("POST", "/api/investigate", request,
                                               {"Origin": "https://attacker.invalid", "Sec-Fetch-Site": "cross-site"})
        self.assertEqual(status, 403)
        self.assertIn("cross-origin", json.loads(body)["error"])
        status, body, _headers = self.request("POST", "/api/investigate", {**request, "plan_ids": ["X"] * 11})
        self.assertEqual(status, 400)
        self.assertIn("bounded limits", json.loads(body)["error"])


class MissingSDKReferenceHostTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        cls.server.daemon_threads = True
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.port = cls.server.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def test_missing_sdk_returns_an_actionable_offline_install_error(self):
        with patch("fabintel.reference_host._create_adapter",
                   side_effect=MCPDependencyError("do not expose implementation detail")):
            connection = HTTPConnection("127.0.0.1", self.port, timeout=5)
            connection.request("POST", "/api/investigate", json.dumps({
                "source_mode": "synthetic", "plan_ids": ["SYN-WF-CURRENT"],
            }), {"Content-Type": "application/json", "X-Analysis-Id": "6c8690f0-906d-46a5-a63f-e380a8b00007"})
            response = connection.getresponse()
            status, body = response.status, response.read()
            connection.close()
        self.assertEqual(status, 503)
        error = json.loads(body)
        self.assertEqual(error["status"], "ERROR")
        self.assertIn("hash-locked bundle", error["reason"])
        self.assertNotIn("implementation detail", error["reason"])


class ReferenceHostAccessibilityStyleTests(unittest.TestCase):
    def test_small_text_controls_and_keyboard_focus_meet_contrast_thresholds(self):
        css = (Path(__file__).resolve().parents[1] / "products" / "p3" / "reference_host" / "src" / "style.css").read_text(encoding="utf-8")
        rules = {selector.strip(): body for selector, body in re.findall(r"([^{}]+)\{([^{}]+)\}", css)}

        def color(selector, property_name):
            match = re.search(rf"\b{re.escape(property_name)}\s*:[^;]*?(#[0-9a-fA-F]{{6}})", rules[selector])
            self.assertIsNotNone(match, f"Missing {property_name} color in {selector}")
            return match.group(1)

        def luminance(value):
            channels = []
            for offset in (1, 3, 5):
                channel = int(value[offset:offset + 2], 16) / 255
                channels.append(channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4)
            return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]

        def contrast(foreground, background):
            light, dark = sorted((luminance(foreground), luminance(background)), reverse=True)
            return (light + 0.05) / (dark + 0.05)

        eyebrow = color(".eyebrow", "color")
        focus = color("button:focus-visible, input:focus-visible, select:focus-visible, summary:focus-visible", "outline")
        field_border = color(".control-grid input, .control-grid select, .control-grid textarea", "border")
        tab_border = color(".capability-tabs button", "border")
        self.assertGreaterEqual(contrast(eyebrow, "#ffffff"), 4.5)
        for background in ("#ffffff", "#f2f5f8", "#f7f9fa", "#edf6fb"):
            self.assertGreaterEqual(contrast(focus, background), 3.0, f"Focus contrast on {background}")
        self.assertGreaterEqual(contrast(field_border, "#ffffff"), 3.0)
        self.assertGreaterEqual(contrast(tab_border, "#f7f9fa"), 3.0)


if __name__ == "__main__":
    unittest.main()
