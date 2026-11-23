"""Record reproducible local candidate checks with synthetic-only evidence."""
from __future__ import annotations

import json
import os
import platform
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
P1_ROOT = ROOT.parents[1] / "product 1" / "FAB_INTELLIGENCE_P1_CODEX_LAUNCHKIT_2026-11-22"
from tree_hash import current_git_commit, source_tree_sha256
from mcp_sdk_offline import qualify_offline_mcp_sdk


def sanitize_text(value):
    text = str(value).replace(str(ROOT), "<P3>").replace(str(P1_ROOT), "<P1_TOOLCHAIN>")
    return re.sub(r"/var/folders/\S+/p3-mcp-offline-[^/\s]+", "<MCP_TEMP>", text)


def run(command):
    result = subprocess.run(command, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, timeout=180, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
    display = list(command)
    if display and Path(display[0]).is_absolute():
        display[0] = Path(display[0]).name
    return {"command": sanitize_text(" ".join(display)), "exit_code": result.returncode,
            "output": sanitize_text(result.stdout)}


def run_suite_panel_checks():
    configured = os.environ.get("FAB_P1_TOOLCHAIN_ROOT")
    p1_root = Path(configured) if configured else P1_ROOT
    node = shutil.which("node")
    p1_modules = p1_root / "node_modules"
    if not node or not (p1_modules / "vitest" / "vitest.mjs").is_file() or not (p1_modules / "typescript" / "bin" / "tsc").is_file():
        return {"status": "NOT_RUN_P1_TOOLCHAIN_NOT_STAGED", "tests": None}

    link = ROOT / "node_modules"
    if link.exists() or link.is_symlink():
        return {"status": "NOT_RUN_PRODUCT_NODE_MODULES_ALREADY_PRESENT", "tests": None}
    link.symlink_to(p1_modules, target_is_directory=True)
    try:
        panel_test = run([node, str(p1_modules / "vitest" / "vitest.mjs"), "run", "--config",
                          str(p1_root / "vite.config.ts"), str(ROOT / "products" / "p3" / "ui" / "P3Panel.test.tsx")])
        typecheck = run([node, str(p1_modules / "typescript" / "bin" / "tsc"), "--noEmit", "--strict", "--esModuleInterop",
                         "--jsx", "react-jsx", "--moduleResolution", "bundler", "--module", "esnext", "--target", "es2022",
                         "--lib", "es2022,dom", "--skipLibCheck", "products/p3/ui/P3Panel.tsx", "products/p3/ui/P3Panel.test.tsx"])
    finally:
        link.unlink()

    match = re.search(r"Tests\s+(\d+) passed", panel_test["output"])
    count = int(match.group(1)) if match else None
    node_version = subprocess.run([node, "--version"], cwd=ROOT, stdout=subprocess.PIPE,
                                  stderr=subprocess.STDOUT, text=True).stdout.strip()
    package = json.loads((p1_root / "package.json").read_text(encoding="utf-8"))
    engine = package.get("engines", {}).get("node", "")
    node_parts = tuple(int(value) for value in re.search(r"v?(\d+)\.(\d+)\.(\d+)", node_version).groups())
    compatible = False
    for clause in engine.split("||"):
        clause = clause.strip()
        minimum = re.search(r"(?:\^|>=)(\d+)\.(\d+)\.(\d+)", clause)
        if not minimum:
            continue
        required = tuple(int(value) for value in minimum.groups())
        if clause.startswith(">=") and node_parts >= required:
            compatible = True
        elif clause.startswith("^") and node_parts[0] == required[0] and node_parts >= required:
            compatible = True
    checks_pass = panel_test["exit_code"] == 0 and typecheck["exit_code"] == 0 and count is not None
    status = "PASS" if checks_pass and compatible else "PASS_WITH_TOOLCHAIN_VERSION_MISMATCH" if checks_pass else "FAIL"
    return {"status": status, "test_execution_status": "PASS" if checks_pass else "FAIL", "tests": count,
            "node_version": node_version, "p1_declared_node_engine": engine,
            "node_engine_qualified": compatible, "panel_test": panel_test, "typecheck": typecheck,
            "toolchain_owner": "P1 suite host; dependencies were not copied into P3"}


def main():
    test = run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"])
    demo = run([sys.executable, "-m", "fabintel", "demo"])
    pending = run([sys.executable, "-m", "fabintel", "qualify-internal"])
    panel = run_suite_panel_checks()
    mcp_sdk = qualify_offline_mcp_sdk(ROOT)
    test_count = None
    match = re.search(r"Ran (\d+) tests? in", test["output"])
    if match:
        test_count = int(match.group(1))
    try:
        demo_object = json.loads(demo["output"])
    except json.JSONDecodeError:
        demo_object = {}
    try:
        pending_object = json.loads(pending["output"])
    except json.JSONDecodeError:
        pending_object = {}
    checks = {
        "unit_suite": {"command": test["command"], "status": "PASS" if test["exit_code"] == 0 and test_count else "FAIL", "tests": test_count},
        "synthetic_demo": {"command": demo["command"], "status": "PASS" if demo["exit_code"] == 0 and demo_object.get("status") == "VALID" else "FAIL",
                           "investigation_id": demo_object.get("investigation_id"), "input_sha256": demo_object.get("provenance", {}).get("input_sha256")},
        "internal_preflight": {"command": pending["command"], "status": "PENDING_INTERNAL" if pending["exit_code"] == 0 and pending_object.get("state") == "PENDING_INTERNAL" else "FAIL",
                               "internal_ready": pending_object.get("internal_ready")},
        "suite_panel": panel,
        "mcp_sdk_candidate": mcp_sdk,
    }
    report = {
        "state": "CANDIDATE",
        "created_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "source_tree_sha256": source_tree_sha256(ROOT),
        "source_commit": current_git_commit(ROOT),
        "environment": {"os": platform.platform(), "architecture": platform.machine(), "python": sys.version,
                        "node": subprocess.run([shutil.which("node") or "node", "--version"], cwd=ROOT,
                                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True).stdout.strip()
                        if shutil.which("node") else None},
        "company_data_used": False,
        "checks": checks,
        "external_status": "CANDIDATE; suite host integration, target OS/network isolation, company supply-chain clearance, company MCP and engineer-study gates remain open.",
    }
    log_items = [test, demo, pending]
    if panel.get("panel_test"):
        log_items.extend((panel["panel_test"], panel["typecheck"]))
    for step in mcp_sdk.get("steps", []):
        log_items.append({"command": sanitize_text(" ".join(step["command"])), "exit_code": step["exit_code"],
                          "output": sanitize_text(step["output"])})
    log = "\n\n".join(f"$ {item['command']}\nexit={item['exit_code']}\n{item['output']}" for item in log_items)
    (ROOT / "release" / "LOCAL_TEST_LOG.txt").write_text(log, encoding="utf-8")
    (ROOT / "release" / "LOCAL_TEST_EVIDENCE.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    ui_evidence = {
        "state": "CANDIDATE",
        "module": "products/p3/ui/P3Panel.tsx",
        "contract": "suite-ui-module.v1",
        "integration_status": "PENDING_P1_SUITE_HOST_AND_SPATIAL_CHART_EXTENSION",
        "toolchain_owner": "P1 suite host",
        "component_tests": {"status": panel["status"], "passed": panel.get("tests"),
                             "node_version": panel.get("node_version"),
                             "p1_declared_node_engine": panel.get("p1_declared_node_engine"),
                             "node_engine_qualified": panel.get("node_engine_qualified", False)},
        "observed_checks": [
            "Source preview and synthetic-only mode render from host supplied props.",
            "C01-C05 status and evidence provenance are visible.",
            "Verified wafer sites delegate drawing to the injected shared renderer and remain available in a semantic table.",
            "Unverified coordinates and refused or inconclusive results withhold spatial rendering.",
            "Empty evidence remains pending without synthetic result fabrication.",
        ],
        "limitation": "No integrated suite host, production token package, real browser task walkthrough, formal accessibility audit, or engineer usability study was available.",
    }
    (ROOT / "release" / "LOCAL_UI_EVIDENCE.json").write_text(json.dumps(ui_evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"tests": test_count, "checks": checks, "source_tree_sha256": report["source_tree_sha256"]}, indent=2))
    if any(value == "FAIL" if isinstance(value, str) else value.get("status") == "FAIL" for value in checks.values()):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
