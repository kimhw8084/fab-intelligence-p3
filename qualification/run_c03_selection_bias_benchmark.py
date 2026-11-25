"""Compare frozen C03 behavior with the outcome-blind-frame abstention guard.

The benchmark is synthetic. Its eligible wafers have independently generated
feature/outcome values; the selected holdout is then deliberately chosen after
observing within-wafer associations. Pass the frozen P3 source root with
``--baseline-root`` to run the same inputs through its actual engine.
"""
from __future__ import annotations

import argparse
import json
import random
import subprocess  # nosec B404 - explicit local Python and caller-selected source root
import sys
from copy import deepcopy
from math import sqrt
from pathlib import Path
from statistics import mean
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from products.p3.engine import _physical_site_values, _prepare_map, associate_quality  # noqa: E402
from qualification.engineer_challenge import build  # noqa: E402

BASELINE_RUNNER = """
import json, sys
from products.p3.engine import associate_quality
payload = json.load(sys.stdin)
results = []
for case in payload:
    coordinates = {tuple(pair) for pair in case['expected_coordinates']}
    result = associate_quality(case['association'], case['expected_context'], coordinates)
    results.append({key: result.get(key) for key in ('status', 'mean_within_wafer_r', 'fisher_wafer_95_ci', 'reason')})
json.dump(results, sys.stdout, allow_nan=False)
"""


def _spatial_r(rows: list[dict[str, Any]]) -> float:
    by_block: dict[str, list[tuple[float, float]]] = {}
    for row in rows:
        by_block.setdefault(row["spatial_block_id"], []).append((row["feature_value"], row["outcome_value"]))
    residuals = []
    for pairs in by_block.values():
        x_mean = mean(pair[0] for pair in pairs)
        y_mean = mean(pair[1] for pair in pairs)
        residuals.extend((x - x_mean, y - y_mean) for x, y in pairs)
    xs = [pair[0] for pair in residuals]
    ys = [pair[1] for pair in residuals]
    x_mean, y_mean = mean(xs), mean(ys)
    ssx = sum((value - x_mean) ** 2 for value in xs)
    ssy = sum((value - y_mean) ** 2 for value in ys)
    return sum((x - x_mean) * (y - y_mean) for x, y in residuals) / sqrt(ssx * ssy)


def _case(seed: int, template: dict[str, Any], expected_context: dict[str, Any],
          expected_coordinates: set[tuple[float, float]]) -> dict[str, Any]:
    rng = random.Random(seed)
    candidate_wafers = []
    for wafer_index in range(80):
        rows = []
        for point in template["observations"][:48]:
            row = deepcopy(point)
            row["wafer_id"] = f"SEL-W-{seed}-{wafer_index:02d}"
            row["lot_id"] = f"SEL-L-{seed}-{wafer_index:02d}"
            row["feature_value"] = rng.gauss(0, 1)
            row["outcome_value"] = rng.gauss(0, 1)
            rows.append(row)
        candidate_wafers.append((_spatial_r(rows), rows))

    # Deliberately inspect outcome-dependent wafer correlations before selecting
    # the 20-wafer holdout. This is the bias mechanism under test.
    selected = sorted(candidate_wafers, key=lambda item: item[0], reverse=True)[:20]
    association = deepcopy(template)
    association["observations"] = [row for _, rows in selected for row in rows]
    association["cohort_selection"] = {
        "verified": True,
        "sampling_design": "OUTCOME_INFORMED_TOP_ASSOCIATION",
        "frame_id": f"SYN-POSTSELECTED-FRAME-{seed}",
        "eligibility_rule_id": "SYN-POST-OUTCOME-CORRELATION-RANK",
        "eligibility_rule_predeclared": False,
        "selection_blind_to_feature_and_outcome": False,
        "eligible_wafer_count": 80,
        "selected_wafer_count": 20,
    }
    return {"association": association, "expected_context": expected_context,
            "expected_coordinates": sorted([list(pair) for pair in expected_coordinates]),
            "selected_r_mean": mean(value for value, _ in selected)}


def run(baseline_root: Path, *, seed_start: int = 88_221, replicates: int = 40) -> dict[str, Any]:
    baseline_root = baseline_root.resolve()
    if not (baseline_root / "products/p3/engine.py").is_file():
        raise ValueError("--baseline-root must point to the frozen P3 source tree")
    if replicates < 1:
        raise ValueError("replicates must be positive")
    current = build()
    association = current["quality_association"]
    geometry = _prepare_map(current)
    context = {**association["context"], "coordinate_system": geometry["coordinate_system"],
               "coordinate_unit": geometry["coordinate_unit"], "radius": geometry["radius"],
               "orientation_deg": geometry["orientation_deg"]}
    coordinates = set(_physical_site_values(current))
    cases = [_case(seed, association, context, coordinates)
             for seed in range(seed_start, seed_start + replicates)]

    payload = [{key: case[key] for key in ("association", "expected_context", "expected_coordinates")} for case in cases]
    completed = subprocess.run([sys.executable, "-c", BASELINE_RUNNER], cwd=baseline_root, input=json.dumps(payload),
                               text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, timeout=60,
                               env={key: value for key, value in __import__("os").environ.items() if key != "PYTHONPATH"})  # nosec B603
    baseline_results = json.loads(completed.stdout)
    current_results = [associate_quality(case["association"], context, coordinates) for case in cases]
    baseline_positive_intervals = [item for item in baseline_results if item["status"] == "VALID"
                                   and item["fisher_wafer_95_ci"][0] > 0]
    current_refusals = [item for item in current_results if item["status"] == "INCONCLUSIVE"]
    return {
        "scope": "independent synthetic selection-bias challenge; no manufacturing validation",
        "generator": "80 candidates per seed; feature and outcome independently sampled per site; top 20 positive within-wafer correlations selected after outcome inspection",
        "seeds": {"start": seed_start, "count": replicates},
        "frozen_baseline": {"root": str(baseline_root), "valid_positive_associations": sum(item["status"] == "VALID" and item["mean_within_wafer_r"] > 0 for item in baseline_results),
                             "positive_nominal_intervals": len(baseline_positive_intervals),
                             "mean_reported_r": round(mean(item["mean_within_wafer_r"] for item in baseline_results
                                                             if item["status"] == "VALID"), 4)},
        "candidate": {"selection_frame_abstentions": len(current_refusals),
                       "expected_abstentions": replicates,
                       "reason_counts": {reason: sum(item.get("reason") == reason for item in current_refusals)
                                         for reason in sorted({item.get("reason") for item in current_refusals})}},
        "selected_null_wafer_r_mean": round(mean(case["selected_r_mean"] for case in cases), 4),
        "interpretation": "The frozen engine accepts outcome-selected cohorts when generic holdout declarations are asserted. The candidate requires an explicit reviewed complete, outcome-blind eligible frame and abstains on this unsupported selection design. This verifies a guard against missing/declared selection semantics, not truthfulness of an external source registry or causal validity.",
        "status": "PASS" if len(current_refusals) == replicates and all(item["status"] == "VALID" for item in baseline_results) else "FAIL",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline-root", type=Path, required=True)
    parser.add_argument("--replicates", type=int, default=40)
    args = parser.parse_args()
    print(json.dumps(run(args.baseline_root, replicates=args.replicates), indent=2, sort_keys=True))
