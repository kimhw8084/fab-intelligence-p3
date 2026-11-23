"use strict";

const input = document.getElementById("input-json");
const analyzeButton = document.getElementById("analyze");
const cancelButton = document.getElementById("cancel");
const downloadButton = document.getElementById("download");
const waferSelect = document.getElementById("wafer-select");
const regionSelect = document.getElementById("region-select");
let loadedDocument = null;
let lastEvidence = null;
let activeAnalysis = null;

function node(tag, text, className) {
  const result = document.createElement(tag);
  if (text !== undefined) result.textContent = text;
  if (className) result.className = className;
  return result;
}

function setMessage(text, error = false) {
  const message = document.getElementById("message");
  message.textContent = text;
  message.className = error ? "error" : "muted";
}

function bundleMaps(data) {
  return data && Array.isArray(data.maps) ? data.maps.filter(map => map && typeof map === "object" && !Array.isArray(map)) : [];
}

function mapLabel(map, index) {
  return [map.wafer_id || `Map ${index + 1}`, map.lot_id, map.step_id,
    map.measurement?.metric, map.measured_at].filter(Boolean).join(" · ");
}

function populateMapSelector(data) {
  const maps = bundleMaps(data);
  const prior = waferSelect.value;
  waferSelect.replaceChildren();
  maps.forEach((map, index) => {
    const option = document.createElement("option");
    option.value = String(index);
    option.textContent = mapLabel(map, index);
    waferSelect.append(option);
  });
  waferSelect.disabled = maps.length < 2;
  if (maps.length && maps.some((_, index) => String(index) === prior)) waferSelect.value = prior;
  else if (maps.length) waferSelect.value = "0";
}

function selectedMap(data) {
  const maps = bundleMaps(data);
  if (!maps.length) return data;
  const index = Number(waferSelect.value);
  return maps[index] || maps[0];
}

function selectedInvestigation(data) {
  const maps = bundleMaps(data);
  if (!maps.length) return data;
  const current = selectedMap(data);
  const investigation = { ...current };
  const sharedInputs = ["baseline_population", "baseline_holdout_verified", "history", "previous_step",
    "previous_steps", "evolution_match_policy", "quality_association", "requested_capabilities", "top_k"];
  for (const key of sharedInputs) {
    if (Object.prototype.hasOwnProperty.call(data, key)) investigation[key] = data[key];
  }
  const currentTime = Date.parse(current.measured_at || "");
  const priorMaps = maps.filter(map => map.wafer_id === current.wafer_id && map !== current
    && Number.isFinite(currentTime) && Date.parse(map.measured_at || "") < currentTime)
    .sort((a, b) => Date.parse(a.measured_at) - Date.parse(b.measured_at));
  if (!Object.prototype.hasOwnProperty.call(data, "previous_steps")
      && !Object.prototype.hasOwnProperty.call(data, "previous_step") && priorMaps.length === 1) {
    investigation.previous_step = priorMaps[0];
  } else if (!Object.prototype.hasOwnProperty.call(data, "previous_steps")
      && !Object.prototype.hasOwnProperty.call(data, "previous_step") && priorMaps.length > 1) {
    investigation.previous_steps = priorMaps;
  }
  const historical = maps.filter(map => map.wafer_id && current.wafer_id
    && map.wafer_id !== current.wafer_id && Number.isFinite(currentTime)
    && Date.parse(map.measured_at || "") < currentTime);
  if (!Object.prototype.hasOwnProperty.call(data, "history") && historical.length) investigation.history = historical;
  return investigation;
}

function clearResults(message) {
  lastEvidence = null;
  downloadButton.disabled = true;
  document.getElementById("evidence").textContent = "No evidence yet.";
  document.getElementById("badge").textContent = "Not run";
  document.getElementById("badge").dataset.state = "";
  document.getElementById("claims").replaceChildren(node("p", "Run an analysis to inspect measured findings and limitations.", "muted"));
  document.getElementById("source-inspector").textContent = "No evidence yet.";
  for (const [id, text] of [["capabilities", ""], ["spatial-summary", "Run an investigation to inspect spatial features."],
    ["history-results", "No historical search yet."], ["evolution-results", "No prior-step comparison yet."],
    ["quality-results", "No downstream association yet."]]) {
    const target = document.getElementById(id);
    target.replaceChildren();
    if (text) target.append(node("p", text, "muted"));
  }
  if (message) setMessage(message);
}

