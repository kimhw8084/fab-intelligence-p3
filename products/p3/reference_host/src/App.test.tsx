import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { App } from "./App";

vi.mock("./SpatialMapRenderer", () => ({
  SpatialMapRenderer: ({ model }: { model: { wafer_id: string } }) => <div role="img" aria-label={`Measured wafer observations for ${model.wafer_id}.`} />,
}));

const moduleResult = {
  contract_version: "p3-reference-module.v2", product_id: "p3", capabilities: ["C01", "C02", "C03", "C04", "C05"],
  source_preview: { status: "SYNTHETIC_ONLY", permission: "Synthetic only", semantic_version: "SYN-1", grain: "wafer site", metric: "die_bin", unit: "category", scope: "W-1", time_window: "2026-01", modality: "die_bin_categorical", coverage: { observations: 4 } },
  evidence: { status: "PARTIAL", investigation_id: "SYN-1", claims: [], limitations: ["Synthetic only."], sources: [], provenance: { input_sha256: "abc", mcp_workflow: { permission_scope: "read_only", bounded_reads: [] } }, artifacts: [{ kind: "p3_analysis", result: {
    fingerprint: { status: "PARTIAL", pattern: "categorical" }, evolution: { status: "INCONCLUSIVE" }, quality_association: { status: "INCONCLUSIVE" }, anomaly: { status: "INCONCLUSIVE" }, similarity: { status: "INCONCLUSIVE" },
  } }] },
  spatial_map: { schema_version: "fab-spatial-map.v2", wafer_id: "W-1", lot_id: "L-1", product_id: "P-1", step_id: "ETCH", step_instance_id: "ETCH-1", measured_at: "2026-01-01T00:00:00Z", coordinates_verified: true, coordinate_unit: "mm", metric: "die_bin", measurement_unit: "category", modality: "die_bin_categorical", geometry: { coordinate_system: "wafer_xy_v1", coordinate_unit: "mm", origin: { x: 0, y: 0 }, radius: 1, orientation_deg: 0 }, sampling: { mask_id: "M-1", observation_count: 4, numeric_measurement_count: 0, categorical_measurement_count: 2, defect_event_count: 0, explicit_missing_value_count: 2, coverage_basis: "DECLARED_EXPECTED_SITE_COUNT", expected_site_count: 8, coverage_fraction: 0.5 }, observations: [
    { site_id: "die-1", x: 0.1, y: 0.1, observation_kind: "CATEGORICAL_MEASUREMENT", value: 2, value_type: "number" },
    { site_id: "die-2", x: 0.2, y: 0.1, observation_kind: "CATEGORICAL_MEASUREMENT", value: "PASS", value_type: "string" },
    { site_id: "die-3", x: 0.3, y: 0.1, observation_kind: "MISSING_MEASUREMENT", value: null, value_type: "null" },
    { site_id: "die-4", x: 0.4, y: 0.1, observation_kind: "DEFECT_EVENT", value: null, value_type: "null" },
  ], interpolation: "none", provenance: { source_id: "SYN", source_version: "SNAP-1", semantic_version: "SYN-1", source_hash: "a".repeat(64), grain: "wafer site" } },
  suite_compatibility: { contract_version: "suite-ui-module.v1", status: "COMPATIBLE", reason: null },
  export: { format: "fab-intelligence-investigation.v1", sha256: "b".repeat(64), canonicalization: "canonical", canonical_json: "{}" },
  export_content: {},
};

afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });

