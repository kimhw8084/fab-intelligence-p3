"""Exercise P3's module with the current P1 spatial schema and renderer.

The generated Vitest file and temporary dependency symlink are removed after
the run. The P1 snapshot is read-only and is not copied into the P3 package.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess  # nosec B404
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
P1_ROOT = Path(os.environ.get("FAB_P1_TOOLCHAIN_ROOT", ROOT.parents[1] / "product 1" / "FAB_INTELLIGENCE_P1_CODEX_LAUNCHKIT_2026-11-22"))
EVIDENCE = ROOT / "release" / "P1_MODULE_INTEGRATION_EVIDENCE.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def integration_test_source(p3_module: str, diagnostic_path: Path, mcp_result_path: Path) -> str:
    template = '''import React from "react";
import { readFileSync, writeFileSync } from "node:fs";
import { render, screen, within } from "@testing-library/react";
import { afterAll, afterEach, describe, expect, it, vi } from "vitest";
import { SuiteSpatialMapRenderer, validateSpatialMap } from "./SharedVisualizations";
import { suiteMapFromP3Input } from "./suiteSpatialMap";
import { P3Panel, type P3Evidence, type P3SourcePreview } from __P3_MODULE__;

const capture = vi.hoisted(() => {
  const options: unknown[] = [];
  const chart = {
    setOption: vi.fn((option: unknown) => { options.push(option); }),
    convertToPixel: vi.fn((_axis: unknown, point: number[]) => [100 + point[0], 100 - point[1]]),
    getWidth: vi.fn(() => 400), getHeight: vi.fn(() => 400),
    resize: vi.fn(), dispose: vi.fn(),
  };
  return { chart, options };
});
vi.mock("echarts/core", () => ({ init: vi.fn(() => capture.chart), use: vi.fn() }));

const sourcePreview: P3SourcePreview = { status: "SYNTHETIC_ONLY", permission: "No company source", semantic_version: "SYN-1",
  grain: "wafer site", metric: "film_thickness", unit: "nm", scope: "P1 integration fixture", time_window: "fixed synthetic window" };
const evidence: P3Evidence = { status: "VALID", investigation_id: "SYN-P3-P1-INTEGRATION", claims: [], limitations: ["Synthetic fixture only."],
  artifacts: [{ kind: "p3_analysis", result: { fingerprint: { status: "VALID" }, evolution: { status: "INCONCLUSIVE" }, quality_association: { status: "INCONCLUSIVE" }, anomaly: { status: "INCONCLUSIVE" }, similarity: { status: "INCONCLUSIVE" } } }] };
const mcpModule = JSON.parse(readFileSync(__MCP_RESULT_PATH__, "utf8")) as {
  product_id: string; contract_version: string; capabilities: string[]; source_preview: P3SourcePreview;
  evidence: P3Evidence & {provenance?: NonNullable<P3Evidence["provenance"]> & {mcp_workflow?: {bounded_reads?: unknown[]}}};
  spatial_map: import(__P3_MODULE__).P3WaferMap;
};
const p3Input = { wafer_id: "SYN-W-01", coordinates_verified: true,
  geometry: { coordinate_system: "wafer_xy_v1", coordinate_unit: "mm", origin: { x: 0, y: 0 }, radius: 1, orientation_deg: 15 },
  measurement: { metric: "film_thickness", unit: "nm", modality: "continuous" },
  sampling_mask_id: "SYN-MASK-01", sampling: { expected_site_count: 4 },
  points: [{ site_id: "center", x: 0, y: 0, value: 10 }, { site_id: "edge", x: 0.8, y: 0, value: 12 }, { site_id: "missing", x: 0, y: 0.7, value: null }] };

describe("P3 module against the P1 shared renderer", () => {
  afterEach(() => { capture.options.length = 0; vi.clearAllMocks(); });
  afterAll(() => {
    const global = globalThis as { __p3HostDiagnostic?: unknown; __p3CategoryDiagnostic?: unknown; __p3McpDiagnostic?: unknown };
    writeFileSync(__P3_DIAGNOSTIC_PATH__, JSON.stringify({renderer: global.__p3HostDiagnostic ?? null,
      category: global.__p3CategoryDiagnostic ?? null, mcp_host_module: global.__p3McpDiagnostic ?? null}));
  });
  it("mounts the P1 wafer renderer and preserves each supplied site in the accessible table", () => {
    const map = suiteMapFromP3Input(p3Input);
    expect(map).not.toBeNull();
    expect(validateSpatialMap(map!)).toBeNull();
    render(<P3Panel sourcePreview={{...sourcePreview, coverage: {observed_sites: 3}}} evidence={{...evidence, sources: [{id: "SYN-MAP", source_hash: "abc", grain: "wafer site"}]}} waferMap={map!} renderWaferMap={model => <SuiteSpatialMapRenderer model={model} />} />);
    expect(screen.getByRole("img", {name: /Observed wafer map for SYN-W-01/})).toBeTruthy();
    const table = screen.getByRole("table", {name: /film_thickness \\(nm\\) on wafer SYN-W-01/});
    expect(within(table).getAllByRole("row")).toHaveLength(4);
    expect(within(table).getByRole("rowheader", {name: "missing"})).toBeTruthy();
    expect(within(table).getByText("Missing")).toBeTruthy();
    const renderOption = capture.options.find((option) => option && typeof option === "object" && "series" in option) as {series: Array<{data: unknown[]}>; visualMap?: {seriesIndex?: number}} | undefined;
    expect(renderOption).toBeTruthy();
    const diagnostic = {
      module_mounted: true,
      suite_renderer_validated_map: true,
      input_points: map!.points.length,
      rendered_numeric_points: renderOption!.series[0].data.length,
      rendered_missing_points: renderOption!.series[1].data.length,
      interpolation: map!.interpolation,
      numeric_color_series_index: renderOption!.visualMap?.seriesIndex,
      expected_numeric_color_series_index: 0,
    };
    (globalThis as { __p3HostDiagnostic?: unknown }).__p3HostDiagnostic = diagnostic;
  });
  it("reports whether the P1 input converter preserves categorical site values", () => {
    const categoricalInput = {...p3Input, measurement: {...p3Input.measurement, modality: "die_bin_categorical"},
      points: [{site_id: "die-1", x: 0.1, y: 0.1, category: "BIN-A"}, {site_id: "die-2", x: 0.2, y: 0.1, category: 2}]};
    const categorical = suiteMapFromP3Input(categoricalInput as unknown as Record<string, unknown>);
    const explicitMissingInput = {...p3Input, points: [{site_id: "numeric-missing", x: 0.1, y: 0.1, value: null}]};
    const explicitMissing = suiteMapFromP3Input(explicitMissingInput as unknown as Record<string, unknown>);
    const defects = suiteMapFromP3Input({...p3Input, measurement: {...p3Input.measurement, modality: "defect_coordinates"},
      points: [{site_id: "defect-1", x: 0.1, y: 0.1, category: "BRIDGE"}]} as unknown as Record<string, unknown>);
    const defectCode = suiteMapFromP3Input({...p3Input, measurement: {...p3Input.measurement, modality: "defect_coordinates"},
      points: [{site_id: "defect-code", x: 0.1, y: 0.1, category: 7}]} as unknown as Record<string, unknown>);
    const unlabeledDefect = suiteMapFromP3Input({...p3Input, measurement: {...p3Input.measurement, modality: "defect_coordinates"},
      points: [{site_id: "defect-event", x: 0.1, y: 0.1}]} as unknown as Record<string, unknown>);
    const numericString = suiteMapFromP3Input({...p3Input, points: [{site_id: "numeric-text", x: 0.1, y: 0.1, value: "12"}]} as unknown as Record<string, unknown>);
    const diagnostic = {
      string_category_preserved: categorical?.points[0]?.value === "BIN-A",
      numeric_category_type_preserved: typeof categorical?.points[1]?.value === "number" && categorical.points[1].value === 2,
      explicit_missing_preserved: explicitMissing?.points[0]?.value === null && explicitMissing.sampling.explicit_missing_value_count === 1,
      defect_category_preserved: defects?.points[0]?.value === "BRIDGE",
      defect_numeric_category_type_preserved: typeof defectCode?.points[0]?.value === "number" && defectCode.points[0].value === 7,
      unlabeled_defect_not_counted_as_missing: unlabeledDefect?.sampling.explicit_missing_value_count === 0,
      numeric_string_refused: numericString === null,
      input_point_count: categoricalInput.points.length,
      output_point_count: categorical?.points.length ?? null,
      interpolation: categorical?.interpolation ?? null,
    };
    (globalThis as { __p3CategoryDiagnostic?: unknown }).__p3CategoryDiagnostic = diagnostic;
    expect(diagnostic).toEqual({string_category_preserved: true, numeric_category_type_preserved: true,
      explicit_missing_preserved: true, defect_category_preserved: true, defect_numeric_category_type_preserved: true,
      unlabeled_defect_not_counted_as_missing: true, numeric_string_refused: true,
      input_point_count: 2, output_point_count: 2, interpolation: "none"});
  });
  it("mounts an official-SDK MCP result in the P3 panel and P1 renderer, then exports its unchanged evidence", () => {
    expect(mcpModule.product_id).toBe("p3");
    expect(mcpModule.contract_version).toBe("suite-ui-module.v1");
    expect(mcpModule.capabilities).toEqual(["C01", "C02", "C03", "C04", "C05"]);
    const onExportEvidence = vi.fn();
    render(<P3Panel sourcePreview={mcpModule.source_preview} evidence={mcpModule.evidence} waferMap={mcpModule.spatial_map}
      onExportEvidence={onExportEvidence} renderWaferMap={model => <SuiteSpatialMapRenderer model={model} />} />);
    const table = screen.getByRole("table", {name: /film_thickness \\(nm\\) on wafer SYN-W-CURRENT/});
    expect(within(table).getAllByRole("row")).toHaveLength(mcpModule.spatial_map.points.length + 1);
    expect(mcpModule.spatial_map.sampling.observed_site_count).toBe(mcpModule.spatial_map.points.length);
    expect(screen.getByRole("img", {name: /Observed wafer map for SYN-W-CURRENT/})).toBeTruthy();
    expect(screen.getByText(/Input SHA-256:/)).toBeTruthy();
    screen.getByRole("button", {name: "Export evidence"}).click();
    expect(onExportEvidence).toHaveBeenCalledOnce();
    expect(onExportEvidence).toHaveBeenCalledWith(mcpModule.evidence);
    const renderOption = capture.options.find((option) => option && typeof option === "object" && "series" in option) as {series: Array<{data: unknown[]}>} | undefined;
    expect(renderOption?.series[0].data).toHaveLength(5);
    (globalThis as {__p3McpDiagnostic?: unknown}).__p3McpDiagnostic = {
      protocol_result_mounted: true, evidence_status: mcpModule.evidence.status,
      current_source: mcpModule.evidence.sources?.find(source => source.id === "MOCK_MAP")?.id,
      bounded_reads: mcpModule.evidence.provenance?.mcp_workflow?.bounded_reads?.length,
      input_points: mcpModule.spatial_map.points.length, accessible_table_site_rows: within(table).getAllByRole("row").length - 1,
      plotted_numeric_points: renderOption?.series[0].data.length, evidence_export_callback_unchanged: onExportEvidence.mock.calls[0]?.[0] === mcpModule.evidence,
    };
  });
  it("withholds invalid or unverified spatial models", () => {
    const valid = suiteMapFromP3Input(p3Input)!;
    expect(validateSpatialMap({...valid, coordinates_verified: false})).toContain("not verified");
    expect(validateSpatialMap({...valid, geometry: {...valid.geometry, orientation_deg: null}})).toContain("orientation");
    expect(validateSpatialMap({...valid, points: [...valid.points, {site_id: "unmeasured", x: 0.2, y: 0.2, value: 0}]})).toContain("point count");
  });
});
'''
    return (template.replace("__P3_MODULE__", json.dumps(p3_module))
            .replace("__P3_DIAGNOSTIC_PATH__", json.dumps(str(diagnostic_path)))
            .replace("__MCP_RESULT_PATH__", json.dumps(str(mcp_result_path))))


def generate_mcp_host_result(destination: Path) -> dict[str, object]:
    """Run the product's hash-locked official SDK against its synthetic peer."""
    bundle = ROOT / "vendor" / "mcp-sdk-2.3.0" / "macos-arm64-cp311"
    lock = bundle / "requirements.lock"
    wheelhouse = bundle / "wheelhouse"
    if not lock.is_file() or not wheelhouse.is_dir():
        return {"status": "NOT_RUN_MISSING_BUNDLE"}
    with tempfile.TemporaryDirectory(prefix="p3-mcp-host-fixture-") as temp:
        venv = Path(temp) / "venv"
        python = venv / "bin" / "python"
        env = {**os.environ, "PIP_NO_INDEX": "1", "PIP_DISABLE_PIP_VERSION_CHECK": "1", "PYTHONDONTWRITEBYTECODE": "1"}
        steps = [
            [sys.executable, "-m", "venv", str(venv)],
            [str(python), "-m", "pip", "install", "--no-index", "--disable-pip-version-check", "--find-links", str(wheelhouse), "--require-hashes", "-r", str(lock)],
            [str(python), "-m", "pip", "check"],
            [str(python), "qualification/build_synthetic_mcp_host_result.py", str(destination)],
        ]
        outputs = []
        for command in steps:
            run = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True, timeout=180, check=False)  # nosec B603
            outputs.append({"command": [Path(command[0]).name, *command[1:]], "exit_code": run.returncode,
                            "output": (run.stdout + run.stderr)[-5000:]})
            if run.returncode:
                destination.unlink(missing_ok=True)
                return {"status": "FAIL", "steps": outputs}
    return {"status": "PASS", "target": "macos-arm64-cp311-offline-wheelhouse", "steps": outputs,
            "fixture_sha256": sha256(destination), "fixture_bytes": destination.stat().st_size}


