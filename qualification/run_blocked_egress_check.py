"""Qualify the synthetic CLI under a host-level outbound-network denial."""
from __future__ import annotations

import json
import platform
import shutil
import subprocess  # nosec B404
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "release" / "OFFLINE_RUNTIME_EVIDENCE.json"
PROFILE = "(version 1)(allow default)(deny network-outbound)"


def main() -> None:
    sandbox = shutil.which("sandbox-exec")
    if not sandbox:
        raise SystemExit("sandbox-exec is unavailable; outbound-denial evidence cannot be produced on this host")
    probe = subprocess.run(  # nosec B603
        [sandbox, "-p", PROFILE, sys.executable, "-S", "-c",
         "import socket; socket.create_connection(('1.1.1.1', 443), timeout=2)"],
        check=False, cwd=ROOT, capture_output=True, text=True, timeout=10,
    )
    denied = probe.returncode != 0 and ("Operation not permitted" in probe.stderr or "Permission denied" in probe.stderr)
    demo = subprocess.run(  # nosec B603
        [sandbox, "-p", PROFILE, sys.executable, "-S", "-m", "fabintel", "demo"],
        check=False, cwd=ROOT, capture_output=True, text=True, timeout=30,
    )
    try:
        result = json.loads(demo.stdout)
    except json.JSONDecodeError:
        result = {}
    analysis = next((item.get("result", {}) for item in result.get("artifacts", [])
                     if item.get("kind") == "p3_analysis"), {})
    capabilities = {key: analysis.get(key, {}).get("status") for key in
                    ("fingerprint", "anomaly", "similarity", "evolution", "quality_association")}
    passed = denied and demo.returncode == 0 and result.get("status") == "VALID" and all(
        status == "VALID" for status in capabilities.values()
    )
    report = {
        "state": "CANDIDATE",
        "created_utc": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "host": {"os": platform.platform(), "architecture": platform.machine(), "python": sys.version},
        "sandbox_profile": PROFILE,
        "outbound_probe": {"exit_code": probe.returncode, "denied_by_os_sandbox": denied,
                           "stderr": probe.stderr.strip()[-1000:]},
        "synthetic_demo": {"exit_code": demo.returncode, "status": result.get("status"),
                           "capabilities": capabilities, "company_data_used": False,
                           "error_tail": demo.stderr.strip()[-1000:]},
        "result": "PASS_HOST_BLOCKED_EGRESS" if passed else "FAIL",
        "scope_note": "Host-level macOS sandbox evidence for the synthetic CLI only; approved deployment OS, network policy, UI binding behavior and company data remain unqualified.",
    }
    OUTPUT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"result": report["result"], "denied_by_os_sandbox": denied,
                      "demo_status": result.get("status"), "capabilities": capabilities}, indent=2))
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
