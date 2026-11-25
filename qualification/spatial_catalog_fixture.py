"""Independent 13k-table synthetic metadata catalog for P3 onboarding studies."""
from __future__ import annotations

from copy import deepcopy

CATALOG_SIZE = 13_000


def _field(name: str, role: str, unit: str | None = None, value_type: str = "string") -> dict:
    return {"name": name, "role": role, "unit": unit, "value_type": value_type}


def _physical_geometry(*, radius: float = 150.0, coordinate_unit: str = "mm") -> dict:
    return {"coordinates_verified": True,
            "geometry": {"radius": radius, "radius_unit": coordinate_unit,
                         "origin": {"x": 0.0, "y": 0.0},
                         "orientation_deg": 0.0, "coordinate_system": "wafer_physical_xy_v1",
                         "coordinate_unit": coordinate_unit}}


def _map(source_id: str, title: str, *, grain: str = "wafer_site",
         geometry: dict | None = None, measurement: dict | None = None,
         fields: list[dict] | None = None, effective_time: dict | None = None) -> dict:
    base_roles = [
        _field("f01", "source_id"), _field("f02", "wafer_id"), _field("f03", "lot_id"),
        _field("f04", "measured_at"), _field("f05", "product_id"),
        _field("f06", "population_signature"), _field("f07", "sampling_mask_id"),
        _field("f08", "site_id"), _field("f09", "x", "mm", "number"),
        _field("f10", "y", "mm", "number"),
    ]
    return {"source_id": source_id, "source_name": title, "metadata_access": "PERMITTED",
            "semantic_version": "SYN-ONBOARD-1", "source_version": "SYN-SNAPSHOT-1",
            "grain": grain, "effective_time": effective_time or {
                "start": "2020-01-01T00:00:00Z", "end": None, "definition_id": "SYN-DEF-1"},
            "units": ["nm", "um", "count", "category", "mm", "die_index"],
            "column_definitions": fields if fields is not None else base_roles,
            "spatial_profile": deepcopy(geometry) if geometry is not None else None,
            "measurement_profiles": [deepcopy(measurement)] if measurement is not None else []}


