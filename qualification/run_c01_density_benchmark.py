"""Paired synthetic C01 local-pattern benchmark against the frozen raw screen."""
from __future__ import annotations

import json
import math
from pathlib import Path
import sys
from time import perf_counter
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from products.p3.engine import _local_clusters, _prepare_map, fingerprint  # noqa: E402
from qualification.engineer_challenge import build_dense_c01_challenge, dense_c01_ground_truth  # noqa: E402


def _candidate_site_ids(data: dict[str, Any], result: dict[str, Any]) -> set[str]:
    grid_size = result["grid_size"]
    radius = data["geometry"]["radius"]
    cells = {tuple(cell) for group in result["clusters"] for cell in group["grid_cells"]}
    selected = set()
    for point in data["points"]:
        cell = (
            min(grid_size - 1, max(0, int((point["x"] / radius + 1) * grid_size / 2))),
            min(grid_size - 1, max(0, int((point["y"] / radius + 1) * grid_size / 2))),
        )
        if cell in cells:
            selected.add(point["site_id"])
    return selected


def _measure(data: dict[str, Any], result: dict[str, Any], *, planted: bool) -> dict[str, float | bool]:
    selected = _candidate_site_ids(data, result)
    truth = set(dense_c01_ground_truth(data)["anomalous_site_ids"])
    if not planted:
        return {"has_candidate": bool(result["clusters"]), "recall": 0.0, "precision": 0.0}
    true_positive = selected & truth
    return {
        "has_candidate": bool(result["clusters"]),
        "recall": len(true_positive) / len(truth) if truth else 0.0,
        "precision": len(true_positive) / len(selected) if selected else 0.0,
    }


def _summarize(records: list[dict[str, float | bool]]) -> dict[str, float | int]:
    count = len(records)
    return {
        "seeded_maps": count,
        "maps_with_any_candidate": sum(bool(row["has_candidate"]) for row in records),
        "mean_planted_site_recall": round(sum(float(row["recall"]) for row in records) / count, 4),
        "mean_candidate_site_precision_across_seeded_maps": round(
            sum(float(row["precision"]) for row in records) / count, 4),
    }


def run(seed_start: int = 73_000, seed_count: int = 80) -> dict[str, Any]:
    if seed_count < 1:
        raise ValueError("seed_count must be positive")
    results: dict[str, Any] = {
        "scope": "independent synthetic C01 challenge; no manufacturing calibration",
        "baseline": "frozen raw observed-value same-radial-band MAD, fixed 32x32 cells",
        "candidate": "P3 density-gated OLS plane residuals, same-radial-band MAD, adaptive 8-32 grid with 16-cell resolution fallback when needed",
        "generator": "qualification.engineer_challenge.build_dense_c01_challenge",
        "seed_start": seed_start,
        "seed_count_per_condition": seed_count,
        "conditions": {},
        "interpretation": "Candidate groups are exploratory descriptions, not alerts, p-values, or production guarantees.",
    }
    started = perf_counter()
    for missing_fraction in (0.0, 0.4):
        key = f"random_missing_{int(missing_fraction * 100)}_percent"
        metrics = {method: {"null": [], "planted": []} for method in ("baseline", "candidate")}
        for seed in range(seed_start, seed_start + seed_count):
            for planted in (False, True):
                data = build_dense_c01_challenge(seed, plant_local_shift=planted,
                                                 random_missing_fraction=missing_fraction)
                prepared = _prepare_map(data)
                baseline = _local_clusters(prepared["points"], prepared["radius"],
                                           prepared["orientation_deg"], grid_size=32)
                candidate = fingerprint(data)["local_clusters"]
                condition = "planted" if planted else "null"
                metrics["baseline"][condition].append(_measure(data, baseline, planted=planted))
                metrics["candidate"][condition].append(_measure(data, candidate, planted=planted))
        results["conditions"][key] = {
            method: {condition: _summarize(rows) for condition, rows in groups.items()}
            for method, groups in metrics.items()
        }
    results["elapsed_seconds"] = round(perf_counter() - started, 3)
    return results


if __name__ == "__main__":
    print(json.dumps(run(), indent=2, sort_keys=True))