def main() -> int:
    p1_schema = P1_ROOT / "contracts" / "suite-ui-module.v1.schema.json"
    spatial_schema = P1_ROOT / "contracts" / "suite-spatial-map.v1.schema.json"
    p1_manifest = P1_ROOT / "products" / "p3" / "ui_contribution.json"
    p1_renderer = P1_ROOT / "products" / "p1" / "ui" / "SharedVisualizations.tsx"
    p1_spatial = P1_ROOT / "products" / "p1" / "ui" / "suiteSpatialMap.ts"
    p1_suite = P1_ROOT / "products" / "p1" / "ui" / "SuiteHost.tsx"
    p1_entry = P1_ROOT / "products" / "p1" / "ui" / "main.tsx"
    p1_engine = P1_ROOT / "products" / "p3" / "engine.py"
    p1_fixture = P1_ROOT / "fixtures" / "p3" / "p3_integrated_synthetic.json"
    p1_panel = P1_ROOT / "products" / "p3" / "ui" / "P3Panel.tsx"
    p3_engine = ROOT / "products" / "p3" / "engine.py"
    p3_fixture = ROOT / "fixtures" / "p3_integrated_synthetic.json"
    p3_panel = ROOT / "products" / "p3" / "ui" / "P3Panel.tsx"
    node = shutil.which("node")
    modules = P1_ROOT / "node_modules"
    result: dict[str, object] = {
        "state": "CANDIDATE",
        "p1_snapshot_revision": "UNAVAILABLE_NO_COMMIT_IN_LOCAL_SNAPSHOT",
        "p1_contracts": {},
        "p1_suite_shell_available": p1_suite.is_file() and p1_entry.is_file(),
        "p1_suite_shell_files": [str(path.relative_to(P1_ROOT)) for path in (p1_suite, p1_entry) if path.is_file()],
        "p1_suite_route": "/fab-intelligence/p3" if p1_suite.is_file() and p1_entry.is_file() else None,
        "p3_source_snapshot": {
            "p3_engine_sha256": sha256(p3_engine), "p1_engine_sha256": sha256(p1_engine) if p1_engine.is_file() else None,
            "p3_fixture_sha256": sha256(p3_fixture), "p1_fixture_sha256": sha256(p1_fixture) if p1_fixture.is_file() else None,
            "p3_panel_sha256": sha256(p3_panel), "p1_panel_sha256": sha256(p1_panel) if p1_panel.is_file() else None,
            "engine_matches": p1_engine.is_file() and sha256(p1_engine) == sha256(p3_engine),
            "fixture_matches": p1_fixture.is_file() and sha256(p1_fixture) == sha256(p3_fixture),
            "panel_matches": p1_panel.is_file() and sha256(p1_panel) == sha256(p3_panel),
        },
    }
    required = (p1_schema, spatial_schema, p1_manifest, p1_renderer, p1_spatial)
    if not all(path.is_file() for path in required) or not node or not (modules / "vitest" / "vitest.mjs").is_file():
        result["status"] = "NOT_RUN_P1_CONTRACT_OR_TOOLCHAIN_MISSING"
        EVIDENCE.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps(result, indent=2))
        return 0

    p3_manifest = json.loads((ROOT / "integration" / "p3-suite-ui-module.v1.json").read_text(encoding="utf-8"))
    current_p1_manifest = json.loads(p1_manifest.read_text(encoding="utf-8"))
    contract_checks = {"p3_module_against_p1_schema": False, "p1_registered_module_against_p1_schema": False,
                       "registrations_match": p3_manifest == current_p1_manifest,
                       "p3_spatial_model_against_p1_schema": False}
    try:
        import jsonschema
        module_schema = json.loads(p1_schema.read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator(module_schema).validate(p3_manifest)
        jsonschema.Draft202012Validator(module_schema).validate(current_p1_manifest)
        spatial_sample = {
            "schema_version": "suite-spatial-map.v1", "wafer_id": "SYN-W-01", "coordinates_verified": True,
            "coordinate_unit": "mm", "metric": "film_thickness", "measurement_unit": "nm",
            "geometry": {"coordinate_system": "wafer_xy_v1", "origin": {"x": 0, "y": 0}, "radius": 1, "orientation_deg": 15},
            "sampling": {"mask_id": "SYN-MASK-01", "observed_site_count": 3, "expected_site_count": 4,
                         "coverage_fraction": 0.75, "explicit_missing_value_count": 1,
                         "coverage_basis": "DECLARED_EXPECTED_SITE_COUNT", "missing_site_ids": ["missing"]},
            "points": [{"site_id": "center", "x": 0, "y": 0, "value": 10},
                       {"site_id": "edge", "x": 0.8, "y": 0, "value": 12},
                       {"site_id": "missing", "x": 0, "y": 0.7, "value": None}],
            "interpolation": "none",
        }
        jsonschema.Draft202012Validator(json.loads(spatial_schema.read_text(encoding="utf-8"))).validate(spatial_sample)
        contract_checks["p3_module_against_p1_schema"] = True
        contract_checks["p1_registered_module_against_p1_schema"] = True
        contract_checks["p3_spatial_model_against_p1_schema"] = True
    except ImportError:
        contract_checks["validator"] = "jsonschema package unavailable"
    result["p1_contracts"] = {
        "suite_ui_module_schema_sha256": sha256(p1_schema),
        "suite_spatial_map_schema_sha256": sha256(spatial_schema),
        "shared_renderer_sha256": sha256(p1_renderer),
        "p1_registration_sha256": sha256(p1_manifest),
        "checks": contract_checks,
    }
    if not all(contract_checks[key] for key in ("p3_module_against_p1_schema", "p1_registered_module_against_p1_schema", "registrations_match", "p3_spatial_model_against_p1_schema")):
        result["status"] = "FAIL_P1_CONTRACT_COMPATIBILITY"
        EVIDENCE.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps(result, indent=2))
        return 1

    test_directory = P1_ROOT / "products" / "p1" / "ui"
    generated = test_directory / "__p3_host_integration.generated.test.tsx"
    if generated.exists():
        result["status"] = "NOT_RUN_TEMP_TEST_PATH_ALREADY_EXISTS"
        EVIDENCE.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps(result, indent=2))
        return 1
    relative_module = os.path.relpath(ROOT / "products" / "p3" / "ui" / "P3Panel.tsx", test_directory).replace(os.sep, "/")
    if not relative_module.startswith("."):
        relative_module = "./" + relative_module
    relative_module = relative_module.removesuffix(".tsx")
    diagnostic_path = ROOT / "release" / ".p1_host_diagnostic.tmp.json"
    mcp_result_path = ROOT / "release" / ".p1_mcp_host_result.tmp.json"
    if diagnostic_path.exists():
        result["status"] = "NOT_RUN_TEMP_DIAGNOSTIC_PATH_ALREADY_EXISTS"
        EVIDENCE.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps(result, indent=2))
        return 1
    if mcp_result_path.exists():
        result["status"] = "NOT_RUN_TEMP_MCP_RESULT_PATH_ALREADY_EXISTS"
        EVIDENCE.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps(result, indent=2))
        return 1
    mcp_fixture = generate_mcp_host_result(mcp_result_path)
    result["mcp_to_module_fixture"] = mcp_fixture
    if mcp_fixture.get("status") != "PASS":
        result["status"] = "FAIL_SYNTHETIC_MCP_TO_MODULE_FIXTURE"
        EVIDENCE.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps(result, indent=2))
        return 1
    generated.write_text(integration_test_source(relative_module, diagnostic_path, mcp_result_path), encoding="utf-8")
    node_modules_link = ROOT / "node_modules"
    link_created = False
    if not node_modules_link.exists() and not node_modules_link.is_symlink():
        node_modules_link.symlink_to(modules, target_is_directory=True)
        link_created = True
    try:
        vitest = subprocess.run([node, str(modules / "vitest" / "vitest.mjs"), "run", "--config",  # nosec B603
            str(P1_ROOT / "vite.config.ts"), str(generated)], cwd=P1_ROOT, capture_output=True, text=True, timeout=60, check=False)
        tsc = subprocess.run([node, str(modules / "typescript" / "bin" / "tsc"), "--noEmit", "--strict",  # nosec B603
            "--esModuleInterop", "--jsx", "react-jsx", "--moduleResolution", "bundler", "--module", "esnext",
            "--target", "es2022", "--lib", "es2022,dom", "--skipLibCheck", str(generated)],
            cwd=P1_ROOT, capture_output=True, text=True, timeout=60, check=False)
    finally:
        generated.unlink(missing_ok=True)
        mcp_result_path.unlink(missing_ok=True)
        if link_created:
            node_modules_link.unlink(missing_ok=True)

    diagnostic_record = json.loads(diagnostic_path.read_text(encoding="utf-8")) if diagnostic_path.is_file() else {}
    diagnostic_path.unlink(missing_ok=True)
    diagnostics = diagnostic_record.get("renderer") or {}
    category = diagnostic_record.get("category") or {}
    mcp_host_module = diagnostic_record.get("mcp_host_module") or {}
    result["integration_test"] = {"vitest_exit_code": vitest.returncode, "vitest_output": (vitest.stdout + vitest.stderr)[-6000:],
                                   "typescript_exit_code": tsc.returncode, "typescript_output": (tsc.stdout + tsc.stderr)[-4000:],
                                   "renderer_diagnostic": diagnostics, "categorical_conversion_diagnostic": category,
                                   "mcp_host_module_diagnostic": mcp_host_module}
    p1_gaps = []
    source_snapshot = result["p3_source_snapshot"]
    for key, label in (("engine_matches", "P3 engine"), ("fixture_matches", "P3 synthetic fixture"), ("panel_matches", "P3 React module")):
        if not source_snapshot[key]:
            p1_gaps.append(f"P1 route snapshot does not match the current tested {label}; review and update its pinned P3 contribution before integrated qualification.")
    if diagnostics.get("numeric_color_series_index") != diagnostics.get("expected_numeric_color_series_index"):
        p1_gaps.append("P1 shared renderer assigns the quantitative visual map to the explicit-missing series when it exists; numeric series index must be 0.")
    category_gaps = []
    for key, message in (
        ("string_category_preserved", "string category value BIN-A"),
        ("numeric_category_type_preserved", "numeric categorical value 2 type"),
        ("explicit_missing_preserved", "explicit missing null value/count"),
        ("defect_category_preserved", "defect_coordinates category value"),
        ("defect_numeric_category_type_preserved", "numeric defect category type"),
        ("unlabeled_defect_not_counted_as_missing", "unlabeled defect event versus missing measurement"),
        ("numeric_string_refused", "rejection of numeric strings in continuous modality"),
    ):
        if not category.get(key):
            category_gaps.append(message)
    if category.get("input_point_count") != category.get("output_point_count"):
        category_gaps.append("exact input/output point count reconciliation")
    if category.get("interpolation") != "none":
        category_gaps.append("explicit no-interpolation contract")
    if category_gaps:
        p1_gaps.append("P1 TS adapter fails typed spatial acceptance cases: " + ", ".join(category_gaps) + ".")
    backend_gaps = []
    backend_probe = r'''
import json, sys
from fabintel.suite import _spatial_map
base = {"coordinates_verified": True, "wafer_id": "SYN-W", "geometry": {"radius": 1, "origin": {"x": 0, "y": 0}, "orientation_deg": 0, "coordinate_system": "wafer_xy_v1", "coordinate_unit": "mm"}, "sampling": {"expected_site_count": 3}}
cases = json.load(sys.stdin)
out = {}
for name, measurement, point in cases:
    data = {**base, "measurement": measurement, "points": [point]}
    result = _spatial_map("p3", data)
    value = result["points"][0]["value"] if result else None
    out[name] = {"value": value, "value_type": type(value).__name__, "missing_count": result["sampling"]["explicit_missing_value_count"] if result else None, "point_count": len(result["points"]) if result else None}
print(json.dumps(out, sort_keys=True))
'''
    backend_cases = [
        ["numeric", {"metric": "thickness", "unit": "nm", "modality": "continuous"}, {"site_id": "n", "x": 0, "y": 0, "value": 42.5}],
        ["numeric_string", {"metric": "thickness", "unit": "nm", "modality": "continuous"}, {"site_id": "ns", "x": 0, "y": 0, "value": "42.5"}],
        ["missing", {"metric": "thickness", "unit": "nm", "modality": "continuous"}, {"site_id": "m", "x": 0, "y": 0, "value": None}],
        ["category_string", {"metric": "bin", "unit": "category", "modality": "die_bin_categorical"}, {"site_id": "c", "x": 0, "y": 0, "category": "BIN-A"}],
        ["category_number", {"metric": "bin", "unit": "category", "modality": "die_bin_categorical"}, {"site_id": "cn", "x": 0, "y": 0, "category": 2}],
        ["defect_string", {"metric": "defect", "unit": "count", "modality": "defect_coordinates"}, {"site_id": "d", "x": 0, "y": 0, "category": "BRIDGE"}],
        ["defect_event", {"metric": "defect", "unit": "count", "modality": "defect_coordinates"}, {"site_id": "de", "x": 0, "y": 0}],
    ]
    try:
        backend_run = subprocess.run([sys.executable, "-c", backend_probe], cwd=P1_ROOT,  # nosec B603
            input=json.dumps(backend_cases), capture_output=True, text=True, timeout=30, check=False)
        backend = json.loads(backend_run.stdout) if backend_run.returncode == 0 else {}
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
        backend_run, backend = None, {}
    expected_backend = {"numeric": (42.5, "float", 0), "numeric_string": (None, None, None),
                        "missing": (None, "NoneType", 1), "category_string": ("BIN-A", "str", 0),
                        "category_number": (2, "int", 0), "defect_string": ("BRIDGE", "str", 0),
                        "defect_event": (None, "NoneType", 0)}
    for name, (expected_value, expected_type, expected_missing) in expected_backend.items():
        actual = backend.get(name, {})
        if (actual.get("value"), actual.get("value_type"), actual.get("missing_count")) != (expected_value, expected_type, expected_missing):
            backend_gaps.append(f"P1 Python API spatial adapter {name}: expected {(expected_value, expected_type, expected_missing)!r}, observed {(actual.get('value'), actual.get('value_type'), actual.get('missing_count'))!r}")
    if backend_run is None or backend_run.returncode != 0:
        backend_gaps.append("P1 Python API spatial adapter probe could not execute")
    if backend_gaps:
        p1_gaps.extend(backend_gaps)
    result["p1_host_owner_changes"] = p1_gaps
    result["p1_backend_value_diagnostic"] = backend
    result["p1_backend_probe_exit_code"] = backend_run.returncode if backend_run is not None else None
    result["integration_test"]["mcp_host_module_diagnostic"] = mcp_host_module
    result["status"] = ("PASS_P3_MODULE_MOUNTED_WITH_P1_SHARED_RENDERER" if vitest.returncode == 0 and tsc.returncode == 0 and not p1_gaps
                        else "PARTIAL_P1_SHARED_CONTRACT_CHANGES_REQUIRED" if p1_gaps and tsc.returncode == 0
                        else "FAIL_P3_P1_MODULE_INTEGRATION")
    EVIDENCE.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "module_vitest_exit_code": vitest.returncode,
                      "strict_typescript_exit_code": tsc.returncode, "renderer_diagnostic": diagnostics,
                      "categorical_conversion_diagnostic": category, "p1_host_owner_changes": p1_gaps,
                      "evidence": "release/P1_MODULE_INTEGRATION_EVIDENCE.json"}, indent=2))
    return 0 if vitest.returncode == 0 and tsc.returncode == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