describe("P3 independent reference workflow", () => {
  it("preserves typed observations, exposes capability detail, provenance, and export", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, _init?: RequestInit) => {
      if (String(input) === "/api/status") return new Response(JSON.stringify({ source_modes: ["synthetic"] }));
      return new Response(JSON.stringify(moduleResult), { status: 200 });
    });
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("crypto", { randomUUID: () => "6c8690f0-906d-46a5-a63f-e380a8b00002" });
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "Run investigation" }));
    await screen.findByRole("table", { name: /die_bin \(category\).*W-1/ });
    const table = screen.getByRole("table", { name: /die_bin \(category\).*W-1/ });
    expect(within(table).getAllByRole("row")).toHaveLength(5);
    expect(within(table).getByText("2")).toBeInTheDocument();
    expect(within(table).getByText("number")).toBeInTheDocument();
    expect(within(table).getByText("PASS")).toBeInTheDocument();
    expect(within(table).getByText("Missing")).toBeInTheDocument();
    expect(within(table).getByText("Unlabeled event")).toBeInTheDocument();
    const evolutionTab = screen.getByRole("tab", { name: /C02/ });
    fireEvent.click(evolutionTab);
    expect(screen.getByRole("tabpanel")).toHaveTextContent("C02 · Process-step evolution");
    expect(evolutionTab).toHaveAttribute("tabindex", "0");
    const associationTab = screen.getByRole("tab", { name: /C03/ });
    fireEvent.keyDown(evolutionTab, { key: "ArrowRight" });
    expect(associationTab).toHaveAttribute("aria-selected", "true");
    expect(associationTab).toHaveAttribute("tabindex", "0");
    expect(screen.getByRole("tabpanel")).toHaveTextContent("C03 · Spatial-to-quality association");
    fireEvent.click(screen.getByText("Source evidence and provenance"));
    expect(screen.getByText(/Source hash:/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Export reproducible evidence" }));
    expect(click).toHaveBeenCalledOnce();
    await waitFor(() => expect(screen.getByText(/Canonical SHA-256/)).toBeInTheDocument());
    const investigateCall = fetchMock.mock.calls.find((call) => String(call[0]) === "/api/investigate");
    expect(investigateCall).toBeDefined();
    expect(JSON.parse(String((investigateCall?.[1] as RequestInit).body)).plan_ids).toHaveLength(5);
  });

  it("shows C01 sampling and measurement questions for categorical observations", async () => {
    const result = JSON.parse(JSON.stringify(moduleResult));
    result.evidence.artifacts[0].result.fingerprint = {
      status: "PARTIAL", modality: "die_bin_categorical", observed_points: 4,
      interpretation_limits: {
        sampling: {
          limitation: "Observed-site counts are not area-weighted.",
          review_question: "Would the conclusion persist on a fixed common sampling mask?",
        },
        measurement_attribution: {
          limitation: "Measurement artifact cannot be identified from this map alone.",
          review_question: "Does the pattern reproduce on an independent calibrated measurement path?",
        },
      },
    };
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      if (String(input) === "/api/status") return new Response(JSON.stringify({ source_modes: ["synthetic"] }));
      return new Response(JSON.stringify(result), { status: 200 });
    }));
    vi.stubGlobal("crypto", { randomUUID: () => "6c8690f0-906d-46a5-a63f-e380a8b00006" });
    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "Run investigation" }));
    await screen.findByRole("table", { name: /die_bin \(category\).*W-1/ });
    const summary = screen.getByRole("region", { name: "C01 engineering summary" });
    expect(summary).toHaveTextContent("Sampling question: Would the conclusion persist on a fixed common sampling mask?");
    expect(summary).toHaveTextContent("Measurement question: Does the pattern reproduce on an independent calibrated measurement path?");
    expect(summary).toHaveTextContent("not area-weighted");
    expect(summary).toHaveTextContent("cannot be identified from this map alone");
  });

  it("makes historical sampling differences visible beside the similarity caveat", async () => {
    const result = JSON.parse(JSON.stringify(moduleResult));
    result.evidence.artifacts[0].result.similarity = {
      status: "VALID",
      neighbors: [{ wafer_id: "SYN-HIST-24", multiscale_rmse: 0.418,
        alignment: "common radial/sector/radial-sector profile descriptors; no reconstruction",
        profile_coverage: { shared_radial_sector_bins: 12 },
        target_observed_site_count: 48, candidate_observed_site_count: 24, sampling_mask_changed: true }],
      excluded: [{ wafer_id: "SYN-FUTURE", reason: "record is not earlier than the target map" }],
    };
    result.historical_spatial_map = {
      ...result.spatial_map, wafer_id: "SYN-HIST-24", lot_id: "L-HIST-24", product_id: "P-1",
      step_id: "ETCH", measured_at: "2025-12-01T00:00:00Z", metric: "film_thickness",
      measurement_unit: "nm", modality: "continuous",
      sampling: { ...result.spatial_map.sampling, mask_id: "M-HIST-24", observation_count: 2,
        numeric_measurement_count: 2, categorical_measurement_count: 0, defect_event_count: 0,
        explicit_missing_value_count: 0 },
      observations: [
        { site_id: "analog-east", x: 0.2, y: 0, observation_kind: "NUMERIC_MEASUREMENT", value: 12, value_type: "number" },
        { site_id: "analog-west", x: -0.2, y: 0, observation_kind: "NUMERIC_MEASUREMENT", value: 11, value_type: "number" },
      ],
    };
    const fetchMock = vi.fn(async (input: RequestInfo | URL, _init?: RequestInit) => {
      if (String(input) === "/api/status") return new Response(JSON.stringify({ source_modes: ["synthetic"] }));
      return new Response(JSON.stringify(result), { status: 200 });
    });
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("crypto", { randomUUID: () => "6c8690f0-906d-46a5-a63f-e380a8b00005" });
    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "Run investigation" }));
    await screen.findByRole("table", { name: /die_bin \(category\).*W-1/ });
    fireEvent.click(screen.getByRole("tab", { name: /C05/ }));
    const summary = screen.getByRole("region", { name: "C05 engineering summary" });
    expect(summary).toHaveTextContent("SYN-HIST-24");
    expect(summary).toHaveTextContent("Compared using common radial/sector/radial-sector profile descriptors; no reconstruction; 1 eligible neighbor returned.");
    expect(summary).toHaveTextContent("Cross-layout profile coverage: 12 common radial-sector bins.");
    expect(summary.textContent?.match(/no reconstruction/g)).toHaveLength(1);
    expect(summary).toHaveTextContent("48 target observations versus 24 on the analog");
    expect(summary).toHaveTextContent("does not fill missing locations");
    expect(summary).toHaveTextContent("incompatible or future record was excluded");
    expect(summary).toHaveTextContent("does not establish a shared mechanism or root cause");
    expect(summary).toHaveTextContent("can miss within-bin structure");
    expect(screen.getByRole("img", { name: /SYN-HIST-24/ })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Closest historical analog map" })).toHaveTextContent("2 measured sites");
    fireEvent.click(screen.getByText("Accessible historical observations (2)"));
    const historicalTable = screen.getByRole("table", { name: /film_thickness \(nm\).*SYN-HIST-24/ });
    expect(within(historicalTable).getAllByRole("row")).toHaveLength(3);
    expect(within(historicalTable).getByText("analog-east")).toBeInTheDocument();
  });

  it("shows conditional standard uncertainty with common-site coverage", async () => {
    const result = JSON.parse(JSON.stringify(moduleResult));
    result.spatial_map.metric = "film_thickness";
    result.spatial_map.measurement_unit = "nm";
    result.spatial_map.modality = "continuous";
    result.spatial_map.sampling.numeric_measurement_count = 4;
    result.spatial_map.sampling.categorical_measurement_count = 0;
    result.spatial_map.observations = result.spatial_map.observations.map((row: Record<string, unknown>, index: number) => ({
      ...row, observation_kind: "NUMERIC_MEASUREMENT", value: 100 + index, value_type: "number",
    }));
    result.evidence.artifacts[0].result.fingerprint = {
      status: "VALID", modality: "continuous", observed_points: 1536, measurement_unit: "nm",
      edge_center: { status: "VALID", difference: 1.25 },
      radial_profile: [{ region: "edge", mean: 102.4 }],
      local_clusters: { status: "EXPLORATORY", grid_size: 21, cell_width: 14.3, coordinate_unit: "mm",
        clusters: [{ observed_site_count: 11 }],
        screening_adjustment: { status: "APPLIED", method: "ordinary_least_squares_plane_residuals_before_same_radial_band_MAD" } },
    };
    result.evidence.artifacts[0].result.evolution = {
      status: "VALID", step_sequence: ["DEPOSITION", "CMP-PRE", "CMP-POST"], matched_sites: 44,
      comparisons: [{ status: "VALID", steps: ["DEPOSITION", "CMP-PRE"], matched_sites: 44, mean_delta: 0.455,
        coverage: { previous: 44 / 48, current: 1 },
        uncertainty: { measurement_uncertainty: { status: "PROPAGATED_FROM_SITE_STANDARD_UNCERTAINTIES",
          mean_delta_standard_uncertainty: 0.038376, unit: "nm",
          unknown_covariance_bounds: { lower_standard_uncertainty: 0.01, upper_standard_uncertainty: 0.2 } } } }],
      uncertainty: { measurement_uncertainty: { status: "PROPAGATED_FROM_SITE_STANDARD_UNCERTAINTIES",
        mean_total_delta_standard_uncertainty: 0.054272 } },
    };
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      if (String(input) === "/api/status") return new Response(JSON.stringify({ source_modes: ["synthetic"] }));
      return new Response(JSON.stringify(result), { status: 200 });
    });
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("crypto", { randomUUID: () => "6c8690f0-906d-46a5-a63f-e380a8b00006" });
    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "Run investigation" }));
    await screen.findByRole("table", { name: /film_thickness \(nm\).*W-1/ });
    fireEvent.click(screen.getByRole("tab", { name: /C01/ }));
    const fingerprint = screen.getByRole("region", { name: "C01 engineering summary" });
    expect(fingerprint).toHaveTextContent("1 exploratory local pattern group; largest group has 11 observed sites");
    expect(fingerprint).toHaveTextContent("removed a fitted broad linear plane before same-radius comparison");
    expect(fingerprint).toHaveTextContent("cell width is about 14.3 mm");
    fireEvent.click(screen.getByRole("tab", { name: /C02/ }));
    const summary = screen.getByRole("region", { name: "C02 engineering summary" });
    expect(summary).toHaveTextContent("44 exact observed-site matches");
    expect(summary).toHaveTextContent("44 common sites (91.7%/100.0% step coverage)");
    expect(summary).toHaveTextContent("conditional 1σ assuming independent errors: 0.038 nm");
    expect(summary).toHaveTextContent("possible 1σ range with unspecified covariance: 0.010–0.200 nm (not a confidence interval)");
    expect(summary).toHaveTextContent("covariance bounds use only supplied marginal uncertainties");
    expect(summary).toHaveTextContent("do not establish calibrated process uncertainty");
  });

  it("qualifies a C04 threshold crossing that is exactly at the finite-sample rank floor", async () => {
    const result = JSON.parse(JSON.stringify(moduleResult));
    result.evidence.artifacts[0].result.anomaly = {
      status: "VALID", alpha: 0.05, baseline_wafers: 20, baseline_lots: 20,
      global_max_t_empirical_p: 1 / 21, minimum_attainable_global_p: 1 / 21,
      baseline_cohort_assessment: { status: "NOT_CERTIFIED_CLEAN", limitation: "Temporal stability checks ordered population change only; they do not certify baseline cleanliness. A temporally stable baseline containing maps similar to a true target anomaly can mask the alert." },
      outliers: [{ site_id: "S-1" }, { site_id: "S-2" }],
    };
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      if (String(input) === "/api/status") return new Response(JSON.stringify({ source_modes: ["synthetic"] }));
      return new Response(JSON.stringify(result), { status: 200 });
    });
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("crypto", { randomUUID: () => "6c8690f0-906d-46a5-a63e-e380a8b00007" });
    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "Run investigation" }));
    await screen.findByRole("table", { name: /die_bin \(category\).*W-1/ });
    fireEvent.click(screen.getByRole("tab", { name: /C04/ }));
    const summary = screen.getByRole("region", { name: "C04 engineering summary" });
    expect(summary).toHaveTextContent("meets alpha=0.050 only at its minimum resolvable empirical rank");
    expect(summary).toHaveTextContent("floor 0.0476");
    expect(summary).toHaveTextContent("20 earlier distinct baseline lots; minimum empirical p=0.0476");
    expect(summary).toHaveTextContent("coarse, conditional screening evidence");
    expect(summary).toHaveTextContent("repeated or adaptively selected target searches are not multiplicity-adjusted");
    expect(summary).toHaveTextContent("do not certify baseline cleanliness");
    expect(summary).toHaveTextContent("can mask the alert");
    expect(summary).not.toHaveTextContent("crossed its supplied threshold");
  });

  it("declares and discloses a bounded C04 target family that the baseline cannot resolve", async () => {
    const result = JSON.parse(JSON.stringify(moduleResult));
    result.evidence.artifacts[0].result.anomaly = {
      status: "INCONCLUSIVE", alpha: 0.025, unadjusted_alpha: 0.05,
      reason: "Bonferroni family alpha=0.025 for 2 predeclared targets is below the empirical rank floor 0.047619; at least 39 distinct baseline wafers are needed for this threshold to be resolvable",
      baseline_wafers: 20, baseline_lots: 20, minimum_attainable_global_p: 1 / 21,
      repeated_target_adjustment: "BONFERRONI", evaluation_scope: "PREDECLARED_TARGET_FAMILY_BONFERRONI",
      target_family: { family_id: "SYN-C04-FAMILY-2", family_size: 2,
        selection_rule_id: "SYN-FIXED-TARGET-ROSTER", predeclared_as_declared: true,
        complete_as_declared: true,
        source_registry_independently_audited: false }, outliers: [],
    };
    const fetchMock = vi.fn(async (input: RequestInfo | URL, _init?: RequestInit) => {
      if (String(input) === "/api/status") return new Response(JSON.stringify({ source_modes: ["synthetic"] }));
      return new Response(JSON.stringify(result), { status: 200 });
    });
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("crypto", { randomUUID: () => "6c8690f0-906d-46a5-a63e-e380a8b00007" });
    render(<App />);
    fireEvent.change(screen.getByLabelText("C04 predeclared family size"), { target: { value: "2" } });
    fireEvent.change(screen.getByLabelText("C04 family ID"), { target: { value: "SYN-C04-FAMILY-2" } });
    fireEvent.change(screen.getByLabelText("C04 selection rule ID"), { target: { value: "SYN-FIXED-TARGET-ROSTER" } });
    fireEvent.click(screen.getByRole("checkbox", { name: /complete target roster and selection rule were fixed/ }));
    fireEvent.click(screen.getByRole("button", { name: "Run investigation" }));
    await screen.findByRole("table", { name: /die_bin \(category\).*W-1/ });
    const investigationCall = fetchMock.mock.calls.find(([input]) => String(input) === "/api/investigate");
    expect(JSON.parse(String(investigationCall?.[1]?.body)).anomaly_target_family).toEqual({
      family_id: "SYN-C04-FAMILY-2", family_size: 2,
      selection_rule_id: "SYN-FIXED-TARGET-ROSTER", predeclared: true, complete: true,
    });
    fireEvent.click(screen.getByRole("tab", { name: /C04/ }));
    const summary = screen.getByRole("region", { name: "C04 engineering summary" });
    expect(summary).toHaveTextContent("family-adjusted threshold alpha=0.025 is below this baseline's minimum empirical rank");
    expect(summary).toHaveTextContent("Bonferroni-adjusted alpha=0.025 for predeclared complete family SYN-C04-FAMILY-2 (2 targets");
    expect(summary).toHaveTextContent("does not independently audit source-registry completeness");
  });

  it("shows the complete-frame selection evidence beside a C03 observational estimate", async () => {
    const result = JSON.parse(JSON.stringify(moduleResult));
    result.evidence.artifacts[0].result.quality_association = {
      status: "VALID", mean_within_wafer_r: 0.12, fisher_wafer_95_ci: [-0.08, 0.31],
      wafers: 20, independent_lots: 20,
      cohort_selection: { sampling_design: "COMPLETE_ELIGIBLE_FRAME", frame_id: "SYN-FRAME-20",
        eligibility_rule_id: "SYN-ELIGIBILITY-1", eligible_wafer_count: 20, selected_wafer_count: 20,
        selection_blind_to_feature_and_outcome: true, eligibility_rule_predeclared: true },
    };
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      if (String(input) === "/api/status") return new Response(JSON.stringify({ source_modes: ["synthetic"] }));
      return new Response(JSON.stringify(result), { status: 200 });
    });
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("crypto", { randomUUID: () => "6c8690f0-906d-46a5-a63e-e380a8b00008" });
    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "Run investigation" }));
    await screen.findByRole("table", { name: /die_bin \(category\).*W-1/ });
    fireEvent.click(screen.getByRole("tab", { name: /C03/ }));
    const summary = screen.getByRole("region", { name: "C03 engineering summary" });
    expect(summary).toHaveTextContent("Declared outcome-blind complete frame SYN-FRAME-20: 20/20 eligible holdout wafers");
    expect(summary).toHaveTextContent("selection rule SYN-ELIGIBILITY-1 was predeclared");
    expect(summary).toHaveTextContent("The interval covers zero");
    expect(summary).toHaveTextContent("P3 does not independently audit that source registry");
  });

  it("shows predeclared temporal reversals that a pooled C03 estimate would hide", async () => {
    const result = JSON.parse(JSON.stringify(moduleResult));
    result.evidence.artifacts[0].result.quality_association = {
      status: "VALID", mean_within_wafer_r: 0.001, fisher_wafer_95_ci: [-0.08, 0.08],
      wafers: 20, independent_lots: 20,
      cohort_selection: { sampling_design: "COMPLETE_ELIGIBLE_FRAME", frame_id: "SYN-TIME-FRAME",
        eligibility_rule_id: "SYN-ELIGIBILITY-1", eligible_wafer_count: 20, selected_wafer_count: 20 },
      temporal_association: { status: "OPPOSITE_DIRECTIONS_OBSERVED", opposite_directions_observed: true,
        partition_id: "SYN-EPOCHS", interval_scope: "nominal per stratum; no family-wise adjustment",
        strata: [
          { label: "early", mean_within_wafer_r: -0.95, fisher_wafer_95_ci: [-0.99, -0.90], independent_lots: 10 },
          { label: "late", mean_within_wafer_r: 0.95, fisher_wafer_95_ci: [0.90, 0.99], independent_lots: 10 },
        ] },
    };
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      if (String(input) === "/api/status") return new Response(JSON.stringify({ source_modes: ["synthetic"] }));
      return new Response(JSON.stringify(result), { status: 200 });
    }));
    vi.stubGlobal("crypto", { randomUUID: () => "6c8690f0-906d-46a5-a63f-e380a8b00009" });
    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "Run investigation" }));
    await screen.findByRole("table", { name: /die_bin \(category\).*W-1/ });
    fireEvent.click(screen.getByRole("tab", { name: /C03/ }));
    const summary = screen.getByRole("region", { name: "C03 engineering summary" });
    expect(summary).toHaveTextContent("not stable across the reviewed time strata");
    expect(summary).toHaveTextContent("early: r=-0.950; nominal 95% interval -0.990 to -0.900 (10 lots)");
    expect(summary).toHaveTextContent("late: r=0.950; nominal 95% interval 0.900 to 0.990 (10 lots)");
    expect(summary).toHaveTextContent("not family-wise adjusted");
  });

  it("shows refusal and recovery without displaying stale findings", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, _init?: RequestInit) => {
      if (String(input) === "/api/status") return new Response(JSON.stringify({ source_modes: ["synthetic"] }));
      return new Response(JSON.stringify({ status: "REFUSED", reason: "Reviewed source permission failed." }), { status: 403 });
    });
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("crypto", { randomUUID: () => "6c8690f0-906d-46a5-a63f-e380a8b00003" });
    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "Run investigation" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Reviewed source permission failed.");
    expect(screen.getByText("Start a spatial investigation")).toBeInTheDocument();
  });

  it("reports cancellation distinctly and allows a clean retry", async () => {
    let investigationCount = 0;
    const fetchMock = vi.fn(async (input: RequestInfo | URL, _init?: RequestInit) => {
      if (String(input) === "/api/status") return new Response(JSON.stringify({ source_modes: ["synthetic"] }));
      investigationCount += 1;
      if (investigationCount === 1) return new Response(JSON.stringify({
        status: "CANCELLED", reason: "Investigation cancelled. No partial analysis was accepted; you can correct the request or retry.",
      }), { status: 409 });
      return new Response(JSON.stringify(moduleResult), { status: 200 });
    });
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("crypto", { randomUUID: () => "6c8690f0-906d-46a5-a63f-e380a8b00004" });
    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "Run investigation" }));
    expect(await screen.findByText(/Investigation cancelled\. No partial analysis was accepted/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Run investigation" })).toBeEnabled();
    fireEvent.click(screen.getByRole("button", { name: "Run investigation" }));
    expect(await screen.findByRole("table", { name: /die_bin \(category\).*W-1/ })).toBeInTheDocument();
  });
});
