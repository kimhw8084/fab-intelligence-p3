"""Run synthetic independent-oracle and timing benchmarks; writes no company data."""
from __future__ import annotations

import hashlib
import json
import math
import platform
import random
import statistics
import sys
import time
import tracemalloc
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from fabintel.catalog import synthetic_catalog
from products.p3.engine import fingerprint

SEED = 20261122
CASE_COUNT = 100
SITES_PER_CASE = 13


def make_case(seed):
    rng = random.Random(seed)
    points = []
    for i in range(3):
        points.append({"site_id": f"C{i}", "x": (i - 1) * 0.08, "y": 0.04, "value": rng.uniform(-8, 8)})
    for i in range(4):
        angle = i * math.pi / 2
        points.append({"site_id": f"E{i}", "x": math.cos(angle), "y": math.sin(angle), "value": rng.uniform(-8, 8) + 3})
    for i in range(6):
        angle = i * math.pi / 3
        radius = 0.35 + 0.25 * (i % 2)
        points.append({"site_id": f"M{i}", "x": radius * math.cos(angle), "y": radius * math.sin(angle), "value": rng.uniform(-8, 8)})
    return {
        "coordinates_verified": True,
        "geometry": {"radius": 1, "origin": {"x": 0, "y": 0}, "orientation_deg": 0, "coordinate_system": "wafer_xy_v1", "coordinate_unit": "mm"},
        "points": points,
        "measurement": {"metric": "m", "unit": "nm", "modality": "continuous", "definition_id": "D1", "layer": "L1"},
        "product_id": "P1", "sampling_mask_id": "M1", "population_signature": "S1",
    }


def make_dense_case(count=13_000):
    golden = math.pi * (3 - math.sqrt(5))
    points = []
    for i in range(count):
        radius = math.sqrt((i + 0.5) / count)
        angle = i * golden
        x, y = radius * math.cos(angle), radius * math.sin(angle)
        value = 10 + 1.75 * radius + 0.2 * math.sin(4 * angle)
        points.append({"site_id": f"D{i}", "x": x, "y": y, "value": value})
    return {
        "coordinates_verified": True,
        "geometry": {"radius": 1, "origin": {"x": 0, "y": 0}, "orientation_deg": 0, "coordinate_system": "wafer_xy_v1", "coordinate_unit": "mm"},
        "points": points,
        "measurement": {"metric": "m", "unit": "nm", "modality": "continuous", "definition_id": "D1", "layer": "L1"},
        "product_id": "P1", "sampling_mask_id": "M1", "population_signature": "S1",
    }


def oracle(data):
    center, edge = [], []
    for point in data["points"]:
        radius = math.sqrt(point["x"] ** 2 + point["y"] ** 2)
        if radius <= 0.2:
            center.append(point["value"])
        elif radius >= 0.8:
            edge.append(point["value"])
    return sum(edge) / len(edge) - sum(center) / len(center)


def percentile(values, q):
    values = sorted(values)
    return values[min(len(values) - 1, max(0, math.ceil(q * len(values)) - 1))]


def source_tree_hash():
    items = []
    generated = {"release/BOOTSTRAP_MANIFEST.sha256", "release/SCIENTIFIC_PERFORMANCE_BENCHMARK.json",
                 "release/GATE_REPORT.json", "release/PACKAGE_QUALIFICATION.json",
                 "release/LOCAL_TEST_EVIDENCE.json", "release/LOCAL_TEST_LOG.txt",
                 "release/CRITICAL_CASE_EVIDENCE.json", "release/SBOM.spdx.json",
                 "release/SUPPLY_CHAIN_AUDIT.json"}
    for path in sorted(ROOT.rglob("*")):
        if path.is_file() and "__pycache__" not in path.parts and path.suffix not in (".pyc",):
            rel = path.relative_to(ROOT).as_posix()
            if rel in generated or rel.endswith((".zip", ".sha256")):
                continue
            items.append(rel.encode() + b"\0" + hashlib.sha256(path.read_bytes()).digest())
    return hashlib.sha256(b"".join(items)).hexdigest()


def main():
    dataset = [make_case(SEED + i) for i in range(CASE_COUNT)]
    cases = []
    durations = []
    for index, data in enumerate(dataset):
        expected = oracle(data)
        start = time.perf_counter_ns()
        result = fingerprint(data)
        durations.append((time.perf_counter_ns() - start) / 1_000_000)
        passed = math.isclose(result["edge_minus_center"], expected, rel_tol=1e-12, abs_tol=1e-12)
        cases.append({"case": index, "seed": SEED + index, "expected_edge_minus_center": expected,
                      "actual_edge_minus_center": result["edge_minus_center"], "status": "PASS" if passed else "FAIL"})
    tracemalloc.start()
    catalog = synthetic_catalog(13_000)
    _, catalog_peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    catalog_pass = len(catalog) == 13_000 and len({item["id"] for item in catalog}) == 13_000
    dense = make_dense_case()
    dense_expected = oracle(dense)
    dense_durations = []
    for _ in range(50):
        start = time.perf_counter_ns()
        dense_result = fingerprint(dense)
        dense_durations.append((time.perf_counter_ns() - start) / 1_000_000)
    tracemalloc.start()
    fingerprint(dense)
    _, dense_peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    dense_pass = math.isclose(dense_result["edge_minus_center"], dense_expected, rel_tol=1e-12, abs_tol=1e-12)
    report = {
        "scope": "synthetic external baseline only",
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "environment": {"os": platform.platform(), "architecture": platform.machine(), "python": sys.version,
                        "cpu_count": __import__("os").cpu_count(), "processor": platform.processor()},
        "seed": SEED,
        "fixed_cases": CASE_COUNT,
        "sites_per_case": SITES_PER_CASE,
        "numeric_oracle": {"method": "independent measured-point center/edge arithmetic", "passed": sum(c["status"] == "PASS" for c in cases),
                           "failed": sum(c["status"] == "FAIL" for c in cases), "cases": cases},
        "latency_ms": {"p50": statistics.median(durations), "p95": percentile(durations, 0.95), "samples": len(durations)},
        "synthetic_catalog": {"requested_tables": 13000, "actual_tables": len(catalog), "unique_ids": len({item["id"] for item in catalog}),
                              "peak_traced_bytes": catalog_peak, "status": "PASS" if catalog_pass else "FAIL"},
        "dense_wafer_measurement": {"measured_sites": len(dense["points"]), "p50_ms": statistics.median(dense_durations),
                                     "p95_ms": percentile(dense_durations, 0.95), "peak_traced_bytes": dense_peak,
                                     "expected_edge_minus_center": dense_expected, "actual_edge_minus_center": dense_result["edge_minus_center"],
                                     "status": "PASS" if dense_pass else "FAIL"},
        "thresholds": "No absolute latency, memory, ROI or user-time target was invented; set thresholds after target-hardware and real analyst baseline measurement.",
        "company_data_used": False,
        "source_tree_sha256": source_tree_hash(),
        "overall": "PASS" if all(c["status"] == "PASS" for c in cases) and catalog_pass and dense_pass else "FAIL",
    }
    out = ROOT / "release" / "SCIENTIFIC_PERFORMANCE_BENCHMARK.json"
    out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"{report['overall']}: {report['numeric_oracle']['passed']}/{CASE_COUNT} numeric oracle cases; "
          f"catalog {len(catalog)}; p50 {report['latency_ms']['p50']:.3f} ms; p95 {report['latency_ms']['p95']:.3f} ms")
    print(f"Wrote {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
