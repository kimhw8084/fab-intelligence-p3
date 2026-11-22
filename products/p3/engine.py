"""Deterministic, observed-site-only P3 analysis methods.

The engine has no network or company-system adapter.  Inputs are synthetic or
must have been authorized, bounded and semantically verified by a future host.
"""
from __future__ import annotations

from datetime import datetime
from math import atan2, cos, floor, hypot, isfinite, log, pi, sin, sqrt, tanh
from statistics import mean, median
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
        if not isinstance(p, dict) or not all(_number(p.get(k)) for k in ("x", "y", "value")):
            raise ValueError(f"point {index} has a missing or invalid coordinate/value")
        if any(abs(p[k]) > MAX_ABS_NUMERIC for k in ("x", "y", "value")):
            raise ValueError(f"point {index} exceeds the numeric range limit")
        x, y = float(p["x"]) - float(ox), float(p["y"]) - float(oy)
        value = float(p["value"])
        r = hypot(x, y)
        if r > radius + max(float(radius) * 1e-9, 1e-12):
            raise ValueError(f"point {index} is outside wafer geometry")
        key = (round(x / tolerance), round(y / tolerance))
        if key in seen:
            raise ValueError("duplicate measured coordinate")
        seen.add(key)
        row = {"x": x, "y": y, "value": value, "radius_fraction": r / float(radius)}
        row["site_id"] = str(p.get("site_id", f"site-{index + 1}"))
        normalized.append(row)
    measurement = _measurement(data)
    modality = measurement.get("modality") or "continuous"
    if modality not in ("continuous", "sparse_continuous"):
        raise ValueError(f"arithmetic is unsupported for modality {modality!r}")
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


def _plane_gradient(points: list[dict], radius: float, orientation: float) -> dict:
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


def _local_clusters(points: list[dict], radius: float, orientation: float, *, grid_size=32) -> dict:
    """Describe contiguous occupied grid cells with large median shifts; not calibrated alerts."""
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
    if m["orientation_deg"] is None:
        raise PermissionError("verified wafer orientation is required for spatial fingerprints")
    if not m["coordinate_system"] or not m["coordinate_unit"] or m["coordinate_unit"] == "[coordinate unit unknown]":
        raise PermissionError("wafer coordinate system and units are not verified")
    if not m["measurement"].get("metric") or not m["measurement"].get("unit"):
        raise ValueError("measurement metric and unit are required")
    if not m["coordinate_unit"] or m["coordinate_unit"] == "[coordinate unit unknown]":
        raise ValueError("coordinate units are required")
    points = m["points"]
    center = [p["value"] for p in points if p["radius_fraction"] <= 0.2]
    mid = [p["value"] for p in points if 0.2 < p["radius_fraction"] < 0.8]
    edge = [p["value"] for p in points if p["radius_fraction"] >= 0.8]
    if not center or not edge:
        raise ValueError("center and edge measurements are both required for edge-center")
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
        "regions": {
            "center": {"count": len(center), "mean": mean(center)},
            "middle": {"count": len(mid), "mean": mean(mid) if mid else None},
            "edge": {"count": len(edge), "mean": mean(edge)},
        },
        "edge_minus_center": mean(edge) - mean(center),
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
    return result


def describe(points, radius):
    """Backward-compatible edge/center API retained for the bootstrap fixtures."""
    result = fingerprint({"coordinates_verified": True,
                          "geometry": {"radius": radius, "origin": {"x": 0, "y": 0}, "orientation_deg": 0,
                                       "coordinate_system": "legacy_xy", "coordinate_unit": "legacy_radius_units"},
                          "measurement": {"metric": "legacy", "unit": "legacy_unit", "modality": "continuous"}, "points": points})
    return {"edge_minus_center": result["edge_minus_center"], "observed_points": result["observed_points"]}


def _context_compatible(left: dict, right: dict, require_orientation=True, cancel=None) -> tuple[bool, str]:
    a, b = _prepare_map(left, cancel), _prepare_map(right, cancel)
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
    if not a["sampling_mask_id"] or not b["sampling_mask_id"] or a["sampling_mask_id"] != b["sampling_mask_id"]:
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


def _physical_site_values(data: dict, cancel=None) -> dict[tuple[int, int], tuple[dict, float]]:
    m = _prepare_map(data, cancel)
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


