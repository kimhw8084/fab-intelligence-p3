import React, { Fragment, type ReactNode } from "react";

export type P3Status = "VALID" | "PARTIAL" | "INCONCLUSIVE" | "REFUSED" | "ERROR";

export interface P3SourcePreview {
  status: string;
  permission: string;
  semantic_version: string;
  grain: string;
  metric: string;
  unit: string;
  scope: string;
  time_window: string;
  coverage?: Record<string, number>;
}

export interface P3Claim {
  statement: string;
  category?: string;
  certainty?: string;
  method?: string;
}

export interface P3Evidence {
  status: P3Status;
  investigation_id: string;
  claims: P3Claim[];
  limitations: string[];
  sources?: Array<{ id: string; source_hash?: string; grain?: string }>;
  provenance?: { input_sha256?: string; engine_version?: string; method_version?: string };
  artifacts?: Array<{ kind: string; result?: Record<string, unknown> }>;
}

export interface P3WaferMap {
  schema_version: "suite-spatial-map.v1";
  wafer_id: string;
  coordinates_verified: boolean;
  coordinate_unit: string;
  metric: string;
  measurement_unit: string;
  geometry: {
    coordinate_system: string;
    origin: { x: number; y: number };
    orientation_deg: number | null;
    radius: number;
  };
  sampling: {
    mask_id: string | null;
    observed_site_count: number;
    expected_site_count?: number;
    coverage_fraction?: number;
    explicit_missing_value_count: number;
    coverage_basis: "DECLARED_EXPECTED_SITE_COUNT" | "EXPECTED_DENOMINATOR_NOT_SUPPLIED";
    missing_site_ids?: string[];
  };
  points: Array<{ site_id: string; x: number; y: number; value: number | string | null }>;
  interpolation: "none";
}

export interface P3PanelProps {
  sourcePreview: P3SourcePreview;
  evidence?: P3Evidence | null;
  waferMap?: P3WaferMap | null;
  requestStatus?: "IDLE" | "LOADING" | "CANCELLED" | "ERROR";
  /** The suite host owns serialization, naming, and the final export destination. */
  onExportEvidence?: (evidence: P3Evidence) => void;
  /** The suite host supplies the single shared spatial visualization renderer. */
  renderWaferMap?: (model: P3WaferMap) => ReactNode;
}

const STOP_STATUSES = new Set<P3Status>(["INCONCLUSIVE", "REFUSED", "ERROR"]);
const CAPABILITIES = [
  ["C01", "Spatial fingerprint", "fingerprint"],
  ["C02", "Signature evolution", "evolution"],
  ["C03", "Quality association", "quality_association"],
  ["C04", "Spatial anomalies", "anomaly"],
  ["C05", "Historical similarity", "similarity"],
] as const;

function displayValue(value: string | number | undefined): string {
  return value === undefined || value === "" ? "Not provided" : String(value);
}

function resultFor(evidence: P3Evidence | null | undefined): Record<string, unknown> {
  const artifact = evidence?.artifacts?.find((item) => item.kind === "p3_analysis");
  return artifact?.result ?? {};
}

function capabilityStatus(value: unknown): string {
  if (value && typeof value === "object" && "status" in value) {
    return String((value as { status: unknown }).status);
  }
  return "NOT_AVAILABLE";
}

function mapCountError(model: P3WaferMap): string | null {
  const pointCount = model.points.length;
  const missingIds = model.points.filter((point) => point.value === null).map((point) => point.site_id);
  const uniqueIds = new Set(model.points.map((point) => point.site_id));
  if (model.sampling.observed_site_count !== pointCount) {
    return `Spatial map declares ${model.sampling.observed_site_count} observed sites but supplies ${pointCount}; rendering is withheld.`;
  }
  if (model.sampling.explicit_missing_value_count !== missingIds.length) {
    return `Spatial map declares ${model.sampling.explicit_missing_value_count} explicit missing values but supplies ${missingIds.length}; rendering is withheld.`;
  }
  if (uniqueIds.size !== pointCount) {
    return "Spatial map contains duplicate site identities; rendering is withheld.";
  }
  if (model.sampling.missing_site_ids) {
    const declaredMissingIds = new Set(model.sampling.missing_site_ids);
    if (declaredMissingIds.size !== model.sampling.missing_site_ids.length ||
        declaredMissingIds.size !== missingIds.length || missingIds.some((siteId) => !declaredMissingIds.has(siteId))) {
      return "Spatial map missing-site identifiers do not match the explicit missing observations; rendering is withheld.";
    }
  }
  return null;
}

