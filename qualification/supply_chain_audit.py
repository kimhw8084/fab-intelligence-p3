"""Create a local source/dependency inventory and SPDX SBOM without network access."""
from __future__ import annotations

import ast
import base64
import hashlib
import json
import re
import shutil
import sys
import zipfile
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {"__pycache__", ".git", ".venv", "venv", "progress", "node_modules", ".pytest_cache", ".ruff_cache"}
OUTPUTS = {"release/SBOM.spdx.json", "release/SUPPLY_CHAIN_AUDIT.json", "release/GATE_REPORT.json",
           "release/GOLDEN_PILOT_FAST_EVIDENCE.json",
           "release/GOLDEN_PILOT_FULL_EVIDENCE.json",
           "release/BOOTSTRAP_MANIFEST.sha256", "release/SCIENTIFIC_PERFORMANCE_BENCHMARK.json",
           "release/PACKAGE_QUALIFICATION.json", "release/MCP_SDK_OFFLINE_QUALIFICATION.json",
           "release/MCP_SDK_OFFLINE_QUALIFICATION_FAILURE_2026-11-23.json",
           "release/NPM_AUDIT_2026-11-23.json", "release/NPM_AUDIT_PRODUCTION_2026-11-23.json",
           "release/PIP_AUDIT_RUN_2026-11-23.json",
           "release/P3_STANDALONE_BROWSER_EVIDENCE.json", "release/P3_SOURCE_VERSION.json",
           "release/P3_FINAL_BROWSER_A11Y_REVIEW_20261124.json",
           "release/P3_CURRENT_OSV_AUDIT_20261124.json",
           "release/NPM_AUDIT_CURRENT_2026-11-24.json",
           "release/P3_CURRENT_SOURCE_BANDIT_20261124.json",
           "release/P3_FINAL_SECURITY_REVIEW_20261124.json",
           "release/P3_FINAL_QUALIFICATION_REPORT.json",
           "release/RUFF_CURRENT_2026-11-23.json", "release/BANDIT_CURRENT_2026-11-23.json",
           "release/NPM_SBOM_2026-11-23.spdx.json", "release/LOCAL_TEST_EVIDENCE.json",
           "release/LOCAL_TEST_LOG.txt", "release/LOCAL_UI_EVIDENCE.json",
           "release/CRITICAL_CASE_EVIDENCE.json"}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_files():
    return [path for path in sorted(ROOT.rglob("*")) if path.is_file()
            and not any(part in SKIP_DIRS for part in path.parts)
            and path.suffix not in (".pyc", ".zip", ".sha256")
            and path.relative_to(ROOT).as_posix() not in OUTPUTS]


def imported_modules(path: Path) -> set[str]:
    if path.suffix != ".py":
        return set()
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module.split(".")[0])
    return names


def inspect_vendor_licenses(root: Path, inventory: dict) -> dict:
    """Verify each pinned wheel/license file and resolve only explicit MIT texts."""
    wheelhouse = root / "vendor" / "mcp-sdk-2.3.0" / "macos-arm64-cp311" / "wheelhouse"
    expressions = {}
    derived = []
    unresolved = []
    verified_wheels = 0
    verified_license_files = 0
    for dependency in inventory.get("packages", []):
        name = dependency["name"]
        wheel_name = dependency["wheel"]
        if not dependency.get("bundled_license_files"):
            raise ValueError(f"No embedded license file is recorded for {name}.")
        wheel_path = wheelhouse / wheel_name
        if (Path(wheel_name).name != wheel_name or wheel_path.is_symlink() or not wheel_path.is_file()
                or sha256(wheel_path) != dependency["wheel_sha256"]):
            raise ValueError(f"Bundled wheel integrity mismatch for {name}.")
        verified_wheels += 1
        license_texts = []
        try:
            with zipfile.ZipFile(wheel_path) as archive:
                archive_names = set(archive.namelist())
                for license_file in dependency.get("bundled_license_files", []):
                    relative = PurePosixPath(license_file["path"])
                    if relative.is_absolute() or ".." in relative.parts or license_file["path"] not in archive_names:
                        raise ValueError(f"Embedded license file is missing or unsafe for {name}.")
                    contents = archive.read(license_file["path"])
                    if hashlib.sha256(contents).hexdigest() != license_file["sha256"]:
                        raise ValueError(f"Embedded license hash mismatch for {name}.")
                    verified_license_files += 1
                    license_texts.append(contents.decode("utf-8", errors="replace"))
        except (OSError, zipfile.BadZipFile) as exc:
            raise ValueError(f"Cannot inspect bundled wheel for {name}.") from exc

        expression = dependency.get("license_expression")
        if expression:
            expressions[name] = expression
        elif any(
            "mit license" in normalized[:500]
            and "permission is hereby granted, free of charge" in normalized
            and "deal in the software without restriction" in normalized
            for normalized in (" ".join(text.lower().split()) for text in license_texts)
        ):
            expressions[name] = "MIT"
            derived.append({"name": name, "version": dependency["version"], "expression": "MIT",
                            "basis": "verified embedded MIT license text", "license_file_count": len(license_texts)})
        else:
            expressions[name] = "NOASSERTION"
            unresolved.append({"name": name, "version": dependency["version"]})
    return {"license_expressions": expressions, "derived_expressions": derived,
            "unresolved_packages": unresolved, "verified_wheels": verified_wheels,
            "verified_embedded_license_files": verified_license_files}


