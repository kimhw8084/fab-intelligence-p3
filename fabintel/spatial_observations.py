"""Product-neutral typed spatial observations shared by P3 and reference hosts.

The contract separates missing measurements from unlabeled defect events and
keeps JSON number/string values intact at every boundary. It contains no
manufacturing semantics or approval authority.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Mapping
from copy import deepcopy
from typing import Any

SCHEMA_VERSION = "fab-spatial-map.v2"
MODALITIES = {"continuous", "sparse_continuous", "die_bin_categorical", "defect_coordinates"}
KINDS = {"NUMERIC_MEASUREMENT", "CATEGORICAL_MEASUREMENT", "DEFECT_EVENT", "MISSING_MEASUREMENT"}


class SpatialContractError(ValueError):
    """The source cannot be represented without changing its meaning."""


def _number(value: Any) -> bool:
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(float(value))
            and (not isinstance(value, int) or abs(value) <= 2**53 - 1))


def _value_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, str):
        return "string"
    if _number(value):
        return "number"
    raise SpatialContractError("spatial values must be finite JSON numbers, strings, or explicit nulls")


def make_spatial_map(current: Mapping[str, Any], source: Mapping[str, Any]) -> dict[str, Any]:
    """Convert a validated P3 map to the standalone typed spatial contract."""
    measurement = current.get("measurement")
    geometry = current.get("geometry")
    raw_points = current.get("points")
    if not isinstance(measurement, Mapping) or not isinstance(geometry, Mapping) or not isinstance(raw_points, list):
        raise SpatialContractError("normalized source map is missing measurement, geometry, or observations")
    modality = measurement.get("modality")
    if modality not in MODALITIES:
        raise SpatialContractError("spatial measurement modality is not supported")

    observations: list[dict[str, Any]] = []
    for point in raw_points:
        if not isinstance(point, Mapping):
            raise SpatialContractError("spatial source observation must be an object")
        if modality in {"continuous", "sparse_continuous"}:
            if "value" not in point:
                raise SpatialContractError("continuous observations require an explicit numeric value or null")
            value = point.get("value")
            kind = "MISSING_MEASUREMENT" if value is None else "NUMERIC_MEASUREMENT"
        elif modality == "die_bin_categorical":
            if "category" not in point and "bin" not in point:
                raise SpatialContractError("categorical observations require an explicit category or bin field")
            if "category" in point and "bin" in point and (type(point["category"]) is not type(point["bin"]) or point["category"] != point["bin"]):
                raise SpatialContractError("category and bin aliases cannot conflict")
            value = point.get("category", point.get("bin"))
            kind = "MISSING_MEASUREMENT" if value is None else "CATEGORICAL_MEASUREMENT"
        else:
            if "category" in point and "bin" in point and (type(point["category"]) is not type(point["bin"]) or point["category"] != point["bin"]):
                raise SpatialContractError("category and bin aliases cannot conflict")
            value = point.get("category", point.get("bin"))
            kind = "DEFECT_EVENT"

        value_type = _value_type(value)
        if kind == "NUMERIC_MEASUREMENT" and value_type != "number":
            raise SpatialContractError("continuous measurements must remain numeric; numeric strings are refused")
        if kind == "CATEGORICAL_MEASUREMENT" and value_type not in {"number", "string"}:
            raise SpatialContractError("categorical measurements require a typed category or explicit missing value")
        if kind == "DEFECT_EVENT" and value_type == "string" and not value.strip():
            raise SpatialContractError("labeled defect events require a nonempty category")

        observation = {
            "site_id": point.get("site_id"),
            "x": point.get("x"),
            "y": point.get("y"),
            "observation_kind": kind,
            "value": value,
            "value_type": value_type,
        }
        if kind == "NUMERIC_MEASUREMENT" and point.get("standard_uncertainty") is not None:
            observation["standard_uncertainty"] = point["standard_uncertainty"]
            observation["standard_uncertainty_unit"] = point.get("standard_uncertainty_unit", measurement.get("unit"))
        observations.append(observation)

    counts = Counter(item["observation_kind"] for item in observations)
    sampling: dict[str, Any] = {
        "mask_id": current.get("sampling_mask_id"),
        "observation_count": len(observations),
        "numeric_measurement_count": counts["NUMERIC_MEASUREMENT"],
        "categorical_measurement_count": counts["CATEGORICAL_MEASUREMENT"],
        "defect_event_count": counts["DEFECT_EVENT"],
        "explicit_missing_value_count": counts["MISSING_MEASUREMENT"],
        "coverage_basis": "EXPECTED_DENOMINATOR_NOT_SUPPLIED",
    }
    expected = current.get("expected_site_count")
    if expected is not None:
        if type(expected) is not int or expected < len(observations) or expected < 1:
            raise SpatialContractError("expected site count must be an integer no smaller than supplied observations")
        if modality != "defect_coordinates":
            sampling.update({"expected_site_count": expected,
                             "coverage_fraction": len(observations) / expected if expected else 1.0,
                             "coverage_basis": "DECLARED_EXPECTED_SITE_COUNT"})
    if modality == "defect_coordinates":
        sampling["coverage_basis"] = "EVENT_COUNTS_ARE_NOT_SITE_COVERAGE"

    result = {
        "schema_version": SCHEMA_VERSION,
        "wafer_id": current.get("wafer_id"),
        "lot_id": current.get("lot_id"),
        "product_id": current.get("product_id"),
        "step_id": current.get("step_id"),
        "step_instance_id": current.get("step_instance_id"),
        "measured_at": current.get("measured_at"),
        "coordinates_verified": current.get("coordinates_verified") is True,
        "coordinate_unit": geometry.get("coordinate_unit"),
        "metric": measurement.get("metric"),
        "measurement_unit": measurement.get("unit"),
        "modality": modality,
        "geometry": deepcopy(dict(geometry)),
        "sampling": sampling,
        "observations": observations,
        "interpolation": "none",
        "provenance": {
            "source_id": source.get("id"),
            "source_version": source.get("source_version"),
            "semantic_version": source.get("approved_semantic_version"),
            "source_hash": source.get("source_hash"),
            "grain": source.get("grain"),
        },
    }
    validate_spatial_map(result)
    return result


def validate_spatial_map(model: Mapping[str, Any]) -> None:
    """Validate modality, typed values, geometry, provenance, and count parity."""
    if model.get("schema_version") != SCHEMA_VERSION:
        raise SpatialContractError("unsupported typed spatial map schema version")
    modality = model.get("modality")
    if modality not in MODALITIES:
        raise SpatialContractError("spatial measurement modality is not supported")
    if model.get("interpolation") != "none":
        raise SpatialContractError("only measured observations may be represented")
    if (not all(isinstance(model.get(key), str) and model[key].strip()
                for key in ("wafer_id", "lot_id", "product_id", "measured_at", "metric", "measurement_unit"))
            or type(model.get("coordinates_verified")) is not bool):
        raise SpatialContractError("wafer, product, measurement, timestamp, and coordinate status are required")
    geometry = model.get("geometry")
    if not isinstance(geometry, Mapping):
        raise SpatialContractError("wafer geometry is required")
    radius = geometry.get("radius")
    origin = geometry.get("origin")
    if (not _number(radius) or radius <= 0 or not isinstance(origin, Mapping)
            or not _number(origin.get("x")) or not _number(origin.get("y"))
            or not isinstance(geometry.get("coordinate_system"), str)
            or not isinstance(model.get("coordinate_unit"), str)
            or geometry.get("coordinate_unit") != model.get("coordinate_unit")
            or not isinstance(model.get("measurement_unit"), str)):
        raise SpatialContractError("verified geometry and units are required")
    observations = model.get("observations")
    sampling = model.get("sampling")
    if not isinstance(observations, list) or not isinstance(sampling, Mapping):
        raise SpatialContractError("typed observations and sampling summary are required")
    if sampling.get("observation_count") != len(observations):
        raise SpatialContractError("observation count does not reconcile with the supplied rows")
    if sampling.get("coverage_basis") not in {"DECLARED_EXPECTED_SITE_COUNT", "EXPECTED_DENOMINATOR_NOT_SUPPLIED",
                                               "EVENT_COUNTS_ARE_NOT_SITE_COVERAGE"}:
        raise SpatialContractError("sampling coverage basis is not recognized")
    counts = Counter()
    site_ids: set[str] = set()
    for observation in observations:
        if not isinstance(observation, Mapping):
            raise SpatialContractError("spatial observation must be an object")
        site_id = observation.get("site_id")
        x, y = observation.get("x"), observation.get("y")
        kind, value = observation.get("observation_kind"), observation.get("value")
        if not isinstance(site_id, str) or not site_id.strip() or site_id in site_ids:
            raise SpatialContractError("site identifiers must be nonempty and unique")
        site_ids.add(site_id)
        if not _number(x) or not _number(y):
            raise SpatialContractError("spatial coordinates must be finite numbers")
        if math.hypot(x - origin["x"], y - origin["y"]) > radius + max(radius * 1e-9, 1e-12):
            raise SpatialContractError("observation lies outside the declared wafer geometry")
        if kind not in KINDS:
            raise SpatialContractError("unknown spatial observation kind")
        value_type = _value_type(value)
        if observation.get("value_type") != value_type:
            raise SpatialContractError("declared value type does not match the original value")
        if modality in {"continuous", "sparse_continuous"}:
            valid = (kind == "MISSING_MEASUREMENT" and value is None) or (kind == "NUMERIC_MEASUREMENT" and value_type == "number")
        elif modality == "die_bin_categorical":
            valid = ((kind == "MISSING_MEASUREMENT" and value is None)
                     or (kind == "CATEGORICAL_MEASUREMENT" and value_type in {"number", "string"}))
        else:
            valid = kind == "DEFECT_EVENT" and value_type in {"number", "string", "null"}
        if not valid:
            raise SpatialContractError("observation kind and typed value are incompatible with modality")
        if kind == "DEFECT_EVENT" and isinstance(value, str) and not value.strip():
            raise SpatialContractError("labeled defect events require a nonempty category")
        uncertainty = observation.get("standard_uncertainty")
        if uncertainty is not None and (kind != "NUMERIC_MEASUREMENT" or not _number(uncertainty) or uncertainty < 0):
            raise SpatialContractError("uncertainty is only valid for numeric observations and must be nonnegative")
        counts[kind] += 1
    fields = {
        "numeric_measurement_count": counts["NUMERIC_MEASUREMENT"],
        "categorical_measurement_count": counts["CATEGORICAL_MEASUREMENT"],
        "defect_event_count": counts["DEFECT_EVENT"],
        "explicit_missing_value_count": counts["MISSING_MEASUREMENT"],
    }
    if any(sampling.get(field) != expected for field, expected in fields.items()):
        raise SpatialContractError("observation-kind counts do not reconcile with the supplied rows")
    expected = sampling.get("expected_site_count")
    fraction = sampling.get("coverage_fraction")
    if sampling.get("coverage_basis") == "DECLARED_EXPECTED_SITE_COUNT":
        if modality == "defect_coordinates" or type(expected) is not int or expected < len(observations) or expected < 1:
            raise SpatialContractError("declared coverage denominator is incompatible with observations")
        if not _number(fraction) or not math.isclose(fraction, len(observations) / expected, rel_tol=1e-12):
            raise SpatialContractError("coverage fraction does not match its declared denominator")
    elif fraction is not None:
        raise SpatialContractError("coverage fraction requires an explicit expected-site denominator")
    provenance = model.get("provenance")
    if (not isinstance(provenance, Mapping)
            or not all(isinstance(provenance.get(key), str) and provenance[key]
                       for key in ("source_id", "source_version", "semantic_version", "source_hash", "grain"))):
        raise SpatialContractError("source provenance is required for typed spatial observations")
    if not re.fullmatch(r"[a-f0-9]{64}", provenance["source_hash"]):
        raise SpatialContractError("source provenance hash must be a SHA-256 digest")


def to_suite_spatial_map_v1(model: Mapping[str, Any]) -> dict[str, Any]:
    """Explicit, lossy-avoiding adapter for existing suite-v1 hosts.

    Defect events cannot be represented in v1 because its null means a missing
    measurement. Those maps are refused instead of silently discarding events.
    """
    validate_spatial_map(model)
    if model.get("modality") == "defect_coordinates":
        raise SpatialContractError("suite-spatial-map.v1 cannot represent defect events without losing their meaning")
    geometry = model["geometry"]
    sampling = model["sampling"]
    observations = model["observations"]
    missing = [item["site_id"] for item in observations if item["observation_kind"] == "MISSING_MEASUREMENT"]
    return {
        "schema_version": "suite-spatial-map.v1",
        "wafer_id": model["wafer_id"],
        "coordinates_verified": model["coordinates_verified"],
        "coordinate_unit": model["coordinate_unit"],
        "metric": model["metric"],
        "measurement_unit": model["measurement_unit"],
        "geometry": {key: geometry[key] for key in ("coordinate_system", "origin", "orientation_deg", "radius")},
        "sampling": {
            "mask_id": sampling.get("mask_id"),
            "observed_site_count": len(observations),
            "explicit_missing_value_count": len(missing),
            "coverage_basis": sampling.get("coverage_basis"),
            **({"expected_site_count": sampling["expected_site_count"],
                "coverage_fraction": sampling["coverage_fraction"]}
               if "expected_site_count" in sampling else {}),
            **({"missing_site_ids": missing} if missing else {}),
        },
        "points": [{"site_id": item["site_id"], "x": item["x"], "y": item["y"], "value": item["value"]}
                   for item in observations],
        "interpolation": "none",
    }
