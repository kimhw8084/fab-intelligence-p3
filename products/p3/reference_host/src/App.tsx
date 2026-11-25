import { lazy, Suspense, useEffect, useMemo, useState } from "react";
import type { SpatialMapV2 } from "../../contracts/spatial-map.v2";

const SpatialMapRenderer = lazy(() => import("./SpatialMapRenderer").then(({ SpatialMapRenderer: component }) => ({ default: component })));

type Capability = { status?: string; [key: string]: unknown };
type Evidence = {
  status: string;
  investigation_id: string;
  claims: Array<{ statement: string; category?: string; certainty?: string; method?: string }>;
  limitations: string[];
  sources: Array<{ id: string; source_hash: string; grain: string; source_version: string; approved_semantic_version: string }>;
  provenance: { input_sha256?: string; mcp_workflow?: { bounded_reads?: Array<Record<string, unknown>>; [key: string]: unknown }; [key: string]: unknown };
  artifacts: Array<{ kind: string; result: Record<string, Capability> }>;
};
type ModuleResult = {
  contract_version: string;
  product_id: "p3";
  capabilities: string[];
  source_preview: { status: string; permission: string; semantic_version: string; grain: string; metric: string; unit: string; scope: string; time_window: string; modality: string; coverage: Record<string, number>; [key: string]: unknown };
  evidence: Evidence;
  spatial_map: SpatialMapV2;
  historical_spatial_map?: SpatialMapV2 | null;
  suite_compatibility: { contract_version: string; status: string; reason: string | null };
  export: { format: string; sha256: string; canonicalization: string; canonical_json: string };
  export_content: Record<string, unknown>;
};

type Summary = { finding: string; evidence: string[]; limitation: string };

function record(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown> : {};
}

function records(value: unknown): Record<string, unknown>[] {
  return Array.isArray(value) ? value.map(record) : [];
}

function numberText(value: unknown, digits = 2): string | null {
  return typeof value === "number" && Number.isFinite(value) ? value.toFixed(digits) : null;
}

