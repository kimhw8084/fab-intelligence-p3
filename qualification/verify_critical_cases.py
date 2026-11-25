"""Execute the frozen P3 critical-case catalog and bind each case to passing tests."""
from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import subprocess  # nosec B404
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "qualification" / "critical_cases.json"
OUTPUT = ROOT / "release" / "CRITICAL_CASE_EVIDENCE.json"
from tree_hash import current_git_commit, source_tree_sha256


def hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    command = [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"]
    result = subprocess.run(command, check=False, cwd=ROOT, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},  # nosec B603
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=180)
    results = []
    for item in catalog:
        tests = [name.strip() for name in item["candidate_test"].split(";")]
        checks = []
        for name in tests:
            lines = [line for line in result.stdout.splitlines() if re.search(rf"\b{re.escape(name)} \(", line)]
            checks.append({"test": name, "status": "PASS" if len(lines) == 1 and lines[0].endswith("... ok") else "FAIL"})
        results.append({"id": item["id"], "status": "PASS" if checks and all(check["status"] == "PASS" for check in checks) else "FAIL",
                        "checks": checks, "required_result": item["required_result"]})
    report = {
        "state": "CANDIDATE",
        "created_utc": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "command": "python -m unittest discover -s tests -v",
        "exit_code": result.returncode,
        "catalog_sha256": hash_file(CATALOG),
        "test_output_sha256": hashlib.sha256(result.stdout.encode()).hexdigest(),
        "source_tree_sha256": source_tree_sha256(ROOT),
        "source_commit": current_git_commit(ROOT),
        "environment": {"os": platform.platform(), "architecture": platform.machine(), "python": sys.version},
        "cases": results,
        "overall": "PASS" if result.returncode == 0 and all(item["status"] == "PASS" for item in results) else "FAIL",
        "company_data_used": False,
        "scope": "synthetic candidate tests only; not an internal Samsung qualification",
    }
    OUTPUT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"overall": report["overall"], "passed": sum(item["status"] == "PASS" for item in results),
                      "cases": len(results), "source_tree_sha256": report["source_tree_sha256"]}, indent=2))
    if report["overall"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
