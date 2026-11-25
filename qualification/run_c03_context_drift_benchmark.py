"""Falsify C03 under context drift, prevalence shifts, sparse support and hidden confounding."""
from __future__ import annotations

import json
import math
import random
import sys
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path
from statistics import mean
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from products.p3.engine import _physical_site_values, _prepare_map, associate_quality  # noqa: E402
from qualification.engineer_challenge import build  # noqa: E402

REPLICATES = 500
CONTEXT_TRIALS = 100
CONTEXT_FIELDS = {
    "product_id": "SYN-PRODUCT-B",
    "recipe_id": "SYN-RECIPE-B",
    "metric": "roughness",
    "measurement_definition_id": "SYN-MET-OTHER",
    "unit": "um",
    "sampling_mask_id": "SYN-MASK-SPARSE",
    "population_signature": "SYN-POP-NEW",
}


def wilson(successes: int, total: int) -> list[float]:
    z = 1.959963984540054
    p = successes / total
    denominator = 1 + z * z / total
    center = (p + z * z / (2 * total)) / denominator
    radius = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denominator
    return [center - radius, center + radius]


def mc_mean(values: list[float]) -> dict[str, float | list[float] | int]:
    average = mean(values)
    se = math.sqrt(sum((value - average) ** 2 for value in values) / max(1, len(values) - 1) / len(values))
    return {"replicates": len(values), "mean": average, "monte_carlo_standard_error": se,
            "monte_carlo_95_interval": [average - 1.96 * se, average + 1.96 * se]}


def _seeded_case(
    replicate: int, kind: str, template: dict[str, Any], base_rows: list[dict[str, Any]]
) -> dict[str, Any]:
    rng = random.Random(20261124 + replicate)
    association = deepcopy(template)
    observations = []
    sites = []
    for source_row in base_rows:
        # The nuisance spatial field is fixed independently of the generator.
        sites.append((float(source_row["x"]) + 0.37 * float(source_row["y"]), source_row))
    center = mean(value for value, _ in sites)
    scale = math.sqrt(mean((value - center) ** 2 for value, _ in sites)) or 1.0
    sites = [((value - center) / scale, row) for value, row in sites]

    for wafer_index in range(20):
        wafer_id = f"C03-{kind}-{replicate:04d}-W{wafer_index:02d}"
        lot_id = f"C03-{kind}-{replicate:04d}-L{wafer_index:02d}"
        epoch = 0 if wafer_index < 10 else 1
        # A wafer-level outcome-prevalence shift is deliberately added. Spatial
        # block demeaning should remove this intercept without treating sites as
        # independent wafers.
        prevalence_shift = -1.25 if epoch == 0 else 1.25
        for spatial_value, source_row in sites:
            row = deepcopy(source_row)
            if kind == "stable_null":
                feature = rng.gauss(0, 1)
                outcome = prevalence_shift + rng.gauss(0, 1)
            elif kind == "hidden_site_confounding":
                # No feature->outcome cause: latent U drives both inside blocks.
                latent = spatial_value + rng.gauss(0, 0.08)
                feature = latent + rng.gauss(0, 0.45)
                outcome = prevalence_shift + latent + rng.gauss(0, 0.45)
            elif kind == "temporal_effect_reversal":
                feature = spatial_value + rng.gauss(0, 0.25)
                outcome = prevalence_shift + (1 if epoch == 0 else -1) * spatial_value + rng.gauss(0, 0.35)
            else:
                raise ValueError(f"unsupported DGP {kind}")
            feature_time = datetime(2025, 1, 1, tzinfo=UTC) + timedelta(days=wafer_index)
            outcome_time = feature_time + timedelta(days=1)
            row.update({"wafer_id": wafer_id, "lot_id": lot_id,
                        "feature_value": feature, "outcome_value": outcome,
                        "feature_at": feature_time.isoformat().replace("+00:00", "Z"),
                        "outcome_at": outcome_time.isoformat().replace("+00:00", "Z"),
                        "recipe_id": "SYN-RECIPE-A"})
            observations.append(row)
    association["observations"] = observations
    return association