function summaryFor(capability: string, raw: Capability | null, unit: string): Summary {
  if (!raw) return { finding: "No result supplied for this capability.", evidence: [], limitation: "" };
  const status = String(raw.status ?? "NOT_AVAILABLE");
  const reason = typeof raw.reason === "string" ? raw.reason : "";
  const familyRankUnresolved = capability === "C04" && reason.includes("Bonferroni family alpha");
  if (status !== "VALID" && status !== "PARTIAL" && !familyRankUnresolved) {
    return { finding: `${capability} is ${status.toLowerCase().replaceAll("_", " ")}.`, evidence: [],
      limitation: reason || "This capability did not produce a supported finding." };
  }

  if (capability === "C01") {
    const observed = numberText(raw.observed_points, 0);
    const edge = record(raw.edge_center);
    const difference = numberText(edge.difference);
    const modality = String(raw.modality ?? "continuous").replaceAll("_", " ");
    const interpretation = record(raw.interpretation_limits);
    const sampling = record(interpretation.sampling);
    const attribution = record(interpretation.measurement_attribution);
    const c01Evidence = [
      typeof sampling.review_question === "string" ? `Sampling question: ${sampling.review_question}` : "",
      typeof attribution.review_question === "string" ? `Measurement question: ${attribution.review_question}` : "",
    ].filter(Boolean);
    const c01Limitations = [sampling.limitation, attribution.limitation]
      .filter((item): item is string => typeof item === "string");
    if (modality.includes("categorical") || modality.includes("defect")) {
      return { finding: `${observed ?? "Observed"} ${modality} sites are preserved as typed observations.`,
        evidence: ["Numeric radial and gradient arithmetic is not applied to categorical values or defect events.", ...c01Evidence],
        limitation: ["Only observed locations are shown; categorical similarity and defect clustering are not continuous-value statistics.", ...c01Limitations].join(" ") };
    }
    const radial = records(raw.radial_profile);
    const radialSummary = radial.filter((row) => typeof row.mean === "number")
      .map((row) => `${String(row.region).replaceAll("_", " ")} ${numberText(row.mean)}`).join(" · ");
    const clusterResult = record(raw.local_clusters);
    const clusters = records(clusterResult.clusters);
    const largestCluster = clusters.reduce((max, row) => Math.max(max, typeof row.observed_site_count === "number" ? row.observed_site_count : 0), 0);
    const adjustment = record(clusterResult.screening_adjustment);
    const adjustmentApplied = adjustment.status === "APPLIED";
    const cellWidth = numberText(clusterResult.cell_width, 1);
    return {
      finding: `${observed ?? "Measured"} numeric sites. ${difference === null ? "Center-to-edge comparison is unavailable." : `Mean edge minus center is ${Number(edge.difference) >= 0 ? "+" : ""}${difference} ${unit}.`}`,
      evidence: [radialSummary ? `Observed radial means (${unit}): ${radialSummary}.` : "Radial regions without measurements remain unavailable.",
        ...c01Evidence,
        clusters.length ? `${clusters.length} exploratory local pattern group${clusters.length === 1 ? "" : "s"}; largest group has ${largestCluster} observed sites.` : "No local group met the current descriptive screening rule.",
        adjustmentApplied
          ? `Dense-map screening removed a fitted broad linear plane before same-radius comparison; cell width is about ${cellWidth ?? "reported"} ${String(clusterResult.coordinate_unit ?? "coordinate units")}.`
          : "Dense-map plane adjustment was not applied; raw observed values were used for local screening."],
      limitation: ["Local groups and plane adjustment are exploratory, not calibrated alerts. Plane detrending requires at least 200 sites with broad quadrant coverage and can absorb overlapping structure. Reticle periodicity is withheld unless geometry and sampling aliases are verified; no values are inferred between sites.", ...c01Limitations].join(" "),
    };
  }
  if (capability === "C02") {
    const sequence = Array.isArray(raw.step_sequence) ? raw.step_sequence.filter((item): item is string => typeof item === "string") : [];
    const comparisons = records(raw.comparisons);
    const matched = numberText(raw.matched_sites, 0);
    const changes = comparisons.map((row) => {
      const steps = Array.isArray(row.steps) ? row.steps.filter((item): item is string => typeof item === "string") : [];
      const delta = numberText(row.mean_delta);
      const coverage = record(row.coverage);
      const uncertainty = record(record(row.uncertainty).measurement_uncertainty);
      const previousCoverage = numberText(typeof coverage.previous === "number" ? coverage.previous * 100 : null, 1);
      const currentCoverage = numberText(typeof coverage.current === "number" ? coverage.current * 100 : null, 1);
      const common = numberText(row.matched_sites, 0);
      const overlap = previousCoverage !== null && currentCoverage !== null
        ? ` across ${common ?? "the observed"} common sites (${previousCoverage}%/${currentCoverage}% step coverage)` : "";
      const propagated = numberText(uncertainty.mean_delta_standard_uncertainty, 3);
      const covarianceBounds = record(uncertainty.unknown_covariance_bounds);
      const covarianceLow = numberText(covarianceBounds.lower_standard_uncertainty, 3);
      const covarianceHigh = numberText(covarianceBounds.upper_standard_uncertainty, 3);
      const boundsText = covarianceLow !== null && covarianceHigh !== null
        ? `; possible 1σ range with unspecified covariance: ${covarianceLow}–${covarianceHigh} ${unit} (not a confidence interval)` : "";
      const uncertaintyText = uncertainty.status === "PROPAGATED_FROM_SITE_STANDARD_UNCERTAINTIES" && propagated !== null
        ? `; conditional 1σ assuming independent errors: ${propagated} ${unit}${boundsText}` : "; measurement uncertainty not supplied";
      return delta === null ? null : `${steps.join(" → ") || "Step transition"}: ${Number(row.mean_delta) >= 0 ? "+" : ""}${delta} ${unit} mean change${overlap}${uncertaintyText}`;
    }).filter((item): item is string => item !== null);
    return { finding: `Compared ${sequence.join(" → ") || "ordered process steps"} using ${matched ?? "available"} exact observed-site matches.`,
      evidence: changes.length ? changes : ["Signed per-site changes and alignment details are available below."],
      limitation: "Only exact observed coordinates are compared. Missing sites are not interpolated. The independent-error estimate is conditional; covariance bounds use only supplied marginal uncertainties, are not a confidence interval, and do not establish calibrated process uncertainty. Cross-step and cross-site covariance are not supplied." };
  }
  if (capability === "C03") {
    const correlation = numberText(raw.mean_within_wafer_r, 3);
    const interval = Array.isArray(raw.fisher_wafer_95_ci) ? raw.fisher_wafer_95_ci : [];
    const low = numberText(interval[0], 3), high = numberText(interval[1], 3);
    const crossesZero = typeof interval[0] === "number" && typeof interval[1] === "number" && interval[0] <= 0 && interval[1] >= 0;
    const wafers = numberText(raw.wafers, 0), lots = numberText(raw.independent_lots, 0);
    const frame = record(raw.cohort_selection);
    const eligibleWafers = numberText(frame.eligible_wafer_count, 0);
    const selectedWafers = numberText(frame.selected_wafer_count, 0);
    const frameEvidence = frame.sampling_design === "COMPLETE_ELIGIBLE_FRAME"
      ? `Declared outcome-blind complete frame ${String(frame.frame_id ?? "unknown")}: ${selectedWafers ?? "unknown"}/${eligibleWafers ?? "unknown"} eligible holdout wafers; selection rule ${String(frame.eligibility_rule_id ?? "unknown")} was predeclared.`
      : `${wafers ?? "Unknown"} holdout wafers from ${lots ?? "unknown"} distinct lots contribute to the estimate; a verifiable complete selection frame was not returned.`;
    const temporal = record(raw.temporal_association);
    const strata = records(temporal.strata);
    const temporalLines = strata.map((stratum) => {
      const bounds = Array.isArray(stratum.fisher_wafer_95_ci) ? stratum.fisher_wafer_95_ci : [];
      const stratumR = numberText(stratum.mean_within_wafer_r, 3);
      const stratumLow = numberText(bounds[0], 3), stratumHigh = numberText(bounds[1], 3);
      return stratumR === null ? null : `${String(stratum.label ?? "Time stratum")}: r=${stratumR}${stratumLow !== null && stratumHigh !== null ? `; nominal 95% interval ${stratumLow} to ${stratumHigh}` : ""} (${numberText(stratum.independent_lots, 0) ?? "?"} lots)`;
    }).filter((line): line is string => line !== null);
    const oppositeDirections = temporal.opposite_directions_observed === true;
    const notAssessed = temporal.status === "NOT_ASSESSED";
    const temporalSummary = oppositeDirections
      ? "Predeclared time strata show opposite nominal interval directions; the pooled value masks temporal variation."
      : notAssessed
      ? "No reviewed temporal partition was supplied; pooling can hide a relationship that changes over time."
      : "Predeclared temporal strata are descriptive; no observed reversal does not establish stability.";
    return { finding: correlation === null ? "Within-wafer association estimate is unavailable." : `Lot-weighted mean within-wafer association r=${correlation}${low !== null && high !== null ? `; 95% lot-level interval ${low} to ${high}` : ""}.${oppositeDirections ? " This pooled estimate is not stable across the reviewed time strata." : ""}`,
      evidence: [frameEvidence, crossesZero ? "The interval covers zero; this holdout does not resolve a nonzero association." : `${wafers ?? "Observed"} holdout wafers from ${lots ?? "unknown"} distinct lots contribute to the estimate.`, ...temporalLines],
      limitation: `This is an observational association, not a causal finding. The selection frame is verified according to its reviewed source semantics; P3 does not independently audit that source registry. Product/process confounding and population drift may remain. ${temporalSummary} Temporal intervals are nominal per stratum and are not family-wise adjusted.` };
  }
  if (capability === "C04") {
    const rawP = raw.global_max_t_empirical_p;
    const p = numberText(rawP, 4);
    const alpha = numberText(raw.alpha, 3);
    const minimumP = numberText(raw.minimum_attainable_global_p, 4);
    const baselineLots = numberText(raw.baseline_lots, 0);
    const outliers = records(raw.outliers);
    const targetFamily = record(raw.target_family);
    const baselineCohort = record(raw.baseline_cohort_assessment);
    const baselineCaveat = typeof baselineCohort.limitation === "string" ? ` ${baselineCohort.limitation}` : "";
    const familySize = numberText(targetFamily.family_size, 0);
    const familyId = typeof targetFamily.family_id === "string" ? targetFamily.family_id : "";
    const familyRule = typeof targetFamily.selection_rule_id === "string" ? targetFamily.selection_rule_id : "";
    const familyAdjusted = raw.repeated_target_adjustment === "BONFERRONI";
    const familyResolutionUnavailable = raw.status === "INCONCLUSIVE" &&
      typeof raw.reason === "string" && raw.reason.includes("Bonferroni family alpha");
    const alert = typeof raw.global_max_t_empirical_p === "number" && typeof raw.alpha === "number" && raw.global_max_t_empirical_p <= raw.alpha;
    const atResolutionFloor = alert && typeof rawP === "number" && typeof raw.minimum_attainable_global_p === "number"
      && Math.abs(rawP - raw.minimum_attainable_global_p) <= 1e-12;
    const finding = familyResolutionUnavailable
      ? `The declared family-adjusted threshold alpha=${alpha ?? "unknown"} is below this baseline's minimum empirical rank (floor ${minimumP ?? "unknown"}); a family-level C04 decision is unresolved.`
      : atResolutionFloor
      ? `The wafer-level screen meets alpha=${alpha ?? "unknown"} only at its minimum resolvable empirical rank (p=${p ?? "unknown"}; floor ${minimumP ?? "unknown"}).`
      : alert
        ? `Wafer-level spatial outlier screen crossed its supplied threshold (empirical p=${p ?? "unknown"}, alpha=${alpha ?? "unknown"}).`
        : `No wafer-level alert at the supplied threshold (empirical p=${p ?? "unknown"}, alpha=${alpha ?? "unknown"}).`;
    const familyEvidence = familyAdjusted
      ? `Bonferroni-adjusted alpha=${alpha ?? "unknown"} for predeclared complete family ${familyId || "unknown"} (${familySize ?? "unknown"} targets; rule ${familyRule || "unknown"}).`
      : "No repeated-target adjustment was applied; this result covers one target only.";
    const limitation = (familyAdjusted
      ? "The empirical p-value has finite rank resolution. P3 records the caller-declared family but does not independently audit source-registry completeness; targets outside the predeclared family are unadjusted. A threshold crossing at the resolution floor is coarse, conditional evidence, not calibrated factory confidence. Localizer sites are not individually significant."
      : "The empirical p-value has finite rank resolution. This is a per-target screen; repeated or adaptively selected target searches are not multiplicity-adjusted. A threshold crossing at the resolution floor is coarse, conditional screening evidence and should not be read as calibrated factory confidence. Localizer sites are not individually significant; calibration is conditional on the supplied population.") + baselineCaveat;
    return { finding,
      evidence: [`${baselineLots ?? "Unknown"} earlier distinct baseline lots; minimum empirical p=${minimumP ?? "not supplied"}; ${outliers.length} sites are shown only as alert localizers.`, familyEvidence],
      limitation };
  }
  if (capability === "C05") {
    const neighbors = records(raw.neighbors);
    const first = neighbors[0];
    const excluded = records(raw.excluded);
    const distance = first ? numberText(first.multiscale_rmse, 3) : null;
    const alignment = first ? String(first.alignment ?? "validated spatial descriptors") : "";
    const reconstructionCaveat = alignment.toLowerCase().includes("no reconstruction") ? "" : "; no reconstruction";
    const evidence = [first ? `Compared using ${alignment}${reconstructionCaveat}; ${neighbors.length} eligible neighbor${neighbors.length === 1 ? "" : "s"} returned.` : "No eligible maps passed the context and time filters."];
    const profileCoverage = first ? record(first.profile_coverage) : {};
    if (alignment.includes("radial-sector")) {
      evidence.push(`Cross-layout profile coverage: ${numberText(profileCoverage.shared_radial_sector_bins, 0) ?? "unknown"} common radial-sector bins.`);
    }
    if (first?.sampling_mask_changed === true) {
      const targetCount = numberText(first.target_observed_site_count, 0);
      const candidateCount = numberText(first.candidate_observed_site_count, 0);
      evidence.push(`Sampling layout differs: ${targetCount ?? "target"} target observations versus ${candidateCount ?? "historical"} on the analog; shared-profile distance does not fill missing locations.`);
    }
    if (excluded.length) evidence.push(`${excluded.length} incompatible or future record${excluded.length === 1 ? " was" : "s were"} excluded.`);
    else evidence.push("No incompatible or future records were reported.");
    return { finding: first ? `Closest eligible historical analog is ${String(first.wafer_id ?? "an unnamed wafer")}${distance === null ? "" : ` (multiscale distance ${distance})`}.` : "No compatible historical analog was found.",
      evidence,
      limitation: "Similarity describes spatial resemblance only. It does not establish a shared mechanism or root cause. Cross-layout distances use shared radial-sector bins and can miss within-bin structure; sampling and context differences remain reviewable below." };
  }
  return { finding: `${capability} produced a ${status.toLowerCase().replaceAll("_", " ")} result.`, evidence: [],
    limitation: reason || "Review the validated technical details and evidence below." };
}