def _candidates() -> list[dict]:
    continuous = {"profile_id": "SYN-MET-1", "metric": "film_thickness", "unit": "nm",
                  "modality": "continuous", "definition_id": "SYN-FILM-1", "layer": "L1",
                  "value_column_id": "f11", "value_role": "value",
                  "coordinate_mode": "physical_observation",
                  "null_semantics": "MISSING_MEASUREMENT"}
    long_fields = [_field("f01", "source_id"), _field("f02", "wafer_id"), _field("f03", "lot_id"),
                   _field("f04", "measured_at"), _field("f05", "product_id"),
                   _field("f06", "population_signature"), _field("f07", "sampling_mask_id"),
                   _field("f08", "site_id"), _field("f09", "x", "mm", "number"),
                   _field("f10", "y", "mm", "number"), _field("f11", "value", "nm", "number")]
    long_map = _map("SYN-SP-00117", "downstream-yield-forecast", geometry=_physical_geometry(),
                    measurement=continuous, fields=long_fields)

    wide_fields = deepcopy(long_fields[:-1]) + [
        _field("f11", "value", "nm", "number"), _field("f12", "value", "um", "number")]
    wide = _map("SYN-SP-01317", "wafer-outcome-summary", geometry=_physical_geometry(),
                fields=wide_fields)
    wide["measurement_profiles"] = [
        {**deepcopy(continuous), "profile_id": "SYN-WIDE-NM", "value_column_id": "f11"},
        {**deepcopy(continuous), "profile_id": "SYN-WIDE-UM", "metric": "film_thickness_alt",
         "unit": "um", "definition_id": "SYN-FILM-2", "value_column_id": "f12"},
    ]

    wafer_metadata = {"source_id": "SYN-SP-03117", "source_name": "legacy-bin-labels",
                      "metadata_access": "PERMITTED", "semantic_version": "SYN-ONBOARD-1",
                      "source_version": "SYN-SNAPSHOT-META", "grain": "wafer",
                      "effective_time": {"start": "2024-01-01T00:00:00Z", "end": None},
                      "column_definitions": [_field("m1", "wafer_id"), _field("m2", "radius", "mm", "number"),
                                             _field("m3", "origin_x", "mm", "number"),
                                             _field("m4", "origin_y", "mm", "number"),
                                             _field("m5", "orientation_deg", "degree", "number")],
                      "spatial_profile": _physical_geometry(), "measurement_profiles": []}
    split_profile = {**continuous, "value_column_id": "o11"}
    split_observations = _map("SYN-SP-04117", "wafer-map-mm", geometry=None,
                              measurement=split_profile,
                              fields=[_field("o1", "source_id"), _field("o2", "wafer_id"),
                                      _field("o3", "lot_id"), _field("o4", "measured_at"),
                                      _field("o5", "product_id"), _field("o6", "population_signature"),
                                      _field("o7", "sampling_mask_id"), _field("o8", "site_id"),
                                      _field("o9", "x", "mm", "number"), _field("o10", "y", "mm", "number"),
                                      _field("o11", "value", "nm", "number")])
    split_observations["coordinate_reference"] = {"coordinate_unit": "mm", "geometry_source_required": True}

    die_grid = _map("SYN-SP-05117", "film-thickness-with-reticle", geometry={
        "coordinates_verified": False,
        "geometry": {"coordinate_system": "integer_die_grid_v1", "coordinate_unit": "die_index",
                     "origin": {"x": 0, "y": 0}, "orientation_deg": 0}},
        measurement=continuous,
        fields=[_field("d1", "source_id"), _field("d2", "wafer_id"), _field("d3", "lot_id"),
                _field("d4", "measured_at"), _field("d5", "product_id"),
                _field("d6", "population_signature"), _field("d7", "sampling_mask_id"),
                _field("d8", "site_id"), _field("d9", "x", "die_index", "integer"),
        _field("d10", "y", "die_index", "integer"), _field("d11", "value", "nm", "number")])
    die_grid["measurement_profiles"][0]["value_column_id"] = "d11"

    categorical = _map("SYN-SP-06117", "wafer-thickness", geometry=_physical_geometry(),
                       measurement={"profile_id": "SYN-BIN-1", "metric": "die_bin", "unit": "category",
                                    "modality": "die_bin_categorical", "definition_id": "SYN-BIN-1",
                                    "layer": "SORT", "category_primitive_types": ["integer", "string"],
                                    "arithmetic_allowed": False},
                       fields=[_field("c1", "source_id"), _field("c2", "wafer_id"), _field("c3", "lot_id"),
                               _field("c4", "measured_at"), _field("c5", "product_id"),
                               _field("c6", "population_signature"), _field("c7", "sampling_mask_id"),
                               _field("c8", "site_id"), _field("c9", "x", "mm", "number"),
                               _field("c10", "y", "mm", "number"), _field("c11", "category", "category", "json_primitive")])

    defects = _map("SYN-SP-07117", "wafer-bin-map", geometry=_physical_geometry(),
                   measurement={"profile_id": "SYN-DEFECT-1", "metric": "defect_event", "unit": "count",
                                "modality": "defect_coordinates", "definition_id": "SYN-DEFECT-1",
                                "layer": "INSPECTION", "event_semantics": {
                                    "row_presence": "DEFECT_EVENT", "unlabeled_category_is_event": True,
                                    "null_is_missing": False}},
                   fields=[_field("e1", "source_id"), _field("e2", "wafer_id"), _field("e3", "lot_id"),
                           _field("e4", "measured_at"), _field("e5", "product_id"),
                           _field("e6", "population_signature"), _field("e7", "sampling_mask_id"),
                           _field("e8", "site_id"), _field("e9", "x", "mm", "number"),
                           _field("e10", "y", "mm", "number"), _field("e11", "category", "category", "json_primitive")])

    quality_roles = [("q1", "source_id"), ("q2", "wafer_id"), ("q3", "lot_id"), ("q4", "die_id"),
                     ("q5", "cohort"), ("q6", "feature_at"), ("q7", "outcome_at"),
                     ("q8", "x"), ("q9", "y"), ("q10", "feature_value"), ("q11", "outcome_value"),
                     ("q12", "spatial_block_id"), ("q13", "product_id"), ("q14", "metric"),
                     ("q15", "measurement_definition_id"), ("q16", "unit"), ("q17", "layer"),
                     ("q18", "population_signature"), ("q19", "sampling_mask_id")]
    quality = {"source_id": "SYN-SP-08117", "source_name": "wafer-thickness-historical",
               "metadata_access": "PERMITTED", "semantic_version": "SYN-ONBOARD-1",
               "source_version": "SYN-SNAPSHOT-QUALITY", "grain": "wafer_die",
               "effective_time": {"start": "2024-01-01T00:00:00Z", "end": None},
               "column_definitions": [_field(name, role, "mm" if role in ("x", "y") else None,
                                              "number" if role in ("x", "y", "feature_value", "outcome_value") else "string")
                                      for name, role in quality_roles],
               "units": ["nm"], "quality_context": {"verified": True},
               "quality_geometry": {"verified": True, **_physical_geometry()["geometry"]},
               "quality_holdout": {"split_method": "out_of_time_by_wafer_and_lot"},
               "quality_cohort_selection": {"sampling_design": "COMPLETE_ELIGIBLE_FRAME"},
               "quality_hypothesis_selection": {"family_complete": True}}

    reticle = {"source_id": "SYN-SP-09117", "source_name": "wafer-die-measurements",
               "metadata_access": "PERMITTED", "semantic_version": "SYN-ONBOARD-1",
               "source_version": "SYN-SNAPSHOT-RETICLE", "grain": "reticle_cell",
               "effective_time": {"start": "2025-01-01T00:00:00Z", "end": None},
               "column_definitions": [_field("r1", "reticle_id"), _field("r2", "row", value_type="integer"),
                                      _field("r3", "column", value_type="integer")],
               "reticle_profile": {"verified": True, "pitch_unit": "mm", "orientation_deg": 0,
                                   "wafer_registration": "NOT_SUPPLIED"}}

    contradictory = _map("SYN-SP-10117", "film-thickness", geometry={
        "coordinates_verified": True,
        "geometry": {"radius": 150, "radius_unit": "cm", "origin": {"x": 0, "y": 0},
                     "orientation_deg": 0, "coordinate_system": "wafer_physical_xy_v1",
                     "coordinate_unit": "mm"}}, measurement=continuous, fields=long_fields)
    wrong_unit = _map("SYN-SP-11117", "categorical-bins", geometry=_physical_geometry(),
                      measurement={**continuous, "unit": "nm", "value_column_id": "u11"},
                      fields=long_fields[:-1] + [_field("u11", "value", "um", "number")])
    missing_modality = _map("SYN-SP-12117", "defect-events", geometry=_physical_geometry(),
                            measurement={"profile_id": "SYN-UNKNOWN", "metric": "defect", "unit": "unknown",
                                         "definition_id": "SYN-UNKNOWN", "layer": "L1"}, fields=long_fields)
    stale = _map("SYN-SP-12317", "current-wafer-map", geometry=_physical_geometry(),
                 measurement=continuous, fields=long_fields,
                 effective_time={"start": "2030-01-01T00:00:00Z", "end": None})
    restricted = {"source_id": "SYN-SP-12417", "source_name": "wafer-measurement-approved",
                  "metadata_access": "RESTRICTED"}
    misleading = {"source_id": "SYN-SP-12517", "source_name": "wafer-spatial-metrology",
                  "metadata_access": "PERMITTED", "semantic_version": "SYN-ONBOARD-1",
                  "grain": "unknown", "effective_time": {"start": "2020-01-01T00:00:00Z", "end": None},
                  "column_definitions": [_field("n1", "opaque_field")],
                  "spatial_profile": None, "measurement_profiles": []}

    return [long_map, wide, wafer_metadata, split_observations, die_grid, categorical,
            defects, quality, reticle, contradictory, wrong_unit, missing_modality,
            stale, restricted, misleading]


