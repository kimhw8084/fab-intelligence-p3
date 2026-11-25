"""Measure per-target and repeated-target C04 null behavior on synthetic maps."""
from __future__ import annotations

import json
import math
from pathlib import Path
import random
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from products.p3.engine import detect_anomalies  # noqa: E402
from qualification.run_scientific_benchmark import SEED, _anomaly_map, _wilson_interval  # noqa: E402


def _family_cluster_bootstrap(rates: list[float], seed: int, replicates: int = 10_000) -> list[float] | None:
    """Percentile interval resampling independent shared-baseline families."""
    if not rates:
        return None
    rng = random.Random(seed)
    means = sorted(sum(rates[rng.randrange(len(rates))] for _ in rates) / len(rates)
                   for _ in range(replicates))
    return [means[math.floor(0.025 * (replicates - 1))],
            means[math.floor(0.975 * (replicates - 1))]]


def run(*, families: int = 20, targets_per_family: int = 20, baseline_wafers: int = 20) -> dict[str, Any]:
    if not 1 <= families <= 500 or not 1 <= targets_per_family <= 500 or baseline_wafers != 20:
        raise ValueError("benchmark bounds are families 1-500, targets 1-500, and exactly 20 baseline wafers")
    noise_families = ("gaussian", "student_t3")
    by_noise: dict[str, dict[str, Any]] = {}
    for noise_index, noise_family in enumerate(noise_families):
        per_target_alerts = family_alerts = valid_targets = stability_abstentions = complete_families = 0
        p_values: list[float] = []
        family_target_alert_rates: list[float] = []
        for family_index in range(families):
            family_id = noise_index * families + family_index
            baseline_rng = random.Random(SEED + 1_900_000 + family_id)  # nosec B311
            baseline = [_anomaly_map(family_id, index, noise_family, baseline_rng)
                        for index in range(baseline_wafers)]
            has_alert = False
            alerts_in_family = 0
            family_incomplete = False
            target_rng = random.Random(SEED + 2_000_000 + family_id)  # nosec B311
            for target_index in range(targets_per_family):
                source_index = baseline_wafers + target_index
                target = _anomaly_map(family_id + families, source_index, noise_family, target_rng)
                result = detect_anomalies(target, baseline, holdout_verified=True)
                if result.get("status") == "INCONCLUSIVE":
                    if result.get("baseline_temporal_stability", {}).get("status") == "INCONCLUSIVE":
                        stability_abstentions += 1
                        family_incomplete = True
                        continue
                    raise AssertionError(f"C04 repeated-target {noise_family} case abstained for an unrelated reason")
                if result.get("status") != "VALID":
                    raise AssertionError(f"C04 repeated-target {noise_family} case returned {result.get('status')}")
                valid_targets += 1
                p_values.append(float(result["global_max_t_empirical_p"]))
                if result["global_max_t_empirical_p"] <= result["alpha"]:
                    per_target_alerts += 1
                    alerts_in_family += 1
                    has_alert = True
            if not family_incomplete:
                complete_families += 1
                family_alerts += has_alert
                family_target_alert_rates.append(alerts_in_family / targets_per_family)
        denominator = valid_targets
        by_noise[noise_family] = {
            "baseline_wafers_per_family": baseline_wafers,
            "families_with_shared_fixed_baseline": families,
            "null_targets_per_family": targets_per_family,
            "valid_null_target_analyses": valid_targets,
            "baseline_stability_abstentions": stability_abstentions,
            "per_target_alerts": per_target_alerts,
            "per_target_alert_rate": per_target_alerts / denominator if denominator else None,
            "per_target_alert_rate_family_cluster_bootstrap_95": _family_cluster_bootstrap(
                family_target_alert_rates, SEED + 3_000_000 + noise_index),
            "per_target_interval_method": "10,000 percentile bootstrap resamples of independent shared-baseline families; targets within each family stay together",
            "families_in_per_target_interval": len(family_target_alert_rates),
            "complete_families_for_familywise_rate": complete_families,
            "incomplete_families_with_stability_abstention": families - complete_families,
            "complete_families_with_at_least_one_alert": family_alerts,
            "observed_family_alert_rate": family_alerts / complete_families if complete_families else None,
            "family_alert_rate_wilson_95": _wilson_interval(family_alerts, complete_families) if complete_families else None,
            "minimum_attainable_p": 1 / (baseline_wafers + 1),
            "target_alpha": 0.05,
            "p_value_counts": {str(value): p_values.count(value) for value in sorted(set(p_values))},
        }
    return {
        "scope": "independent synthetic C04 repeated-target null study; no manufacturing calibration",
        "method": "fixed baseline is reused for multiple independent null target wafers; each target runs the unchanged leave-one-wafer-out spatial max-T rank screen",
        "exchangeability_oracle": {
            "per_target_alert_probability": 1 / (baseline_wafers + 1),
            "familywise_any_alert_probability": targets_per_family / (baseline_wafers + targets_per_family),
            "assumption": "continuous exchangeable null maximum-statistic ranks, complete analyses, and no stability abstentions",
        },
        "families_per_noise_distribution": families,
        "targets_per_family": targets_per_family,
        "results": by_noise,
        "interpretation": "Per-target rank evidence is not a family-wise guarantee when the same baseline is repeatedly searched. The study estimates behavior under the declared synthetic null families only.",
    }


if __name__ == "__main__":
    print(json.dumps(run(), indent=2, sort_keys=True))