def run(*, replicates: int = REPLICATES, context_trials: int = CONTEXT_TRIALS) -> dict[str, Any]:
    if replicates < 200 or context_trials < 50:
        raise ValueError("use at least 200 statistical and 50 contract-rejection replicates")
    current = build()
    template = deepcopy(current["quality_association"])
    base_rows = template["observations"][:48]
    prepared = _prepare_map(current)
    expected_context = {**template["context"], "coordinate_system": prepared["coordinate_system"],
                        "coordinate_unit": prepared["coordinate_unit"], "radius": prepared["radius"],
                        "orientation_deg": prepared["orientation_deg"], "recipe_id": "SYN-RECIPE-A"}
    template["context"]["recipe_id"] = "SYN-RECIPE-A"
    expected_coordinates = set(_physical_site_values(current))

    # Monte Carlo calibration under a known null with lot-level independent
    # units, spatial-block common causes, and changing outcome prevalence.
    null_results = []
    for replicate in range(replicates):
        association = _seeded_case(replicate, "stable_null", template, base_rows)
        result = associate_quality(association, expected_context, expected_coordinates)
        valid = result.get("status") == "VALID"
        covers = bool(valid and result["fisher_wafer_95_ci"][0] <= 0 <= result["fisher_wafer_95_ci"][1])
        null_results.append({"status": result.get("status"), "covers_zero": covers,
                             "estimate": result.get("mean_within_wafer_r"),
                             "reason": result.get("reason")})
    null_valid = [row for row in null_results if row["status"] == "VALID"]
    null_coverage = sum(row["covers_zero"] for row in null_valid)

    # Explicit semantic drift must not be pooled into the selected wafer's
    # context. Change one randomly selected holdout wafer in each seeded trial.
    context_results: dict[str, list[dict[str, Any]]] = {field: [] for field in CONTEXT_FIELDS}
    for field, incompatible in CONTEXT_FIELDS.items():
        for replicate in range(context_trials):
            association = _seeded_case(replicate, "stable_null", template, base_rows)
            changed_wafer = f"C03-stable_null-{replicate:04d}-W{replicate % 20:02d}"
            for row in association["observations"]:
                if row["wafer_id"] == changed_wafer:
                    row[field] = incompatible
            result = associate_quality(association, expected_context, expected_coordinates)
            context_results[field].append({"status": result.get("status"), "reason": result.get("reason")})

    # Contract challenge cases cover invalid common support, dependent lots,
    # unstable block assignments and outcome-informed cohort selection.
    refusal_results = {name: [] for name in ("sparse_common_support", "duplicate_lot",
                                              "changed_block_map", "outcome_dependent_selection")}
    for replicate in range(context_trials):
        for name in refusal_results:
            association = _seeded_case(replicate, "stable_null", template, base_rows)
            rows = association["observations"]
            if name == "sparse_common_support":
                rows = [row for row in rows if not (row["wafer_id"].endswith("W00") and row["die_id"] == base_rows[0]["die_id"])]
                association["observations"] = rows
            elif name == "duplicate_lot":
                for row in rows:
                    if row["wafer_id"].endswith("W01"):
                        row["lot_id"] = row["lot_id"].replace("L01", "L00")
            elif name == "changed_block_map":
                changed_site = base_rows[0]["die_id"]
                for row in rows:
                    if row["die_id"] == changed_site and row["wafer_id"].endswith("W01"):
                        row["spatial_block_id"] = "SYN-UNREGISTERED-BLOCK"
            else:
                association["cohort_selection"]["selection_blind_to_feature_and_outcome"] = False
            result = associate_quality(association, expected_context, expected_coordinates)
            refusal_results[name].append({"status": result.get("status"), "reason": result.get("reason")})

    # Hidden common cause is not identifiable from the permitted fields. The
    # engine may describe the observational pattern, but must retain its
    # residual-confounding/non-causality limitation.
    hidden_results = []
    for replicate in range(replicates):
        association = _seeded_case(replicate, "hidden_site_confounding", template, base_rows)
        result = associate_quality(association, expected_context, expected_coordinates)
        hidden_results.append({"status": result.get("status"),
                              "estimate": result.get("mean_within_wafer_r"),
                              "interval": result.get("fisher_wafer_95_ci"),
                              "interpretation": result.get("interpretation", "")})

    # Visible time-varying effects without a source-declared population epoch
    # are not identifiable as drift. Record the engine's behavior rather than
    # pretending that timestamps alone establish semantic equivalence.
    reversal_results = []
    for replicate in range(replicates):
        association = _seeded_case(replicate, "temporal_effect_reversal", template, base_rows)
        association["temporal_partition"] = {
            "verified": True, "predeclared_before_holdout_outcomes": True,
            "partition_id": "SYN-TIME-EPOCH-REVERSAL",
            "source_id": "SYN-AUTHORIZED-TEMPORAL-METADATA",
            "approval_reference": "SYN-REVIEW-C03-TEMPORAL-1",
            "cutoff_at": "2025-01-11T00:00:00Z",
            "earlier_label": "early", "later_label": "late",
            "minimum_independent_lots_per_stratum": 10,
        }
        result = associate_quality(association, expected_context, expected_coordinates)
        reversal_results.append({"status": result.get("status"),
                                 "estimate": result.get("mean_within_wafer_r"),
                                 "interval": result.get("fisher_wafer_95_ci"),
                                 "temporal_association": result.get("temporal_association", {}),
                                 "interpretation": result.get("interpretation", "")})

    context_summary = {}
    for field, rows in context_results.items():
        abstained = sum(row["status"] == "INCONCLUSIVE" for row in rows)
        context_summary[field] = {"trials": len(rows), "inconclusive": abstained,
                                  "abstention_rate": abstained / len(rows),
                                  "wilson_95": wilson(abstained, len(rows)),
                                  "unexpected_statuses": sorted({row["status"] for row in rows if row["status"] != "INCONCLUSIVE"})}
    refusal_summary = {}
    for name, rows in refusal_results.items():
        abstained = sum(row["status"] == "INCONCLUSIVE" for row in rows)
        refusal_summary[name] = {"trials": len(rows), "inconclusive": abstained,
                                 "abstention_rate": abstained / len(rows),
                                 "wilson_95": wilson(abstained, len(rows)),
                                 "unexpected_statuses": sorted({row["status"] for row in rows if row["status"] != "INCONCLUSIVE"})}

    hidden_valid = [row for row in hidden_results if row["status"] == "VALID"]
    reversal_valid = [row for row in reversal_results if row["status"] == "VALID"]
    hidden_caveat = sum("Residual confounding remains possible" in row["interpretation"]
                        and "observational" in row["interpretation"] for row in hidden_valid)
    reversal_caveat = sum("Residual confounding remains possible" in row["interpretation"]
                          and "observational" in row["interpretation"] for row in reversal_valid)
    reversal_detected = sum(row["temporal_association"].get("opposite_directions_observed") is True
                            for row in reversal_valid)
    null_coverage_rate = null_coverage / len(null_valid) if null_valid else 0.0
    null_pass = (len(null_valid) == replicates and 0.88 <= null_coverage_rate <= 0.99)
    drift_pass = all(summary["inconclusive"] == summary["trials"] for summary in context_summary.values())
    refusal_pass = all(summary["inconclusive"] == summary["trials"] for summary in refusal_summary.values())
    caveats_pass = (len(hidden_valid) == replicates and hidden_caveat == replicates
                    and len(reversal_valid) == replicates and reversal_caveat == replicates
                    and reversal_detected == replicates)
    report = {
        "schema": "p3-c03-context-drift-benchmark/v2",
        "created_utc": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "scope": "Independent synthetic falsification study; no manufacturing data, internal semantic validation, or causal claim.",
        "predeclared_acceptance": {
            "stable_null": "All 500 analyses VALID and nominal 95% intervals cover zero in 88%-99% of replicates; Wilson interval reported.",
            "declared_context_drift": "Every changed product/recipe/metric/definition/unit/mask/population signature abstains INCONCLUSIVE.",
            "invalid_support": "Sparse exact-site coverage, repeated lots, changed block registration and outcome-informed selection all abstain.",
            "unmeasured_confounding": "Report behavior and verify non-causal/residual-confounding language; do not interpret a VALID estimate as causal.",
            "temporal_reversal": "All predeclared-reversal replicates report opposite nominal interval directions by authorized time stratum even if the pooled estimate is near zero; no post-outcome cutpoint selection.",
        },
        "design": {"statistical_replicates_per_dgp": replicates, "contract_trials_per_case": context_trials,
                   "wafers_per_replicate": 20, "distinct_lots_per_replicate": 20,
                   "sites_per_wafer": len(base_rows), "one_wafer_per_lot": True,
                   "feature_precedes_outcome": True,
                   "outcome_prevalence_shift": "wafer-level intercept -1.25 to +1.25 across the two time epochs",
                   "random_seed": 20261124},
        "stable_null_with_prevalence_shift": {
            "valid": len(null_valid), "abstentions": replicates - len(null_valid),
            "zero_covered": null_coverage, "coverage_fraction": null_coverage_rate,
            "coverage_wilson_95": wilson(null_coverage, len(null_valid)) if null_valid else None,
            "mean_within_wafer_r_mc": mc_mean([row["estimate"] for row in null_valid]) if null_valid else None,
            "ground_truth": "Within each wafer and predeclared spatial block, feature and outcome residuals are independent; a changing wafer-level outcome intercept is not a spatial effect.",
        },
        "declared_context_drift": context_summary,
        "other_abstention_challenges": refusal_summary,
        "hidden_site_confounding": {
            "valid": len(hidden_valid),
            "reported_association_mc": mc_mean([row["estimate"] for row in hidden_valid]) if hidden_valid else None,
            "interval_excludes_zero": sum(not (row["interval"][0] <= 0 <= row["interval"][1]) for row in hidden_valid),
            "significant_fraction_wilson_95": wilson(
                sum(not (row["interval"][0] <= 0 <= row["interval"][1]) for row in hidden_valid), len(hidden_valid)
            ) if hidden_valid else None,
            "noncausal_caveat_present": hidden_caveat == len(hidden_valid),
            "ground_truth": "A latent site field U causes both feature and outcome; there is no feature-to-outcome causal path. U is intentionally absent from source semantics.",
        },
        "temporal_effect_reversal": {
            "valid": len(reversal_valid),
            "reported_association_mc": mc_mean([row["estimate"] for row in reversal_valid]) if reversal_valid else None,
            "opposite_predeclared_directions_detected": reversal_detected,
            "interval_excludes_zero": sum(not (row["interval"][0] <= 0 <= row["interval"][1]) for row in reversal_valid),
            "interval_excludes_zero_fraction_wilson_95": wilson(
                sum(not (row["interval"][0] <= 0 <= row["interval"][1]) for row in reversal_valid), len(reversal_valid)
            ) if reversal_valid else None,
            "noncausal_caveat_present": reversal_caveat == len(reversal_valid),
            "ground_truth": "Feature/outcome spatial association reverses sign between timestamp epochs while the declared population signature is falsely held constant; this models stale source semantics and must not be treated as a validated stable effect.",
            "strata_example": reversal_valid[0]["temporal_association"] if reversal_valid else None,
            "limitation": "A verified, predeclared temporal partition reveals opposite descriptive estimates in this synthetic challenge. Without authorized epoch boundaries, P3 cannot detect a population epoch omitted or misrepresented by the source authority. Stratum intervals are nominal and not multiplicity-adjusted.",
        },
        "interpretation": "Observed context drift and support violations are rejected. Prevalence-only wafer intercept shifts are removed by within-wafer spatial-block adjustment in this design. Hidden common causes and stale/unreported population epochs can still yield VALID observational associations; current source authority and cohort attestations are trusted inputs, not facts P3 can independently establish. The result is not causal.",
        "status": "PASS" if null_pass and drift_pass and refusal_pass and caveats_pass else "FAIL",
        "company_data_used": False,
    }
    output = ROOT / "progress" / "C03_CONTEXT_DRIFT_BENCHMARK.json"
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "null_valid": len(null_valid),
                      "null_interval_coverage": round(null_coverage_rate, 4),
                      "declared_context_cases_abstain": drift_pass,
                      "support_cases_abstain": refusal_pass,
                      "hidden_confound_valid_and_caveated": caveats_pass,
                      "hidden_association_mean": report["hidden_site_confounding"]["reported_association_mc"]["mean"],
                      "temporal_reversal_mean": report["temporal_effect_reversal"]["reported_association_mc"]["mean"],
                      "temporal_reversals_detected": reversal_detected,
                      "output": str(output)}, indent=2))
    if report["status"] != "PASS":
        raise SystemExit(1)
    return report


if __name__ == "__main__":
    run()
