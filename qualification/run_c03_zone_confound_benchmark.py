"""Challenge C03 block adjustment with a process-zone common cause."""
from __future__ import annotations

import json
import math
import random
import sys
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from products.p3.engine import _physical_site_values, _prepare_map, associate_quality  # noqa: E402
from qualification.engineer_challenge import build  # noqa: E402


def correlation(xs: list[float], ys: list[float]) -> float:
    mx, my = mean(xs), mean(ys)
    ssx = sum((x - mx) ** 2 for x in xs)
    ssy = sum((y - my) ** 2 for y in ys)
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / math.sqrt(ssx * ssy)


def wilson(successes: int, total: int) -> list[float]:
    z = 1.959963984540054
    p = successes / total
    denom = 1 + z * z / total
    center = (p + z * z / (2 * total)) / denom
    radius = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denom
    return [center - radius, center + radius]


def run(*, seed_start: int = 20261123, replicates: int = 40) -> dict[str, Any]:
    if replicates < 1:
        raise ValueError("replicates must be positive")
    current = build()
    template = deepcopy(current["quality_association"])
    geometry = _prepare_map(current)
    expected_context = {**template["context"], "coordinate_system": geometry["coordinate_system"],
                        "coordinate_unit": geometry["coordinate_unit"], "radius": geometry["radius"],
                        "orientation_deg": geometry["orientation_deg"]}
    expected_coordinates = set(_physical_site_values(current))
    results = []
    pooled_correlations = []
    for replicate in range(replicates):
        rng = random.Random(seed_start + replicate)
        association = deepcopy(template)
        observations = []
        pooled_x, pooled_y = [], []
        for wafer_index in range(20):
            wafer_id = f"ZONE-W-{replicate:03d}-{wafer_index:02d}"
            lot_id = f"ZONE-L-{replicate:03d}-{wafer_index:02d}"
            zone_effects = {"SYN-RADIAL-INNER": rng.gauss(0, 2.5),
                            "SYN-RADIAL-OUTER": rng.gauss(0, 2.5)}
            for source_row in template["observations"][:48]:
                row = deepcopy(source_row)
                zone = row["spatial_block_id"]
                # A shared process-zone factor drives both columns between
                # blocks; independent residuals make the within-zone truth 0.
                x = 2.0 * zone_effects[zone] + rng.gauss(0, 0.8)
                y = 1.5 * zone_effects[zone] + rng.gauss(0, 0.8)
                row.update({"wafer_id": wafer_id, "lot_id": lot_id,
                            "feature_value": x, "outcome_value": y})
                observations.append(row)
                pooled_x.append(x)
                pooled_y.append(y)
        association["observations"] = observations
        result = associate_quality(association, expected_context, expected_coordinates)
        if result.get("status") == "VALID":
            interval = result["fisher_wafer_95_ci"]
            covers_zero = interval[0] <= 0 <= interval[1]
            results.append({"status": result["status"], "estimate": result["mean_within_wafer_r"],
                            "interval": interval, "covers_zero": covers_zero})
        else:
            results.append({"status": result.get("status"), "reason": result.get("reason"),
                            "covers_zero": False})
        pooled_correlations.append(correlation(pooled_x, pooled_y))

    valid = [row for row in results if row["status"] == "VALID"]
    covers = sum(row["covers_zero"] for row in valid)
    false_nonzero = sum(not row["covers_zero"] for row in valid)
    reasons = {reason: sum(row.get("reason") == reason for row in results)
               for reason in sorted({row.get("reason") for row in results if row.get("reason")})}
    report = {
        "schema": "p3-c03-zone-confounding-benchmark/v1",
        "created_utc": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "scope": "Synthetic C03 falsification challenge only; no manufacturing data or causal claim.",
        "ground_truth": "Within each predeclared spatial block, feature and downstream outcome residuals are independent. A shared process-zone effect drives both block means; this is a between-block confound, not a within-block association.",
        "design": {"replicates": replicates, "seed_start": seed_start, "wafers_per_replicate": 20,
                   "independent_lots_per_replicate": 20, "sites_per_wafer": len(template["observations"]) // 20,
                   "spatial_blocks": ["SYN-RADIAL-INNER", "SYN-RADIAL-OUTER"],
                   "complete_outcome_blind_eligible_frame": True, "feature_time_precedes_outcome": True},
        "candidate": {"valid_results": len(valid), "abstentions": replicates - len(valid),
                      "abstention_reasons": reasons,
                      "nominal_intervals_covering_zero": covers,
                      "nominal_intervals_excluding_zero": false_nonzero,
                      "interval_coverage_fraction": covers / len(valid) if valid else None,
                      "interval_coverage_wilson_95": wilson(covers, len(valid)) if valid else None,
                      "mean_within_wafer_r": mean(row["estimate"] for row in valid) if valid else None,
                      "mean_pooled_unadjusted_r": mean(pooled_correlations)},
        "interpretation": "The pooled correlation is induced by a known shared process-zone factor. C03 targets within-wafer association after predeclared spatial-block fixed effects; this benchmark evaluates that narrow estimand. It does not establish control of unmeasured confounding or causation.",
        "status": "PASS" if len(valid) == replicates and covers >= math.ceil(0.9 * replicates) else "FAIL",
        "company_data_used": False,
    }
    output = ROOT / "progress" / "C03_ZONE_CONFOUND_BENCHMARK.json"
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "valid": len(valid), "covers_zero": covers,
                      "mean_within_wafer_r": report["candidate"]["mean_within_wafer_r"],
                      "mean_pooled_unadjusted_r": report["candidate"]["mean_pooled_unadjusted_r"],
                      "output": str(output)}, indent=2))
    if report["status"] != "PASS":
        raise SystemExit(1)
    return report


if __name__ == "__main__":
    run()