function capabilityCard(title, result) {
  const card = node("div", undefined, "cap");
  card.append(node("b", title));
  card.append(node("small", `${result.status || "UNKNOWN"}${result.reason ? ` · ${result.reason}` : ""}`));
  return card;
}

function renderCapabilities(report) {
  const root = document.getElementById("capabilities");
  root.replaceChildren(
    capabilityCard("C01 · Fingerprint", report.fingerprint || {}),
    capabilityCard("C04 · Anomalies", report.anomaly || {}),
    capabilityCard("C05 · Similarity", report.similarity || {}),
    capabilityCard("C02 · Evolution", report.evolution || {}),
    capabilityCard("C03 · Quality association", report.quality_association || {})
  );
}

function renderClaims(evidence) {
  const root = document.getElementById("claims");
  root.replaceChildren();
  if (evidence.claims && evidence.claims.length) {
    for (const item of evidence.claims) {
      const claim = node("p", undefined, "claim");
      claim.append(node("strong", `${item.category} · ${item.certainty}: `));
      claim.append(document.createTextNode(item.statement));
      if (Array.isArray(item.source_ids) && item.source_ids.length) claim.append(node("small", `Sources: ${item.source_ids.join(", ")}`));
      root.append(claim);
    }
  } else {
    root.append(node("p", "No scientific claim was produced.", "warning"));
  }
  if (evidence.limitations && evidence.limitations.length) {
    const list = node("ul");
    for (const limitation of evidence.limitations) list.append(node("li", limitation));
    root.append(list);
  }
}

function renderProvenance(evidence) {
  const root = document.getElementById("source-inspector");
  root.replaceChildren();
  const provenance = evidence.provenance || {};
  root.append(node("p", `Investigation ${evidence.investigation_id} · engine ${provenance.engine_version || "unknown"} · method ${provenance.method_version || "unknown"}`));
  root.append(node("p", `Input SHA-256: ${provenance.input_sha256 || "unavailable"}`));
  root.append(node("p", `Units: ${JSON.stringify(evidence.units || {})}`));
  root.append(node("p", `Populations: ${JSON.stringify(evidence.populations || [])}`));
  root.append(node("p", `Transformations: ${JSON.stringify(evidence.transformations || [])}`));
  root.append(node("p", `Uncertainty: ${JSON.stringify(evidence.uncertainty || {})}`));
  const sources = Array.isArray(evidence.sources) ? evidence.sources : [];
  if (sources.length) {
    const sourceList = node("ul");
    for (const source of sources) sourceList.append(node("li", `${source.id} · ${source.approved_semantic_version} · grain ${source.grain} · SHA-256 ${source.source_hash}`));
    root.append(node("strong", "Input sources"), sourceList);
  } else root.append(node("p", "No source identifier was included in the synthetic input."));
  const assumptions = Array.isArray(evidence.assumptions) ? evidence.assumptions : [];
  const assumptionList = node("ul");
  for (const assumption of assumptions) assumptionList.append(node("li", assumption));
  root.append(node("strong", "Assumptions"), assumptionList);
}

