import React from "react";
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { P3Panel, type P3Evidence, type P3SourcePreview, type P3WaferMap } from "./P3Panel";

const sourcePreview: P3SourcePreview = {
  status: "SYNTHETIC_ONLY",
  permission: "No company access configured.",
  semantic_version: "SYNTHETIC-NOT-APPROVED",
  grain: "one observation per wafer site",
  metric: "film_thickness",
  unit: "nm",
  scope: "seeded P3 fixture",
  time_window: "2026-01-01 to 2026-01-07",
  coverage: { wafers: 5, observed_sites: 25 },
};

const evidence: P3Evidence = {
  status: "PARTIAL",
  investigation_id: "SYN-p3-panel-test",
  claims: [{ statement: "Observed spatial summary only.", category: "DESCRIPTIVE", certainty: "SUPPORTED", method: "p3-observed-spatial-v1" }],
  limitations: ["Synthetic fixture only; no company source was consulted."],
  sources: [{ id: "SYN-MAP-test", source_hash: "abc123", grain: "wafer site" }],
  provenance: { input_sha256: "abc123", engine_version: "p3-test", method_version: "p3-method-test" },
  artifacts: [{ kind: "p3_analysis", result: {
    fingerprint: { status: "VALID" }, evolution: { status: "VALID" }, quality_association: { status: "NOT_REQUESTED" },
    anomaly: { status: "INCONCLUSIVE" }, similarity: { status: "VALID" },
  } }],
};

const waferMap: P3WaferMap = {
  schema_version: "suite-spatial-map.v1",
  wafer_id: "SYN-W-01",
  coordinates_verified: true,
  coordinate_unit: "mm",
  metric: "film_thickness",
  measurement_unit: "nm",
  geometry: { coordinate_system: "wafer_xy_v1", origin: { x: 0, y: 0 }, orientation_deg: 0, radius: 150 },
  sampling: { mask_id: "SYN-MASK-01", observed_site_count: 2, expected_site_count: 4,
    coverage_fraction: 0.5, explicit_missing_value_count: 1,
    coverage_basis: "DECLARED_EXPECTED_SITE_COUNT", missing_site_ids: ["east"] },
  points: [{ site_id: "center", x: 0, y: 0, value: 42.5 }, { site_id: "east", x: 120, y: 0, value: null }],
  interpolation: "none",
};