const CAPABILITY_NAMES: Record<string, string> = {
  C01: "Spatial fingerprint", C02: "Process-step evolution", C03: "Spatial-to-quality association",
  C04: "Spatial anomaly review", C05: "Historical analogs",
};
const CAPABILITY_IDS = Object.keys(CAPABILITY_NAMES);
const RESULTS: Record<string, string> = {
  C01: "fingerprint", C02: "evolution", C03: "quality_association", C04: "anomaly", C05: "similarity",
};
const PLANS = ["SYN-WF-CURRENT", "SYN-WF-PREVIOUS", "SYN-WF-BASELINE", "SYN-WF-HISTORY", "SYN-WF-ASSOCIATION"];

export function App() {
  const [sourceMode, setSourceMode] = useState("synthetic");
  const [planText, setPlanText] = useState(PLANS.join(", "));
  const [timeStart, setTimeStart] = useState("2026-01-01T00:00:00Z");
  const [timeEnd, setTimeEnd] = useState("2026-02-01T00:00:00Z");
  const [anomalyFamilySize, setAnomalyFamilySize] = useState("");
  const [anomalyFamilyId, setAnomalyFamilyId] = useState("");
  const [anomalyFamilyRule, setAnomalyFamilyRule] = useState("");
  const [anomalyFamilyPredeclared, setAnomalyFamilyPredeclared] = useState(false);
  const [sourceModes, setSourceModes] = useState(["synthetic"]);
  const [result, setResult] = useState<ModuleResult | null>(null);
  const [selected, setSelected] = useState("C01");
  const [state, setState] = useState<"IDLE" | "LOADING" | "CANCELLED" | "ERROR" | "REFUSED">("IDLE");
  const [message, setMessage] = useState("Ready. Synthetic source is isolated and uses no company data.");
  const [activeRequest, setActiveRequest] = useState<string | null>(null);
  const [duration, setDuration] = useState<number | null>(null);

  useEffect(() => {
    fetch("/api/status").then((response) => response.json()).then((body: { source_modes?: string[] }) => {
      if (Array.isArray(body.source_modes)) setSourceModes(body.source_modes);
    }).catch(() => setMessage("Local host status is unavailable; check the server and retry."));
  }, []);

  const selectedResult = useMemo(() => {
    const key = RESULTS[selected];
    return result?.evidence.artifacts.find((item) => item.kind === "p3_analysis")?.result[key] ?? null;
  }, [result, selected]);

  async function investigate() {
    const requestId = crypto.randomUUID();
    setActiveRequest(requestId);
    setState("LOADING");
    setMessage("Discovering approved tools and reading bounded source rows through the MCP SDK…");
    setResult(null);
    const started = performance.now();
    try {
      const parsedFamilySize = anomalyFamilySize.trim() ? Number(anomalyFamilySize) : 1;
      const anomalyTargetFamily = parsedFamilySize > 1 ? {
        family_id: anomalyFamilyId.trim(), family_size: parsedFamilySize,
        selection_rule_id: anomalyFamilyRule.trim(),
        predeclared: anomalyFamilyPredeclared, complete: anomalyFamilyPredeclared,
      } : null;
      const response = await fetch("/api/investigate", {
        method: "POST", headers: { "Content-Type": "application/json", "X-Analysis-Id": requestId },
        body: JSON.stringify({ source_mode: sourceMode, plan_ids: planText.split(",").map((item) => item.trim()).filter(Boolean), time_start: timeStart, time_end: timeEnd, top_k: 5, anomaly_target_family: anomalyTargetFamily }),
      });
      const body = await response.json();
      setDuration(Math.round(performance.now() - started));
      if (!response.ok) {
        setState(body.status === "CANCELLED" ? "CANCELLED" : body.status === "REFUSED" ? "REFUSED" : "ERROR");
        setMessage(body.reason ?? body.error ?? "The investigation failed. Correct the request or retry.");
        return;
      }
      setResult(body as ModuleResult);
      setState("IDLE");
      setMessage(`Investigation completed in ${Math.round(performance.now() - started)} ms. Evidence is synthetic or read-only unqualified.`);
    } catch {
      setDuration(Math.round(performance.now() - started));
      setState("ERROR");
      setMessage("The local host could not complete the request. Check its status and retry.");
    } finally {
      setActiveRequest(null);
    }
  }

  async function cancel() {
    if (!activeRequest) return;
    setMessage("Cancellation requested. Waiting for the bounded read to stop…");
    try {
      await fetch("/api/cancel", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ request_id: activeRequest }) });
    } catch {
      setMessage("Cancellation could not reach the local host. The bounded MCP call still has its configured timeout.");
    }
  }

  function exportEvidence() {
    if (!result) return;
    const payload = result.export.canonical_json;
    const blob = new Blob([payload], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `p3-investigation-${result.evidence.investigation_id}.json`;
    anchor.click();
    URL.revokeObjectURL(url);
    setMessage(`Evidence export saved. Canonical SHA-256: ${result.export.sha256}`);
  }

  const map = result?.spatial_map;
  const selectedStatus = selectedResult?.status ?? "NOT_AVAILABLE";
  const selectedSummary = summaryFor(selected, selectedResult, map?.measurement_unit ?? "");
  return <main className="app-shell">
    <header className="topbar">
      <div className="brand"><span className="brand-mark" aria-hidden="true">F</span><div><p className="eyebrow">FAB INTELLIGENCE · INDEPENDENT PRODUCT</p><h1>Spatial &amp; Yield Intelligence</h1></div></div>
      <span className="qualification-badge">Company qualification pending</span>
    </header>

    <section className="investigation-control" aria-labelledby="investigation-title">
      <div><p className="eyebrow">INVESTIGATION SETUP</p><h2 id="investigation-title">Choose a source and run C01–C05</h2></div>
      <div className="control-grid">
        <label>Source mode<select value={sourceMode} onChange={(event) => { setSourceMode(event.target.value); setPlanText(event.target.value === "synthetic" ? PLANS.join(", ") : ""); }}>
          {sourceModes.map((mode) => <option key={mode} value={mode}>{mode === "synthetic" ? "Synthetic MCP demonstration" : "Configured read-only MCP"}</option>)}
        </select></label>
        <label className="wide">Approved plan identifiers <textarea rows={2} value={planText} onChange={(event) => setPlanText(event.target.value)} aria-describedby="plan-help" /></label>
        <label>Time start <input value={timeStart} onChange={(event) => setTimeStart(event.target.value)} /></label>
        <label>Time end <input value={timeEnd} onChange={(event) => setTimeEnd(event.target.value)} /></label>
        <label>C04 predeclared family size <input type="number" min={2} max={1000} step={1} value={anomalyFamilySize} onChange={(event) => setAnomalyFamilySize(event.target.value)} aria-describedby="target-family-help" /></label>
        <label>C04 family ID <input value={anomalyFamilyId} onChange={(event) => setAnomalyFamilyId(event.target.value)} aria-describedby="target-family-help" /></label>
        <label className="wide">C04 selection rule ID <input value={anomalyFamilyRule} onChange={(event) => setAnomalyFamilyRule(event.target.value)} aria-describedby="target-family-help" /></label>
        <label className="wide check-field"><input type="checkbox" checked={anomalyFamilyPredeclared} onChange={(event) => setAnomalyFamilyPredeclared(event.target.checked)} /> The complete target roster and selection rule were fixed before reviewing anomaly results</label>
      </div>
      <p id="plan-help" className="field-help">Use identifiers from the active MCP configuration. Synthetic mode supplies a fixed demonstration workflow.</p>
      <p id="target-family-help" className="field-help">Leave family size empty for a single-target C04 screen. A declared family uses Bonferroni adjustment; P3 records the roster declaration but cannot audit the source registry. Insufficient empirical rank resolution will abstain.</p>
      <div className="action-row">
        <button className="primary" onClick={() => void investigate()} disabled={state === "LOADING" || !planText.trim()}>Run investigation</button>
        {state === "LOADING" && <button className="secondary" onClick={() => void cancel()}>Cancel</button>}
        {duration !== null && <span className="duration">Last request: {duration} ms</span>}
      </div>
      <p className={`live-message ${state.toLowerCase()}`} role={state === "ERROR" || state === "REFUSED" ? "alert" : "status"} aria-live="polite">{message}</p>
    </section>

    {result && map ? <>
      <section className="summary-row" aria-label="Investigation summary">
        <div><span>Wafer</span><strong>{map.wafer_id}</strong><small>{map.product_id} · {map.step_id ?? "Step not supplied"}</small></div>
        <div><span>Measurement</span><strong>{map.metric}</strong><small>{map.measurement_unit} · {map.modality.replaceAll("_", " ")}</small></div>
        <div><span>Observed sites</span><strong>{map.sampling.observation_count}</strong><small>{map.sampling.explicit_missing_value_count} explicitly missing · no interpolation</small></div>
        <div><span>Evidence</span><strong>{result.evidence.status}</strong><small>{result.evidence.provenance.mcp_workflow?.bounded_reads?.length ?? 0} bounded reads</small></div>
      </section>

      <section className="work-area">
        <section className="panel spatial-panel" aria-labelledby="map-title">
          <div className="panel-heading"><div><p className="eyebrow">MEASURED OBSERVATIONS</p><h2 id="map-title">Wafer map</h2></div><span className="quiet-tag">{map.sampling.coverage_fraction === undefined ? "Coverage denominator unavailable" : `${(map.sampling.coverage_fraction * 100).toFixed(1)}% declared coverage`}</span></div>
          {map.coordinates_verified ? <Suspense fallback={<p role="status">Loading measured-site visualization…</p>}><SpatialMapRenderer model={map} /></Suspense> : <p role="status">Coordinates are unverified. The spatial plot is withheld; the typed observation table remains available.</p>}
          <p className="chart-caption">Only measured sites are plotted. Numeric values use a continuous scale; categories and defect events retain their original types.</p>
          <details open><summary>Accessible typed observations ({map.observations.length})</summary>
            <div className="table-scroll"><table><caption>{map.metric} ({map.measurement_unit}) · wafer {map.wafer_id} · input and rendered counts reconcile</caption>
              <thead><tr><th scope="col">Site</th><th scope="col">X ({map.coordinate_unit})</th><th scope="col">Y ({map.coordinate_unit})</th><th scope="col">Kind</th><th scope="col">Value</th><th scope="col">Type</th></tr></thead>
              <tbody>{map.observations.map((row, index) => <tr key={`${row.site_id}-${index}`}>
                <th scope="row">{row.site_id}</th><td>{row.x}</td><td>{row.y}</td><td>{row.observation_kind.replaceAll("_", " ")}</td>
                <td>{row.observation_kind === "MISSING_MEASUREMENT" ? "Missing" : row.observation_kind === "DEFECT_EVENT" && row.value === null ? "Unlabeled event" : String(row.value)}</td><td>{row.value_type}</td>
              </tr>)}</tbody>
            </table></div>
          </details>
        </section>

        <section className="panel capability-panel" aria-labelledby="cap-title">
          <div className="panel-heading"><div><p className="eyebrow">SCIENTIFIC REVIEW</p><h2 id="cap-title">C01–C05 capabilities</h2></div></div>
          <div className="capability-tabs" role="tablist" aria-label="P3 scientific capabilities">
            {Object.entries(CAPABILITY_NAMES).map(([id, label], index) => {
              const key = RESULTS[id];
              const status = result.evidence.artifacts.find((item) => item.kind === "p3_analysis")?.result[key]?.status ?? "NOT_AVAILABLE";
              return <button id={`cap-tab-${id}`} role="tab" tabIndex={selected === id ? 0 : -1}
                aria-selected={selected === id} aria-controls="capability-detail" key={id} onClick={() => setSelected(id)}
                onKeyDown={(event) => {
                  const next = event.key === "ArrowRight" ? (index + 1) % CAPABILITY_IDS.length
                    : event.key === "ArrowLeft" ? (index - 1 + CAPABILITY_IDS.length) % CAPABILITY_IDS.length
                    : event.key === "Home" ? 0 : event.key === "End" ? CAPABILITY_IDS.length - 1 : index;
                  if (next !== index) {
                    event.preventDefault();
                    setSelected(CAPABILITY_IDS[next]);
                    event.currentTarget.parentElement?.querySelectorAll<HTMLButtonElement>("[role='tab']")[next]?.focus();
                  }
                }}><b>{id}</b><span>{label}</span><em>{status}</em></button>;
            })}
          </div>
          <div id="capability-detail" role="tabpanel" aria-labelledby={`cap-tab-${selected}`} tabIndex={0} aria-live="polite">
            <h3>{selected} · {CAPABILITY_NAMES[selected]}</h3><p className="status-line">Status: <strong>{selectedStatus}</strong></p>
            <section className="scientific-summary" aria-label={`${selected} engineering summary`}>
              <p className="summary-finding">{selectedSummary.finding}</p>
              {selectedSummary.evidence.length > 0 && <ul>{selectedSummary.evidence.map((item, index) => <li key={index}>{item}</li>)}</ul>}
              {selectedSummary.limitation && <p className="summary-limitation">{selectedSummary.limitation}</p>}
            </section>
            {selected === "C05" && result.historical_spatial_map && <section className="historical-comparison" aria-label="Closest historical analog map">
              <div className="panel-heading"><div><p className="eyebrow">OBSERVED HISTORICAL ANALOG</p>
                <h4>{result.historical_spatial_map.wafer_id}</h4></div>
                <span className="quiet-tag">{result.historical_spatial_map.sampling.observation_count} measured sites</span>
              </div>
              <p className="chart-caption">{result.historical_spatial_map.product_id} · {result.historical_spatial_map.step_id ?? "Step not supplied"} · {result.historical_spatial_map.measured_at} · {result.historical_spatial_map.metric} ({result.historical_spatial_map.measurement_unit}) · mask {result.historical_spatial_map.sampling.mask_id ?? "not supplied"}</p>
              {result.historical_spatial_map.coordinates_verified
                ? <Suspense fallback={<p role="status">Loading historical measured-site visualization…</p>}><SpatialMapRenderer model={result.historical_spatial_map} /></Suspense>
                : <p role="status">Historical coordinates are unverified. The plot is withheld; C05 evidence remains available.</p>}
              <p className="chart-caption">Only the analog’s observed locations are rendered. No missing sites are reconstructed or interpolated.</p>
              <details><summary>Accessible historical observations ({result.historical_spatial_map.observations.length})</summary>
                <div className="table-scroll"><table><caption>{result.historical_spatial_map.metric} ({result.historical_spatial_map.measurement_unit}) · wafer {result.historical_spatial_map.wafer_id} · input and rendered counts reconcile</caption>
                  <thead><tr><th scope="col">Site</th><th scope="col">X ({result.historical_spatial_map.coordinate_unit})</th><th scope="col">Y ({result.historical_spatial_map.coordinate_unit})</th><th scope="col">Kind</th><th scope="col">Value</th><th scope="col">Type</th></tr></thead>
                  <tbody>{result.historical_spatial_map.observations.map((row, index) => <tr key={`${row.site_id}-${index}`}>
                    <th scope="row">{row.site_id}</th><td>{row.x}</td><td>{row.y}</td><td>{row.observation_kind.replaceAll("_", " ")}</td>
                    <td>{row.observation_kind === "MISSING_MEASUREMENT" ? "Missing" : row.observation_kind === "DEFECT_EVENT" && row.value === null ? "Unlabeled event" : String(row.value)}</td><td>{row.value_type}</td>
                  </tr>)}</tbody>
                </table></div>
              </details>
            </section>}
            {selectedResult && <details className="technical-detail"><summary>Technical calculation detail</summary><pre className="result-json">{JSON.stringify(selectedResult, null, 2)}</pre></details>}
          </div>
          <details className="provenance"><summary>Source evidence and provenance</summary>
            <p>Read-only scope: {String(result.evidence.provenance.mcp_workflow?.permission_scope ?? "not supplied")}</p>
            <p>Semantic mapping: {map.provenance.semantic_version} · source snapshot {map.provenance.source_version}</p>
            <p>Source hash: <code>{map.provenance.source_hash}</code></p>
            <p>Host compatibility adapter: {result.suite_compatibility.status}{result.suite_compatibility.reason ? ` — ${result.suite_compatibility.reason}` : ""}</p>
            <details><summary>Bounded read audit</summary><pre className="result-json">{JSON.stringify(result.evidence.provenance.mcp_workflow?.bounded_reads ?? [], null, 2)}</pre></details>
            <details><summary>All scientific limitations</summary><ul>{result.evidence.limitations.map((item, index) => <li key={index}>{item}</li>)}</ul></details>
          </details>
          <button className="secondary export-button" onClick={exportEvidence}>Export reproducible evidence</button>
          <p className="hash-line">Export SHA-256: <code>{result.export.sha256}</code></p>
        </section>
      </section>
    </> : <section className="empty-state"><div aria-hidden="true">◎</div><h2>Start a spatial investigation</h2><p>Run the synthetic MCP workflow to inspect measured coverage, C01–C05 findings, source provenance, and an exportable evidence envelope.</p></section>}
    <footer className="page-footer">P3 reference host · local loopback only · synthetic MCP data or explicitly configured read-only source · internal qualification remains pending</footer>
  </main>;
}