function renderSpatialSummary(fingerprint) {
  const root = document.getElementById("spatial-summary");
  root.replaceChildren();
  if (!fingerprint || !fingerprint.radial_profile) {
    root.append(node("p", fingerprint?.reason || "Spatial summaries are unavailable for this input.", "muted"));
    return;
  }
  root.append(node("p", `${fingerprint.observed_points} measured sites · ${fingerprint.modality || "continuous"} · coverage counts are observed only.`, "muted"));
  if (fingerprint.edge_center?.status === "VALID") {
    const uncertainty = fingerprint.edge_center.uncertainty_status === "PROPAGATED_FROM_SITE_STANDARD_UNCERTAINTIES"
      ? ` · one-standard-uncertainty ${fingerprint.edge_center.standard_uncertainty} ${fingerprint.measurement_unit}`
      : " · measurement uncertainty not supplied";
    root.append(node("p", `Edge − center: ${fingerprint.edge_minus_center} ${fingerprint.measurement_unit}${uncertainty}`));
  } else if (fingerprint.edge_center?.reason) root.append(node("p", `Edge − center: ${fingerprint.edge_center.status} · ${fingerprint.edge_center.reason}`, "warning"));
  const values = fingerprint.radial_profile.map(row => row.mean).filter(Number.isFinite);
  const center = values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : 0;
  const scale = Math.max(...values.map(value => Math.abs(value - center)), 1e-9);
  for (const row of fingerprint.radial_profile) {
    const line = node("div", undefined, "chart-row");
    line.append(node("span", row.region.replaceAll("_", " ")));
    const track = node("div", undefined, "bar-track");
    const bar = node("div", undefined, "bar");
    const value = Number.isFinite(row.mean) ? row.mean - center : 0;
    bar.style.width = `${Math.max(2, Math.min(100, Math.abs(value) / scale * 100))}%`;
    if (value < 0) bar.classList.add("negative");
    track.append(bar);
    line.append(track, node("span", `n=${row.count} · ${row.mean ?? "no observations"} ${fingerprint.measurement_unit || ""}`));
    root.append(line);
  }
  if (Array.isArray(fingerprint.sectors)) {
    const sectorCounts = fingerprint.sectors.map(row => `${row.sector + 1}:${row.count}`).join(" · ");
    root.append(node("p", `Sector coverage (measured sites): ${sectorCounts}`, "muted"));
  }
}

function renderHistory(report) {
  const root = document.getElementById("history-results");
  root.replaceChildren();
  const history = report.similarity || {};
  if (history.status !== "VALID") {
    root.append(node("p", history.reason || "No historical retrieval was requested.", "muted"));
    return;
  }
  const table = document.createElement("table");
  const head = document.createElement("thead");
  const heading = document.createElement("tr");
  ["Rank", "Wafer", "Distance", "Alignment", "Profile bins"].forEach(label => heading.append(node("th", label)));
  head.append(heading); table.append(head);
  const body = document.createElement("tbody");
  history.neighbors.forEach((item, index) => {
    const row = document.createElement("tr");
    [index + 1, item.wafer_id, item.multiscale_rmse, item.alignment,
      `${item.profile_coverage?.shared_radial_bins ?? "—"} radial / ${item.profile_coverage?.shared_sector_bins ?? "—"} sector`]
      .forEach(value => row.append(node("td", String(value))));
    body.append(row);
  });
  table.append(body); root.append(table);
  root.append(node("p", history.interpretation || "Similarity does not establish a shared mechanism.", "muted"));
}

function renderEvolution(report) {
  const root = document.getElementById("evolution-results");
  root.replaceChildren();
  const evolution = report.evolution || {};
  if (evolution.status !== "VALID") {
    root.append(node("p", evolution.reason || "No prior-step comparison was requested.", "muted"));
    return;
  }
  root.append(node("p", `${evolution.steps?.join(" → ") || "Step sequence"} · ${evolution.matched_sites} observed-site matches · mean change ${evolution.mean_delta} · maximum coordinate residual ${evolution.registration_residual} coordinate units.`));
  if (evolution.coverage) root.append(node("p", `Common-site coverage: previous ${evolution.coverage.previous}; current ${evolution.coverage.current}; no reconstruction.`));
  const rows = Array.isArray(evolution.site_deltas) ? evolution.site_deltas.slice(0, 50) : [];
  if (rows.length) {
    const table = document.createElement("table");
    const head = document.createElement("tr");
    ["Site", "Previous", "Current", "Δ", "1σ"].forEach(label => head.append(node("th", label)));
    table.append(head);
    for (const item of rows) {
      const row = document.createElement("tr");
      [item.site_id, item.previous ?? item.step_deltas?.join(" → "), item.current ?? item.total_delta,
        item.delta ?? item.total_delta, item.standard_uncertainty ?? item.total_delta_standard_uncertainty ?? "not supplied"]
        .forEach(value => row.append(node("td", String(value))));
      table.append(row);
    }
    root.append(table);
    if (evolution.site_deltas.length > rows.length) root.append(node("p", `Showing ${rows.length} of ${evolution.site_deltas.length} measured-site comparisons.`, "muted"));
  }
}

