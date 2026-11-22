"""Evaluate a site-generated logical MCP capability capture without guessing APIs."""
from __future__ import annotations

import json
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
MAX_REPORT_BYTES = 2 * 1024 * 1024
REQUIRED_SITE_TESTS = ("permission_denial", "bounded_read", "audit_trace", "cancel", "empty_data")


def evaluate(report: dict | None) -> dict:
    """Return gaps for a site-provided capture; never certify internal readiness."""
    try:
        contract = json.loads((BASE / "contracts" / "adapter-operations.v1.json").read_text(encoding="utf-8"))
        operations = [item["name"] for item in contract["logical_operations"]]
    except (OSError, KeyError, json.JSONDecodeError):
        operations = ["discover", "semantics", "relationships", "read_bounded", "cancel", "audit"]
    gaps = []
    checks = []

    def check(name, passed, reason):
        checks.append({"check": name, "status": "PASS" if passed else "PENDING", "reason": None if passed else reason})
        if not passed:
            gaps.append(reason)

    if not isinstance(report, dict):
        return {"state": "PENDING_INTERNAL", "preflight_state": "NO_CAPTURE", "checks": [],
                "gaps": ["No site-generated qualification capture was supplied."], "internal_ready": False}

    check("capture_version", report.get("capture_version") == "p3-site-capture-v1", "Capture must identify p3-site-capture-v1 format.")
    system = report.get("system") if isinstance(report.get("system"), dict) else {}
    check("target_platform", bool(system.get("os") and system.get("architecture") and system.get("python_version")),
          "Record actual target OS, architecture and Python version.")
    check("public_egress", system.get("public_egress_blocked") is True,
          "Verify public network egress is blocked on the target system.")

    bindings = report.get("logical_operation_bindings") if isinstance(report.get("logical_operation_bindings"), dict) else {}
    for operation in operations:
        binding = bindings.get(operation) if isinstance(bindings.get(operation), dict) else {}
        present = bool(binding.get("discovered_name") and binding.get("version") and binding.get("supported") is True)
        check("operation:" + operation, present, f"Discover and verify the {operation} logical operation through the approved adapter.")
    discover = bindings.get("discover") if isinstance(bindings.get("discover"), dict) else {}
    check("read_only_scope", discover.get("read_only") is True,
          "Verify the discovered source permission context is read-only.")

    sources = report.get("approved_sources") if isinstance(report.get("approved_sources"), list) else []
    source_ok = bool(sources) and all(
        isinstance(item, dict) and item.get("approved") is True and item.get("source_id")
        and item.get("semantic_version") and item.get("grain") and item.get("effective_time")
        and isinstance(item.get("units"), list) for item in sources
    )
    check("approved_source_semantics", source_ok,
          "Capture approved source definitions with grain, units, semantic version and effective time.")

    relationships = report.get("relationships") if isinstance(report.get("relationships"), list) else []
    relation_ok = bool(relationships) and all(
        isinstance(item, dict) and item.get("approved") is True and item.get("source_reference")
        and isinstance(item.get("keys"), list) and bool(item["keys"])
        and item.get("cardinality") in ("one_to_one", "one_to_many", "many_to_one")
        and item.get("grain") and item.get("effective_time") for item in relationships
    )
    check("approved_relationships", relation_ok,
          "Capture approved entity relationships, join keys, cardinality, grain and effective time.")

    security = report.get("security_checks") if isinstance(report.get("security_checks"), dict) else {}
    for key, label in (("read_only_enforced", "read-only enforcement"), ("bounded_query_limits", "row/byte/time query bounds"),
                       ("audit_redaction", "redacted audit logging"), ("cancellation_verified", "operation cancellation")):
        check("security:" + key, security.get(key) is True, f"Verify {label} on the authorized target.")
    tests = report.get("site_test_results") if isinstance(report.get("site_test_results"), dict) else {}
    for test in REQUIRED_SITE_TESTS:
        check("site_test:" + test, tests.get(test) == "PASS", f"Run and record the {test} qualification case with actual site evidence.")

    capture_time = report.get("captured_at")
    check("capture_time", isinstance(capture_time, str) and bool(capture_time.strip()), "Record the capture time from the target system.")
    approval = report.get("approval_record")
    check("human_approval", isinstance(approval, dict) and bool(approval.get("reference")),
          "Authorized human owner/security approval must be recorded at the site.")

    complete = all(item["status"] == "PASS" for item in checks)
    return {
        "state": "PENDING_INTERNAL",
        "preflight_state": "READY_FOR_AUTHORIZED_REVIEW" if complete else "GAPS_REMAIN",
        "checks": checks,
        "gaps": gaps,
        "internal_ready": False,
        "note": "A file-based preflight cannot authenticate company authority or certify READY_INTERNAL. Final approval and first engineer result remain internal gates.",
    }


def read_report(path: str | Path) -> dict:
    file_path = Path(path)
    if file_path.stat().st_size > MAX_REPORT_BYTES:
        raise ValueError("qualification capture exceeds the 2 MiB limit")
    parsed = json.loads(file_path.read_text(encoding="utf-8"))
    if not isinstance(parsed, dict):
        raise ValueError("qualification capture must be a JSON object")
    return parsed

