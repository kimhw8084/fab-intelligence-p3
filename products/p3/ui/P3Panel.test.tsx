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
  schema_version: "p3-wafer-map.v1",
  wafer_id: "SYN-W-01",
  coordinates_verified: true,
  coordinate_unit: "mm",
  metric: "film_thickness",
  measurement_unit: "nm",
  geometry: { coordinate_system: "wafer_xy_v1", orientation_deg: 0, radius: 150 },
  points: [{ site_id: "center", x: 0, y: 0, value: 42.5 }, { site_id: "east", x: 120, y: 0, value: null }],
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

  it("delegates verified spatial drawing to the shared host and keeps the exact accessible data", () => {
    const renderWaferMap = vi.fn(() => <div role="img" aria-label="Shared host wafer map" />);
    render(<P3Panel sourcePreview={sourcePreview} evidence={evidence} waferMap={waferMap} renderWaferMap={renderWaferMap} />);
    expect(renderWaferMap).toHaveBeenCalledWith(waferMap);
    expect(screen.getByRole("img", { name: "Shared host wafer map" })).toBeTruthy();
    const table = screen.getByRole("table", { name: "film_thickness (nm) on wafer SYN-W-01" });
    expect(within(table).getByRole("rowheader", { name: "center" })).toBeTruthy();
    expect(within(table).getByText("42.5")).toBeTruthy();
    expect(within(table).getByText("Missing")).toBeTruthy();
  });

  it("withholds spatial rendering when coordinates are unverified", () => {
    const renderWaferMap = vi.fn(() => <div role="img" aria-label="must not render" />);
    render(<P3Panel sourcePreview={sourcePreview} evidence={evidence} waferMap={{ ...waferMap, coordinates_verified: false }} renderWaferMap={renderWaferMap} />);
    expect(renderWaferMap).not.toHaveBeenCalled();
    expect(screen.getByText("Wafer map withheld because the coordinate system has not been verified.")).toBeTruthy();
    expect(screen.queryByRole("img", { name: "must not render" })).toBeNull();
  });

  it("does not render positive claims for refused or inconclusive evidence", () => {
    for (const status of ["REFUSED", "INCONCLUSIVE"] as const) {
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
});
