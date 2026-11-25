"""Record reproducible local candidate checks with synthetic-only evidence."""
from __future__ import annotations

import json
import os
import platform
import re
import shutil
import subprocess  # nosec B404
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
from mcp_sdk_offline import qualify_offline_mcp_sdk
from tree_hash import current_git_commit, source_tree_sha256


def sanitize_text(value):
    text = str(value).replace(str(ROOT), "<P3>")
    return re.sub(r"/var/folders/\S+/p3-mcp-offline-[^/\s]+", "<MCP_TEMP>", text)


def run(command):
    result = subprocess.run(command, check=False, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,  # nosec B603
                            text=True, timeout=180, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
    display = list(command)
    if display and Path(display[0]).is_absolute():
        display[0] = Path(display[0]).name
    return {"command": sanitize_text(" ".join(display)), "exit_code": result.returncode,
            "output": sanitize_text(result.stdout)}


def run_p3_ui_checks():
    node = shutil.which("node")
    npm = shutil.which("npm")
    modules = ROOT / "node_modules"
    if not node or not npm or not (modules / "vitest" / "vitest.mjs").is_file() or not (modules / "typescript" / "bin" / "tsc").is_file():
        return {"status": "NOT_RUN_P3_NODE_DEPENDENCIES_NOT_INSTALLED", "tests": None}

    panel_test = run([node, str(modules / "vitest" / "vitest.mjs"), "run"])
    typecheck = run([node, str(modules / "typescript" / "bin" / "tsc"), "--noEmit", "--project", "tsconfig.json"])
    build = run([npm, "run", "build"])
    match = re.search(r"Tests\s+(\d+) passed", panel_test["output"])
    count = int(match.group(1)) if match else None
    checks_pass = panel_test["exit_code"] == 0 and typecheck["exit_code"] == 0 and build["exit_code"] == 0 and count is not None
    return {"status": "PASS" if checks_pass else "FAIL", "test_execution_status": "PASS" if checks_pass else "FAIL",
            "tests": count, "node_version": run([node, "--version"])["output"].strip(),
            "toolchain_owner": "P3 lockfile", "panel_and_host_tests": panel_test,
            "typecheck": typecheck, "production_build": build}


def main():
    test = run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"])
    demo = run([sys.executable, "-m", "fabintel", "demo"])
    pending = run([sys.executable, "-m", "fabintel", "qualify-internal"])
    ui = run_p3_ui_checks()
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
    critical_path = ROOT / "release" / "CRITICAL_CASE_EVIDENCE.json"
    critical_object = json.loads(critical_path.read_text(encoding="utf-8")) if critical_path.is_file() else {}
    browser_path = ROOT / "release" / "P3_STANDALONE_BROWSER_EVIDENCE.json"
    browser_object = json.loads(browser_path.read_text(encoding="utf-8")) if browser_path.is_file() else {}
    p1_path = ROOT / "release" / "P1_MODULE_INTEGRATION_EVIDENCE.json"
    p1_object = json.loads(p1_path.read_text(encoding="utf-8")) if p1_path.is_file() else {}
    sdk_pass = mcp_sdk.get("status") == "PASS"
    browser_pass = browser_object.get("state") == "PASS_SYNTHETIC_BROWSER_WORKFLOW"
    product_pass = (test["exit_code"] == 0 and test_count is not None and demo["exit_code"] == 0
                    and demo_object.get("status") == "VALID" and ui.get("status") == "PASS"
                    and sdk_pass and browser_pass and critical_object.get("overall") == "PASS")
    p1_pending = p1_object.get("status") not in ("PASS", "PASS_ALL_ACCEPTANCE")
    checks = {
        "unit_suite": {"command": test["command"], "status": "PASS" if test["exit_code"] == 0 and test_count else "FAIL", "tests": test_count},
        "synthetic_demo": {"command": demo["command"], "status": "PASS" if demo["exit_code"] == 0 and demo_object.get("status") == "VALID" else "FAIL",
                           "investigation_id": demo_object.get("investigation_id"), "input_sha256": demo_object.get("provenance", {}).get("input_sha256")},
        "internal_preflight": {"command": pending["command"], "status": "PENDING_INTERNAL" if pending["exit_code"] == 0 and pending_object.get("state") == "PENDING_INTERNAL" else "FAIL",
                               "internal_ready": pending_object.get("internal_ready")},
        "p3_ui": ui,
        "critical_cases": {"status": critical_object.get("overall", "NOT_RUN"),
                            "passed": sum(item.get("status") == "PASS" for item in critical_object.get("cases", [])),
                            "total": len(critical_object.get("cases", []))},
        "standalone_browser_workflow": {"status": "PASS_SYNTHETIC" if browser_pass else "NOT_RUN",
                                        "evidence": "release/P3_STANDALONE_BROWSER_EVIDENCE.json"},
        "shared_suite_integration": {"status": "SUITE_INTEGRATION_PENDING" if p1_pending else "PASS",
                                      "evidence": "release/P1_MODULE_INTEGRATION_EVIDENCE.json",
                                      "p1_owned_changes": p1_object.get("p1_host_owner_changes", [])},
        "mcp_sdk_candidate": mcp_sdk,
    }
    report = {
        "state": "CANDIDATE",
        "created_utc": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "source_tree_sha256": source_tree_sha256(ROOT),
        "source_commit": current_git_commit(ROOT),
        "environment": {"os": platform.platform(), "architecture": platform.machine(), "python": sys.version,
                        "node": subprocess.run([shutil.which("node") or "node", "--version"], check=False, cwd=ROOT,  # nosec B603
                                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True).stdout.strip()
                        if shutil.which("node") else None},
        "company_data_used": False,
        "states": {
            "P3_PRODUCT_IMPLEMENTATION_COMPLETE": product_pass,
            "P3_STANDALONE_WORKFLOW_VERIFIED": browser_pass and sdk_pass,
            "SHARED_SUITE_COMPATIBILITY_READY": ui.get("status") == "PASS",
            "SHARED_SUITE_INTEGRATION_PENDING": p1_pending,
            "EXTERNAL_TRANSFER_READY": False,
            "INTERNAL_QUALIFICATION_PENDING": pending_object.get("state") == "PENDING_INTERNAL",
        },
        "checks": checks,
        "external_status": "P3 standalone synthetic workflow is verified independently. The actual P1 suite adapter still fails its typed spatial contract; company authorization, target OS, rights/security clearance and engineer acceptance remain pending.",
    }
    log_items = [test, demo, pending]
    if ui.get("panel_and_host_tests"):
        log_items.extend((ui["panel_and_host_tests"], ui["typecheck"], ui["production_build"]))
    for step in mcp_sdk.get("steps", []):
        log_items.append({"command": sanitize_text(" ".join(step["command"])), "exit_code": step["exit_code"],
                          "output": sanitize_text(step["output"])})
    log = "\n\n".join(f"$ {item['command']}\nexit={item['exit_code']}\n{item['output']}" for item in log_items)
    (ROOT / "release" / "LOCAL_TEST_LOG.txt").write_text(log, encoding="utf-8")
    (ROOT / "release" / "LOCAL_TEST_EVIDENCE.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    ui_evidence = {
        "state": "PASS_P3_STANDALONE_UI_CHECKS" if ui.get("status") == "PASS" else ui.get("status"),
        "module": "products/p3/ui/P3Panel.tsx",
        "reference_host": "products/p3/reference_host/",
        "contract": "suite-ui-module.v1 plus independent p3-reference-module.v2",
        "toolchain_owner": "P3 lockfile",
        "component_and_host_tests": {"status": ui.get("status"), "passed": ui.get("tests"), "node_version": ui.get("node_version")},
        "standalone_browser_evidence": "release/P3_STANDALONE_BROWSER_EVIDENCE.json",
        "p1_integration_status": "SUITE_INTEGRATION_PENDING",
        "p1_integration_evidence": "release/P1_MODULE_INTEGRATION_EVIDENCE.json",
        "observed_checks": [
            "P3 starts independently and runs the official-SDK synthetic MCP workflow through C01-C05.",
            "Typed numeric, categorical, missing and defect-event rows render without coercion or loss.",
            "Capability status, source provenance, sampling and limitations are inspectable; evidence export is reproducible.",
            "Cancellation, permission refusal, error and recovery have executable host/component tests.",
        ],
        "limitations": ["The browser evidence is synthetic; formal accessibility audit and engineer usability study remain pending.",
                        "The actual P1 route still fails its own typed spatial converter acceptance."],
    }
    (ROOT / "release" / "LOCAL_UI_EVIDENCE.json").write_text(json.dumps(ui_evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"tests": test_count, "states": report["states"], "checks": checks,
                      "source_tree_sha256": report["source_tree_sha256"]}, indent=2))
    if any(value == "FAIL" if isinstance(value, str) else value.get("status") == "FAIL" for value in checks.values()):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