def compare_evolution(previous: dict, current: dict, cancel=None) -> dict:
    """Compare same-wafer, same-definition measurements at matched observed sites."""
    _check_cancel(cancel)
    try:
        ok, reason = _context_compatible(previous, current, cancel=cancel)
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
    if before.keys() != after.keys():
        return {"status": "INCONCLUSIVE", "reason": "observed coordinate sets differ; no interpolation was performed", "site_deltas": []}
    deltas = []
    for index, key in enumerate(sorted(before)):
        if index % 1024 == 0:
            _check_cancel(cancel)
        p0, v0 = before[key]
        p1, v1 = after[key]
        deltas.append({"site_id": p1["site_id"], "x_normalized": key[0], "y_normalized": key[1], "previous": v0, "current": v1, "delta": v1 - v0})
    return {
        "status": "VALID",
        "matched_sites": len(deltas),
        "mean_delta": mean(row["delta"] for row in deltas),
        "registration_residual": 0.0,
        "site_deltas": deltas,
        "alignment": "exact observed-site match after declared orientation transform",
        "uncertainty": {"registration": "exact declared-origin/orientation coordinate match; no transform uncertainty supplied",
                        "measurement_repeatability": "NOT_SUPPLIED"},
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
    site_labels: dict[tuple[float, float], str] = {}
    for result in comparisons:
        for row in result["site_deltas"]:
            key = (row["x_normalized"], row["y_normalized"])
            site_changes.setdefault(key, []).append(row["delta"])
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
                           "direction_persistent": direction_persistent})
    persistent_count = sum(row["direction_persistent"] for row in persistent)
    step_ids = [item.get("step_id") for item in maps]
    return {"status": "VALID", "matched_sites": len(persistent), "mean_delta": mean(totals),
            "registration_residual": max(result["registration_residual"] for result in comparisons),
            "site_deltas": persistent, "steps": [step_ids[0], step_ids[-1]], "step_sequence": step_ids,
            "comparisons": comparisons,
            "persistence": {"transitions": len(comparisons), "sites_with_same_nonzero_direction": persistent_count,
                            "fraction_with_same_nonzero_direction": persistent_count / len(persistent) if persistent else None},
            "uncertainty": {"registration": "exact declared-origin/orientation coordinate match; no transform uncertainty supplied",
                            "measurement_repeatability": "NOT_SUPPLIED"}}


