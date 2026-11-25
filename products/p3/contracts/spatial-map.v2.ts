export type SpatialModality = "continuous" | "sparse_continuous" | "die_bin_categorical" | "defect_coordinates";
export type ObservationKind = "NUMERIC_MEASUREMENT" | "CATEGORICAL_MEASUREMENT" | "DEFECT_EVENT" | "MISSING_MEASUREMENT";
export type PrimitiveValue = number | string | null;

export interface SpatialObservation {
  site_id: string;
  x: number;
  y: number;
  observation_kind: ObservationKind;
  value: PrimitiveValue;
  value_type: "number" | "string" | "null";
  standard_uncertainty?: number;
  standard_uncertainty_unit?: string;
}

export interface SpatialMapV2 {
  schema_version: "fab-spatial-map.v2";
  wafer_id: string;
  lot_id: string;
  product_id: string;
  step_id: string | null;
  step_instance_id: string | null;
  measured_at: string;
  coordinates_verified: boolean;
  coordinate_unit: string;
  metric: string;
  measurement_unit: string;
  modality: SpatialModality;
  geometry: {
    coordinate_system: string;
    coordinate_unit: string;
    origin: { x: number; y: number };
    radius: number;
    orientation_deg?: number | null;
    reticle?: Record<string, unknown> | null;
    [key: string]: unknown;
  };
  sampling: {
    mask_id: string | null;
    observation_count: number;
    numeric_measurement_count: number;
    categorical_measurement_count: number;
    defect_event_count: number;
    explicit_missing_value_count: number;
    coverage_basis: "DECLARED_EXPECTED_SITE_COUNT" | "EXPECTED_DENOMINATOR_NOT_SUPPLIED" | "EVENT_COUNTS_ARE_NOT_SITE_COVERAGE";
    expected_site_count?: number;
    coverage_fraction?: number;
  };
  observations: SpatialObservation[];
  interpolation: "none";
  provenance: {
    source_id: string;
    source_version: string;
    semantic_version: string;
    source_hash: string;
    grain: string;
  };
}