function renderQuality(report) {
  const root = document.getElementById("quality-results");
  root.replaceChildren();
  const quality = report.quality_association || {};
  if (quality.status !== "VALID") {
    root.append(node("p", quality.reason || "No downstream association was requested.", "muted"));
    return;
  }
  root.append(node("p", `Observational within-wafer association r=${quality.mean_within_wafer_r} · 95% wafer-level interval ${quality.fisher_wafer_95_ci?.join(" to ")} · ${quality.wafers} wafers / ${quality.independent_lots} distinct lots.`));
  root.append(node("p", `Leave-one-lot-out r range ${quality.uncertainty?.leave_one_lot_out_r_range?.join(" to ")}. ${quality.interpretation}`, "muted"));
}

function regionFor(point, radius, region, orientation = 0) {
  if (region === "all") return true;
  const fraction = Math.hypot(Number(point.x), Number(point.y)) / radius;
  if (["center", "inner_middle", "outer_middle", "edge"].includes(region)) {
    return region === "center" ? fraction <= 0.2 : region === "inner_middle" ? fraction > 0.2 && fraction <= 0.5
      : region === "outer_middle" ? fraction > 0.5 && fraction <= 0.8 : fraction > 0.8;
  }
  if (region.startsWith("sector-")) {
    const sector = Number(region.slice(7));
    const theta = Number(orientation) * Math.PI / 180;
    const x = Number(point.x) * Math.cos(theta) - Number(point.y) * Math.sin(theta);
    const y = Number(point.x) * Math.sin(theta) + Number(point.y) * Math.cos(theta);
    const angle = (Math.atan2(y, x) + 2 * Math.PI) % (2 * Math.PI);
    return Math.floor(angle / (Math.PI / 4)) % 8 === sector;
  }
  return true;
}

