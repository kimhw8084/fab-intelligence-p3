"""Canonical digest of product inputs, excluding generated qualification output."""
from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GENERATED_EVIDENCE_FILES = {
    "release/BOOTSTRAP_MANIFEST.sha256",
    "release/CRITICAL_CASE_EVIDENCE.json",
    "release/GATE_REPORT.json",
    "release/GOLDEN_PILOT_FAST_EVIDENCE.json",
    "release/LOCAL_TEST_EVIDENCE.json",
    "release/LOCAL_TEST_LOG.txt",
    "release/LOCAL_UI_EVIDENCE.json",
    "release/OFFLINE_RUNTIME_EVIDENCE.json",
    "release/PACKAGE_QUALIFICATION.json",
    "release/REUSE_COMPARISON_EVIDENCE.json",
    "release/SBOM.spdx.json",
    "release/SCIENTIFIC_PERFORMANCE_BENCHMARK.json",
    "release/SUPPLY_CHAIN_AUDIT.json",
    "progress/STATE.md",
}


def source_tree_sha256(root: Path = ROOT) -> str:
    """Hash the same source/config/docs/test tree from every qualification runner."""
    entries = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or "__pycache__" in path.parts or path.suffix in {
            ".pyc", ".zip", ".dmg", ".exe", ".whl", ".sha256",
        }:
            continue
        relative = path.relative_to(root).as_posix()
        if relative.startswith(".git/") or relative in GENERATED_EVIDENCE_FILES:
            continue
        if relative.startswith("release/p3-candidate-"):
            continue
        entries.append(relative.encode("utf-8") + b"\0" + hashlib.sha256(path.read_bytes()).digest())
    return hashlib.sha256(b"".join(entries)).hexdigest()


def current_git_commit(root: Path = ROOT) -> str | None:
    try:
        result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, check=True,
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    value = result.stdout.strip()
    return value if len(value) == 40 else None