def build_catalog(count: int = CATALOG_SIZE) -> list[dict]:
    candidates = _candidates()
    if type(count) is not int or count < len(candidates) or count > 20_000:
        raise ValueError(f"catalog count must be in {len(candidates)}..20000")
    catalog = [{"source_id": f"SYN-SRC-{index:05d}",
                "source_name": ("wafer-yield-map" if index % 3 == 0 else "thickness-metrology"),
                "metadata_access": "RESTRICTED" if index % 997 == 0 else "PERMITTED",
                "grain": "unknown"}
               for index in range(count)]
    for descriptor in candidates:
        index = int(descriptor["source_id"].rsplit("-", 1)[1])
        if index >= count:
            raise ValueError("catalog is too small for the fixed independent candidate IDs")
        catalog[index] = descriptor
    return catalog


def obfuscate_catalog_fields(catalog: list[dict]) -> list[dict]:
    """Return a field-name variant while preserving typed source roles."""
    result = deepcopy(catalog)
    for source_index, source in enumerate(result):
        renamed = {}
        columns = source.get("column_definitions", [])
        if isinstance(columns, list):
            for column_index, column in enumerate(columns):
                if not isinstance(column, dict) or not isinstance(column.get("name"), str):
                    continue
                old_name = column["name"]
                new_name = f"opaque_column_{column_index:02d}"
                renamed[old_name] = new_name
                column["name"] = new_name
        for profile in source.get("measurement_profiles", []):
            if isinstance(profile, dict) and profile.get("value_column_id") in renamed:
                profile["value_column_id"] = renamed[profile["value_column_id"]]
        source["source_name"] = f"unrelated_record_{source_index:05d}"
    return result
