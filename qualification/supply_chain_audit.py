"""Create a local source/dependency inventory and SPDX SBOM without network access."""
from __future__ import annotations

import ast
import hashlib
import json
import re
import shutil
import sys
import zipfile
from pathlib import PurePosixPath
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {"__pycache__", ".git"}
OUTPUTS = {"release/SBOM.spdx.json", "release/SUPPLY_CHAIN_AUDIT.json", "release/GATE_REPORT.json",
           "release/GOLDEN_PILOT_FAST_EVIDENCE.json",
           "release/GOLDEN_PILOT_FULL_EVIDENCE.json",
           "release/BOOTSTRAP_MANIFEST.sha256", "release/SCIENTIFIC_PERFORMANCE_BENCHMARK.json",
           "release/PACKAGE_QUALIFICATION.json", "release/LOCAL_TEST_EVIDENCE.json",
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
    local_assets = {"remote_script_or_style_reference": False, "remote_font_or_image_reference": False,
                    "remote_runtime_api_reference": False}
    remote_urls = []
    for path in files:
        if path.suffix not in (".html", ".js", ".css"):
            continue
        body = path.read_text(encoding="utf-8")
        if re.search(r"(?:src|href)\s*=\s*[\"']https?://|@import\s+url\(\s*[\"']?https?://", body, re.I):
            local_assets["remote_script_or_style_reference"] = True
        remote_urls.extend(url for url in re.findall(r"https?://[^\s\"'<>]+", body)
                           if not url.startswith("http://www.w3.org/2000/svg"))
    local_assets["remote_runtime_api_reference"] = bool(remote_urls)
    local_assets["remote_font_or_image_reference"] = bool(remote_urls)
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
    document = {
        "spdxVersion": "SPDX-2.3",
        "dataLicense": "CC0-1.0",
        "SPDXID": "SPDXRef-DOCUMENT",
        "name": "FAB Spatial & Yield Intelligence P3 candidate SBOM",
        "documentNamespace": "https://spdx.org/spdxdocs/fabintel-p3-" + sha256(ROOT / "product.json"),
        "creationInfo": {"creators": ["Tool: local-standard-library-supply-chain-audit"],
                         "created": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")},
        "packages": [package, *dependency_packages],
        "files": spdx_files,
        "relationships": [{"spdxElementId": "SPDXRef-DOCUMENT", "relationshipType": "DESCRIBES", "relatedSpdxElement": "SPDXRef-Package-P3"},
                           *dependency_relationships],
    }
    audit = {
        "state": "CANDIDATE",
        "scan_scope": "local source tree only; no network access",
        "created_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "runtime": {"minimum_python": "3.10", "base_dependencies": "Python standard library",
                    "runtime_import_roots_not_in_stdlib": third_party,
                    "optional_mcp_dependency": {"package": "mcp==2.3.0", "activated_by": "mcp-discover",
                                                 "target": "macOS arm64 CPython 3.11 candidate only",
                                                 "bundled_hash_locked_wheelhouse":
                                                     (ROOT / "vendor/mcp-sdk-2.3.0/macos-arm64-cp311/requirements.lock").is_file(),
                                                 "wheel_count": len(inventory.get("packages", [])),
                                                 "license_inventory": "vendor/mcp-sdk-2.3.0/macos-arm64-cp311/license-inventory.json"},
                    "ui_runtime": "React peer supplied by the P1 suite host; no UI shell or chart engine is bundled",
                    "bundled_ui_assets": False, "remote_asset_findings": local_assets},
        "files_in_sbom": len(spdx_files),
        "package_components_in_sbom": len(dependency_packages),
        "file_sha256": {item["fileName"][2:]: item["checksums"][0]["checksumValue"] for item in spdx_files},
        "license_review": {"root_license_files": licenses, "first_party_license": "NOASSERTION",
                            "third_party_runtime_dependencies": ["mcp==2.3.0 optional candidate; hash-locked wheel closure"] if third_party else [],
                            "bundled_optional_package_count": len(dependency_packages),
                            "verified_bundled_wheels": license_audit["verified_wheels"],
                            "verified_embedded_license_files": license_audit["verified_embedded_license_files"],
                            "license_expression_derivations": license_audit["derived_expressions"],
                            "unresolved_package_licenses": license_audit["unresolved_packages"],
                            "status": "PENDING_RIGHTS_REVIEW" if not licenses else "PENDING_SCOPE_REVIEW"},
        "vulnerability_review": {"syft_available": shutil.which("syft") is not None,
                                 "grype_available": shutil.which("grype") is not None,
                                 "vulnerability_database": "not available locally",
                                 "status": "PENDING_SCANNER_AND_CURRENT_DATABASE"},
        "limitations": ["The target Python distribution and operating-system libraries are not bundled or pinned here.",
                        "No root source license was supplied; SPDX uses NOASSERTION and does not grant redistribution rights.",
                        "No local Syft/Grype vulnerability database was available; this is not a vulnerability scan."],
    }
    (ROOT / "release" / "SBOM.spdx.json").write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (ROOT / "release" / "SUPPLY_CHAIN_AUDIT.json").write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"files": len(spdx_files), "third_party_imports": third_party,
                      "root_license_files": licenses, "license_status": audit["license_review"]["status"],
                      "verified_wheels": audit["license_review"]["verified_bundled_wheels"],
                      "verified_license_files": audit["license_review"]["verified_embedded_license_files"],
                      "derived_licenses": [item["name"] for item in license_audit["derived_expressions"]],
                      "unresolved_package_licenses": license_audit["unresolved_packages"],
                      "vulnerability_status": audit["vulnerability_review"]["status"]}, indent=2))


if __name__ == "__main__":
    main()
