"""Regenerate the SHA-256 inventory for every package file except itself."""
from __future__ import annotations

import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = Path("release/BOOTSTRAP_MANIFEST.sha256")
GENERATED = {MANIFEST.as_posix(), "release/PACKAGE_QUALIFICATION.json"}
ARCHIVE_SUFFIXES = {".zip", ".dmg", ".exe", ".pyc", ".sha256"}


def package_files():
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file() or "__pycache__" in path.parts or ".git" in path.parts:
            continue
        relative = path.relative_to(ROOT).as_posix()
        if relative in GENERATED or path.suffix in ARCHIVE_SUFFIXES:
            continue
        yield relative, path


def main():
    rows = [f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {relative}"
            for relative, path in package_files()]
    target = ROOT / MANIFEST
    target.write_text("\n".join(rows) + "\n", encoding="utf-8")
    print(f"Wrote {len(rows)} package hashes to {MANIFEST.as_posix()}")


if __name__ == "__main__":
    main()