function renderMap(data, report = {}, focus = "all") {
  const svg = document.getElementById("wafer-map");
  svg.replaceChildren();
  const title = nodeSvg("title", { id: "map-title" }, "Measured wafer sites");
  const desc = nodeSvg("desc", { id: "map-desc" }, "No map loaded.");
  svg.append(title, desc);
  const geometry = data.geometry && typeof data.geometry === "object" ? data.geometry : {};
  const radius = Number(geometry.radius ?? data.radius);
  const origin = geometry.origin ?? { x: 0, y: 0 };
  const ox = Array.isArray(origin) ? Number(origin[0]) : Number(origin.x ?? 0);
  const oy = Array.isArray(origin) ? Number(origin[1]) : Number(origin.y ?? 0);
  const allPoints = Array.isArray(data.points) ? data.points.filter(point => point && Number.isFinite(Number(point.x)) && Number.isFinite(Number(point.y))) : [];
  const orientation = geometry.orientation_deg ?? data.orientation_deg ?? 0;
  const points = allPoints.filter(point => regionFor({ x: Number(point.x) - ox, y: Number(point.y) - oy }, radius, focus, orientation));
  if (!(radius > 0) || !points.length) {
    desc.textContent = "No measured sites are available in this view.";
    svg.append(nodeSvg("text", { x: 250, y: 250, "text-anchor": "middle", fill: "#526677" }, "No measured sites"));
    document.getElementById("site-table").replaceChildren(node("p", "No measured sites to list in this view.", "muted"));
    return;
  }
  const scale = 190 / radius;
  svg.append(nodeSvg("circle", { cx: 250, cy: 250, r: 190, fill: "#fbfcfd", stroke: "#416276", "stroke-width": 2 }));
  svg.append(nodeSvg("line", { x1: 60, y1: 250, x2: 440, y2: 250, stroke: "#d9e1e6", "stroke-width": 1 }));
  svg.append(nodeSvg("line", { x1: 250, y1: 60, x2: 250, y2: 440, stroke: "#d9e1e6", "stroke-width": 1 }));
  const numeric = points.map(point => Number(point.value)).filter(Number.isFinite);
  const min = numeric.length ? numeric.reduce((value, current) => Math.min(value, current), Infinity) : 0;
  const max = numeric.length ? numeric.reduce((value, current) => Math.max(value, current), -Infinity) : 0;
  const measurement = data.measurement && typeof data.measurement === "object" ? data.measurement : {};
  const cats = [...new Set(points.map(point => String(point.category ?? point.bin ?? "defect event")))].sort();
  const categoryColors = ["#28779c", "#b45239", "#6a57a5", "#3e805d", "#a26d13", "#586b7a"];
  document.querySelector(".legend").textContent = numeric.length
    ? `Each dot is a measured point. Color shows ${measurement.metric || "the selected metric"} from ${min} to ${max} ${measurement.unit || "unit not supplied"}. ${points.length} of ${allPoints.length} sites are in this display focus; analysis uses the complete selected wafer. Blank areas remain unmeasured.`
    : `Each dot is one observed ${measurement.modality === "defect_coordinates" ? "defect-coordinate event" : "categorical die/bin observation"}. The display focus shows ${points.length} of ${allPoints.length} observed records; analysis uses the selected wafer. Blank areas remain unmeasured.`;
  const localizerIds = new Set((report.anomaly?.outliers || []).map(item => String(item.site_id)));
  for (const point of points.slice(0, 2000)) {
    const x = Number(point.x) - ox;
    const y = Number(point.y) - oy;
    const value = Number(point.value);
    const fill = Number.isFinite(value)
      ? `rgb(${Math.round(29 + 174 * (max === min ? 0.5 : (value - min) / (max - min)))},92,${Math.round(183 - 125 * (max === min ? 0.5 : (value - min) / (max - min)))})`
      : categoryColors[Math.max(0, cats.indexOf(String(point.category ?? point.bin ?? "defect event"))) % categoryColors.length];
    const circle = nodeSvg("circle", { cx: 250 + x * scale, cy: 250 - y * scale, r: 5, fill, stroke: "#17384c", "stroke-width": 1,
      "data-site-id": point.site_id ?? "", tabindex: 0, role: "img", class: localizerIds.has(String(point.site_id)) ? "anomaly-outline" : "" });
    const label = Number.isFinite(value) ? value : String(point.category ?? point.bin ?? "defect event");
    circle.append(nodeSvg("title", {}, `${point.site_id ?? "measured site"}: (${point.x}, ${point.y}) = ${label}`));
    svg.append(circle);
  }
  desc.textContent = `${Math.min(points.length, 2000)} measured sites shown in ${focus === "all" ? "whole-wafer" : focus} view. No values are drawn between sites. Outlined dots localize a wafer-level anomaly signal and are not individually significant.`;
  const table = document.createElement("table");
  const head = document.createElement("thead");
  const heading = document.createElement("tr");
  ["Site", "X", "Y", numeric.length ? measurement.metric || "Value" : "Category"].forEach(label => heading.append(node("th", label)));
  head.append(heading); table.append(head);
  const body = document.createElement("tbody");
  for (const [index, point] of points.slice(0, 250).entries()) {
    const row = document.createElement("tr");
    [point.site_id ?? `site-${index + 1}`, point.x, point.y, Number.isFinite(Number(point.value)) ? point.value : point.category ?? point.bin ?? "defect event"]
      .forEach(value => row.append(node("td", String(value))));
    body.append(row);
  }
  table.append(body);
  const wrapper = document.getElementById("site-table");
  wrapper.replaceChildren(table);
  if (points.length > 250) wrapper.append(node("p", `Showing first 250 of ${points.length} sites in this view.`, "muted"));
  if (points.length > 2000) wrapper.append(node("p", `The map displays first 2,000 of ${points.length} sites in this view.`, "muted"));
}

function nodeSvg(tag, attributes, text) {
  const element = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const [key, value] of Object.entries(attributes)) element.setAttribute(key, String(value));
  if (text !== undefined) element.textContent = text;
  return element;
}

function loadDocument(data, message) {
  loadedDocument = data;
  input.value = JSON.stringify(data, null, 2);
  populateMapSelector(data);
  const map = selectedMap(data);
  renderMap(map, {}, regionSelect.value);
  clearResults();
  setMessage(message);
}

