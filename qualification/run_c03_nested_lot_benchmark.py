"""Independent Monte Carlo challenge for repeated wafers nested within lots."""
from __future__ import annotations

import json
import random
import sys
from copy import deepcopy
from datetime import UTC, datetime
from math import cos, sin, sqrt
from pathlib import Path
from statistics import mean, median

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from products.p3.engine import _physical_site_values, _prepare_map, associate_quality  # noqa: E402
from qualification.engineer_challenge import build  # noqa: E402

REPLICATES = 500
LOTS = 20
WAFERS_PER_LOT = 2
SITES = 48
LATENT_RHO = 0.4
MEASUREMENT_NOISE_SD = 0.5


def informative_cluster_size_challenge() -> dict:
    """Ensure wafer count cannot reweight lots; one missing site must abstain."""
    challenge = build()
    association = deepcopy(challenge["quality_association"])
    association["context"]["recipe_id"] = "SYN-RECIPE-A"
    base_rows = association["observations"][:SITES]
    prepared = _prepare_map(challenge)
    expected_context = {**association["context"], "coordinate_system": prepared["coordinate_system"],
                        "coordinate_unit": prepared["coordinate_unit"], "radius": prepared["radius"],
                        "orientation_deg": prepared["orientation_deg"]}
    expected_coordinates = set(_physical_site_values(challenge))

    blocks: dict[str, list[int]] = {}
    for index, row in enumerate(base_rows):
        blocks.setdefault(str(row["spatial_block_id"]), []).append(index)
    feature = [sin(index * 0.71) + cos(index * 0.19) for index in range(SITES)]
    orthogonal = [cos(index * 0.37) - sin(index * 0.23) for index in range(SITES)]
    for indices in blocks.values():
        feature_mean = mean(feature[index] for index in indices)
        orthogonal_mean = mean(orthogonal[index] for index in indices)
        for index in indices:
            feature[index] -= feature_mean
            orthogonal[index] -= orthogonal_mean
    projection = sum(feature[index] * orthogonal[index] for index in range(SITES)) / sum(value * value for value in feature)
    orthogonal = [value - projection * feature[index] for index, value in enumerate(orthogonal)]
    feature_norm = sqrt(sum(value * value for value in feature))
    orthogonal_norm = sqrt(sum(value * value for value in orthogonal))
    feature = [value / feature_norm for value in feature]
    orthogonal = [value / orthogonal_norm for value in orthogonal]

    rows = []
    for lot_index in range(LOTS):
        rho = 0.8 if lot_index < 10 else -0.8
        cluster_size = 3 if lot_index < 10 else 1
        for wafer_index in range(cluster_size):
            wafer = f"C03-CS-L{lot_index:02d}-W{wafer_index:02d}"
            lot = f"C03-CS-L{lot_index:02d}"
            for site_index, source in enumerate(base_rows):
                row = deepcopy(source)
                row.update({"wafer_id": wafer, "lot_id": lot, "cohort": "holdout",
                            "feature_value": feature[site_index],
                            "outcome_value": rho * feature[site_index] + sqrt(1 - rho * rho) * orthogonal[site_index],
                            "recipe_id": "SYN-RECIPE-A",
                            "feature_at": f"2025-01-{lot_index + 1:02d}T00:00:00Z",
                            "outcome_at": f"2025-01-{lot_index + 2:02d}T00:00:00Z"})
                rows.append(row)
    association["observations"] = rows
    wafer_count = len({row["wafer_id"] for row in rows})
    association["cohort_selection"]["eligible_wafer_count"] = wafer_count
    association["cohort_selection"]["selected_wafer_count"] = wafer_count
    result = associate_quality(association, expected_context, expected_coordinates)
    expected_equal_lot_r = 0.0
    naive_wafer_weighted_r = 0.6
    missing = deepcopy(association)
    missing["observations"] = [row for row in missing["observations"]
                               if not (row["wafer_id"] == "C03-CS-L00-W00" and row["die_id"] == base_rows[0]["die_id"])]
    missing_result = associate_quality(missing, expected_context, expected_coordinates)
    return {"status": result.get("status"), "wafers": result.get("wafers"),
            "independent_lots": result.get("independent_lots"),
            "equal_lot_expected_r": expected_equal_lot_r,
            "observed_lot_weighted_r": result.get("mean_within_wafer_r"),
            "naive_wafer_weighted_r": naive_wafer_weighted_r,
            "lot_size_pattern": "10 positive lots have 3 wafers each; 10 negative lots have 1 each",
            "single_missing_site_status": missing_result.get("status"),
            "single_missing_site_reason": missing_result.get("reason"),
            "acceptance": (result.get("status") == "VALID" and result.get("wafers") == 40
                           and result.get("independent_lots") == 20
                           and abs(result.get("mean_within_wafer_r", 1.0) - expected_equal_lot_r) < 1e-6
                           and abs(result.get("mean_within_wafer_r", 1.0) - naive_wafer_weighted_r) > 0.5
                           and missing_result.get("status") == "INCONCLUSIVE")}