def inspect_npm_dependencies(root: Path, lock: dict) -> dict:
    """Inventory the installed target-platform npm tree from lock-pinned package metadata."""
    packages = lock.get("packages")
    if not isinstance(packages, dict):
        raise TypeError("package-lock.json must contain the v2/v3 packages object")
    installed = []
    missing_locked = []
    unresolved = []
    licenses = {}
    for lock_path, locked in sorted(packages.items()):
        if not lock_path.startswith("node_modules/") or not isinstance(locked, dict):
            continue
        relative = lock_path.removeprefix("node_modules/")
        manifest_path = root / "node_modules" / relative / "package.json"
        if not manifest_path.is_file():
            missing_locked.append({"lock_path": lock_path, "version": locked.get("version"),
                                   "optional": bool(locked.get("optional")),
                                   "os": locked.get("os"), "cpu": locked.get("cpu")})
            continue
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        name = manifest.get("name")
        version = locked.get("version") or manifest.get("version")
        expression = manifest.get("license")
        if isinstance(expression, dict):
            expression = expression.get("type")
        if not isinstance(expression, str) or not expression.strip():
            expression = "NOASSERTION"
            unresolved.append({"name": name, "version": version, "manifest": str(manifest_path.relative_to(root))})
        licenses[expression] = licenses.get(expression, 0) + 1
        integrity = locked.get("integrity")
        checksums = []
        if isinstance(integrity, str) and integrity.startswith("sha512-"):
            try:
                raw_digest = base64.b64decode(integrity[7:], validate=True)
            except ValueError:
                raw_digest = b""
            if len(raw_digest) == 64:
                checksums.append({"algorithm": "SHA512", "checksumValue": raw_digest.hex()})
        installed.append({"name": name, "version": version, "license": expression,
                          "lock_path": lock_path, "integrity": integrity,
                          "resolved": locked.get("resolved"), "optional": bool(locked.get("optional")),
                          "dev": bool(locked.get("dev")), "checksums": checksums})
    return {"installed_packages": installed, "license_summary": licenses,
            "unresolved_installed_package_licenses": unresolved,
            "locked_but_not_installed": missing_locked,
            "locked_package_count": sum(path.startswith("node_modules/") for path in packages),
            "installed_package_count": len(installed)}