describe("P3Panel suite contribution", () => {
  afterEach(() => cleanup());

  it("shows synthetic source, all five capabilities, findings, limitations, and provenance", () => {
    render(<P3Panel sourcePreview={sourcePreview} evidence={evidence} />);
    expect(screen.getByText("Synthetic demonstration data only")).toBeTruthy();
    expect(screen.getByText("one observation per wafer site")).toBeTruthy();
    expect(screen.getByText("C01 · Spatial fingerprint:")).toBeTruthy();
    expect(screen.getByText("C05 · Historical similarity:")).toBeTruthy();
    expect(screen.getByText("Observed spatial summary only.")).toBeTruthy();
    expect(screen.getByText("Synthetic fixture only; no company source was consulted.")).toBeTruthy();
    expect(screen.getByText(/SHA-256 abc123/)).toBeTruthy();
    expect(screen.getByText(/Input SHA-256: abc123/)).toBeTruthy();
  });

  it("delegates evidence export to the shared host without altering the validated envelope", () => {
    const onExportEvidence = vi.fn();
    render(<P3Panel sourcePreview={sourcePreview} evidence={evidence} onExportEvidence={onExportEvidence} />);
    screen.getByRole("button", { name: "Export evidence" }).click();
    expect(onExportEvidence).toHaveBeenCalledOnce();
    expect(onExportEvidence).toHaveBeenCalledWith(evidence);
  });

  it("delegates verified spatial drawing to the shared host and keeps the exact accessible data", () => {
    const renderWaferMap = vi.fn(() => <div role="img" aria-label="Shared host wafer map" />);
    render(<P3Panel sourcePreview={sourcePreview} evidence={evidence} waferMap={waferMap} renderWaferMap={renderWaferMap} />);
    expect(renderWaferMap).toHaveBeenCalledWith(waferMap);
    expect(screen.getByRole("img", { name: "Shared host wafer map" })).toBeTruthy();
    const table = screen.getByRole("table", { name: /film_thickness \(nm\) on wafer SYN-W-01/ });
    expect(within(table).getByRole("rowheader", { name: "center" })).toBeTruthy();
    expect(within(table).getByText("42.5")).toBeTruthy();
    expect(within(table).getByText("Missing")).toBeTruthy();
  });

  it("preserves typed numeric, categorical, and missing observations with reconciled counts", () => {
    const renderWaferMap = vi.fn((_model: P3WaferMap) => <div role="img" aria-label="Typed shared wafer map" />);
    const typedMap: P3WaferMap = {
      ...waferMap,
      sampling: { ...waferMap.sampling, observed_site_count: 4, explicit_missing_value_count: 1,
        missing_site_ids: ["unmeasured"] },
      points: [
        { site_id: "metrology", x: 0, y: 0, value: 42.5 },
        { site_id: "bin-label", x: 10, y: 0, value: "BIN-A" },
        { site_id: "bin-code", x: 0, y: 10, value: 2 },
        { site_id: "unmeasured", x: -10, y: 0, value: null },
      ],
    };
    render(<P3Panel sourcePreview={sourcePreview} evidence={evidence} waferMap={typedMap} renderWaferMap={renderWaferMap} />);
    expect(renderWaferMap).toHaveBeenCalledWith(typedMap);
    const passedModel = renderWaferMap.mock.calls[0][0] as P3WaferMap;
    expect(typeof passedModel.points[0].value).toBe("number");
    expect(passedModel.points.map((point) => point.value)).toEqual([42.5, "BIN-A", 2, null]);
    expect(passedModel.points).toHaveLength(4);
    expect(passedModel.sampling.observed_site_count).toBe(4);
    expect(passedModel.sampling.explicit_missing_value_count).toBe(1);
    const table = screen.getByRole("table", { name: /film_thickness \(nm\) on wafer SYN-W-01/ });
    expect(within(table).getAllByRole("row")).toHaveLength(passedModel.points.length + 1);
    expect(within(table).getByRole("rowheader", { name: "bin-label" })).toBeTruthy();
    expect(within(table).getByText("BIN-A")).toBeTruthy();
    expect(within(table).getByText("Missing")).toBeTruthy();
  });

  it("withholds map and table rendering when declared counts disagree with supplied observations", () => {
    const renderWaferMap = vi.fn(() => <div role="img" aria-label="must not render inconsistent counts" />);
    const inconsistentMap: P3WaferMap = {
      ...waferMap,
      sampling: { ...waferMap.sampling, observed_site_count: 3, explicit_missing_value_count: 0 },
    };
    render(<P3Panel sourcePreview={sourcePreview} evidence={evidence}
      waferMap={inconsistentMap} renderWaferMap={renderWaferMap} />);
    expect(renderWaferMap).not.toHaveBeenCalled();
    expect(screen.getByRole("alert").textContent).toMatch(/declares 3 observed sites but supplies 2/);
    expect(screen.queryByRole("table")).toBeNull();
    expect(screen.queryByRole("img", { name: "must not render inconsistent counts" })).toBeNull();
  });

  it("does not reinterpret unlabeled event values as explicit missing measurements", () => {
    const renderWaferMap = vi.fn(() => <div role="img" aria-label="must not render ambiguous nulls" />);
    const unlabeledEventMap: P3WaferMap = {
      ...waferMap,
      sampling: { mask_id: "SYN-EVENT-MASK", observed_site_count: 2,
        explicit_missing_value_count: 0, coverage_basis: "EXPECTED_DENOMINATOR_NOT_SUPPLIED" },
      points: [
        { site_id: "event-labeled", x: 0, y: 0, value: "BRIDGE" },
        { site_id: "event-unlabeled", x: 10, y: 0, value: null },
      ],
    };
    render(<P3Panel sourcePreview={sourcePreview} evidence={evidence}
      waferMap={unlabeledEventMap} renderWaferMap={renderWaferMap} />);
    expect(renderWaferMap).not.toHaveBeenCalled();
    expect(screen.getByRole("alert").textContent).toMatch(/declares 0 explicit missing values but supplies 1/);
    expect(screen.queryByRole("table")).toBeNull();
  });

  it("withholds spatial rendering when coordinates are unverified", () => {
    const renderWaferMap = vi.fn(() => <div role="img" aria-label="must not render" />);
    render(<P3Panel sourcePreview={sourcePreview} evidence={evidence} waferMap={{ ...waferMap, coordinates_verified: false }} renderWaferMap={renderWaferMap} />);
    expect(renderWaferMap).not.toHaveBeenCalled();
    expect(screen.getByText("Wafer map withheld because the coordinate system has not been verified.")).toBeTruthy();
    expect(screen.queryByRole("img", { name: "must not render" })).toBeNull();
    const table = screen.getByRole("table", { name: /film_thickness \(nm\) on wafer SYN-W-01/ });
    expect(within(table).getByRole("rowheader", { name: "center" })).toBeTruthy();
    expect(within(table).getByText("42.5")).toBeTruthy();
  });

  it("exposes geometry and declared sampling coverage beside observed values", () => {
    render(<P3Panel sourcePreview={sourcePreview} evidence={evidence} waferMap={waferMap} />);
    expect(screen.getByText(/50.0% of 4 declared sites/)).toBeTruthy();
    expect(screen.getByText(/orientation 0°/)).toBeTruthy();
    expect(screen.getByText(/coverage basis DECLARED_EXPECTED_SITE_COUNT/)).toBeTruthy();
  });

  it("retains the accessible data table when orientation is unknown", () => {
    const renderWaferMap = vi.fn(() => <p role="status">Spatial renderer withheld: orientation</p>);
    render(<P3Panel sourcePreview={sourcePreview} evidence={evidence}
      waferMap={{ ...waferMap, geometry: { ...waferMap.geometry, orientation_deg: null } }}
      renderWaferMap={renderWaferMap} />);
    expect(renderWaferMap).toHaveBeenCalledWith(expect.objectContaining({
      schema_version: "suite-spatial-map.v1", geometry: expect.objectContaining({ orientation_deg: null }),
    }));
    expect(screen.getByRole("table", { name: /film_thickness \(nm\) on wafer SYN-W-01/ })).toBeTruthy();
  });

  it("does not render positive claims for refused or inconclusive evidence", () => {
    for (const status of ["REFUSED", "INCONCLUSIVE", "ERROR"] as const) {
      const blocked: P3Evidence = { ...evidence, status, claims: [{ statement: "must not render", category: "ASSOCIATION" }] };
      const { unmount } = render(<P3Panel sourcePreview={sourcePreview} evidence={blocked} waferMap={waferMap} />);
      expect(screen.getByText(`No positive finding is presented because this result is ${status.toLowerCase()}.`)).toBeTruthy();
      expect(screen.queryByText("must not render")).toBeNull();
      expect(screen.queryByRole("heading", { name: "Observed wafer map" })).toBeNull();
      unmount();
    }
  });

  it("shows a pending empty state without inventing results", () => {
    render(<P3Panel sourcePreview={sourcePreview} />);
    expect(screen.getByText("No analysis result is available. The shared workspace controls request and retry actions.")).toBeTruthy();
  });

  it("distinguishes loading, cancellation, and transport error from empty results", () => {
    for (const [requestStatus, message, role] of [
      ["LOADING", "Analysis is running. No new result is available yet.", "status"],
      ["CANCELLED", "Cancellation was requested. No result is available for this request.", "status"],
      ["ERROR", "The analysis request failed before a valid result was returned.", "alert"],
    ] as const) {
      const { unmount } = render(<P3Panel sourcePreview={sourcePreview} requestStatus={requestStatus} />);
      const requestMessage = screen.getByText(message);
      expect(requestMessage.getAttribute("role")).toBe(role);
      expect(requestMessage.textContent).toBe(message);
      expect(screen.queryByText("No analysis result is available. The shared workspace controls request and retry actions.")).toBeNull();
      unmount();
    }
  });
});
