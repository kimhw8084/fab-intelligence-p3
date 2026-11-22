"""Create a local source/dependency inventory and SPDX SBOM without network access."""
from __future__ import annotations

import ast
import hashlib
import json
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {"__pycache__", ".git"}
OUTPUTS = {"release/SBOM.spdx.json", "release/SUPPLY_CHAIN_AUDIT.json", "release/GATE_REPORT.json",
           "release/BOOTSTRAP_MANIFEST.sha256", "release/SCIENTIFIC_PERFORMANCE_BENCHMARK.json",
           "release/PACKAGE_QUALIFICATION.json", "release/LOCAL_TEST_EVIDENCE.json",
           "release/LOCAL_TEST_LOG.txt", "release/CRITICAL_CASE_EVIDENCE.json"}


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


def main():
    files = source_files()
    runtime_roots = set()
    for path in files:
        runtime_roots.update(imported_modules(path))
    stdlib = set(getattr(sys, "stdlib_module_names", ()))
    first_party = {"fabintel", "products", "qualification", "cli"}
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
    document = {
        "spdxVersion": "SPDX-2.3",
        "dataLicense": "CC0-1.0",
        "SPDXID": "SPDXRef-DOCUMENT",
        "name": "FAB Spatial & Yield Intelligence P3 candidate SBOM",
        "documentNamespace": "https://spdx.org/spdxdocs/fabintel-p3-" + sha256(ROOT / "product.json"),
        "creationInfo": {"creators": ["Tool: local-standard-library-supply-chain-audit"],
                         "created": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")},
        "packages": [package],
        "files": spdx_files,
        "relationships": [{"spdxElementId": "SPDXRef-DOCUMENT", "relationshipType": "DESCRIBES", "relatedSpdxElement": "SPDXRef-Package-P3"}],
    }
    audit = {
        "state": "CANDIDATE",
        "scan_scope": "local source tree only; no network access",
        "created_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "runtime": {"minimum_python": "3.10", "third_party_imports": third_party,
                    "external_python_dependencies": 0 if not third_party else None,
                    "bundled_ui_assets": True, "remote_asset_findings": local_assets},
        "files_in_sbom": len(spdx_files),
        "file_sha256": {item["fileName"][2:]: item["checksums"][0]["checksumValue"] for item in spdx_files},
        "license_review": {"root_license_files": licenses, "first_party_license": "NOASSERTION",
                            "third_party_runtime_dependencies": third_party,
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
                      "vulnerability_status": audit["vulnerability_review"]["status"]}, indent=2))


if __name__ == "__main__":
    main()