def search_history(current: dict, history: list[dict], top_k=5, cancel=None) -> dict:
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
        current_sites = _physical_site_values(current, cancel)
    except (ValueError, KeyError, TypeError, PermissionError) as exc:
        return {"status": "INCONCLUSIVE", "reason": str(exc), "neighbors": []}
    current_prepared = _prepare_map(current, cancel)
    current_mean = mean(p["value"] for p in current_prepared["points"])
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
        try:
            ok, reason = _context_compatible(current, candidate, cancel=cancel)
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
            sites = _physical_site_values(candidate, cancel)
        except (ValueError, KeyError, TypeError, PermissionError) as exc:
            excluded.append({"wafer_id": candidate.get("wafer_id"), "reason": str(exc)})
            continue
        if current_sites.keys() != sites.keys():
            excluded.append({"wafer_id": candidate.get("wafer_id"), "reason": "observed coordinate sets differ"})
            continue
        cand_values = [sites[key][1] for key in current_sites]
        mean_candidate = mean(cand_values)
        current_centered = [current_sites[key][1] - current_mean for key in current_sites]
        candidate_centered = [sites[key][1] - mean_candidate for key in current_sites]
        shape_rmse = sqrt(mean((a - b) ** 2 for a, b in zip(current_centered, candidate_centered)))
        numeric_floor = max(max((abs(value) for value in [current_sites[key][1] for key in current_sites]
                                  + [sites[key][1] for key in current_sites]), default=0.0) * 1e-12, 1e-300)
        if shape_rmse <= numeric_floor:
            shape_rmse = 0.0
        raw_rmse = sqrt(mean((current_sites[key][1] - sites[key][1]) ** 2 for key in current_sites))
        def profile_rmse(group_for_point):
            left: dict[Any, list[float]] = {}
            right: dict[Any, list[float]] = {}
            for key in current_sites:
                group = group_for_point(current_sites[key][0])
                left.setdefault(group, []).append(current_sites[key][1] - current_mean)
                right.setdefault(group, []).append(sites[key][1] - mean_candidate)
            groups = sorted(set(left) & set(right), key=str)
            if not groups:
                return None
            return sqrt(mean((mean(left[group]) - mean(right[group])) ** 2 for group in groups))

        radial_rmse = profile_rmse(lambda point: 0 if point["radius_fraction"] <= 0.2 else
                                   1 if point["radius_fraction"] <= 0.5 else
                                   2 if point["radius_fraction"] <= 0.8 else 3)
        sector_rmse = profile_rmse(lambda point: _sector_index(point["x"], point["y"], current_prepared["orientation_deg"]))
        radial_rmse = 0.0 if radial_rmse is not None and radial_rmse <= numeric_floor else radial_rmse
        sector_rmse = 0.0 if sector_rmse is not None and sector_rmse <= numeric_floor else sector_rmse
        levels = [shape_rmse] + [value for value in (radial_rmse, sector_rmse) if value is not None]
        multiscale_rmse = sqrt(mean(value * value for value in levels))
        rows.append({"wafer_id": candidate["wafer_id"], "source_ids": _source_ids(candidate), "shape_rmse": shape_rmse,
                     "radial_profile_rmse": radial_rmse, "sector_profile_rmse": sector_rmse,
                     "multiscale_rmse": multiscale_rmse,
                     "distance_components": {"site_centered_rmse": shape_rmse, "radial_profile_rmse": radial_rmse,
                                             "sector_profile_rmse": sector_rmse},
                     "raw_rmse": raw_rmse, "mean_level_delta": mean_candidate - current_mean})
    rows.sort(key=lambda row: (row["multiscale_rmse"], row["shape_rmse"], row["raw_rmse"], str(row["wafer_id"])))
    return {"status": "VALID" if rows else "INCONCLUSIVE", "reason": None if rows else "no compatible historical maps", "neighbors": rows[:top_k], "excluded": excluded,
            "interpretation": "shape similarity only; a neighbor does not establish a shared mechanism"}


def _bh_adjust(p_values: list[float]) -> list[float]:
    order = sorted(range(len(p_values)), key=lambda i: p_values[i])
    adjusted = [1.0] * len(p_values)
    running = 1.0
    n = len(p_values)
    for rank_index in range(n - 1, -1, -1):
        i = order[rank_index]
        rank = rank_index + 1
        running = min(running, p_values[i] * n / rank)
        adjusted[i] = min(1.0, running)
    return adjusted


