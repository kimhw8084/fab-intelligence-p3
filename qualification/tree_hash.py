"""Canonical digest of product inputs, excluding generated qualification output."""
from __future__ import annotations

import hashlib
import shutil
import subprocess  # nosec B404
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IGNORED_SOURCE_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", ".pytest_cache", ".ruff_cache"}
GENERATED_EVIDENCE_FILES = {
    "release/BOOTSTRAP_MANIFEST.sha256",
    "release/CRITICAL_CASE_EVIDENCE.json",
    "release/GATE_REPORT.json",
    "release/GOLDEN_PILOT_FAST_EVIDENCE.json",
    "release/GOLDEN_PILOT_FULL_EVIDENCE.json",
    "release/GOLDEN_PY003_RUFF_2026-11-23.json",
    "release/GOLDEN_SEC001_BANDIT_2026-11-23.json",
    "release/LOCAL_TEST_EVIDENCE.json",
    "release/LOCAL_TEST_LOG.txt",
    "release/LOCAL_UI_EVIDENCE.json",
    "release/MCP_SDK_OFFLINE_QUALIFICATION.json",
    "release/MCP_SDK_OFFLINE_QUALIFICATION_FAILURE_2026-11-23.json",
    "release/NPM_AUDIT_2026-11-23.json",
    "release/NPM_AUDIT_PRODUCTION_2026-11-23.json",
    "release/P3_STANDALONE_BROWSER_EVIDENCE.json",
    "release/P3_FINAL_BROWSER_A11Y_REVIEW_20261124.json",
    "release/P3_CURRENT_OSV_AUDIT_20261124.json",
    "release/NPM_AUDIT_CURRENT_2026-11-24.json",
    "release/P3_CURRENT_SOURCE_BANDIT_20261124.json",
    "release/P3_FINAL_SECURITY_REVIEW_20261124.json",
    "release/P3_FINAL_QUALIFICATION_REPORT.json",
    "release/P3_SOURCE_VERSION.json",
    "release/P3_WORKING_SOURCE_VERSION_20261124.json",
    "release/RUFF_CURRENT_2026-11-23.json",
    "release/BANDIT_CURRENT_2026-11-23.json",
    "release/OFFLINE_RUNTIME_EVIDENCE.json",
    "release/PACKAGE_QUALIFICATION.json",
    "release/REUSE_COMPARISON_EVIDENCE.json",
    "release/SBOM.spdx.json",
    "release/SCIENTIFIC_PERFORMANCE_BENCHMARK.json",
    "release/SUPPLY_CHAIN_AUDIT.json",
    "release/PIP_AUDIT_OSV.json",
    "release/PIP_AUDIT_RUN_2026-11-23.json",
    "release/BANDIT_SOURCE_SCAN.json",
    "release/P1_NPM_AUDIT.json",
    "release/P1_HOST_INTEGRATION_AUDIT.json",
    "release/P1_MODULE_INTEGRATION_EVIDENCE.json",
    "release/P1_BROWSER_WORKFLOW_EVIDENCE.json",
    "release/THIRD_PARTY_SECURITY_SCAN_EVIDENCE.json",
    "progress/OVERNIGHT_EXECUTION.md",
    "progress/NEXT_ACTIONS.json",
    "progress/REQUIREMENT_EVIDENCE_MATRIX.md",
    "progress/STATE.md",
    "progress/C02_COVARIANCE_BROWSER_ACCEPTANCE.json",
    "progress/C02_BROWSER_UNCERTAINTY_ACCEPTANCE.json",
    "progress/C02_SEQUENCE_MASK_CHALLENGE.json",
    "progress/C04_BASELINE_CONTAMINATION_CHALLENGE.json",
    "progress/C01_SAMPLING_AND_ARTIFACT_CHALLENGE.json",
    "progress/C02_CORRELATED_ERROR_STUDY.json",
    "progress/C03_ZONE_CONFOUND_BENCHMARK.json",
    "progress/C03_CONTEXT_DRIFT_BENCHMARK.json",
    "progress/C03_NESTED_LOT_BENCHMARK.json",
    "progress/SPATIAL_ONBOARDING_BENCHMARK.json",
    "progress/ONBOARDING_BOOTSTRAP_BENCHMARK.json",
    "progress/SPATIAL_ONBOARDING_BROWSER_ACCEPTANCE.json",
    "progress/C04_FAMILY_BROWSER_ACCEPTANCE.json",
    "progress/C04_REPEATED_TARGET_NULL_STUDY.json",
    "progress/C05_SCALE_10K_BENCHMARK.json",
    "progress/C05_SCALE_15K_BENCHMARK.json",
    "progress/C05_SCALE_15K_COMPACTED_BENCHMARK.json",
    "progress/C01_GEOMETRY_ORACLE.json",
    "progress/REGRESSION_2026-11-23.json",
}


def source_tree_sha256(root: Path = ROOT) -> str:
    """Hash the same source/config/docs/test tree from every qualification runner."""
    entries = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or any(part in IGNORED_SOURCE_DIRS for part in path.parts) or path.suffix in {
            ".pyc", ".zip", ".dmg", ".exe", ".whl", ".sha256",
        }:
            continue
        relative = path.relative_to(root).as_posix()
        if relative in GENERATED_EVIDENCE_FILES:
            continue
        if relative.startswith("release/p3-candidate-"):
            continue
        entries.append(relative.encode("utf-8") + b"\0" + hashlib.sha256(path.read_bytes()).digest())
    return hashlib.sha256(b"".join(entries)).hexdigest()


def current_git_commit(root: Path = ROOT) -> str | None:
    git = shutil.which("git")
    if git is None:
        return None
    try:
        result = subprocess.run([git, "rev-parse", "HEAD"], cwd=root, check=True,  # nosec B603
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    value = result.stdout.strip()
    return value if len(value) == 40 else None
