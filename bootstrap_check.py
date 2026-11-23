"""Verify the supplied ZIP extraction has not been altered, then run seeded tests."""
from pathlib import Path
import hashlib, subprocess, sys
ROOT=Path(__file__).resolve().parent
GENERATED={"release/BOOTSTRAP_MANIFEST.sha256","release/PACKAGE_QUALIFICATION.json"}
ARCHIVE_SUFFIXES={".zip",".dmg",".exe",".pyc",".sha256"}

def package_files():
    rows=set()
    for path in ROOT.rglob('*'):
        if not path.is_file() or '__pycache__' in path.parts or '.git' in path.parts: continue
        relative=path.relative_to(ROOT).as_posix()
        if relative in GENERATED or path.suffix in ARCHIVE_SUFFIXES: continue
        rows.add(relative)
    return rows

def main():
    manifest=ROOT/'release'/'BOOTSTRAP_MANIFEST.sha256'
    checks=0; entries=set()
    for line in manifest.read_text(encoding='utf8').splitlines():
        if not line.strip(): continue
        expected,rel=line.split('  ',1)
        if rel in entries: raise SystemExit('DUPLICATE MANIFEST ENTRY: '+rel)
        entries.add(rel)
        actual=hashlib.sha256((ROOT/rel).read_bytes()).hexdigest()
        if actual!=expected:
            raise SystemExit('INTEGRITY FAILED: '+rel)
        checks+=1
    missing=package_files()-entries
    extra=entries-package_files()
    if missing or extra:
        raise SystemExit('MANIFEST COVERAGE FAILED: missing='+','.join(sorted(missing))+' extra='+','.join(sorted(extra)))
    print('BOOTSTRAP INTEGRITY PASS:',checks,'files')
    tests=subprocess.run([sys.executable,'-m','unittest','discover','-s','tests','-v'],cwd=ROOT)
    if tests.returncode: raise SystemExit(tests.returncode)
    print('BOOTSTRAP TESTS PASS — PRODUCT IS A CANDIDATE, NOT EXTERNAL_TRANSFER_READY')

if __name__=='__main__':main()