async function loadExample() {
  setMessage("Loading local synthetic example…");
  try {
    const response = await fetch("/api/example", { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    loadDocument(await response.json(), "Synthetic example loaded locally. No external network request was made.");
  } catch (error) {
    setMessage(`Could not load the local example: ${error.message}`, true);
  }
}

async function runAnalysis() {
  analyzeButton.disabled = true;
  cancelButton.disabled = false;
  downloadButton.disabled = true;
  setMessage("Analyzing locally…");
  try {
    const source = JSON.parse(input.value);
    if (!source || Array.isArray(source) || typeof source !== "object") throw new Error("Input must be a JSON object.");
    loadedDocument = source;
    populateMapSelector(source);
    const data = selectedInvestigation(source);
    if (!data.coordinates_verified) throw new Error("The selected map must carry verified coordinate metadata before analysis.");
    const requestId = crypto.randomUUID();
    const controller = new AbortController();
    activeAnalysis = { requestId, controller };
    const response = await fetch("/api/analyze", {
      method: "POST", headers: { "Content-Type": "application/json", "X-Analysis-Id": requestId },
      body: JSON.stringify(data), signal: controller.signal
    });
    const evidence = await response.json();
    if (response.status === 409 && evidence.status === "CANCELLED") {
      setMessage("Analysis cancelled. The local worker stopped.");
      return;
    }
    if (!response.ok) throw new Error(evidence.error || `HTTP ${response.status}`);
    lastEvidence = evidence;
    document.getElementById("evidence").textContent = JSON.stringify(evidence, null, 2);
    const badge = document.getElementById("badge");
    badge.textContent = evidence.status;
    badge.dataset.state = evidence.status;
    renderClaims(evidence);
    renderProvenance(evidence);
    const report = evidence.artifacts?.find(item => item.kind === "p3_analysis")?.result || {};
    renderCapabilities(report);
    renderSpatialSummary(report.fingerprint);
    renderHistory(report);
    renderEvolution(report);
    renderQuality(report);
    renderMap(selectedMap(source), report, regionSelect.value);
    downloadButton.disabled = false;
    setMessage(`Completed · investigation ${evidence.investigation_id}`);
  } catch (error) {
    if (error.name === "AbortError") setMessage("Analysis cancelled. The local worker stop was requested.");
    else setMessage(error instanceof SyntaxError ? "Input is not valid JSON. Correct it and retry." : error.message, true);
  } finally {
    activeAnalysis = null;
    cancelButton.disabled = true;
    analyzeButton.disabled = false;
  }
}

async function cancelAnalysis() {
  if (!activeAnalysis) return;
  cancelButton.disabled = true;
  setMessage("Stopping the local analysis…");
  try {
    await fetch("/api/cancel", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ request_id: activeAnalysis.requestId }) });
  } catch (_) {
    // Aborting the browser request still releases the UI if the server exits.
  }
  activeAnalysis.controller.abort();
}

document.getElementById("map-file").addEventListener("change", async event => {
  const file = event.target.files?.[0];
  if (!file) return;
  if (file.size > 10 * 1024 * 1024) {
    setMessage("File exceeds the 10 MiB limit.", true);
    event.target.value = "";
    return;
  }
  try {
    const data = JSON.parse(await file.text());
    if (!data || Array.isArray(data) || typeof data !== "object") throw new Error("JSON content must be an object.");
    loadDocument(data, `Loaded ${file.name}. Select a measured wafer and run the local investigation.`);
  } catch (error) {
    setMessage(`Could not read the JSON file: ${error.message}`, true);
  }
});

waferSelect.addEventListener("change", () => {
  if (!loadedDocument) return;
  renderMap(selectedMap(loadedDocument), {}, regionSelect.value);
  clearResults("Selected wafer changed. Run analysis to refresh the evidence.");
});
regionSelect.addEventListener("change", () => {
  try {
    const data = JSON.parse(input.value);
    if (data && typeof data === "object" && !Array.isArray(data)) renderMap(selectedMap(data), {}, regionSelect.value);
  } catch (_) {
    // Keep the previous map view until the edited JSON is valid.
  }
});
document.getElementById("example").addEventListener("click", loadExample);
analyzeButton.addEventListener("click", runAnalysis);
cancelButton.addEventListener("click", cancelAnalysis);
downloadButton.addEventListener("click", () => {
  if (!lastEvidence) return;
  const blob = new Blob([JSON.stringify(lastEvidence, null, 2) + "\n"], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `${lastEvidence.investigation_id}.json`;
  anchor.click();
  URL.revokeObjectURL(url);
});
loadExample();
