"""Measure C02's conditional uncertainty under known synthetic covariance."""
from __future__ import annotations

import argparse
import json
import math
import random
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# isort: split
from products.p3.engine import compare_evolution  # noqa: I001


N_SITES = 44
REPLICATES = 10_000
COMMON_SD = 1.0
SITE_SD = 0.1


def wilson(successes: int, total: int) -> list[float]:
    z = 1.959963984540054
    proportion = successes / total
    denominator = 1 + z * z / total
    center = (proportion + z * z / (2 * total)) / denominator
    margin = z * math.sqrt(proportion * (1 - proportion) / total + z * z / (4 * total * total)) / denominator
    return [center - margin, center + margin]


def wafer(values: list[float], *, step: str, instance: str, measured_at: str) -> dict:
    points = []
    for index, value in enumerate(values):
        angle = 2 * math.pi * index / N_SITES
        points.append({"site_id": f"S{index:02d}", "x": 105 * math.cos(angle), "y": 105 * math.sin(angle),
                       "value": value, "standard_uncertainty": math.hypot(COMMON_SD, SITE_SD)})
    return {
        "coordinates_verified": True,
        "geometry": {"radius": 150, "origin": {"x": 0, "y": 0}, "orientation_deg": 0,
                     "coordinate_system": "synthetic-wafer-xy", "coordinate_unit": "mm"},
        "measurement": {"metric": "thickness", "unit": "nm", "modality": "continuous",
                         "definition_id": "SYN-MET-1", "layer": "SYN-L1"},
        "points": points,
        "product_id": "SYN-P1", "wafer_id": "SYN-W1", "lot_id": "SYN-LOT1",
        "measured_at": measured_at, "sampling_mask_id": "SYN-MASK-44", "population_signature": "SYN-POP1",
        "step_id": step, "step_instance_id": instance,
    }


def evaluate(rho: float, seed: int, conditional_sigma: float) -> dict:
    rng = random.Random(seed)
    misses = 0
    estimates = []
    for _ in range(REPLICATES):
        common_previous = rng.gauss(0, COMMON_SD)
        common_current = rho * common_previous + math.sqrt(1 - rho * rho) * rng.gauss(0, COMMON_SD)
        deltas = [common_current - common_previous + rng.gauss(0, SITE_SD) - rng.gauss(0, SITE_SD)
                  for _ in range(N_SITES)]
        estimate = sum(deltas) / N_SITES
        estimates.append(estimate)
        misses += abs(estimate) <= conditional_sigma
    empirical_sd = math.sqrt(sum(value * value for value in estimates) / len(estimates))
    coverage = misses / REPLICATES
    analytical_sd = math.sqrt(2 * COMMON_SD**2 * (1 - rho) + 2 * SITE_SD**2 / N_SITES)
    return {
        "cross_step_common_error_correlation": rho,
        "conditional_independence_1sigma_nm": conditional_sigma,
        "known_model_standard_deviation_nm": analytical_sd,
        "monte_carlo_standard_deviation_nm": empirical_sd,
        "actual_to_conditional_sigma_ratio": analytical_sd / conditional_sigma,
        "empirical_fraction_within_reported_1sigma": coverage,
        "empirical_fraction_95_wilson": wilson(misses, REPLICATES),
        "nominal_normal_1sigma_coverage": 0.6826894921370859,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=20261123)
    parser.add_argument("--output", type=Path, default=ROOT / "progress" / "C02_CORRELATED_ERROR_STUDY.json")
    args = parser.parse_args()

    marginal_sd = math.hypot(COMMON_SD, SITE_SD)
    probe = compare_evolution(
        wafer([0.0] * N_SITES, step="S1", instance="I1", measured_at="2026-01-01T00:00:00Z"),
        wafer([0.0] * N_SITES, step="S2", instance="I2", measured_at="2026-01-02T00:00:00Z"),
    )
    uncertainty = probe["uncertainty"]["measurement_uncertainty"]
    conditional_sigma = uncertainty["mean_delta_standard_uncertainty"]
    expected_conditional_sigma = math.sqrt(2 * marginal_sd**2 / N_SITES)
    if probe["status"] != "VALID" or not uncertainty["conditional_on_independence"]:
        raise SystemExit("C02 probe did not expose its conditional independent-error estimate")
    if not math.isclose(conditional_sigma, expected_conditional_sigma, rel_tol=1e-12):
        raise SystemExit("C02 conditional uncertainty differs from the independent-site oracle")

    cases = [evaluate(rho, args.seed + index, conditional_sigma)
             for index, rho in enumerate((0.0, 0.5, 1.0))]
    covariance_bounds = uncertainty["unknown_covariance_bounds"]
    for case in cases:
        case["known_model_sd_within_marginal_only_bounds"] = (
            covariance_bounds["lower_standard_uncertainty"]
            <= case["known_model_standard_deviation_nm"]
            <= covariance_bounds["upper_standard_uncertainty"])
    if not all(case["known_model_sd_within_marginal_only_bounds"] for case in cases):
        raise SystemExit("C02 covariance-agnostic standard-deviation bounds missed a known synthetic model")
    report = {
        "schema": "p3-c02-correlated-error-benchmark/v1",
        "created_utc": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "result": "PASS_SYNTHETIC_COVARIANCE_BOUNDS_CHALLENGE",
        "assumption": "Zero true process change; 44 common sites; each site's supplied marginal standard uncertainty is sqrt(common_component^2 + site_component^2). Common error components are shared across all sites; between-step correlation varies by case.",
        "parameters": {"replicates": REPLICATES, "sites": N_SITES, "common_component_sd_nm": COMMON_SD,
                       "site_independent_sd_nm": SITE_SD, "marginal_per_site_sd_nm": marginal_sd,
                       "seed": args.seed},
        "actual_engine_probe": {"status": probe["status"], "uncertainty": uncertainty,
                                "independence_formula_matches_oracle": True},
        "cases": cases,
        "interpretation": "The independence-based point estimate remains conditional. The added lower/upper standard-deviation bounds contain each independently known synthetic covariance model; they are not a confidence interval and may be wide. Scalar marginal uncertainties cannot identify covariance or calibrated process uncertainty.",
        "company_data_used": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"result": report["result"], "conditional_sigma_nm": conditional_sigma,
                      "cases": [{"rho": row["cross_step_common_error_correlation"],
                                 "actual_to_conditional_sigma_ratio": row["actual_to_conditional_sigma_ratio"],
                                 "within_reported_1sigma": row["empirical_fraction_within_reported_1sigma"]}
                                for row in cases], "output": str(args.output)}, indent=2))


if __name__ == "__main__":
    main()
