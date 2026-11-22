"""Record reproducible local candidate checks with synthetic-only evidence."""
from __future__ import annotations

import hashlib
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
OUTPUTS = {"release/LOCAL_TEST_EVIDENCE.json", "release/LOCAL_TEST_LOG.txt", "release/GATE_REPORT.json",
           "release/BOOTSTRAP_MANIFEST.sha256", "release/PACKAGE_QUALIFICATION.json"}


def source_hash():
    digest = hashlib.sha256()
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file() or "__pycache__" in path.parts or path.suffix == ".pyc":
            continue
        relative = path.relative_to(ROOT).as_posix()
        if relative in OUTPUTS or relative.startswith("release/p3-candidate-") or relative.endswith(".zip"):
            continue
        digest.update(relative.encode("utf-8") + b"\0" + hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def run(command):
    result = subprocess.run(command, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, timeout=180, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
    return {"command": " ".join(command), "exit_code": result.returncode, "output": result.stdout}


def main():
    test = run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"])
    demo = run([sys.executable, "-m", "fabintel", "demo"])
    pending = run([sys.executable, "-m", "fabintel", "qualify-internal"])
    js = run([shutil.which("node") or "node", "--check", "ui/app.js"]) if shutil.which("node") else {
        "command": "node --check ui/app.js", "exit_code": None, "output": "Node.js unavailable; UI bundle must be checked on target host."}
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
        "javascript_syntax": {"command": js["command"], "status": "PASS" if js["exit_code"] == 0 else "PENDING" if js["exit_code"] is None else "FAIL"},
    }
    report = {
        "state": "CANDIDATE",
        "created_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "source_tree_sha256": source_hash(),
        "git_commit": None,
        "environment": {"os": platform.platform(), "architecture": platform.machine(), "python": sys.version,
                        "node": subprocess.run([shutil.which("node") or "node", "--version"], cwd=ROOT,
                                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True).stdout.strip()
                        if shutil.which("node") else None},
        "company_data_used": False,
        "checks": checks,
        "external_status": "CANDIDATE; target OS/network isolation, supply chain, license, company MCP and user-study gates are not established by this local run.",
    }
    log = "\n\n".join(f"$ {item['command']}\nexit={item['exit_code']}\n{item['output']}" for item in (test, demo, pending, js))
    (ROOT / "release" / "LOCAL_TEST_LOG.txt").write_text(log, encoding="utf-8")
    (ROOT / "release" / "LOCAL_TEST_EVIDENCE.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"tests": test_count, "checks": checks, "source_tree_sha256": report["source_tree_sha256"]}, indent=2))
    if any(value["status"] == "FAIL" for value in checks.values()):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
