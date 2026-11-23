"""Create and freshly extract/test a reproducible offline P3 source bundle."""
from __future__ import annotations

import hashlib
import json
import os
import platform
import stat
import subprocess
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from qualification.tree_hash import current_git_commit, source_tree_sha256

ARCHIVE_NAME = "p3-candidate-20261122.zip"
GENERATED = {ARCHIVE_NAME, ARCHIVE_NAME + ".sha256", "PACKAGE_QUALIFICATION.json"}


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def package_files():
    files = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or "__pycache__" in path.parts or path.suffix == ".pyc":
            continue
        rel = path.relative_to(ROOT).as_posix()
        if rel.startswith(".git/") or rel in {".git"}:
            continue
        if rel.startswith("release/") and Path(rel).name in GENERATED:
            continue
        if path.suffix in (".zip", ".dmg", ".exe", ".whl"):
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
        for required in ("bootstrap_check.py", "product.json", "products/p3/engine.py", "ui/index.html", "release/GATE_REPORT.json"):
            if required not in names:
                raise ValueError("archive is missing " + required)
    with tempfile.TemporaryDirectory(prefix="p3-fresh-extract-") as temp:
        with zipfile.ZipFile(archive_path) as archive:
            archive.extractall(temp)
        extracted = Path(temp)
        env = dict(os.environ)
        env.pop("PYTHONPATH", None)
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        test = subprocess.run([sys.executable, "-S", "-m", "unittest", "discover", "-s", "tests", "-v"],
                              cwd=extracted, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=120)
        demo = subprocess.run([sys.executable, "-S", "-m", "fabintel", "demo"], cwd=extracted, env=env,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=20)
        report = {"fresh_extraction_test_exit": test.returncode, "fresh_extraction_demo_exit": demo.returncode,
                  "fresh_extraction_tests": test.stdout[-8000:], "fresh_extraction_demo": demo.stdout[-3000:]}
        if test.returncode or demo.returncode:
            raise RuntimeError(json.dumps(report, indent=2))
        return report


def main():
    release = ROOT / "release"
    archive = release / ARCHIVE_NAME
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
    archive_hash = sha256_bytes(archive.read_bytes())
    fresh = verify_archive(archive)
    (release / (ARCHIVE_NAME + ".sha256")).write_text(f"{archive_hash}  {ARCHIVE_NAME}\n", encoding="utf-8")
    report = {
        "state": "CANDIDATE",
        "created_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "archive": ARCHIVE_NAME,
        "sha256": archive_hash,
        "source_commit": current_git_commit(ROOT),
        "source_tree_sha256": source_tree_sha256(ROOT),
        "bytes": archive.stat().st_size,
        "entries": len(package_files()),
        "repeated_build_sha256_equal": first_hash == second_hash,
        "fresh_extraction_tests": {"command": "python -S -m unittest discover -s tests -v", "exit_code": fresh["fresh_extraction_test_exit"]},
        "fresh_extraction_demo": {"command": "python -S -m fabintel demo", "exit_code": fresh["fresh_extraction_demo_exit"]},
        "environment": {"os": platform.platform(), "architecture": platform.machine(), "python": sys.version},
        "network_isolation": "Not established by this host build; this tests standard-library-only execution with site packages disabled.",
        "fresh_extraction_test_log_tail": fresh["fresh_extraction_tests"],
    }
    (release / "PACKAGE_QUALIFICATION.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"archive": str(archive), "sha256": archive_hash, "bytes": archive.stat().st_size,
                      "repeated_builds_equal": report["repeated_build_sha256_equal"],
                      "extracted_tests": report["fresh_extraction_tests"]["exit_code"],
                      "extracted_demo": report["fresh_extraction_demo"]["exit_code"]}, indent=2))


if __name__ == "__main__":
    main()