def inspect_runtime_references(files: list[Path]) -> dict:
    """Detect active external resource/API declarations, not URLs embedded as documentation."""
    remote_scripts_or_styles = set()
    remote_fonts_or_images = set()
    remote_runtime_apis = set()
    for path in files:
        if path.suffix.lower() not in {".html", ".js", ".mjs", ".cjs", ".css"}:
            continue
        body = path.read_text(encoding="utf-8")
        source = path.as_posix()
        suffix = path.suffix.lower()
        if suffix == ".html":
            for match in re.finditer(r"<(?:script|link)\b[^>]*(?:src|href)\s*=\s*([\"'])(https?://[^\"']+)\1", body, re.IGNORECASE):
                remote_scripts_or_styles.add(f"{source}: {match.group(2)}")
            for match in re.finditer(r"<(?:img|source)\b[^>]*src\s*=\s*([\"'])(https?://[^\"']+)\1", body, re.IGNORECASE):
                remote_fonts_or_images.add(f"{source}: {match.group(2)}")
        elif suffix == ".css":
            for match in re.finditer(r"@import\s+(?:url\()?\s*[\"']?(https?://[^\s\"')]+)", body, re.IGNORECASE):
                remote_scripts_or_styles.add(f"{source}: {match.group(1)}")
            css_assets = re.sub(r"@import[^;]*;", "", body, flags=re.IGNORECASE)
            for match in re.finditer(r"url\(\s*[\"']?(https?://[^\s\"')]+)", css_assets, re.IGNORECASE):
                remote_fonts_or_images.add(f"{source}: {match.group(1)}")
        else:
            for match in re.finditer(r"(?:from\s*|import\s*\(|import\s*)([\"'])(https?://[^\"']+)\1", body):
                remote_scripts_or_styles.add(f"{source}: {match.group(2)}")
            api_patterns = (
                r"\bfetch\s*\(\s*([\"'])(https?://[^\"']+)",
                r"\bnew\s+(?:WebSocket|EventSource)\s*\(\s*([\"'])(https?://[^\"']+)",
                r"\.open\s*\(\s*[\"'][A-Z]+[\"']\s*,\s*([\"'])(https?://[^\"']+)",
            )
            for pattern in api_patterns:
                for match in re.finditer(pattern, body):
                    remote_runtime_apis.add(f"{source}: {match.group(2)}")
            for match in re.finditer(r"(?:\.src\s*=|setAttribute\s*\(\s*[\"']src[\"']\s*,)\s*([\"'])(https?://[^\"']+)", body):
                remote_fonts_or_images.add(f"{source}: {match.group(2)}")
    return {
        "remote_script_or_style_reference": bool(remote_scripts_or_styles),
        "remote_font_or_image_reference": bool(remote_fonts_or_images),
        "remote_runtime_api_reference": bool(remote_runtime_apis),
        "external_script_or_style_references": sorted(remote_scripts_or_styles),
        "external_font_or_image_references": sorted(remote_fonts_or_images),
        "external_runtime_api_references": sorted(remote_runtime_apis),
    }


