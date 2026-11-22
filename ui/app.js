"use strict";

const input = document.getElementById("input-json");
const analyzeButton = document.getElementById("analyze");
const cancelButton = document.getElementById("cancel");
const downloadButton = document.getElementById("download");
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
      if (Array.isArray(item.source_ids) && item.source_ids.length) {
        claim.append(node("small", `Sources: ${item.source_ids.join(", ")}`));
      }
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
  } else {
    root.append(node("p", "No source identifier was included in the synthetic input."));
  }
  const assumptions = Array.isArray(evidence.assumptions) ? evidence.assumptions : [];
  const assumptionList = node("ul");
  for (const assumption of assumptions) assumptionList.append(node("li", assumption));
  root.append(node("strong", "Assumptions"), assumptionList);
}

function renderMap(data) {
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
  const points = Array.isArray(data.points) ? data.points.filter(p => p && Number.isFinite(Number(p.x)) && Number.isFinite(Number(p.y)) && Number.isFinite(Number(p.value))) : [];
  if (!(radius > 0) || !points.length) {
    desc.textContent = "No valid measured points are available to draw.";
    svg.append(nodeSvg("text", { x: 250, y: 250, "text-anchor": "middle", fill: "#526677" }, "No measured sites"));
    document.getElementById("site-table").replaceChildren(node("p", "No measured sites to list.", "muted"));
    return;
  }
  const scale = 190 / radius;
  svg.append(nodeSvg("circle", { cx: 250, cy: 250, r: 190, fill: "#fbfcfd", stroke: "#416276", "stroke-width": 2 }));
  svg.append(nodeSvg("line", { x1: 60, y1: 250, x2: 440, y2: 250, stroke: "#d9e1e6", "stroke-width": 1 }));
  svg.append(nodeSvg("line", { x1: 250, y1: 60, x2: 250, y2: 440, stroke: "#d9e1e6", "stroke-width": 1 }));
  let min = Infinity;
  let max = -Infinity;
  for (const point of points) {
    const value = Number(point.value);
    if (value < min) min = value;
    if (value > max) max = value;
  }
  const measurement = data.measurement && typeof data.measurement === "object" ? data.measurement : {};
  const valueUnit = measurement.unit || "unit not supplied";
  document.querySelector(".legend").textContent = `Each dot is one measured point. Color ranges from ${min} to ${max} ${valueUnit}; the table lists measured coordinates and values. The circle marks wafer geometry. No values are assigned to unmeasured locations.`;
  for (const point of points.slice(0, 2000)) {
    const x = Number(point.x) - ox;
    const y = Number(point.y) - oy;
    const fraction = max === min ? 0.5 : (Number(point.value) - min) / (max - min);
    const red = Math.round(29 + 174 * fraction);
    const blue = Math.round(183 - 125 * fraction);
    const circle = nodeSvg("circle", { cx: 250 + x * scale, cy: 250 - y * scale, r: 5, fill: `rgb(${red},92,${blue})`, stroke: "#17384c", "stroke-width": 1 });
    circle.append(nodeSvg("title", {}, `${point.site_id ?? "measured site"}: (${point.x}, ${point.y}) = ${point.value}`));
    svg.append(circle);
  }
  desc.textContent = `${Math.min(points.length, 2000)} measured sites shown. No values are drawn between sites.`;
  const table = document.createElement("table");
  const head = document.createElement("thead");
  const hr = document.createElement("tr");
  for (const label of ["Site", "X", "Y", "Value"]) hr.append(node("th", label));
  head.append(hr);
  table.append(head);
  const body = document.createElement("tbody");
  for (const [index, p] of points.slice(0, 250).entries()) {
    const row = document.createElement("tr");
    for (const value of [p.site_id ?? `site-${index + 1}`, p.x, p.y, p.value]) row.append(node("td", String(value)));
    body.append(row);
  }
  table.append(body);
  const wrapper = document.getElementById("site-table");
  wrapper.replaceChildren(table);
  if (points.length > 250) wrapper.append(node("p", `Showing first 250 of ${points.length} measured sites in the table.`, "muted"));
  if (points.length > 2000) wrapper.append(node("p", `The map displays first 2,000 of ${points.length} measured sites.`, "muted"));
}

function nodeSvg(tag, attributes, text) {
  const element = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const [key, value] of Object.entries(attributes)) element.setAttribute(key, String(value));
  if (text !== undefined) element.textContent = text;
  return element;
}

async function loadExample() {
  setMessage("Loading local synthetic example…");
  try {
    const response = await fetch("/api/example", { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    input.value = JSON.stringify(data, null, 2);
    renderMap(data);
    setMessage("Synthetic example loaded locally. No external network request was made.");
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
    const data = JSON.parse(input.value);
    if (!data || Array.isArray(data) || typeof data !== "object") throw new Error("Input must be a JSON object.");
    const requestId = crypto.randomUUID();
    const controller = new AbortController();
    activeAnalysis = { requestId, controller };
    const response = await fetch("/api/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Analysis-Id": requestId },
      body: JSON.stringify(data),
      signal: controller.signal
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
    const report = evidence.artifacts?.find(a => a.kind === "p3_analysis")?.result || {};
    renderCapabilities(report);
    renderMap(data);
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
    await fetch("/api/cancel", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ request_id: activeAnalysis.requestId })
    });
  } catch (_) {
    // Aborting the browser request below still releases the UI if the server exits.
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
    const raw = await file.text();
    const data = JSON.parse(raw);
    if (!data || Array.isArray(data) || typeof data !== "object") throw new Error("JSON content must be an object.");
    input.value = JSON.stringify(data, null, 2);
    renderMap(data);
    setMessage(`Loaded ${file.name} into this browser. Press Analyze to run locally.`);
  } catch (error) {
    setMessage(`Could not read JSON file: ${error.message}`, true);
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