def run(replicates: int = REPLICATES) -> dict:
    if replicates < 300:
        raise ValueError("predeclared qualification needs at least 300 Monte Carlo replicates")
    target_r = LATENT_RHO / (1 + MEASUREMENT_NOISE_SD ** 2)
    single_covered = paired_covered = 0
    single_widths, paired_widths = [], []
    single_estimates, paired_estimates = [], []
    challenge = build()
    template = deepcopy(challenge["quality_association"])
    template["context"]["recipe_id"] = "SYN-RECIPE-A"
    base_rows = template["observations"][:SITES]
    spatial_blocks = sorted({str(row["spatial_block_id"]) for row in base_rows})
    prepared = _prepare_map(challenge)
    expected_context = {**template["context"], "coordinate_system": prepared["coordinate_system"],
                        "coordinate_unit": prepared["coordinate_unit"], "radius": prepared["radius"],
                        "orientation_deg": prepared["orientation_deg"]}
    expected_coordinates = set(_physical_site_values(challenge))
    invalid_engine_results = {"single_wafer": 0, "nested_wafers": 0}
    for replicate in range(replicates):
        rng = random.Random(20261124 + replicate)
        product_rows = []
        for lot_index in range(LOTS):
            block_x = {block: rng.gauss(0, 0.8) for block in spatial_blocks}
            block_y = {block: rng.gauss(0, 0.8) for block in spatial_blocks}
            latent = []
            for site in range(SITES):
                ux = rng.gauss(0, 1)
                uy = LATENT_RHO * ux + sqrt(1 - LATENT_RHO ** 2) * rng.gauss(0, 1)
                block = str(base_rows[site]["spatial_block_id"])
                latent.append((block_x[block] + ux, block_y[block] + uy))
            for _wafer in range(WAFERS_PER_LOT):
                observed = [(x + rng.gauss(0, MEASUREMENT_NOISE_SD),
                             y + rng.gauss(0, MEASUREMENT_NOISE_SD)) for x, y in latent]
                for site_index, source in enumerate(base_rows):
                    row = deepcopy(source)
                    row.update({"wafer_id": f"C03-NESTED-{replicate:04d}-L{lot_index:02d}-W{_wafer}",
                                "lot_id": f"C03-NESTED-{replicate:04d}-L{lot_index:02d}",
                                "die_id": source["die_id"], "feature_value": observed[site_index][0],
                                "outcome_value": observed[site_index][1], "cohort": "holdout",
                                "recipe_id": "SYN-RECIPE-A",
                                "feature_at": f"2025-01-{lot_index + 1:02d}T00:00:00Z",
                                "outcome_at": f"2025-01-{lot_index + 2:02d}T00:00:00Z"})
                    product_rows.append(row)

        def engine_result(rows: list[dict]) -> dict:
            association = deepcopy(template)
            association["observations"] = rows
            count = len({row["wafer_id"] for row in rows})
            association["cohort_selection"]["eligible_wafer_count"] = count
            association["cohort_selection"]["selected_wafer_count"] = count
            return associate_quality(association, expected_context, expected_coordinates)

        single_rows = [row for row in product_rows if row["wafer_id"].endswith("-W0")]
        single_result = engine_result(single_rows)
        paired_result = engine_result(product_rows)
        if single_result.get("status") != "VALID":
            invalid_engine_results["single_wafer"] += 1
            continue
        if paired_result.get("status") != "VALID":
            invalid_engine_results["nested_wafers"] += 1
            continue
        single, single_low, single_high = (single_result["mean_within_wafer_r"],
                                           *single_result["fisher_wafer_95_ci"])
        paired, paired_low, paired_high = (paired_result["mean_within_wafer_r"],
                                           *paired_result["fisher_wafer_95_ci"])
        single_estimates.append(single)
        paired_estimates.append(paired)
        single_widths.append(single_high - single_low)
        paired_widths.append(paired_high - paired_low)
        single_covered += single_low <= target_r <= single_high
        paired_covered += paired_low <= target_r <= paired_high

    single_coverage = single_covered / replicates
    paired_coverage = paired_covered / replicates
    median_single_width, median_paired_width = median(single_widths), median(paired_widths)
    width_reduction = 1 - median_paired_width / median_single_width
    cluster_size_challenge = informative_cluster_size_challenge()
    report = {
        "schema": "p3-c03-nested-lot-benchmark/v1",
        "created_utc": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "status": "PASS" if (cluster_size_challenge["acceptance"] and not any(invalid_engine_results.values())
                               and 0.90 <= single_coverage <= 0.99 and 0.90 <= paired_coverage <= 0.99
                               and width_reduction >= 0.05) else "FAIL",
        "company_data_used": False,
        "design": {"replicates": replicates, "independent_lots": LOTS, "wafers_per_lot": WAFERS_PER_LOT,
                   "sites_per_wafer": SITES, "spatial_blocks": len(spatial_blocks),
                   "latent_spatial_correlation": LATENT_RHO,
                   "independent_wafer_measurement_noise_sd": MEASUREMENT_NOISE_SD,
                   "random_seed_start": 20261124,
                   "estimand": "population correlation after block adjustment and independent wafer measurement error",
                   "oracle_correlation": target_r,
                   "oracle_formula": "latent_rho / (1 + measurement_noise_variance)"},
        "predeclared_acceptance": {
            "both_methods_nominal_95_coverage": "90%-99% across 500 independent simulated investigations",
            "useful_gain": "At least 5% reduction in median 95% interval width at unchanged independent lot count",
            "candidate": "Average Fisher-z wafer correlations within each lot, then estimate across independent lots; no wafer pseudoreplication",
            "informative_cluster_size": "Unequal lot sizes correlated with lot effect preserve equal-lot estimand rather than wafer weighting; one missing site in any wafer abstains.",
        },
        "engine_integration": {"invalid_results": invalid_engine_results,
                               "method": "products.p3.engine.associate_quality; independent DGP, verified wafer-site context and complete-frame metadata"},
        "informative_cluster_size_and_missing_site": cluster_size_challenge,
        "one_wafer_per_lot_baseline": {"coverage": single_coverage,
            "wilson_95": _wilson(single_covered, replicates), "median_interval_width": median_single_width,
            "mean_estimate_mc": mean(single_estimates)},
        "two_wafers_per_lot_clustered_candidate": {"coverage": paired_coverage,
            "wilson_95": _wilson(paired_covered, replicates), "median_interval_width": median_paired_width,
            "mean_estimate_mc": mean(paired_estimates), "median_width_reduction_vs_baseline": width_reduction},
        "interpretation": "Synthetic Monte Carlo only. The candidate averages wafer estimates within lot and uses lots as independent units; this does not establish manufacturing validity or complete control of within-lot dependence.",
    }
    output = ROOT / "progress" / "C03_NESTED_LOT_BENCHMARK.json"
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "cluster_size_challenge": cluster_size_challenge,
                      "single_coverage": single_coverage,
                      "paired_coverage": paired_coverage, "median_width_reduction": width_reduction,
                      "target_correlation": target_r, "output": str(output)}, indent=2))
    if report["status"] != "PASS":
        raise SystemExit(1)
    return report


def _wilson(successes: int, total: int) -> list[float]:
    z = 1.959963984540054
    p = successes / total
    denominator = 1 + z * z / total
    center = (p + z * z / (2 * total)) / denominator
    radius = z * sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denominator
    return [center - radius, center + radius]


if __name__ == "__main__":
    run()