function P3Map({ model, renderWaferMap }: { model: P3WaferMap; renderWaferMap?: P3PanelProps["renderWaferMap"] }) {
  const countError = mapCountError(model);
  return (
    <section aria-labelledby="p3-map-title">
      <h3 id="p3-map-title">Observed wafer map</h3>
      {countError ? (
        <p role="alert">{countError}</p>
      ) : !model.coordinates_verified ? (
        <p role="status">Wafer map withheld because the coordinate system has not been verified.</p>
      ) : renderWaferMap ? (
        <figure>{renderWaferMap(model)}<figcaption>Only supplied measurement sites are shown. No values are interpolated.</figcaption></figure>
      ) : (
        <p role="status">The shared spatial renderer is not mounted; verified site data remains available in the table.</p>
      )}
      <p>Wafer {model.wafer_id} · {model.geometry.coordinate_system} · origin ({model.geometry.origin.x}, {model.geometry.origin.y}) {model.coordinate_unit} · radius {model.geometry.radius} {model.coordinate_unit} · orientation {model.geometry.orientation_deg === null ? "unknown" : `${model.geometry.orientation_deg}°`} · {model.points.length} supplied site observations · {model.sampling.explicit_missing_value_count} explicit missing values{model.sampling.coverage_fraction === undefined || model.sampling.expected_site_count === undefined ? "" : ` · ${(model.sampling.coverage_fraction * 100).toFixed(1)}% of ${model.sampling.expected_site_count} declared sites`} · no interpolation.</p>
      {!countError && <details open>
        <summary>Accessible measured sites</summary>
        <table>
          <caption>{model.metric} ({model.measurement_unit}) on wafer {model.wafer_id}; {model.sampling.observed_site_count} observed sites; coverage basis {model.sampling.coverage_basis}</caption>
          <thead><tr><th scope="col">Site</th><th scope="col">X ({model.coordinate_unit})</th><th scope="col">Y ({model.coordinate_unit})</th><th scope="col">Value ({model.measurement_unit})</th></tr></thead>
          <tbody>{model.points.map((point, index) => (
            <tr key={`${model.wafer_id}-${point.site_id}-${index}`}>
              <th scope="row">{point.site_id}</th><td>{point.x}</td><td>{point.y}</td>
              <td>{point.value === null ? "Missing" : String(point.value)}</td>
            </tr>
          ))}</tbody>
        </table>
      </details>}
    </section>
  );
}

/** P3 evidence module. The FAB Intelligence host owns route, shell, controls, tokens, and shared renderers. */
export function P3Panel({ sourcePreview, evidence, waferMap, requestStatus = "IDLE", onExportEvidence, renderWaferMap }: P3PanelProps) {
  const blocked = Boolean(evidence && STOP_STATUSES.has(evidence.status));
  const result = resultFor(evidence);

  return (
    <article aria-labelledby="p3-panel-title" data-product-id="p3">
      <header>
        <h2 id="p3-panel-title">Spatial &amp; Yield Intelligence</h2>
        <p>Observed wafer patterns, evolution, anomaly evidence, historical similarity, and eligible downstream associations.</p>
        {sourcePreview.status === "SYNTHETIC_ONLY" && <p role="status">Synthetic demonstration data only</p>}
      </header>

      <section aria-labelledby="p3-source-title">
        <h3 id="p3-source-title">Source and scope</h3>
        <dl>
          <dt>Source status</dt><dd>{displayValue(sourcePreview.status)}</dd>
          <dt>Permission</dt><dd>{displayValue(sourcePreview.permission)}</dd>
          <dt>Semantic version</dt><dd>{displayValue(sourcePreview.semantic_version)}</dd>
          <dt>Observation grain</dt><dd>{displayValue(sourcePreview.grain)}</dd>
          <dt>Metric and unit</dt><dd>{displayValue(sourcePreview.metric)} ({displayValue(sourcePreview.unit)})</dd>
          <dt>Scope</dt><dd>{displayValue(sourcePreview.scope)}</dd>
          <dt>Time window</dt><dd>{displayValue(sourcePreview.time_window)}</dd>
          {Object.entries(sourcePreview.coverage ?? {}).map(([label, count]) => <Fragment key={label}><dt>{label.replaceAll("_", " ")}</dt><dd>{String(count)}</dd></Fragment>)}
        </dl>
      </section>

      {requestStatus === "LOADING" && <p role="status">Analysis is running. No new result is available yet.</p>}
      {requestStatus === "CANCELLED" && <p role="status">Cancellation was requested. No result is available for this request.</p>}
      {requestStatus === "ERROR" && <p role="alert">The analysis request failed before a valid result was returned.</p>}

      {!evidence ? (requestStatus === "IDLE" ? <p role="status">No analysis result is available. The shared workspace controls request and retry actions.</p> : null) : (
        <>
          <section aria-labelledby="p3-capabilities-title">
            <h3 id="p3-capabilities-title">Capability status</h3>
            <ul>
              {CAPABILITIES.map(([id, label, key]) => <li key={id}><strong>{id} · {label}:</strong> {capabilityStatus(result[key])}</li>)}
            </ul>
          </section>

          <section aria-labelledby="p3-findings-title" aria-live="polite">
            <h3 id="p3-findings-title">Findings and uncertainty</h3>
            {blocked ? <p role="status">No positive finding is presented because this result is {evidence.status.toLowerCase()}.</p> : (
              evidence.claims.map((claim, index) => <blockquote key={`${evidence.investigation_id}-${index}`}>
                <p>{claim.statement}</p>
                <footer>{[claim.category, claim.certainty, claim.method].filter(Boolean).join(" · ")}</footer>
              </blockquote>)
            )}
            {evidence.limitations.map((item, index) => <p key={`limitation-${index}`}>{item}</p>)}
          </section>

          {waferMap && !blocked && <P3Map model={waferMap} renderWaferMap={renderWaferMap} />}

          <details>
            <summary>Evidence provenance</summary>
            <p>Investigation: {evidence.investigation_id}</p>
            {evidence.sources?.map((source) => <p key={source.id}>{source.id}{source.grain ? ` · ${source.grain}` : ""}{source.source_hash ? ` · SHA-256 ${source.source_hash}` : ""}</p>)}
            {evidence.provenance?.input_sha256 && <p>Input SHA-256: {evidence.provenance.input_sha256}</p>}
            {evidence.provenance?.engine_version && <p>Engine: {evidence.provenance.engine_version}</p>}
            {evidence.provenance?.method_version && <p>Method: {evidence.provenance.method_version}</p>}
          </details>
          {onExportEvidence && <button type="button" onClick={() => onExportEvidence(evidence)}>Export evidence</button>}
        </>
      )}
    </article>
  );
}
