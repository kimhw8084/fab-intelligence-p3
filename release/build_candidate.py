"""Create and freshly extract/test a reproducible offline P3 source bundle."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import stat
import subprocess  # nosec B404
import sys
import tempfile
import zipfile
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from qualification.mcp_sdk_offline import qualify_offline_mcp_sdk
from qualification.tree_hash import current_git_commit, source_tree_sha256

ARCHIVE_NAME = "p3-candidate-20261123.zip"
DEFAULT_ARCHIVE_NAME = "p3-candidate-20261124-onboarding.zip"
GENERATED = {ARCHIVE_NAME, ARCHIVE_NAME + ".sha256", "PACKAGE_QUALIFICATION.json"}
IGNORED_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", ".pytest_cache", ".ruff_cache"}


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def package_files():
    files = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or any(part in IGNORED_DIRS for part in path.parts) or path.suffix == ".pyc":
            continue
        rel = path.relative_to(ROOT).as_posix()
        if rel.startswith(".git/") or rel in {".git"}:
            continue
        if rel.startswith("release/p3-candidate-"):
            continue
        if rel.startswith("progress/"):
            continue
        if rel.startswith("release/") and (Path(rel).name in GENERATED or Path(rel).name == "GATE_REPORT.json"):
            continue
        if path.suffix in (".zip", ".dmg", ".exe"):
            continue
        files.append((rel, path))
    return sorted(files)


def write_archive(destination: Path):
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for rel, path in package_files():
            info = zipfile.ZipInfo(rel, date_time=(2026, 11, 22, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            info.create_system = 3
            archive.writestr(info, path.read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)


def verify_archive(archive_path: Path) -> dict:
    with zipfile.ZipFile(archive_path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise ValueError("archive contains duplicate paths")
        if any(name.startswith("/") or ".." in Path(name).parts for name in names):
            raise ValueError("archive contains an unsafe path")
        for required in ("bootstrap_check.py", "product.json", "products/p3/engine.py",
                         "products/p3/ui/P3Panel.tsx", "integration/p3-suite-ui-module.v1.json",
                         "products/p3/contracts/spatial-map.v2.schema.json",
                         "products/p3/contracts/spatial-map.v2.ts",
                         "products/p3/reference_host/module-manifest.v2.json",
                         "products/p3/reference_host/static/index.html",
                         "products/p3/reference_host/src/App.tsx",
                         "fabintel/reference_host.py", "tests/test_reference_host.py",
                         "package.json", "package-lock.json",
                         "vendor/mcp-sdk-2.3.0/macos-arm64-cp311/requirements.lock",
                         "vendor/mcp-sdk-2.3.0/macos-arm64-cp311/wheelhouse/mcp-2.3.0-py3-none-any.whl",
                         "bootstrap_check.py", "release/BOOTSTRAP_MANIFEST.sha256",
                         "release/CRITICAL_CASE_EVIDENCE.json",
                         "release/LOCAL_TEST_EVIDENCE.json",
                         "release/MCP_SDK_OFFLINE_QUALIFICATION.json",
                         "release/P3_STANDALONE_BROWSER_EVIDENCE.json",
                         "release/P3_FINAL_BROWSER_A11Y_REVIEW_20261124.json",
                         "release/P3_CURRENT_OSV_AUDIT_20261124.json",
                         "release/NPM_AUDIT_CURRENT_2026-11-24.json",
                         "release/SBOM.spdx.json", "release/SUPPLY_CHAIN_AUDIT.json",
                         "release/THIRD_PARTY_NOTICES.md",
                         "release/P3_CURRENT_SOURCE_BANDIT_20261124.json",
                         "release/P3_FINAL_SECURITY_REVIEW_20261124.json",
                         "release/P3_FINAL_QUALIFICATION_REPORT.json",
                         "release/P3_WORKING_SOURCE_VERSION_20261124.json",
                         "release/RUNBOOK_ROLLBACK_KILL_SWITCH.md",
                         ".opencode/skills/p3-spatial-onboarding/SKILL.md",
                         ".agents/skills/p3-spatial-onboarding/SKILL.md",
                         "docs/INTERNAL_COMPANY_FIRST_RUN.md",
                         "requirements/mcp-onboarding-metadata.template.json",
                         "requirements/p3-onboarding-review.template.json",
                         "requirements/mcp-adapter.template.json",
                         "release/INTERNAL_QUALIFICATION_REPORT_TEMPLATE.json"):
            if required not in names:
                raise ValueError("archive is missing " + required)
    with tempfile.TemporaryDirectory(prefix="p3-fresh-extract-") as temp:
        with zipfile.ZipFile(archive_path) as archive:
            archive.extractall(temp)
        extracted = Path(temp)
        env = dict(os.environ)
        env.pop("PYTHONPATH", None)
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        bootstrap = subprocess.run([sys.executable, "-S", "bootstrap_check.py"], check=False,
                                   cwd=extracted, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   text=True, timeout=30)
        test = subprocess.run([sys.executable, "-S", "-m", "unittest", "discover", "-s", "tests", "-v"], check=False,  # nosec B603
                              cwd=extracted, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=120)
        demo = subprocess.run([sys.executable, "-S", "-m", "fabintel", "demo"], check=False, cwd=extracted, env=env,  # nosec B603
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=20)
        mcp_sdk = qualify_offline_mcp_sdk(extracted)
        report = {"fresh_extraction_bootstrap_exit": bootstrap.returncode,
                  "fresh_extraction_bootstrap": bootstrap.stdout[-3000:],
                  "fresh_extraction_test_exit": test.returncode, "fresh_extraction_demo_exit": demo.returncode,
                  "fresh_extraction_tests": test.stdout[-8000:], "fresh_extraction_demo": demo.stdout[-3000:],
                  "fresh_extraction_offline_mcp_sdk": mcp_sdk}
        if bootstrap.returncode or test.returncode or demo.returncode or mcp_sdk["status"] == "FAIL":
            raise RuntimeError(json.dumps(report, indent=2))
        return report


def candidate_output_paths(release: Path, archive_name: str) -> tuple[Path, Path, Path]:
    if (not isinstance(archive_name, str) or Path(archive_name).name != archive_name
            or not archive_name.startswith("p3-candidate-") or not archive_name.endswith(".zip")):
        raise ValueError("archive name must be a simple p3-candidate-*.zip filename")
    archive = release / archive_name
    sidecar = release / (archive_name + ".sha256")
    qualification = release / (archive_name.removesuffix(".zip") + ".qualification.json")
    if any(path.exists() for path in (archive, sidecar, qualification)):
        raise FileExistsError("candidate output already exists; choose a new versioned archive name")
    return archive, sidecar, qualification


def main(argv: list[str] | None = None):
    parser = argparse.ArgumentParser(description="Build and freshly qualify an immutable P3 candidate archive.")
    parser.add_argument("--archive-name", default=DEFAULT_ARCHIVE_NAME,
                        help="new versioned archive filename; existing candidates are never overwritten")
    args = parser.parse_args(argv)
    release = ROOT / "release"
    try:
        archive, sidecar, qualification = candidate_output_paths(release, args.archive_name)
    except (FileExistsError, ValueError) as exc:
        parser.error(str(exc))
    baseline = release / ARCHIVE_NAME
    baseline_hash = sha256_bytes(baseline.read_bytes()) if baseline.is_file() else None
    with tempfile.TemporaryDirectory(prefix="p3-repro-build-") as temp:
        first = Path(temp) / "first.zip"
        second = Path(temp) / "second.zip"
        write_archive(first)
        write_archive(second)
        first_hash = sha256_bytes(first.read_bytes())
        second_hash = sha256_bytes(second.read_bytes())
        if first_hash != second_hash:
            raise SystemExit("reproducible archive check failed: repeated builds differ")
        archive.write_bytes(first.read_bytes())
    try:
        archive_hash = sha256_bytes(archive.read_bytes())
        fresh = verify_archive(archive)
    except BaseException:
        archive.unlink(missing_ok=True)
        raise
    sidecar.write_text(f"{archive_hash}  {archive.name}\n", encoding="utf-8")
    report = {
        "state": "CANDIDATE",
        "created_utc": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "archive": archive.name,
        "sha256": archive_hash,
        "frozen_baseline_archive_sha256": baseline_hash,
        "frozen_baseline_modified": False,
        "source_version_file": "release/P3_WORKING_SOURCE_VERSION_20261124.json",
        "source_commit": current_git_commit(ROOT),
        "source_tree_sha256": source_tree_sha256(ROOT),
        "bytes": archive.stat().st_size,
        "entries": len(package_files()),
        "repeated_build_sha256_equal": first_hash == second_hash,
        "fresh_extraction_tests": {"command": "python -S -m unittest discover -s tests -v", "exit_code": fresh["fresh_extraction_test_exit"]},
        "fresh_extraction_bootstrap": {"command": "python -S bootstrap_check.py", "exit_code": fresh["fresh_extraction_bootstrap_exit"]},
        "fresh_extraction_demo": {"command": "python -S -m fabintel demo", "exit_code": fresh["fresh_extraction_demo_exit"]},
        "fresh_extraction_offline_mcp_sdk": fresh["fresh_extraction_offline_mcp_sdk"],
        "environment": {"os": platform.platform(), "architecture": platform.machine(), "python": sys.version},
        "network_isolation": "Not established by this host build; this tests standard-library-only execution with site packages disabled.",
        "fresh_extraction_test_log_tail": fresh["fresh_extraction_tests"],
    }
    qualification.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"archive": str(archive), "qualification": str(qualification),
                      "frozen_baseline_archive_sha256": baseline_hash,
                      "sha256": archive_hash, "bytes": archive.stat().st_size,
                      "repeated_builds_equal": report["repeated_build_sha256_equal"],
                      "extracted_tests": report["fresh_extraction_tests"]["exit_code"],
                      "extracted_demo": report["fresh_extraction_demo"]["exit_code"]}, indent=2))


if __name__ == "__main__":
    main()
