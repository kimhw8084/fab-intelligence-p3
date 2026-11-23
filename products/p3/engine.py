"""Deterministic, observed-site-only P3 analysis methods.

The engine has no network or company-system adapter.  Inputs are synthetic or
must have been authorized, bounded and semantically verified by a future host.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import heapq
from math import atan2, cos, floor, hypot, isfinite, log, pi, sin, sqrt, tanh
from statistics import mean, median
from threading import RLock
from typing import Any

from fabintel.contracts import claim, digest, envelope

ENGINE_VERSION = "0.2.0"
METHOD_VERSION = "p3-observed-spatial-v1"
MAX_POINTS = 250_000
MAX_ABS_NUMERIC = 1e150
ANOMALY_ALPHA = 0.05
ANOMALY_ROBUST_Z = 3.5


def _number(value: Any) -> bool:
    return type(value) in (int, float) and isfinite(value)


class AnalysisCancelled(RuntimeError):
    """Raised when a local caller stops a bounded analysis."""


def _check_cancel(cancel):
    if cancel is not None and cancel.is_set():
        raise AnalysisCancelled("analysis cancelled by caller")


def _measurement(data: dict) -> dict:
    if "measurement" in data:
        m = data.get("measurement")
        if not isinstance(m, dict):
            raise ValueError("measurement definition must be an object")
        return m
    return {
        "metric": data.get("metric"),
        "unit": data.get("unit"),
        "modality": data.get("modality", "continuous"),
        "definition_id": data.get("measurement_definition_id"),
        "layer": data.get("layer"),
    }


def _prepare_map(data: dict, cancel=None) -> dict:
    if not isinstance(data, dict):
        raise ValueError("map input must be an object")
    if data.get("coordinates_verified") is not True:
        raise PermissionError("wafer coordinate system/orientation is not verified")
    if "geometry" in data and not isinstance(data.get("geometry"), dict):
        raise ValueError("wafer geometry must be an object")
    geometry = data.get("geometry") if isinstance(data.get("geometry"), dict) else {}
    radius = geometry.get("radius", data.get("radius"))
    if not _number(radius) or radius <= 0 or radius > MAX_ABS_NUMERIC:
        raise ValueError("wafer radius must be a finite positive number")
    if isinstance(data.get("geometry"), dict) and "origin" not in geometry:
        raise PermissionError("wafer coordinate origin is not verified")
    origin = geometry.get("origin", {"x": 0, "y": 0})
    if isinstance(origin, (list, tuple)) and len(origin) == 2:
        ox, oy = origin
    elif isinstance(origin, dict):
        if isinstance(data.get("geometry"), dict) and not all(key in origin for key in ("x", "y")):
            raise PermissionError("wafer coordinate origin is incomplete")
        ox, oy = origin.get("x", 0), origin.get("y", 0)
    else:
        raise ValueError("geometry origin must contain x and y")
    if not _number(ox) or not _number(oy) or abs(ox) > MAX_ABS_NUMERIC or abs(oy) > MAX_ABS_NUMERIC:
        raise ValueError("geometry origin must be finite")
    orientation = geometry.get("orientation_deg", data.get("orientation_deg"))
    if orientation is not None and (not _number(orientation) or not 0 <= orientation < 360):
        raise ValueError("orientation_deg must be in [0, 360)")
    measurement = _measurement(data)
    modality = measurement.get("modality") or "continuous"
    if modality not in ("continuous", "sparse_continuous", "die_bin_categorical", "defect_coordinates"):
        raise ValueError(f"unsupported measurement modality {modality!r}")
    categorical = modality in ("die_bin_categorical", "defect_coordinates")
    points = data.get("points")
    if not isinstance(points, list) or len(points) < 3:
        raise ValueError("at least three measured sites are required")
    if len(points) > MAX_POINTS:
        raise ValueError(f"point limit exceeded ({MAX_POINTS})")
    normalized = []
    seen = set()
    tolerance = max(float(radius) * 1e-9, 1e-12)
    for index, p in enumerate(points):
        if index % 1024 == 0:
            _check_cancel(cancel)
        required = ("x", "y") if categorical else ("x", "y", "value")
        if not isinstance(p, dict) or not all(_number(p.get(k)) for k in required):
            raise ValueError(f"point {index} has a missing or invalid coordinate/value")
        if any(abs(p[k]) > MAX_ABS_NUMERIC for k in required):
            raise ValueError(f"point {index} exceeds the numeric range limit")
        x, y = float(p["x"]) - float(ox), float(p["y"]) - float(oy)
        value = None if categorical else float(p["value"])
        r = hypot(x, y)
        if r > radius + max(float(radius) * 1e-9, 1e-12):
            raise ValueError(f"point {index} is outside wafer geometry")
        key = (round(x / tolerance), round(y / tolerance))
        if key in seen:
            raise ValueError("duplicate measured coordinate")
        seen.add(key)
        row = {"x": x, "y": y, "radius_fraction": r / float(radius)}
        if not categorical:
            row["value"] = value
            uncertainty = p.get("standard_uncertainty")
            if uncertainty is not None:
                if not _number(uncertainty) or uncertainty < 0 or uncertainty > MAX_ABS_NUMERIC:
                    raise ValueError(f"point {index} standard_uncertainty must be finite and nonnegative")
                uncertainty_unit = p.get("standard_uncertainty_unit")
                if uncertainty_unit is not None and uncertainty_unit != measurement.get("unit"):
                    raise ValueError(f"point {index} uncertainty unit must match the measurement unit")
                row["standard_uncertainty"] = float(uncertainty)
        elif modality == "die_bin_categorical":
            category = p.get("category", p.get("bin"))
            if not isinstance(category, (str, int)) or isinstance(category, bool) or not str(category).strip():
                raise ValueError(f"point {index} requires a nonempty categorical bin/category")
            row["category"] = str(category)
        row["site_id"] = str(p.get("site_id", f"site-{index + 1}"))
        normalized.append(row)
    return {
        "raw": data,
        "radius": float(radius),
        "origin": (float(ox), float(oy)),
        "orientation_deg": float(orientation) if orientation is not None else None,
        "points": normalized,
        "measurement": measurement,
        "coordinate_unit": geometry.get("coordinate_unit", data.get("coordinate_unit", "[coordinate unit unknown]")),
        "wafer_id": data.get("wafer_id"),
        "product_id": data.get("product_id"),
        "coordinate_system": geometry.get("coordinate_system", data.get("coordinate_system")),
        "population_signature": data.get("population_signature"),
        "sampling_mask_id": data.get("sampling_mask_id", data.get("sampling", {}).get("mask_id") if isinstance(data.get("sampling"), dict) else None),
    }


def _rotate(x: float, y: float, degrees: float | None) -> tuple[float, float]:
    if degrees is None:
        raise ValueError("orientation metadata is required for physical alignment")
    theta = degrees * pi / 180.0
    return (x * cos(theta) - y * sin(theta), x * sin(theta) + y * cos(theta))


def _sector_index(x: float, y: float, orientation: float) -> int:
    px, py = _rotate(x, y, orientation)
    return int(((atan2(py, px) + 2 * pi) % (2 * pi)) / (pi / 4)) % 8


def _linear_slope(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 2:
        return None
    mx, my = mean(xs), mean(ys)
    denominator = sum((x - mx) ** 2 for x in xs)
    if denominator == 0:
        return None
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / denominator


def _mad(values: list[float]) -> float | None:
    if not values:
        return None
    middle = median(values)
    return median([abs(value - middle) for value in values])


def _summary(values: list[float]) -> dict:
    if not values:
        return {"count": 0, "mean": None, "median": None, "mad": None, "minimum": None, "maximum": None}
    return {"count": len(values), "mean": mean(values), "median": median(values), "mad": _mad(values),
            "minimum": min(values), "maximum": max(values)}


def _plane_gradient(points: list[dict], radius: float, orientation: float | None) -> dict:
    if orientation is None:
        return {"status": "INCONCLUSIVE", "reason": "verified wafer orientation is required for a physical directional gradient"}
    if len(points) < 3:
        return {"status": "INCONCLUSIVE", "reason": "at least three non-collinear observed sites are required"}
    rotated = [_rotate(p["x"], p["y"], orientation) for p in points]
    xs = [x / radius for x, _ in rotated]
    ys = [y / radius for _, y in rotated]
    values = [p["value"] for p in points]
    mx, my, mz = mean(xs), mean(ys), mean(values)
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sxv = sum((x - mx) * (value - mz) for x, value in zip(xs, values))
    syv = sum((y - my) * (value - mz) for y, value in zip(ys, values))
    determinant = sxx * syy - sxy * sxy
    if abs(determinant) <= max(sxx * syy, 1.0) * 1e-14:
        return {"status": "INCONCLUSIVE", "reason": "observed coordinates do not span two spatial dimensions"}
    gx = (sxv * syy - syv * sxy) / determinant
    gy = (syv * sxx - sxv * sxy) / determinant
    magnitude = hypot(gx, gy)
    return {"status": "VALID", "gradient_x_per_radius": gx, "gradient_y_per_radius": gy,
            "magnitude_per_radius": magnitude,
            "direction_deg": (atan2(gy, gx) * 180 / pi) % 360 if magnitude else None,
            "method": "ordinary_least_squares_plane_on_observed_sites"}


def _local_clusters(points: list[dict], radius: float, orientation: float | None, *, grid_size=32) -> dict:
    """Describe contiguous occupied grid cells with large median shifts; not calibrated alerts."""
    if orientation is None:
        return {"status": "INCONCLUSIVE", "reason": "verified wafer orientation is required for physical cluster locations"}
    buckets: dict[tuple[int, int], list[float]] = {}
    for point in points:
        x, y = _rotate(point["x"], point["y"], orientation)
        ix = min(grid_size - 1, max(0, int((x / radius + 1) * grid_size / 2)))
        iy = min(grid_size - 1, max(0, int((y / radius + 1) * grid_size / 2)))
        buckets.setdefault((ix, iy), []).append(point["value"])
    all_values = [p["value"] for p in points]
    center = median(all_values)
    scale = _mad(all_values)
    candidates = {}
    cell_rows = []
    for key, values in buckets.items():
        cell_median = median(values)
        robust_z = (0.67448975 * (cell_median - center) / scale) if scale and scale > 0 else None
        candidate = len(values) >= 3 and robust_z is not None and abs(robust_z) >= ANOMALY_ROBUST_Z
        cell_rows.append({"grid_x": key[0], "grid_y": key[1], **_summary(values),
                          "robust_z_vs_global_median": robust_z, "candidate": candidate})
        if candidate:
            candidates[key] = robust_z
    clusters = []
    while candidates:
        seed = next(iter(candidates))
        todo, component = [seed], set()
        while todo:
            key = todo.pop()
            if key in component or key not in candidates:
                continue
            component.add(key)
            x, y = key
            todo.extend((x + dx, y + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1) if dx or dy)
        for key in component:
            candidates.pop(key, None)
        cluster_values = [value for key in component for value in buckets[key]]
        clusters.append({"grid_cells": [list(key) for key in sorted(component)],
                         "observed_site_count": len(cluster_values), "median": median(cluster_values),
                         "maximum_absolute_robust_z": max(abs((median(buckets[key]) - center) * 0.67448975 / scale) for key in component)})
    clusters.sort(key=lambda item: (-item["maximum_absolute_robust_z"], -item["observed_site_count"]))
    return {"status": "EXPLORATORY", "grid_size": grid_size, "occupied_cells": len(buckets),
            "minimum_sites_per_candidate_cell": 3, "global_median": center, "global_mad": scale,
            "cells": sorted(cell_rows, key=lambda item: (item["grid_x"], item["grid_y"])),
            "clusters": clusters,
            "interpretation": "descriptive candidate groups only; cell size and score are not calibrated for alerts"}


def _reticle_periodicity(data: dict, prepared: dict) -> dict:
    reticle = data.get("reticle")
    if reticle is None:
        return {"status": "NOT_COMPUTED", "reason": "verified reticle pitch/origin and sampling-alias review were not supplied"}
    if not isinstance(reticle, dict):
        return {"status": "INCONCLUSIVE", "reason": "reticle metadata must be an object"}
    if reticle.get("sampling_alias_verified") is not True or not reticle.get("alias_check_id"):
        return {"status": "NOT_COMPUTED", "reason": "a traceable sampling-alias verification is required"}
    pitch_x, pitch_y = reticle.get("pitch_x"), reticle.get("pitch_y")
    origin = reticle.get("origin")
    if (not _number(pitch_x) or not _number(pitch_y) or pitch_x <= 0 or pitch_y <= 0
            or not isinstance(origin, dict) or not _number(origin.get("x")) or not _number(origin.get("y"))
            or reticle.get("coordinate_unit") != prepared["coordinate_unit"]):
        return {"status": "INCONCLUSIVE", "reason": "reticle pitches, physical origin and matching coordinate units are required"}
    if prepared["orientation_deg"] is None or not prepared["coordinate_system"]:
        return {"status": "INCONCLUSIVE", "reason": "verified physical orientation and coordinate system are required"}
    physical = [_rotate(point["x"], point["y"], prepared["orientation_deg"]) for point in prepared["points"]]
    if len(physical) < 30:
        return {"status": "INCONCLUSIVE", "reason": "at least 30 measured sites are required for the exploratory periodicity score"}
    x_values, y_values = [p[0] for p in physical], [p[1] for p in physical]
    x_periods = floor((max(x_values) - float(origin["x"])) / pitch_x) - floor((min(x_values) - float(origin["x"])) / pitch_x) + 1
    y_periods = floor((max(y_values) - float(origin["y"])) / pitch_y) - floor((min(y_values) - float(origin["y"])) / pitch_y) + 1
    phase_bins_x = {int((((x - float(origin["x"])) / pitch_x) % 1) * 8) for x in x_values}
    phase_bins_y = {int((((y - float(origin["y"])) / pitch_y) % 1) * 8) for y in y_values}
    if x_periods < 3 or y_periods < 3 or len(phase_bins_x) < 4 or len(phase_bins_y) < 4:
        return {"status": "INCONCLUSIVE", "reason": "observed sites do not span three reticle periods and four phase bins on both axes"}
    values = [point["value"] for point in prepared["points"]]
    mx, my, mz = mean(x / prepared["radius"] for x in x_values), mean(y / prepared["radius"] for y in y_values), mean(values)
    gradient = _plane_gradient(prepared["points"], prepared["radius"], prepared["orientation_deg"])
    if gradient.get("status") != "VALID":
        return {"status": "INCONCLUSIVE", "reason": "a two-dimensional trend must be estimable before reticle scoring"}
    residuals = [value - (mz + gradient["gradient_x_per_radius"] * (x / prepared["radius"] - mx)
                          + gradient["gradient_y_per_radius"] * (y / prepared["radius"] - my))
                 for value, x, y in zip(values, x_values, y_values)]

    def amplitude(axis_values, pitch, axis_origin):
        phases = [2 * pi * (coordinate - axis_origin) / pitch for coordinate in axis_values]
        cosine = sum(value * cos(phase) for value, phase in zip(residuals, phases))
        sine = sum(value * sin(phase) for value, phase in zip(residuals, phases))
        return 2 * hypot(cosine, sine) / len(residuals)

    return {"status": "EXPLORATORY", "amplitude_x": amplitude(x_values, pitch_x, float(origin["x"])),
            "amplitude_y": amplitude(y_values, pitch_y, float(origin["y"])), "unit": prepared["measurement"].get("unit"),
            "measured_sites": len(physical), "spanned_periods": {"x": x_periods, "y": y_periods},
            "phase_bins": {"x": len(phase_bins_x), "y": len(phase_bins_y)},
            "sampling_alias_check_id": str(reticle["alias_check_id"]),
            "method": "detrended_single_frequency_sinusoidal_projection",
            "interpretation": "exploratory amplitude only; not a significance test or causal conclusion"}


def fingerprint(data: dict, cancel=None) -> dict:
    """Describe only measured sites; regions with no measurements stay absent."""
    m = _prepare_map(data, cancel)
    if not m["coordinate_system"] or not m["coordinate_unit"] or m["coordinate_unit"] == "[coordinate unit unknown]":
        raise PermissionError("wafer coordinate system and units are not verified")
    if not m["measurement"].get("metric") or not m["measurement"].get("unit"):
        raise ValueError("measurement metric and unit are required")
    points = m["points"]
    modality = m["measurement"].get("modality") or "continuous"
    if modality in ("die_bin_categorical", "defect_coordinates"):
        regions = {"center": [], "middle": [], "edge": []}
        radial_bins = ((0.0, 0.2, "center"), (0.2, 0.5, "inner_middle"),
                       (0.5, 0.8, "outer_middle"), (0.8, 1.0 + 1e-9, "edge"))
        radial_profile = []
        for point in points:
            label = "center" if point["radius_fraction"] <= 0.2 else "edge" if point["radius_fraction"] >= 0.8 else "middle"
            regions[label].append(point)
        for low, high, label in radial_bins:
            selected = [point for point in points if (point["radius_fraction"] <= high if label == "center"
                                                       else low < point["radius_fraction"] <= high)]
            radial_profile.append({"region": label, "radius_fraction": [low, high], "count": len(selected)})
        region_result = {}
        for label, selected in regions.items():
            row = {"count": len(selected), "mean": None, "median": None, "mad": None,
                   "minimum": None, "maximum": None}
            if modality == "die_bin_categorical":
                category_counts: dict[str, int] = {}
                for point in selected:
                    category_counts[point["category"]] = category_counts.get(point["category"], 0) + 1
                row["category_counts"] = dict(sorted(category_counts.items()))
            region_result[label] = row
        directional = ( {"status": "NOT_APPLICABLE", "reason": "directional numeric gradients do not apply to categorical observations"}
                        if modality == "die_bin_categorical" else
                        {"status": "NOT_APPLICABLE", "reason": "directional numeric gradients do not apply to defect-coordinate events"})
        return {
            "observed_points": len(points), "modality": modality, "regions": region_result,
            "edge_center": {"status": "NOT_APPLICABLE", "reason": "edge-center arithmetic is not valid for categorical observations"},
            "edge_minus_center": None, "radial_gradient_per_radius": None,
            "radial_profile": radial_profile, "directional_gradient": directional,
            "local_clusters": {"status": "NOT_APPLICABLE", "reason": "numeric cluster scoring is not valid for categorical observations"},
            "reticle_periodicity": {"status": "NOT_APPLICABLE", "reason": "numeric periodicity scoring is not valid for categorical observations"},
            "sectors": ({"status": "INCONCLUSIVE", "reason": "verified wafer orientation is required for sector counts"}
                        if m["orientation_deg"] is None else [
                            {"sector": sector, "count": sum(_sector_index(point["x"], point["y"], m["orientation_deg"]) == sector for point in points)}
                            for sector in range(8)]),
            "measurement_unit": m["measurement"].get("unit"), "metric": m["measurement"].get("metric"),
            "measurement_definition_id": m["measurement"].get("definition_id"), "layer": m["measurement"].get("layer"),
            "coordinate_unit": m["coordinate_unit"], "sampling_mask_id": m["sampling_mask_id"],
        }
    center = [p["value"] for p in points if p["radius_fraction"] <= 0.2]
    mid = [p["value"] for p in points if 0.2 < p["radius_fraction"] < 0.8]
    edge = [p["value"] for p in points if p["radius_fraction"] >= 0.8]
    edge_center_status = "VALID" if center and edge else "INCONCLUSIVE"
    edge_center = {
        "status": edge_center_status,
        "center_count": len(center), "edge_count": len(edge),
        "difference": mean(edge) - mean(center) if center and edge else None,
        "reason": None if center and edge else "both center and edge measurements are required for this feature",
    }
    center_points = [point for point in points if point["radius_fraction"] <= 0.2]
    edge_points = [point for point in points if point["radius_fraction"] >= 0.8]
    if center and edge and all(point.get("standard_uncertainty") is not None for point in center_points + edge_points):
        center_u = [point["standard_uncertainty"] for point in center_points]
        edge_u = [point["standard_uncertainty"] for point in edge_points]
        edge_center["standard_uncertainty"] = sqrt(sum(u * u for u in edge_u) / len(edge_u) ** 2
                                                       + sum(u * u for u in center_u) / len(center_u) ** 2)
        edge_center["uncertainty_status"] = "PROPAGATED_FROM_SITE_STANDARD_UNCERTAINTIES"
        edge_center["uncertainty_method"] = "independent_site_uncertainties_root_sum_square_of_region_means"
        edge_center["uncertainty_unit"] = m["measurement"].get("unit")
    else:
        edge_center["standard_uncertainty"] = None
        edge_center["uncertainty_status"] = "NOT_SUPPLIED"
    radial_bins = [(0.0, 0.2, "center"), (0.2, 0.5, "inner_middle"),
                   (0.5, 0.8, "outer_middle"), (0.8, 1.0 + 1e-9, "edge")]
    radial_profile = []
    for low, high, label in radial_bins:
        def in_bin(fraction):
            return fraction <= high if label == "center" else low < fraction <= high
        values = [p["value"] for p in points if in_bin(p["radius_fraction"])]
        radial_profile.append({"region": label, "radius_fraction": [low, high], **_summary(values)})
    result = {
        "observed_points": len(points),
        "modality": modality,
        "regions": {
            "center": {"count": len(center), "mean": mean(center) if center else None},
            "middle": {"count": len(mid), "mean": mean(mid) if mid else None},
            "edge": {"count": len(edge), "mean": mean(edge) if edge else None},
        },
        "edge_center": edge_center,
        "edge_minus_center": edge_center["difference"],
        "radial_gradient_per_radius": _linear_slope([p["radius_fraction"] for p in points], [p["value"] for p in points]),
        "radial_profile": radial_profile,
        "directional_gradient": _plane_gradient(points, m["radius"], m["orientation_deg"]),
        "local_clusters": _local_clusters(points, m["radius"], m["orientation_deg"]),
        "reticle_periodicity": _reticle_periodicity(data, m),
        "sectors": None,
        "measurement_unit": m["measurement"].get("unit") or "[unit unknown]",
        "metric": m["measurement"].get("metric"),
        "measurement_definition_id": m["measurement"].get("definition_id"),
        "layer": m["measurement"].get("layer"),
        "coordinate_unit": m["coordinate_unit"],
        "sampling_mask_id": m["sampling_mask_id"],
    }
    if m["orientation_deg"] is not None:
        buckets = [[] for _ in range(8)]
        for index, p in enumerate(points):
            if index % 1024 == 0:
                _check_cancel(cancel)
            buckets[_sector_index(p["x"], p["y"], m["orientation_deg"])].append(p["value"])
        result["sectors"] = [
            {"sector": i, **_summary(values)} for i, values in enumerate(buckets)
        ]
    else:
        result["sectors"] = {"status": "INCONCLUSIVE", "reason": "verified wafer orientation is required for physical sector locations"}
    return result


def describe(points, radius):
    """Backward-compatible edge/center API retained for the bootstrap fixtures."""
    result = fingerprint({"coordinates_verified": True,
                          "geometry": {"radius": radius, "origin": {"x": 0, "y": 0}, "orientation_deg": 0,
                                       "coordinate_system": "legacy_xy", "coordinate_unit": "legacy_radius_units"},
                          "measurement": {"metric": "legacy", "unit": "legacy_unit", "modality": "continuous"}, "points": points})
    return {"edge_minus_center": result["edge_minus_center"], "observed_points": result["observed_points"]}


def _context_compatible(left: dict, right: dict, require_orientation=True, cancel=None,
                       require_sampling_mask=True, prepared_left=None, prepared_right=None) -> tuple[bool, str]:
    a = prepared_left or _prepare_map(left, cancel)
    b = prepared_right or _prepare_map(right, cancel)
    ma, mb = a["measurement"], b["measurement"]
    for key in ("metric", "unit", "definition_id", "layer", "modality"):
        va, vb = ma.get(key), mb.get(key)
        if not va or not vb or va != vb:
            return False, f"incompatible or missing measurement {key}"
    for key in ("product_id",):
        va, vb = left.get(key), right.get(key)
        if not va or not vb or va != vb:
            return False, f"incompatible or missing {key}"
    for key in ("recipe_id", "tool_id", "chamber_id", "route_id", "edge_exclusion_radius"):
        va, vb = left.get(key), right.get(key)
        if va is not None or vb is not None:
            if va is None or vb is None or va != vb:
                return False, f"incompatible or missing {key}"
    if abs(a["radius"] - b["radius"]) > max(a["radius"], b["radius"]) * 1e-8:
        return False, "wafer radii differ"
    if not a["sampling_mask_id"] or not b["sampling_mask_id"]:
        return False, "sampling masks are unverified"
    if require_sampling_mask and a["sampling_mask_id"] != b["sampling_mask_id"]:
        return False, "sampling masks differ or are unverified"
    if not a["coordinate_system"] or not b["coordinate_system"] or a["coordinate_system"] == "unknown" or b["coordinate_system"] == "unknown" or a["coordinate_system"] != b["coordinate_system"]:
        return False, "coordinate systems differ or are unverified"
    if (not a["coordinate_unit"] or not b["coordinate_unit"] or a["coordinate_unit"] == "[coordinate unit unknown]"
            or b["coordinate_unit"] == "[coordinate unit unknown]" or a["coordinate_unit"] != b["coordinate_unit"]):
        return False, "coordinate units differ or are unverified"
    if not a["population_signature"] or not b["population_signature"] or a["population_signature"] != b["population_signature"]:
        return False, "comparable population context is missing or differs"
    if require_orientation and (a["orientation_deg"] is None or b["orientation_deg"] is None):
        return False, "verified orientation is required"
    return True, "compatible"


def _physical_site_values(data: dict, cancel=None, *, prepared=None) -> dict[tuple[int, int], tuple[dict, float]]:
    m = prepared or _prepare_map(data, cancel)
    if m["orientation_deg"] is None:
        raise ValueError("verified orientation is required for physical alignment")
    sites = {}
    for index, p in enumerate(m["points"]):
        if index % 1024 == 0:
            _check_cancel(cancel)
        x, y = _rotate(p["x"], p["y"], m["orientation_deg"])
        key = (round(x / m["radius"], 8), round(y / m["radius"], 8))
        if key in sites:
            raise ValueError("coordinate transform produced duplicate sites")
        sites[key] = (p, p["value"])
    return sites


def _validate_common_site_policy(policy: Any) -> tuple[int, float] | None:
    if policy is None:
        return None
    if (not isinstance(policy, dict) or policy.get("predeclared") is not True
            or policy.get("method") != "exact_common_site_v1"):
        raise ValueError("common-site matching requires a predeclared exact_common_site_v1 policy")
    minimum_sites = policy.get("minimum_sites")
    minimum_coverage = policy.get("minimum_coverage_fraction")
    if (type(minimum_sites) is not int or minimum_sites < 5
            or not _number(minimum_coverage) or not 0.5 <= minimum_coverage <= 1):
        raise ValueError("common-site policy requires at least five sites and 0.5–1.0 coverage per map")
    return minimum_sites, float(minimum_coverage)


def compare_evolution(previous: dict, current: dict, cancel=None, *, match_policy=None) -> dict:
    """Compare same-wafer, same-definition measurements at matched observed sites."""
    _check_cancel(cancel)
    try:
        common_site_policy = _validate_common_site_policy(match_policy)
    except ValueError as exc:
        return {"status": "INCONCLUSIVE", "reason": str(exc), "site_deltas": []}
    try:
        ok, reason = _context_compatible(previous, current, cancel=cancel,
                                         require_sampling_mask=common_site_policy is None)
    except (ValueError, KeyError, TypeError, PermissionError) as exc:
        return {"status": "INCONCLUSIVE", "reason": str(exc), "site_deltas": []}
    if not ok:
        return {"status": "INCONCLUSIVE", "reason": reason, "site_deltas": []}
    if not previous.get("wafer_id") or previous.get("wafer_id") != current.get("wafer_id"):
        return {"status": "REFUSED", "reason": "cross-step evolution requires the same verified wafer identity", "site_deltas": []}
    if not previous.get("lot_id") or previous.get("lot_id") != current.get("lot_id"):
        return {"status": "REFUSED", "reason": "cross-step evolution requires a consistent lot identity", "site_deltas": []}
    if not previous.get("step_id") or not current.get("step_id") or previous.get("step_id") == current.get("step_id"):
        return {"status": "INCONCLUSIVE", "reason": "distinct, identified step instances are required", "site_deltas": []}
    if (not previous.get("step_instance_id") or not current.get("step_instance_id")
            or previous.get("step_instance_id") == current.get("step_instance_id")):
        return {"status": "INCONCLUSIVE", "reason": "distinct step-instance identities are required", "site_deltas": []}
    try:
        if _parse_time(current.get("measured_at")) <= _parse_time(previous.get("measured_at")):
            return {"status": "REFUSED", "reason": "current step measurement must be later than previous step measurement", "site_deltas": []}
    except ValueError as exc:
        return {"status": "INCONCLUSIVE", "reason": str(exc), "site_deltas": []}
    before, after = _physical_site_values(previous, cancel), _physical_site_values(current, cancel)
    matched_keys = before.keys() & after.keys()
    if common_site_policy is None and before.keys() != after.keys():
        return {"status": "INCONCLUSIVE", "reason": "observed coordinate sets differ; no interpolation was performed", "site_deltas": []}
    minimum_sites, minimum_coverage = common_site_policy if common_site_policy else (0, 0.0)
    before_coverage = len(matched_keys) / len(before)
    after_coverage = len(matched_keys) / len(after)
    if common_site_policy is not None and (len(matched_keys) < minimum_sites
            or before_coverage < minimum_coverage or after_coverage < minimum_coverage):
        return {"status": "INCONCLUSIVE", "reason": "exact common-site overlap is below the predeclared site or coverage minimum; no interpolation was performed",
                "site_deltas": [], "matched_sites": len(matched_keys),
                "coverage": {"previous": before_coverage, "current": after_coverage}}
    deltas = []
    site_uncertainties = []
    residuals = []
    previous_prepared = _prepare_map(previous, cancel)
    current_prepared = _prepare_map(current, cancel)
    for index, key in enumerate(sorted(matched_keys)):
        if index % 1024 == 0:
            _check_cancel(cancel)
        p0, v0 = before[key]
        p1, v1 = after[key]
        prev_coordinates = _rotate(p0["x"], p0["y"], previous_prepared["orientation_deg"])
        current_coordinates = _rotate(p1["x"], p1["y"], current_prepared["orientation_deg"])
        residuals.append(hypot(prev_coordinates[0] - current_coordinates[0], prev_coordinates[1] - current_coordinates[1]))
        deltas.append({"site_id": p1["site_id"], "x_normalized": key[0], "y_normalized": key[1], "previous": v0, "current": v1, "delta": v1 - v0})
        u0, u1 = p0.get("standard_uncertainty"), p1.get("standard_uncertainty")
        if u0 is None or u1 is None:
            site_uncertainties.append(None)
        else:
            combined = sqrt(u0 * u0 + u1 * u1)
            site_uncertainties.append(combined)
            deltas[-1]["standard_uncertainty"] = combined
    if deltas and all(value is not None for value in site_uncertainties):
        mean_uncertainty = sqrt(sum(value * value for value in site_uncertainties) / len(site_uncertainties) ** 2)
        measurement_uncertainty = {"status": "PROPAGATED_FROM_SITE_STANDARD_UNCERTAINTIES",
                                   "mean_delta_standard_uncertainty": mean_uncertainty,
                                   "unit": _measurement(current).get("unit"),
                                   "assumption": "independent previous/current measurements and independent matched sites"}
    else:
        measurement_uncertainty = {"status": "NOT_SUPPLIED", "mean_delta_standard_uncertainty": None,
                                   "unit": _measurement(current).get("unit")}
    return {
        "status": "VALID",
        "matched_sites": len(deltas),
        "mean_delta": mean(row["delta"] for row in deltas),
        "registration_residual": max(residuals, default=0.0),
        "site_deltas": deltas,
        "alignment": "exact observed-site match after declared origin/orientation transform" if common_site_policy is None else "predeclared exact common-site match after declared origin/orientation transform; no reconstruction",
        "alignment_method": "exact_observed_site_v1" if common_site_policy is None else "exact_common_site_v1",
        "coverage": {"previous": before_coverage, "current": after_coverage,
                     "unmatched_previous_sites": len(before) - len(matched_keys),
                     "unmatched_current_sites": len(after) - len(matched_keys)},
        "uncertainty": {"registration_residual_units": "coordinate unit", "maximum_matched_site_coordinate_residual": max(residuals, default=0.0),
                        "coordinate_key_tolerance_normalized_per_axis": 1e-8,
                        "measurement_repeatability": measurement_uncertainty},
        "steps": [previous["step_id"], current["step_id"]],
    }


def compare_evolution_sequence(previous_steps: list[dict], current: dict, cancel=None) -> dict:
    """Compare an ordered same-wafer sequence and summarize site-level direction persistence."""
    if not isinstance(previous_steps, list) or not previous_steps:
        return {"status": "INCONCLUSIVE", "reason": "at least one prior step map is required", "site_deltas": []}
    maps = previous_steps + [current]
    comparisons = []
    for before, after in zip(maps, maps[1:]):
        _check_cancel(cancel)
        result = compare_evolution(before, after, cancel)
        if result.get("status") != "VALID":
            return {"status": result.get("status", "INCONCLUSIVE"), "reason": result.get("reason", "step sequence is not comparable"),
                    "site_deltas": [], "comparisons": comparisons}
        comparisons.append(result)
    site_changes: dict[tuple[float, float], list[float]] = {}
    site_uncertainty_changes: dict[tuple[float, float], list[float | None]] = {}
    site_labels: dict[tuple[float, float], str] = {}
    for result in comparisons:
        for row in result["site_deltas"]:
            key = (row["x_normalized"], row["y_normalized"])
            site_changes.setdefault(key, []).append(row["delta"])
            site_uncertainty_changes.setdefault(key, []).append(row.get("standard_uncertainty"))
            site_labels[key] = row["site_id"]
    persistent = []
    totals = []
    for key in sorted(site_changes):
        deltas = site_changes[key]
        signs = {1 if value > 0 else -1 for value in deltas if value != 0}
        direction_persistent = len(deltas) > 1 and len(signs) == 1 and all(value != 0 for value in deltas)
        total_delta = sum(deltas)
        totals.append(total_delta)
        persistent.append({"site_id": site_labels[key], "x_normalized": key[0], "y_normalized": key[1],
                           "step_deltas": deltas, "total_delta": total_delta,
                           "direction_persistent": direction_persistent,
                           "_transition_standard_uncertainties": site_uncertainty_changes.get(key, [])})
    persistent_count = sum(row["direction_persistent"] for row in persistent)
    step_ids = [item.get("step_id") for item in maps]
    sequence_uncertainties = []
    for row in persistent:
        values = row.pop("_transition_standard_uncertainties", [])
        if len(values) == len(comparisons) and all(value is not None for value in values):
            total_u = sqrt(sum(value * value for value in values))
            row["total_delta_standard_uncertainty"] = total_u
            sequence_uncertainties.append(total_u)
        else:
            row["total_delta_standard_uncertainty"] = None
    if len(sequence_uncertainties) == len(persistent) and persistent:
        sequence_measurement_uncertainty = {"status": "PROPAGATED_FROM_SITE_STANDARD_UNCERTAINTIES",
                                            "mean_total_delta_standard_uncertainty": sqrt(sum(value * value for value in sequence_uncertainties) / len(sequence_uncertainties) ** 2),
                                            "assumption": "independent measurements across transitions and independent matched sites"}
    else:
        sequence_measurement_uncertainty = {"status": "NOT_SUPPLIED", "mean_total_delta_standard_uncertainty": None}
    return {"status": "VALID", "matched_sites": len(persistent), "mean_delta": mean(totals),
            "registration_residual": max(result["registration_residual"] for result in comparisons),
            "site_deltas": persistent, "steps": [step_ids[0], step_ids[-1]], "step_sequence": step_ids,
            "comparisons": comparisons,
            "persistence": {"transitions": len(comparisons), "sites_with_same_nonzero_direction": persistent_count,
                            "fraction_with_same_nonzero_direction": persistent_count / len(persistent) if persistent else None},
            "uncertainty": {"registration": "exact declared-origin/orientation coordinate match; no transform uncertainty supplied",
                            "measurement_repeatability": sequence_measurement_uncertainty}}


def _spatial_profiles(prepared: dict) -> dict[str, dict[int, dict[str, float | int]]]:
    points = prepared["points"]
    overall = mean(point["value"] for point in points)
    radial: dict[int, list[float]] = {}
    sectors: dict[int, list[float]] = {}
    for point in points:
        fraction = point["radius_fraction"]
        radial_bin = 0 if fraction <= 0.2 else 1 if fraction <= 0.5 else 2 if fraction <= 0.8 else 3
        radial.setdefault(radial_bin, []).append(point["value"])
        sector = _sector_index(point["x"], point["y"], prepared["orientation_deg"])
        sectors.setdefault(sector, []).append(point["value"])
    return {"radial": {key: {"centered_mean": mean(values) - overall, "count": len(values)}
                        for key, values in radial.items()},
            "sectors": {key: {"centered_mean": mean(values) - overall, "count": len(values)}
                        for key, values in sectors.items()}}


class SpatialSignatureIndex:
    """Offline in-memory snapshot index with explicit invalidation and refresh."""

    def __init__(self, maps, *, max_maps=50_000, max_total_sites=1_000_000, cancel=None):
        if type(max_maps) is not int or not 1 <= max_maps <= 100_000:
            raise ValueError("max_maps must be between 1 and 100000")
        if type(max_total_sites) is not int or not 1 <= max_total_sites <= 5_000_000:
            raise ValueError("max_total_sites must be between 1 and 5000000")
        if not isinstance(maps, list) or len(maps) > max_maps:
            raise ValueError("index input must be a bounded list of historical maps")
        site_count = 0
        for item in maps:
            points = item.get("points") if isinstance(item, dict) else None
            if isinstance(points, list):
                site_count += len(points)
                if site_count > max_total_sites:
                    raise ValueError("historical index exceeds the configured total-site limit")
        self._max_maps = max_maps
        self._max_total_sites = max_total_sites
        self._lock = RLock()
        self._generation = 1
        self._invalidated = False
        # Keep the descriptors tied to the exact records that were validated.
        # Callers may reuse or mutate their input list after index construction.
        self._maps = deepcopy(maps)
        self._cache: dict[int, dict[str, Any]] = {}
        self._total_sites = 0
        self._indexed = 0
        self._excluded = 0
        for index, item in enumerate(self._maps):
            if index % 32 == 0:
                _check_cancel(cancel)
            try:
                if not isinstance(item, dict):
                    raise ValueError("historical map is not an object")
                points = item.get("points")
                if not isinstance(points, list):
                    raise ValueError("historical map points must be a list")
                self._total_sites += len(points)
                if self._total_sites > max_total_sites:
                    raise ValueError("historical index exceeds the configured total-site limit")
                prepared = _prepare_map(item)
                if prepared["measurement"].get("modality") not in ("continuous", "sparse_continuous"):
                    raise ValueError("numeric spatial index does not accept categorical or event maps")
                sites = _physical_site_values(item, prepared=prepared)
                profiles = _spatial_profiles(prepared)
                self._cache[id(item)] = {"prepared": prepared, "sites": sites, "profiles": profiles}
                self._indexed += 1
            except (ValueError, KeyError, TypeError, PermissionError) as exc:
                self._cache[id(item)] = {"error": str(exc)}
                self._excluded += 1
                if "total-site limit" in str(exc):
                    raise

    @property
    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {"historical_maps": len(self._maps), "indexed_maps": self._indexed,
                    "excluded_maps": self._excluded, "indexed_sites": self._total_sites,
                    "generation": self._generation, "invalidated": self._invalidated}

    def invalidate(self) -> dict[str, Any]:
        """Drop a stale snapshot before its backing historical population changes."""
        with self._lock:
            self._maps = []
            self._cache.clear()
            self._total_sites = self._indexed = self._excluded = 0
            self._invalidated = True
            return self.stats

    def refresh(self, maps, *, cancel=None) -> dict[str, Any]:
        """Build a bounded replacement snapshot and atomically publish its cache."""
        replacement = type(self)(maps, max_maps=self._max_maps,
                                 max_total_sites=self._max_total_sites, cancel=cancel)
        with self._lock:
            self._maps = replacement._maps
            self._cache = replacement._cache
            self._total_sites = replacement._total_sites
            self._indexed = replacement._indexed
            self._excluded = replacement._excluded
            self._invalidated = False
            self._generation += 1
            return self.stats

    def search(self, current: dict, top_k=5, cancel=None) -> dict:
        with self._lock:
            if self._invalidated:
                return {"status": "INCONCLUSIVE",
                        "reason": "historical index snapshot was invalidated and must be refreshed before search",
                        "neighbors": [], "index": self.stats}
            return search_history(current, self._maps, top_k=top_k, cancel=cancel,
                                  _prepared_cache=self._cache, index_stats=self.stats)


def search_history(current: dict, history: list[dict], top_k=5, cancel=None, *,
                   _prepared_cache=None, index_stats=None) -> dict:
    if not isinstance(history, list) or not history:
        return {"status": "INCONCLUSIVE", "reason": "no historical maps supplied", "neighbors": []}
    if not current.get("wafer_id") or not current.get("lot_id"):
        return {"status": "INCONCLUSIVE", "reason": "target wafer and lot identities are required for independent historical search", "neighbors": []}
    try:
        _parse_time(current.get("measured_at"))
    except ValueError as exc:
        return {"status": "INCONCLUSIVE", "reason": str(exc), "neighbors": []}
    if type(top_k) is not int or not 1 <= top_k <= 50:
        return {"status": "INCONCLUSIVE", "reason": "top_k must be between 1 and 50", "neighbors": []}
    try:
        current_prepared = _prepare_map(current, cancel)
        current_sites = _physical_site_values(current, cancel, prepared=current_prepared)
    except (ValueError, KeyError, TypeError, PermissionError) as exc:
        return {"status": "INCONCLUSIVE", "reason": str(exc), "neighbors": []}
    if current_prepared["measurement"].get("modality") not in ("continuous", "sparse_continuous"):
        return {"status": "INCONCLUSIVE", "reason": "numeric historical profile retrieval is unavailable for categorical or event data", "neighbors": []}
    current_mean = mean(p["value"] for p in current_prepared["points"])
    current_profiles = _spatial_profiles(current_prepared)
    rows = []
    excluded = []
    for candidate in history:
        _check_cancel(cancel)
        if not isinstance(candidate, dict):
            excluded.append({"wafer_id": None, "reason": "historical map is not an object"})
            continue
        try:
            if not current.get("lot_id") or not candidate.get("lot_id") or candidate.get("lot_id") == current.get("lot_id"):
                excluded.append({"wafer_id": candidate.get("wafer_id"), "reason": "historical lot is missing or not independent"})
                continue
            if _parse_time(candidate.get("measured_at")) >= _parse_time(current.get("measured_at")):
                excluded.append({"wafer_id": candidate.get("wafer_id"), "reason": "record is not earlier than the target map"})
                continue
        except ValueError as exc:
            excluded.append({"wafer_id": candidate.get("wafer_id"), "reason": str(exc)})
            continue
        cached = _prepared_cache.get(id(candidate)) if _prepared_cache is not None else None
        if isinstance(cached, dict) and cached.get("error"):
            excluded.append({"wafer_id": candidate.get("wafer_id"), "reason": cached["error"]})
            continue
        try:
            candidate_prepared = cached["prepared"] if isinstance(cached, dict) else _prepare_map(candidate, cancel)
            ok, reason = _context_compatible(current, candidate, cancel=cancel, require_sampling_mask=False,
                                             prepared_left=current_prepared, prepared_right=candidate_prepared)
        except (ValueError, KeyError, TypeError, PermissionError) as exc:
            excluded.append({"wafer_id": candidate.get("wafer_id") if isinstance(candidate, dict) else None, "reason": str(exc)})
            continue
        if not ok:
            excluded.append({"wafer_id": candidate.get("wafer_id"), "reason": reason})
            continue
        if not candidate.get("wafer_id") or candidate.get("wafer_id") == current.get("wafer_id"):
            excluded.append({"wafer_id": candidate.get("wafer_id"), "reason": "missing or non-independent wafer identity"})
            continue
        try:
            sites = cached["sites"] if isinstance(cached, dict) else _physical_site_values(candidate, cancel, prepared=candidate_prepared)
        except (ValueError, KeyError, TypeError, PermissionError) as exc:
            excluded.append({"wafer_id": candidate.get("wafer_id"), "reason": str(exc)})
            continue
        if candidate_prepared["measurement"].get("modality") not in ("continuous", "sparse_continuous"):
            excluded.append({"wafer_id": candidate.get("wafer_id"), "reason": "numeric profile retrieval is unavailable for categorical or event data"})
            continue
        cand_values = [entry[1] for entry in sites.values()]
        mean_candidate = mean(cand_values)
        shape_rmse = None
        numeric_floor = max(max((abs(value) for value in [current_sites[key][1] for key in current_sites]
                                  + [sites[key][1] for key in sites]), default=0.0) * 1e-12, 1e-300)
        raw_rmse = None
        if current_sites.keys() == sites.keys():
            current_centered = [current_sites[key][1] - current_mean for key in current_sites]
            candidate_centered = [sites[key][1] - mean_candidate for key in current_sites]
            shape_rmse = sqrt(mean((a - b) ** 2 for a, b in zip(current_centered, candidate_centered)))
            if shape_rmse <= numeric_floor:
                shape_rmse = 0.0
            raw_rmse = sqrt(mean((current_sites[key][1] - sites[key][1]) ** 2 for key in current_sites))
        candidate_profiles = cached["profiles"] if isinstance(cached, dict) else _spatial_profiles(candidate_prepared)
        radial_groups = sorted(set(current_profiles["radial"]) & set(candidate_profiles["radial"]))
        sector_groups = sorted(set(current_profiles["sectors"]) & set(candidate_profiles["sectors"]))
        if current_sites.keys() != sites.keys() and (len(radial_groups) < 2 or len(sector_groups) < 4):
            excluded.append({"wafer_id": candidate.get("wafer_id"),
                             "reason": "different sampling layouts share fewer than two radial and four sector profile bins"})
            continue
        def profile_rmse(left, right, groups):
            if not groups:
                return None
            return sqrt(mean((left[group]["centered_mean"] - right[group]["centered_mean"]) ** 2
                             for group in groups))

        radial_rmse = profile_rmse(current_profiles["radial"], candidate_profiles["radial"], radial_groups)
        sector_rmse = profile_rmse(current_profiles["sectors"], candidate_profiles["sectors"], sector_groups)
        radial_rmse = 0.0 if radial_rmse is not None and radial_rmse <= numeric_floor else radial_rmse
        sector_rmse = 0.0 if sector_rmse is not None and sector_rmse <= numeric_floor else sector_rmse
        levels = ([shape_rmse] if shape_rmse is not None else []) + [value for value in (radial_rmse, sector_rmse) if value is not None]
        multiscale_rmse = sqrt(mean(value * value for value in levels))
        rows.append({"wafer_id": candidate["wafer_id"], "source_ids": _source_ids(candidate), "shape_rmse": shape_rmse,
                     "radial_profile_rmse": radial_rmse, "sector_profile_rmse": sector_rmse,
                     "multiscale_rmse": multiscale_rmse,
                     "distance_components": {"site_centered_rmse": shape_rmse, "radial_profile_rmse": radial_rmse,
                                             "sector_profile_rmse": sector_rmse},
                     "raw_rmse": raw_rmse, "mean_level_delta": mean_candidate - current_mean,
                     "alignment": "exact observed-site values" if shape_rmse is not None else "common radial/sector profile descriptors; no reconstruction",
                     "profile_coverage": {"shared_radial_bins": len(radial_groups), "current_radial_bins": len(current_profiles["radial"]),
                                          "candidate_radial_bins": len(candidate_profiles["radial"]), "shared_sector_bins": len(sector_groups),
                                          "current_sector_bins": len(current_profiles["sectors"]), "candidate_sector_bins": len(candidate_profiles["sectors"])}})
    rank_key = lambda row: (row["multiscale_rmse"], row["shape_rmse"] if row["shape_rmse"] is not None else row["multiscale_rmse"],
                            row["raw_rmse"] if row["raw_rmse"] is not None else row["multiscale_rmse"], str(row["wafer_id"]))
    neighbors = heapq.nsmallest(top_k, rows, key=rank_key)
    return {"status": "VALID" if rows else "INCONCLUSIVE", "reason": None if rows else "no compatible historical maps", "neighbors": neighbors, "excluded": excluded,
            "index": index_stats, "interpretation": "spatial profile similarity only; common-profile comparisons use observed bins without interpolation and a neighbor does not establish a shared mechanism"}


def detect_anomalies(current: dict, baseline: list[dict], *, holdout_verified=False, cancel=None) -> dict:
    """Calibrated wafer-level max-T screen; site rows are post-test localizers only."""
    if not isinstance(baseline, list) or not baseline:
        return {"status": "INCONCLUSIVE", "reason": "matched baseline population is unavailable", "outliers": []}
    if holdout_verified is not True:
        return {"status": "INCONCLUSIVE", "reason": "wafer/lot/time holdout and leakage checks are not verified", "outliers": []}
    _check_cancel(cancel)
    current_sites = _physical_site_values(current, cancel)
    prepared = []
    seen_wafers = set()
    seen_lots = set()
    try:
        current_lot = current.get("lot_id")
        current_time = _parse_time(current.get("measured_at"))
        if not current_lot or not current.get("wafer_id"):
            raise ValueError("current wafer and lot identities are required for grouped baseline checks")
    except (TypeError, ValueError) as exc:
        return {"status": "INCONCLUSIVE", "reason": str(exc), "outliers": []}
    for item in baseline:
        _check_cancel(cancel)
        if not isinstance(item, dict):
            return {"status": "INCONCLUSIVE", "reason": "baseline entry is not a map object", "outliers": []}
        if not item.get("wafer_id") or item["wafer_id"] in seen_wafers or item.get("wafer_id") == current.get("wafer_id"):
            return {"status": "INCONCLUSIVE", "reason": "baseline must use distinct independent wafers", "outliers": []}
        seen_wafers.add(item["wafer_id"])
        lot = item.get("lot_id")
        if not lot or lot == current_lot or lot in seen_lots:
            return {"status": "INCONCLUSIVE", "reason": "holdout baseline must be grouped by distinct lots", "outliers": []}
        seen_lots.add(lot)
        try:
            if _parse_time(item.get("measured_at")) >= current_time:
                return {"status": "INCONCLUSIVE", "reason": "baseline time must precede the target wafer", "outliers": []}
        except ValueError as exc:
            return {"status": "INCONCLUSIVE", "reason": str(exc), "outliers": []}
        ok, reason = _context_compatible(current, item, cancel=cancel)
        if not ok:
            return {"status": "INCONCLUSIVE", "reason": "baseline compatibility failed: " + reason, "outliers": []}
        sites = _physical_site_values(item, cancel)
        if current_sites.keys() != sites.keys():
            return {"status": "INCONCLUSIVE", "reason": "baseline observed-site masks differ", "outliers": []}
        prepared.append(sites)
    if len(prepared) < 20:
        return {"status": "INCONCLUSIVE", "reason": "at least 20 distinct baseline wafers are required for the empirical screen", "outliers": [], "baseline_wafers": len(prepared)}

    rows = []
    for index, key in enumerate(sorted(current_sites)):
        if index % 1024 == 0:
            _check_cancel(cancel)
        observed = current_sites[key][1]
        values = [sites[key][1] for sites in prepared]
        middle = median(values)
        deviations = [abs(value - middle) for value in values]
        mad = median(deviations)
        robust_z = (0.67448975 * (observed - middle) / mad) if mad > 0 else (0.0 if observed == middle else None)
        robust_extreme = (abs(robust_z) >= ANOMALY_ROBUST_Z) if robust_z is not None else observed != middle
        rows.append({"site_id": current_sites[key][0]["site_id"], "value": observed, "baseline_median": middle,
                     "baseline_mad": mad, "robust_z": robust_z, "robust_scale_zero_and_shifted": robust_z is None and observed != middle,
                     "robust_extreme": robust_extreme, "localizer_candidate": False})

    # A single wafer-level maximum statistic controls the search over all measured
    # sites while preserving the observed spatial dependence. Leave-one-wafer-out
    # scores are symmetric across the target and baseline maps; this avoids treating
    # correlated sites as independent tests.
    maps = list(baseline) + [current]
    max_statistics = []
    target_index = len(maps) - 1
    target_scores = []
    for focus_index, focus in enumerate(maps):
        _check_cancel(cancel)
        focus_sites = current_sites if focus_index == target_index else _physical_site_values(focus, cancel)
        reference_sites = [prepared[index] if index < target_index else current_sites
                           for index in range(len(maps)) if index != focus_index]
        scores = []
        for key in sorted(focus_sites):
            values = [sites[key][1] for sites in reference_sites]
            middle = median(values)
            scale = _mad(values)
            observed = focus_sites[key][1]
            if scale and scale > 0:
                scores.append(abs(0.67448975 * (observed - middle) / scale))
            else:
                scores.append(float("inf") if observed != middle else 0.0)
        maximum = max(scores, default=0.0)
        max_statistics.append(maximum)
        if focus_index == target_index:
            target_scores = scores
    target_max = max(target_scores, default=0.0)
    null_max = max_statistics[:target_index]
    max_t_p = (1 + sum(value >= target_max for value in null_max)) / (len(null_max) + 1)
    for row, score in zip(rows, target_scores):
        row["max_t_score"] = score if isfinite(score) else None
        row["localizer_candidate"] = max_t_p <= ANOMALY_ALPHA and row["robust_extreme"]
    outliers = [row for row in rows if row["localizer_candidate"]]
    return {"status": "VALID", "baseline_wafers": len(prepared), "baseline_lots": len(seen_lots),
            "tested_sites": len(rows), "alpha": ANOMALY_ALPHA,
            "global_max_t_empirical_p": max_t_p,
            "minimum_attainable_global_p": 1 / (len(prepared) + 1),
            "global_test_method": "leave_one_wafer_out_spatial_maxT_rank_v1",
            "site_scores": rows, "outliers": outliers,
            "localization_interpretation": "localized sites contribute to a wafer-level max-T finding; site rows are not individually significant",
            "interpretation": "conditional whole-wafer outlier screen against the supplied matched population; spatial dependence is preserved and the result is not a root-cause finding"}


def _parse_time(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ValueError("timestamps must be ISO-8601 strings with timezone")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("timestamps must be ISO-8601 strings with timezone") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timestamps must include an explicit timezone")
    return parsed


def _t_critical_95(df: int) -> float:
    """Cornish-Fisher approximation to two-sided Student-t 95% critical value."""
    z = 1.959963984540054
    n = float(df)
    z2 = z * z
    return (z + (z * z2 + z) / (4 * n)
            + (5 * z * z2 * z2 + 16 * z * z2 + 3 * z) / (96 * n * n)
            + (3 * z * z2 * z2 * z2 + 19 * z * z2 * z2 + 17 * z * z2 - 15 * z) / (384 * n * n * n))


def associate_quality(association: dict, expected_context=None, expected_coordinates=None, cancel=None) -> dict:
    """Spatially matched die analysis, summarized with wafer as independent unit."""
    if not isinstance(association, dict):
        return {"status": "INCONCLUSIVE", "reason": "downstream association inputs are unavailable"}
    if not isinstance(expected_context, dict) or not isinstance(expected_coordinates, set) or len(expected_coordinates) < 5:
        return {"status": "INCONCLUSIVE", "reason": "a selected map with at least five verified observed sites is required for spatial matching"}
    supplied_context = association.get("context")
    required_context = ("product_id", "metric", "measurement_definition_id", "unit", "layer", "population_signature", "sampling_mask_id")
    optional_context = ("recipe_id", "tool_id", "chamber_id", "route_id")
    context_keys = required_context + tuple(key for key in optional_context if expected_context.get(key) is not None)
    if not isinstance(supplied_context, dict) or any(
        not expected_context.get(key) or supplied_context.get(key) != expected_context[key]
        for key in context_keys
    ):
        return {"status": "INCONCLUSIVE", "reason": "downstream cohort does not match the selected map's product/measurement/population context"}
    if any(supplied_context.get(key) is not None and expected_context.get(key) is None for key in optional_context):
        return {"status": "INCONCLUSIVE", "reason": "selected map lacks tool/recipe/chamber/route context needed to control the downstream cohort"}
    relation = association.get("relationship", {})
    if not isinstance(relation, dict):
        return {"status": "REFUSED", "reason": "relationship definition must be a structured approved record"}
    if relation.get("approved") is not True or not relation.get("source_id") or relation.get("grain") != "wafer_die" or relation.get("coordinate_mapping_verified") is not True:
        return {"status": "REFUSED", "reason": "an approved wafer-to-die coordinate relationship is required"}
    if relation.get("spatial_block_method") != "predeclared_block_fixed_effects_v1":
        return {"status": "INCONCLUSIVE", "reason": "a predeclared spatial block mapping is required for adjusted association"}
    geometry = association.get("geometry")
    if not isinstance(geometry, dict) or geometry.get("verified") is not True:
        return {"status": "INCONCLUSIVE", "reason": "verified downstream wafer/die geometry is required"}
    radius = geometry.get("radius")
    origin = geometry.get("origin", {"x": 0, "y": 0})
    if isinstance(origin, (list, tuple)) and len(origin) == 2:
        ox, oy = origin
    elif isinstance(origin, dict):
        ox, oy = origin.get("x", 0), origin.get("y", 0)
    else:
        return {"status": "INCONCLUSIVE", "reason": "downstream coordinate origin is invalid"}
    if (not _number(radius) or radius <= 0 or radius > MAX_ABS_NUMERIC
            or not _number(ox) or not _number(oy) or not geometry.get("coordinate_system") or not geometry.get("coordinate_unit")):
        return {"status": "INCONCLUSIVE", "reason": "downstream coordinate system, units, origin and radius are required"}
    orientation = geometry.get("orientation_deg")
    expected_radius = expected_context.get("radius")
    if (not _number(orientation) or not 0 <= orientation < 360
            or not _number(expected_radius) or expected_radius <= 0
            or geometry.get("coordinate_system") != expected_context.get("coordinate_system")
            or geometry.get("coordinate_unit") != expected_context.get("coordinate_unit")
            or abs(radius - expected_radius) > max(radius, expected_radius) * 1e-8
            or orientation != expected_context.get("orientation_deg")):
        return {"status": "INCONCLUSIVE", "reason": "downstream coordinate frame does not match the selected map's verified geometry"}
    holdout = association.get("holdout", {})
    if not isinstance(holdout, dict):
        return {"status": "INCONCLUSIVE", "reason": "out-of-time holdout metadata is missing"}
    if (holdout.get("verified") is not True or holdout.get("split_method") != "out_of_time_by_wafer_and_lot"
            or holdout.get("grouped_by_wafer") is not True or holdout.get("grouped_by_lot") is not True
            or holdout.get("leakage_checked") is not True):
        return {"status": "INCONCLUSIVE", "reason": "out-of-time holdout grouped by wafer and lot with leakage checks is required"}
    rows = association.get("observations")
    if not isinstance(rows, list):
        return {"status": "INCONCLUSIVE", "reason": "spatially matched feature/outcome observations are required"}
    grouped: dict[str, list[tuple[float, float, str]]] = {}
    seen = set()
    seen_coordinates: dict[str, set[tuple[int, int]]] = {}
    coordinate_blocks: dict[tuple[int, int], str] = {}
    wafer_lots: dict[str, str] = {}
    lot_wafers: dict[str, str] = {}
    context_signature = None
    try:
        for index, row in enumerate(rows):
            if index % 1024 == 0:
                _check_cancel(cancel)
            wafer = row.get("wafer_id")
            die = row.get("die_id")
            if not wafer or not die or (wafer, die) in seen:
                return {"status": "REFUSED", "reason": "each wafer/die pair must be unique and identified"}
            seen.add((wafer, die))
            if row.get("cohort") != "holdout":
                continue
            lot = row.get("lot_id")
            if not isinstance(lot, str) or not lot.strip():
                return {"status": "INCONCLUSIVE", "reason": "each holdout wafer must carry a verified lot identity"}
            if wafer in wafer_lots and wafer_lots[wafer] != lot:
                return {"status": "INCONCLUSIVE", "reason": "a holdout wafer maps to multiple lots"}
            if lot in lot_wafers and lot_wafers[lot] != wafer:
                return {"status": "INCONCLUSIVE", "reason": "holdout wafers are not independent by lot"}
            wafer_lots[str(wafer)] = lot
            lot_wafers[lot] = str(wafer)
            t_feature = _parse_time(row.get("feature_at"))
            t_outcome = _parse_time(row.get("outcome_at"))
            if t_outcome <= t_feature:
                return {"status": "REFUSED", "reason": "downstream outcome must occur after the measured spatial feature"}
            x, y = row.get("feature_value"), row.get("outcome_value")
            if not _number(row.get("x")) or not _number(row.get("y")):
                return {"status": "INCONCLUSIVE", "reason": "verified die coordinates are required for spatial matching"}
            x_coord, y_coord = float(row["x"]) - float(ox), float(row["y"]) - float(oy)
            if hypot(x_coord, y_coord) > radius + max(radius * 1e-9, 1e-12):
                return {"status": "REFUSED", "reason": "downstream die coordinate lies outside the verified wafer geometry"}
            aligned_x, aligned_y = _rotate(x_coord, y_coord, orientation)
            site_key = (round(aligned_x / radius, 8), round(aligned_y / radius, 8))
            wafer_sites = seen_coordinates.setdefault(str(wafer), set())
            if site_key in wafer_sites:
                return {"status": "REFUSED", "reason": "duplicate die coordinates within a wafer"}
            wafer_sites.add(site_key)
            if site_key not in expected_coordinates:
                return {"status": "REFUSED", "reason": "downstream die coordinate is not an observed site on the selected map"}
            block_id = row.get("spatial_block_id")
            if not isinstance(block_id, str) or not block_id.strip():
                return {"status": "INCONCLUSIVE", "reason": "each matched die must carry its predeclared spatial block identifier"}
            if site_key in coordinate_blocks and coordinate_blocks[site_key] != block_id:
                return {"status": "INCONCLUSIVE", "reason": "spatial block mapping changes across holdout wafers"}
            coordinate_blocks[site_key] = block_id
            row_context = tuple(row.get(key) for key in context_keys)
            expected_row_context = tuple(expected_context[key] for key in context_keys)
            if any(row.get(key) is not None and expected_context.get(key) is None for key in optional_context):
                return {"status": "INCONCLUSIVE", "reason": "holdout row includes tool/recipe/chamber/route context unavailable on the selected map"}
            if not all(row_context) or row_context != expected_row_context:
                return {"status": "INCONCLUSIVE", "reason": "downstream observation product/measurement/population context is missing or mismatched"}
            if context_signature is None:
                context_signature = row_context
            elif row_context != context_signature:
                return {"status": "INCONCLUSIVE", "reason": "quality association rows mix product or measurement definitions"}
            if not _number(x) or not _number(y):
                return {"status": "INCONCLUSIVE", "reason": "feature and outcome values must be finite numbers"}
            if abs(x) > MAX_ABS_NUMERIC or abs(y) > MAX_ABS_NUMERIC:
                return {"status": "INCONCLUSIVE", "reason": "feature or outcome exceeds the numeric range limit"}
            grouped.setdefault(str(wafer), []).append((float(x), float(y), block_id))
    except (AttributeError, TypeError, ValueError) as exc:
        return {"status": "INCONCLUSIVE", "reason": str(exc)}
    if any(seen_coordinates.get(wafer, set()) != expected_coordinates for wafer in grouped):
        return {"status": "INCONCLUSIVE", "reason": "holdout wafers do not cover the selected map's exact observed-site mask"}
    if len(grouped) < 20 or len(lot_wafers) < 20:
        return {"status": "INCONCLUSIVE", "reason": "at least 20 independent holdout wafers from distinct lots are required", "wafers": len(grouped), "lots": len(lot_wafers)}
    wafer_correlations = []
    matched_sites = 0
    for index, (wafer, pairs) in enumerate(sorted(grouped.items())):
        if index % 32 == 0:
            _check_cancel(cancel)
        if len(pairs) < 5:
            return {"status": "INCONCLUSIVE", "reason": f"wafer {wafer} has fewer than five spatially matched die sites", "wafers": len(grouped)}
        blocks: dict[str, list[tuple[float, float]]] = {}
        for feature, outcome, block_id in pairs:
            blocks.setdefault(block_id, []).append((feature, outcome))
        if len(blocks) < 2 or any(len(values) < 2 for values in blocks.values()):
            return {"status": "INCONCLUSIVE", "reason": f"wafer {wafer} needs at least two observations in each of two spatial blocks", "wafers": len(grouped)}
        residuals = []
        for values in blocks.values():
            block_x = mean(pair[0] for pair in values)
            block_y = mean(pair[1] for pair in values)
            residuals.extend((x - block_x, y - block_y) for x, y in values)
        xs, ys = [p[0] for p in residuals], [p[1] for p in residuals]
        mx, my = mean(xs), mean(ys)
        ssx = sum((x - mx) ** 2 for x in xs)
        ssy = sum((y - my) ** 2 for y in ys)
        if ssx == 0 or ssy == 0:
            return {"status": "INCONCLUSIVE", "reason": f"association is undefined on wafer {wafer}", "wafers": len(grouped)}
        r = sum((x - mx) * (y - my) for x, y in residuals) / sqrt(ssx * ssy)
        r = min(0.999999999, max(-0.999999999, r))
        wafer_correlations.append(0.5 * log((1 + r) / (1 - r)))
        matched_sites += len(pairs)
    mean_z = mean(wafer_correlations)
    se = sqrt(sum((z - mean_z) ** 2 for z in wafer_correlations) / (len(wafer_correlations) - 1) / len(wafer_correlations))
    critical = _t_critical_95(len(wafer_correlations) - 1)
    ci = [tanh(mean_z - critical * se), tanh(mean_z + critical * se)]
    leave_one_lot_out = [tanh(mean(wafer_correlations[:index] + wafer_correlations[index + 1:]))
                         for index in range(len(wafer_correlations))]
    return {"status": "VALID", "wafers": len(grouped), "matched_die_sites": matched_sites,
            "mean_within_wafer_r": tanh(mean_z), "fisher_wafer_95_ci": ci,
            "relationship_source_id": relation["source_id"], "grain": "wafer_die",
            "holdout_split": "out_of_time_by_wafer_and_lot",
            "independent_lots": len(lot_wafers),
            "population_scope": "context-matched holdout wafers",
            "spatial_block_method": "predeclared_block_fixed_effects_v1",
            "confounding_controls": {"product_measurement_population": "exact_context_match",
                                     "tool_recipe_chamber_route": "exact_match_when supplied; unavailable dimensions are rejected if they appear only in the cohort",
                                     "spatial_blocks": "within-wafer fixed effects",
                                     "independent_unit": "one holdout wafer from each of at least 20 distinct lots"},
            "uncertainty": {"interval": "95% t interval on Fisher-z transformed wafer correlations",
                            "leave_one_lot_out_r_range": [min(leave_one_lot_out), max(leave_one_lot_out)],
                            "leave_one_lot_out_estimates": leave_one_lot_out,
                            "measurement_repeatability": "NOT_SUPPLIED"},
            "interpretation": "observational within-wafer association adjusted for predeclared spatial blocks; it does not attribute the selected wafer's outcome; residual confounding and selection effects remain possible"}


def _source_ids(data: dict) -> list[str]:
    values = data.get("source_ids")
    if isinstance(values, list):
        return [str(value) for value in values if value]
    value = data.get("source_id")
    return [str(value)] if value else []


def analyze(data: dict, cancel=None) -> dict:
    """Run available P3 capabilities and return a shared evidence envelope."""
    _check_cancel(cancel)
    if not isinstance(data, dict):
        data = {"invalid_input": str(type(data).__name__)}
        ev = envelope("p3", data, "REFUSED", [], ["Analysis input must be a JSON object."])
        ev["claim_category"] = "NONE"
        return ev
    if data.get("mode") not in (None, "SYNTHETIC_DEMO"):
        ev = envelope("p3", data, "REFUSED", [], ["This build has no authorized company adapter; INTERNAL_AUTHORIZED analysis is unavailable."])
        ev["claim_category"] = "NONE"
        return ev
    if data.get("coordinates_verified") is not True:
        ev = envelope("p3", data, "REFUSED", [], ["Wafer coordinate system/orientation not verified."])
        ev["claim_category"] = "NONE"
        ev["artifacts"] = [{"kind": "p3_analysis", "result": {"fingerprint": {"status": "REFUSED"}, "anomaly": {"status": "REFUSED"}, "similarity": {"status": "REFUSED"}, "evolution": {"status": "REFUSED"}, "quality_association": {"status": "REFUSED"}}}]
        return ev
    try:
        base = fingerprint(data, cancel)
    except (ValueError, KeyError, TypeError, PermissionError) as exc:
        status = "REFUSED" if isinstance(exc, PermissionError) or "unsupported for modality" in str(exc) else "INCONCLUSIVE"
        ev = envelope("p3", data, status, [], ["Spatial analysis unavailable: " + str(exc)])
        ev["claim_category"] = "NONE"
        ev["artifacts"] = [{"kind": "p3_analysis", "result": {"fingerprint": {"status": status, "reason": str(exc)}}}]
        return ev

    source_ids = _source_ids(data)
    unit = base["measurement_unit"]
    limitations = ["No interpolation; unmeasured wafer regions remain unobserved.",
                   "No causal inference, manufacturing actuation, or company-system access is performed."]
    claims = []
    if base["edge_center"]["status"] == "VALID":
        claims.append(claim(
            f'Measured edge-center difference for {base["metric"]} = {base["edge_minus_center"]:g} {unit} from {base["observed_points"]} observed sites.',
            method=METHOD_VERSION, source_ids=source_ids,
        ))
    elif base["edge_center"]["status"] == "INCONCLUSIVE":
        limitations.append("C01 edge-center feature unavailable: " + base["edge_center"]["reason"])
    elif base["modality"] == "die_bin_categorical":
        category_totals: dict[str, int] = {}
        for region in base["regions"].values():
            for category, count in region.get("category_counts", {}).items():
                category_totals[category] = category_totals.get(category, 0) + count
        claims.append(claim(
            f'Observed categorical die/bin distribution for {base["metric"]} across {base["observed_points"]} measured sites: '
            + ", ".join(f"{category}={count}" for category, count in sorted(category_totals.items())) + ".",
            method="observed_categorical_site_counts_v1", source_ids=source_ids,
        ))
    elif base["modality"] == "defect_coordinates":
        claims.append(claim(
            f'Observed {base["observed_points"]} defect-coordinate events in the supplied measured-site set; no unobserved locations were inferred.',
            method="observed_defect_coordinate_counts_v1", source_ids=source_ids,
        ))
    report = {
        "fingerprint": {"status": "PARTIAL" if any(base[key].get("status") == "INCONCLUSIVE" for key in ("edge_center", "directional_gradient", "local_clusters")) or (isinstance(base["sectors"], dict) and base["sectors"].get("status") == "INCONCLUSIVE") else "VALID", **base},
        "anomaly": {"status": "NOT_REQUESTED", "reason": "matched baseline not supplied", "outliers": []},
        "similarity": {"status": "NOT_REQUESTED", "reason": "historical maps not supplied", "neighbors": []},
        "evolution": {"status": "NOT_REQUESTED", "reason": "prior step not supplied", "site_deltas": []},
        "quality_association": {"status": "NOT_REQUESTED", "reason": "downstream association not supplied"},
    }
    if base["directional_gradient"].get("status") == "INCONCLUSIVE" or (isinstance(base["sectors"], dict) and base["sectors"].get("status") == "INCONCLUSIVE"):
        limitations.append("C01 orientation-dependent features unavailable: verified wafer orientation was not supplied.")
    requested_raw = data.get("requested_capabilities", [])
    requested = {value for value in requested_raw if isinstance(value, str)} if isinstance(requested_raw, list) else set()

    baseline = data.get("baseline_population")
    if baseline is not None or "C04" in requested:
        try:
            report["anomaly"] = detect_anomalies(data, baseline or [], holdout_verified=data.get("baseline_holdout_verified", False), cancel=cancel)
        except (ValueError, KeyError, TypeError, PermissionError) as exc:
            report["anomaly"] = {"status": "INCONCLUSIVE", "reason": str(exc), "outliers": []}
        if report["anomaly"]["status"] == "VALID":
            count = len(report["anomaly"]["outliers"])
            baseline_sources = [source_id for item in baseline for source_id in _source_ids(item)]
            if report["anomaly"]["global_max_t_empirical_p"] <= report["anomaly"]["alpha"]:
                claims.append(claim(f"The measured wafer met the predeclared spatial max-T screen against {report['anomaly']['baseline_wafers']} matched baseline wafers (global empirical p={report['anomaly']['global_max_t_empirical_p']:.4g}); {count} measured sites localize the wafer-level signal and are not separately significant.",
                                     method="leave_one_wafer_out_spatial_maxT_rank_v1", source_ids=list(dict.fromkeys(source_ids + baseline_sources)), certainty="CONDITIONAL"))
            else:
                limitations.append(f"C04 max-T screen found no wafer-level alert at alpha={report['anomaly']['alpha']}; global empirical p={report['anomaly']['global_max_t_empirical_p']:.4g}.")
        else:
            limitations.append("C04 anomaly screen unavailable: " + report["anomaly"].get("reason", "insufficient evidence"))

    history = data.get("history")
    if history is not None or "C05" in requested:
        report["similarity"] = search_history(data, history or [], data.get("top_k", 5), cancel=cancel)
        if report["similarity"]["status"] == "VALID":
            top = report["similarity"]["neighbors"][0]
            claims.append(claim(f"Nearest compatible historical map is wafer {top['wafer_id']} by multiscale spatial descriptor RMSE {top['multiscale_rmse']:g} {unit}; similarity does not establish a shared cause.",
                                 method="exact_observed_site_centered_rmse_v1", source_ids=list(dict.fromkeys(source_ids + top.get("source_ids", []))), certainty="CONDITIONAL"))
        else:
            limitations.append("C05 historical search unavailable: " + report["similarity"].get("reason", "insufficient evidence"))

    previous = data.get("previous_step")
    previous_steps = data.get("previous_steps")
    if previous_steps is not None or previous is not None or "C02" in requested:
        try:
            prior_maps = previous_steps if previous_steps is not None else ([previous] if previous is not None else [])
            if len(prior_maps) == 1:
                report["evolution"] = compare_evolution(prior_maps[0], data, cancel,
                                                        match_policy=data.get("evolution_match_policy"))
            else:
                report["evolution"] = compare_evolution_sequence(prior_maps, data, cancel)
        except (ValueError, KeyError, TypeError, PermissionError) as exc:
            report["evolution"] = {"status": "INCONCLUSIVE", "reason": str(exc), "site_deltas": []}
        if report["evolution"]["status"] == "VALID":
            evo = report["evolution"]
            evolution_sources = [source_id for item in prior_maps if isinstance(item, dict) for source_id in _source_ids(item)]
            persistence = evo.get("persistence", {})
            persistence_text = (f" {persistence['fraction_with_same_nonzero_direction']:.1%} of sites kept the same nonzero direction across {persistence['transitions']} transitions."
                                if persistence.get("transitions", 0) > 1 and persistence.get("fraction_with_same_nonzero_direction") is not None else "")
            repeatability = evo.get("uncertainty", {}).get("measurement_repeatability", {})
            if repeatability.get("status") == "PROPAGATED_FROM_SITE_STANDARD_UNCERTAINTIES":
                mean_uncertainty = repeatability.get("mean_total_delta_standard_uncertainty",
                                                    repeatability.get("mean_delta_standard_uncertainty"))
                uncertainty_text = f" Propagated one-standard-uncertainty for the mean change was {mean_uncertainty:g} {unit}."
            else:
                uncertainty_text = " Measurement repeatability uncertainty was not supplied."
            claims.append(claim(f"Across {evo['matched_sites']} matched observed sites, mean change from {evo['steps'][0]} to {evo['steps'][1]} was {evo['mean_delta']:g} {unit}.{uncertainty_text}{persistence_text}",
                                 method="same_wafer_orientation_aligned_observed_delta_v1", source_ids=list(dict.fromkeys(source_ids + evolution_sources)), certainty="CONDITIONAL"))
        else:
            limitations.append("C02 evolution unavailable: " + report["evolution"].get("reason", "insufficient evidence"))

    association = data.get("quality_association")
    if association is not None or "C03" in requested:
        if base["modality"] not in ("continuous", "sparse_continuous"):
            report["quality_association"] = {"status": "INCONCLUSIVE",
                                             "reason": "downstream spatial association requires a numeric continuous measurement"}
        else:
            try:
                expected_context = {"product_id": data.get("product_id"), "metric": _measurement(data).get("metric"),
                                    "measurement_definition_id": _measurement(data).get("definition_id"), "unit": _measurement(data).get("unit"),
                                    "layer": _measurement(data).get("layer"), "population_signature": data.get("population_signature"),
                                    "sampling_mask_id": data.get("sampling_mask_id", data.get("sampling", {}).get("mask_id") if isinstance(data.get("sampling"), dict) else None)}
                for key in ("recipe_id", "tool_id", "chamber_id", "route_id"):
                    if data.get(key) is not None:
                        expected_context[key] = data[key]
                geometry_context = _prepare_map(data, cancel)
                expected_context.update({
                    "coordinate_system": geometry_context["coordinate_system"],
                    "coordinate_unit": geometry_context["coordinate_unit"],
                    "radius": geometry_context["radius"],
                    "orientation_deg": geometry_context["orientation_deg"],
                })
                expected_coordinates = set(_physical_site_values(data, cancel))
                report["quality_association"] = associate_quality(association or {}, expected_context=expected_context,
                                                                  expected_coordinates=expected_coordinates, cancel=cancel)
            except (ValueError, KeyError, TypeError, PermissionError) as exc:
                report["quality_association"] = {"status": "INCONCLUSIVE", "reason": str(exc)}
        if report["quality_association"]["status"] == "VALID":
            q = report["quality_association"]
            claims.append(claim(f"Across {q['wafers']} holdout wafers and {q['matched_die_sites']} matched die sites, mean spatial-block-adjusted within-wafer association was r={q['mean_within_wafer_r']:.4f} (95% wafer-level Fisher interval {q['fisher_wafer_95_ci'][0]:.4f} to {q['fisher_wafer_95_ci'][1]:.4f}); this is not causal evidence.",
                                 category="ASSOCIATION", method="within_wafer_pearson_fisher_z_t_interval_v1", source_ids=list(dict.fromkeys(source_ids + [q["relationship_source_id"]])), certainty="CONDITIONAL"))
        else:
            limitations.append("C03 downstream association unavailable: " + report["quality_association"].get("reason", "insufficient evidence"))

    unavailable_requested = (report["fingerprint"]["status"] == "PARTIAL" or any(
        report[key]["status"] in ("INCONCLUSIVE", "REFUSED")
        for key in ("anomaly", "similarity", "evolution", "quality_association")
        if ({"anomaly": "C04", "similarity": "C05", "evolution": "C02", "quality_association": "C03"}[key] in requested or report[key]["status"] != "NOT_REQUESTED")))
    status = "PARTIAL" if unavailable_requested else "VALID"
    related_sources = []
    if isinstance(baseline, list):
        related_sources.extend(source_id for item in baseline if isinstance(item, dict) for source_id in _source_ids(item))
    if isinstance(history, list):
        related_sources.extend(source_id for item in history if isinstance(item, dict) for source_id in _source_ids(item))
    related_sources.extend(_source_ids(previous) if isinstance(previous, dict) else [])
    if isinstance(previous_steps, list):
        related_sources.extend(source_id for item in previous_steps if isinstance(item, dict) for source_id in _source_ids(item))
    relation_source = report["quality_association"].get("relationship_source_id")
    if relation_source:
        related_sources.append(relation_source)
    source_ids_all = list(dict.fromkeys(source_ids + related_sources))
    source_payloads: dict[str, list[dict]] = {}

    def bind_payload(payload, identifiers):
        if not isinstance(payload, dict):
            return
        for identifier in identifiers:
            source_payloads.setdefault(identifier, []).append(payload)

    bind_payload(data, source_ids)
    if isinstance(baseline, list):
        for item in baseline:
            bind_payload(item, _source_ids(item) if isinstance(item, dict) else [])
    if isinstance(history, list):
        for item in history:
            bind_payload(item, _source_ids(item) if isinstance(item, dict) else [])
    if isinstance(previous, dict):
        bind_payload(previous, _source_ids(previous))
    if isinstance(previous_steps, list):
        for item in previous_steps:
            bind_payload(item, _source_ids(item) if isinstance(item, dict) else [])
    if relation_source and isinstance(association, dict):
        relation_payload = association.get("relationship")
        if isinstance(relation_payload, dict):
            bind_payload(relation_payload, [relation_source])
    ev = envelope("p3", data, status, claims, limitations,
                  assumptions=["Input coordinate and semantic verification assertions were supplied by the caller; no real MCP verification occurred."],
                  sources=[{"id": source_id, "approved_semantic_version": "SYNTHETIC-1", "grain": "synthetic_input_snapshot",
                            "source_hash": digest({"source_id": source_id, "payloads": source_payloads.get(source_id, [data])})}
                           for source_id in source_ids_all])
    ev["claim_category"] = "ASSOCIATION" if any(c["category"] == "ASSOCIATION" for c in claims) else "DESCRIPTIVE"
    ev["artifacts"] = [{"kind": "p3_analysis", "result": report}]
    ev["units"] = {"spatial_measurement": unit, "coordinate": base["coordinate_unit"]}
    ev["populations"] = [{"grain": "measured_site", "observed_count": base["observed_points"], "sampling_mask_id": base["sampling_mask_id"]}]
    ev["transformations"] = [{"method": METHOD_VERSION, "interpolation": False, "orientation_deg": _prepare_map(data)["orientation_deg"]}]
    ev["uncertainty"] = {"interpolation": "none", "region_coverage": {k: v["count"] for k, v in base["regions"].items()},
                         "edge_center_standard_uncertainty": base["edge_center"].get("standard_uncertainty"),
                         "edge_center_uncertainty_status": base["edge_center"].get("uncertainty_status", "NOT_APPLICABLE")}
    ev["provenance"]["engine_version"] = ENGINE_VERSION
    ev["provenance"]["method_version"] = METHOD_VERSION
    return ev