def detect_anomalies(current: dict, baseline: list[dict], *, holdout_verified=False, cancel=None) -> dict:
    """Empirical per-site outlier screen with BH correction; never a cause claim."""
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
        p = (1 + sum(dev >= abs(observed - middle) for dev in deviations)) / (len(deviations) + 1)
        rows.append({"site_id": current_sites[key][0]["site_id"], "value": observed, "baseline_median": middle,
                     "baseline_mad": mad, "robust_z": robust_z, "robust_scale_zero_and_shifted": robust_z is None and observed != middle,
                     "robust_extreme": robust_extreme, "empirical_p": p})
    q_values = _bh_adjust([row["empirical_p"] for row in rows])
    for row, q in zip(rows, q_values):
        row["bh_q"] = q
        row["outlier_candidate"] = row["robust_extreme"] and q <= ANOMALY_ALPHA
    outliers = [row for row in rows if row["outlier_candidate"]]
    return {"status": "VALID", "baseline_wafers": len(prepared), "tested_sites": len(rows), "alpha": ANOMALY_ALPHA,
            "multiple_test_method": "Benjamini-Hochberg", "outliers": outliers,
            "site_scores": rows, "interpretation": "conditional outlier screen against the supplied matched population; not a root-cause finding"}


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
    return {"status": "VALID", "wafers": len(grouped), "matched_die_sites": matched_sites,
            "mean_within_wafer_r": tanh(mean_z), "fisher_wafer_95_ci": ci,
            "relationship_source_id": relation["source_id"], "grain": "wafer_die",
            "holdout_split": "out_of_time_by_wafer_and_lot",
            "independent_lots": len(lot_wafers),
            "population_scope": "context-matched holdout wafers",
            "spatial_block_method": "predeclared_block_fixed_effects_v1",
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
    claims = [claim(
        f'Measured edge-center difference for {base["metric"]} = {base["edge_minus_center"]:g} {unit} from {base["observed_points"]} observed sites.',
        method=METHOD_VERSION, source_ids=source_ids,
    )]
    report = {
        "fingerprint": {"status": "VALID", **base},
        "anomaly": {"status": "NOT_REQUESTED", "reason": "matched baseline not supplied", "outliers": []},
        "similarity": {"status": "NOT_REQUESTED", "reason": "historical maps not supplied", "neighbors": []},
        "evolution": {"status": "NOT_REQUESTED", "reason": "prior step not supplied", "site_deltas": []},
        "quality_association": {"status": "NOT_REQUESTED", "reason": "downstream association not supplied"},
    }
    limitations = ["No interpolation; unmeasured wafer regions remain unobserved.",
                   "No causal inference, manufacturing actuation, or company-system access is performed."]
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
            claims.append(claim(f"{count} measured sites met the predeclared outlier screen against the supplied matched baseline.",
                                 method="empirical_site_tail_probability_bh_v1", source_ids=list(dict.fromkeys(source_ids + baseline_sources)), certainty="CONDITIONAL"))
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
            report["evolution"] = compare_evolution_sequence(prior_maps, data, cancel)
        except (ValueError, KeyError, TypeError, PermissionError) as exc:
            report["evolution"] = {"status": "INCONCLUSIVE", "reason": str(exc), "site_deltas": []}
        if report["evolution"]["status"] == "VALID":
            evo = report["evolution"]
            evolution_sources = [source_id for item in prior_maps if isinstance(item, dict) for source_id in _source_ids(item)]
            persistence = evo.get("persistence", {})
            persistence_text = (f" {persistence['fraction_with_same_nonzero_direction']:.1%} of sites kept the same nonzero direction across {persistence['transitions']} transitions."
                                if persistence.get("transitions", 0) > 1 and persistence.get("fraction_with_same_nonzero_direction") is not None else "")
            claims.append(claim(f"Across {evo['matched_sites']} matched observed sites, mean change from {evo['steps'][0]} to {evo['steps'][1]} was {evo['mean_delta']:g} {unit}.{persistence_text}",
                                 method="same_wafer_orientation_aligned_observed_delta_v1", source_ids=list(dict.fromkeys(source_ids + evolution_sources)), certainty="CONDITIONAL"))
        else:
            limitations.append("C02 evolution unavailable: " + report["evolution"].get("reason", "insufficient evidence"))

    association = data.get("quality_association")
    if association is not None or "C03" in requested:
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
        if report["quality_association"]["status"] == "VALID":
            q = report["quality_association"]
            claims.append(claim(f"Across {q['wafers']} holdout wafers and {q['matched_die_sites']} matched die sites, mean spatial-block-adjusted within-wafer association was r={q['mean_within_wafer_r']:.4f} (95% wafer-level Fisher interval {q['fisher_wafer_95_ci'][0]:.4f} to {q['fisher_wafer_95_ci'][1]:.4f}); this is not causal evidence.",
                                 category="ASSOCIATION", method="within_wafer_pearson_fisher_z_t_interval_v1", source_ids=list(dict.fromkeys(source_ids + [q["relationship_source_id"]])), certainty="CONDITIONAL"))
        else:
            limitations.append("C03 downstream association unavailable: " + report["quality_association"].get("reason", "insufficient evidence"))

    unavailable_requested = any(report[key]["status"] in ("INCONCLUSIVE", "REFUSED") for key in ("anomaly", "similarity", "evolution", "quality_association") if ({"anomaly": "C04", "similarity": "C05", "evolution": "C02", "quality_association": "C03"}[key] in requested or report[key]["status"] != "NOT_REQUESTED"))
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
    ev["uncertainty"] = {"interpolation": "none", "region_coverage": {k: v["count"] for k, v in base["regions"].items()}}
    ev["provenance"]["engine_version"] = ENGINE_VERSION
    ev["provenance"]["method_version"] = METHOD_VERSION
    return ev