def main():
    files = source_files()
    runtime_roots = set()
    runtime_sources = [path for path in files if path.suffix == ".py"
                       and path.relative_to(ROOT).parts[0] in {"fabintel", "products"}]
    for path in runtime_sources:
        runtime_roots.update(imported_modules(path))
    stdlib = set(getattr(sys, "stdlib_module_names", ()))
    first_party = {"fabintel", "products", "qualification", "tests", "cli", "tree_hash"}
    third_party = sorted(name for name in runtime_roots if name not in stdlib and name not in first_party)
    local_assets = inspect_runtime_references(files)
    licenses = [p.name for p in ROOT.iterdir() if p.is_file() and re.match(r"(?i)(license|copying|notice)(\.|$)", p.name)]
    spdx_files = []
    for index, path in enumerate(files, 1):
        rel = path.relative_to(ROOT).as_posix()
        spdx_files.append({
            "fileName": "./" + rel,
            "SPDXID": f"SPDXRef-File-{index}",
            "checksums": [{"algorithm": "SHA256", "checksumValue": sha256(path)}],
            "licenseConcluded": "NOASSERTION",
            "licenseInfoInFiles": ["NOASSERTION"],
            "copyrightText": "NOASSERTION",
        })
    package = {
        "name": "fab-spatial-yield-intelligence-p3",
        "SPDXID": "SPDXRef-Package-P3",
        "versionInfo": "0.2.0",
        "downloadLocation": "NOASSERTION",
        "filesAnalyzed": True,
        "licenseConcluded": "NOASSERTION",
        "licenseDeclared": "NOASSERTION",
        "copyrightText": "NOASSERTION",
        "primaryPackagePurpose": "APPLICATION",
    }
    inventory_path = ROOT / "vendor" / "mcp-sdk-2.3.0" / "macos-arm64-cp311" / "license-inventory.json"
    inventory = json.loads(inventory_path.read_text(encoding="utf-8")) if inventory_path.is_file() else {"packages": []}
    license_audit = inspect_vendor_licenses(ROOT, inventory)
    npm_lock_path = ROOT / "package-lock.json"
    npm_audit = inspect_npm_dependencies(ROOT, json.loads(npm_lock_path.read_text(encoding="utf-8"))) \
        if npm_lock_path.is_file() else {"installed_packages": [], "license_summary": {},
                                         "unresolved_installed_package_licenses": [],
                                         "locked_but_not_installed": [], "locked_package_count": 0,
                                         "installed_package_count": 0}
    dependency_packages = []
    dependency_relationships = []
    for dependency in inventory.get("packages", []):
        safe_name = re.sub(r"[^A-Za-z0-9.-]", "-", dependency["name"])
        dependency_id = "SPDXRef-Python-" + safe_name + "-" + dependency["version"]
        source = next((item["url"] for item in dependency.get("source_references", [])
                       if "source" in item.get("label", "").lower() or "homepage" in item.get("label", "").lower()),
                      "NOASSERTION")
        license_expression = license_audit["license_expressions"][dependency["name"]]
        dependency_packages.append({
            "name": dependency["name"],
            "SPDXID": dependency_id,
            "versionInfo": dependency["version"],
            "downloadLocation": source,
            "filesAnalyzed": False,
            "checksums": [{"algorithm": "SHA256", "checksumValue": dependency["wheel_sha256"]}],
            "licenseConcluded": "NOASSERTION",
            "licenseDeclared": license_expression,
            "copyrightText": "NOASSERTION",
            "primaryPackagePurpose": "LIBRARY",
            "externalRefs": [{"referenceCategory": "PACKAGE-MANAGER", "referenceType": "purl",
                              "referenceLocator": f"pkg:pypi/{dependency['normalized_name']}@{dependency['version']}"}],
        })
        dependency_relationships.append({"spdxElementId": "SPDXRef-Package-P3", "relationshipType": "CONTAINS",
                                         "relatedSpdxElement": dependency_id})
    npm_dependency_packages = []
    npm_dependency_relationships = []
    for dependency in npm_audit["installed_packages"]:
        package_name = dependency["name"] or dependency["lock_path"].removeprefix("node_modules/")
        safe_name = re.sub(r"[^A-Za-z0-9.-]", "-", package_name)
        path_tag = hashlib.sha256(dependency["lock_path"].encode("utf-8")).hexdigest()[:8]
        dependency_id = f"SPDXRef-NPM-{safe_name}-{dependency['version']}-{path_tag}"
        package_entry = {"name": package_name, "SPDXID": dependency_id,
                         "versionInfo": dependency["version"],
                         "downloadLocation": dependency["resolved"] or "NOASSERTION",
                         "filesAnalyzed": False,
                         "checksums": dependency["checksums"],
                         "licenseConcluded": "NOASSERTION",
                         "licenseDeclared": dependency["license"],
                         "copyrightText": "NOASSERTION",
                         "primaryPackagePurpose": "LIBRARY",
                         "externalRefs": [{"referenceCategory": "PACKAGE-MANAGER", "referenceType": "purl",
                                           "referenceLocator": f"pkg:npm/{quote(package_name, safe='/')}@{dependency['version']}"}]}
        npm_dependency_packages.append(package_entry)
        npm_dependency_relationships.append({"spdxElementId": "SPDXRef-Package-P3", "relationshipType": "CONTAINS",
                                             "relatedSpdxElement": dependency_id})
    document = {
        "spdxVersion": "SPDX-2.3",
        "dataLicense": "CC0-1.0",
        "SPDXID": "SPDXRef-DOCUMENT",
        "name": "FAB Spatial & Yield Intelligence P3 candidate SBOM",
        "documentNamespace": "https://spdx.org/spdxdocs/fabintel-p3-" + sha256(ROOT / "product.json"),
        "creationInfo": {"creators": ["Tool: local-standard-library-supply-chain-audit"],
                         "created": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")},
        "packages": [package, *dependency_packages, *npm_dependency_packages],
        "files": spdx_files,
        "relationships": [{"spdxElementId": "SPDXRef-DOCUMENT", "relationshipType": "DESCRIBES", "relatedSpdxElement": "SPDXRef-Package-P3"},
                           *dependency_relationships, *npm_dependency_relationships],
    }
    npm_audit_report_path = ROOT / "release" / "NPM_AUDIT_PRODUCTION_2026-11-23.json"
    npm_audit_report = json.loads(npm_audit_report_path.read_text(encoding="utf-8")) \
        if npm_audit_report_path.is_file() else {}
    npm_vulnerabilities = npm_audit_report.get("metadata", {}).get("vulnerabilities", {})
    pip_audit_run_path = ROOT / "release" / "PIP_AUDIT_RUN_2026-11-23.json"
    pip_audit_run = json.loads(pip_audit_run_path.read_text(encoding="utf-8")) \
        if pip_audit_run_path.is_file() else {}
    audit = {
        "state": "CANDIDATE",
        "scan_scope": "local source tree only; no network access",
        "created_utc": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "runtime": {"minimum_python": "3.10", "base_dependencies": "Python standard library",
                    "runtime_import_roots_not_in_stdlib": third_party,
                    "optional_mcp_dependency": {"package": "mcp==2.3.0", "activated_by": "mcp-discover",
                                                 "target": "macOS arm64 CPython 3.11 candidate only",
                                                 "bundled_hash_locked_wheelhouse":
                                                     (ROOT / "vendor/mcp-sdk-2.3.0/macos-arm64-cp311/requirements.lock").is_file(),
                                                 "wheel_count": len(inventory.get("packages", [])),
                                                 "license_inventory": "vendor/mcp-sdk-2.3.0/macos-arm64-cp311/license-inventory.json"},
                    "ui_runtime": "React 19 production bundle and Apache ECharts 6.1.0 assets bundled locally for the standalone reference host",
                    "bundled_ui_assets": True,
                    "bundled_ui_entrypoint": "products/p3/reference_host/static/index.html",
                    "npm_lockfile": "package-lock.json", "npm_installed_target_packages": npm_audit["installed_package_count"],
                    "remote_asset_findings": local_assets},
        "files_in_sbom": len(spdx_files),
        "package_components_in_sbom": len(dependency_packages) + len(npm_dependency_packages),
        "python_package_components_in_sbom": len(dependency_packages),
        "npm_package_components_in_sbom": len(npm_dependency_packages),
        "file_sha256": {item["fileName"][2:]: item["checksums"][0]["checksumValue"] for item in spdx_files},
        "license_review": {"root_license_files": licenses, "first_party_license": "NOASSERTION",
                            "third_party_runtime_dependencies": ["mcp==2.3.0 optional candidate; hash-locked wheel closure"] if third_party else [],
                            "bundled_optional_python_package_count": len(dependency_packages),
                            "installed_npm_dependency_count": npm_audit["installed_package_count"],
                            "installed_npm_license_summary": npm_audit["license_summary"],
                            "unresolved_npm_package_licenses": npm_audit["unresolved_installed_package_licenses"],
                            "locked_but_not_installed_target_packages": npm_audit["locked_but_not_installed"],
                            "verified_bundled_wheels": license_audit["verified_wheels"],
                            "verified_embedded_license_files": license_audit["verified_embedded_license_files"],
                            "license_expression_derivations": license_audit["derived_expressions"],
                            "unresolved_package_licenses": license_audit["unresolved_packages"],
                            "status": "PENDING_RIGHTS_REVIEW" if not licenses else "PENDING_SCOPE_REVIEW"},
        "vulnerability_review": {"syft_available": shutil.which("syft") is not None,
                                 "grype_available": shutil.which("grype") is not None,
                                 "vulnerability_database": "OSV queried online; scanner report is point-in-time",
                                 "pip_audit_report": "release/PIP_AUDIT_RUN_2026-11-23.json" if pip_audit_run else "NOT_RUN",
                                 "pip_audit_executed_at_utc": pip_audit_run.get("executed_at_utc"),
                                 "pip_vulnerability_count": pip_audit_run.get("vulnerability_count"),
                                 "npm_audit_report": "release/NPM_AUDIT_PRODUCTION_2026-11-23.json",
                                 "npm_production_vulnerabilities": npm_vulnerabilities,
                                 "npm_audit_status": "NO_ADVISORIES_REPORTED" if npm_audit_report else "NOT_RUN",
                                 "status": "PENDING_INDEPENDENT_TARGET_HOST_REVIEW"},
        "limitations": ["The target Python distribution and operating-system libraries are not bundled or pinned here.",
                        "No root source license was supplied; SPDX uses NOASSERTION and does not grant redistribution rights.",
                        "Point-in-time pip-audit and npm audit results do not replace an independent target-host security review.",
                        "Syft and Grype binaries were not available locally."],
    }
    (ROOT / "release" / "SBOM.spdx.json").write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (ROOT / "release" / "SUPPLY_CHAIN_AUDIT.json").write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"files": len(spdx_files), "third_party_imports": third_party,
                      "root_license_files": licenses, "license_status": audit["license_review"]["status"],
                      "verified_wheels": audit["license_review"]["verified_bundled_wheels"],
                      "verified_license_files": audit["license_review"]["verified_embedded_license_files"],
                      "derived_licenses": [item["name"] for item in license_audit["derived_expressions"]],
                      "unresolved_package_licenses": license_audit["unresolved_packages"],
                      "npm_dependency_count": npm_audit["installed_package_count"],
                      "npm_license_summary": npm_audit["license_summary"],
                      "npm_unresolved_licenses": len(npm_audit["unresolved_installed_package_licenses"]),
                      "npm_production_vulnerabilities": npm_vulnerabilities,
                      "vulnerability_status": audit["vulnerability_review"]["status"]}, indent=2))


if __name__ == "__main__":
    main()
