"""Run the optional MCP SDK candidate checks from the bundled offline wheelhouse."""
from __future__ import annotations

import os
import platform
import subprocess
import sys
import tempfile
from pathlib import Path


def qualify_offline_mcp_sdk(root: Path, *, timeout: int = 240) -> dict:
    """Install and test only the pinned macOS arm64 / CPython 3.11 candidate."""
    if not (platform.system() == "Darwin" and platform.machine() == "arm64" and sys.version_info[:2] == (3, 11)):
        return {"status": "NOT_RUN_TARGET_MISMATCH", "target": "macos-arm64-cp311",
                "reason": "The local candidate only contains macOS arm64 CPython 3.11 wheels."}

    bundle = root / "vendor" / "mcp-sdk-2.3.0" / "macos-arm64-cp311"
    lock = bundle / "requirements.lock"
    wheelhouse = bundle / "wheelhouse"
    if not lock.is_file() or not wheelhouse.is_dir():
        return {"status": "NOT_RUN_MISSING_BUNDLE", "target": "macos-arm64-cp311"}

    with tempfile.TemporaryDirectory(prefix="p3-mcp-offline-") as temp:
        venv = Path(temp) / "venv"
        commands = [
            [sys.executable, "-m", "venv", str(venv)],
            [str(venv / "bin" / "python"), "-m", "pip", "install", "--no-index", "--disable-pip-version-check",
             "--find-links", str(wheelhouse), "--require-hashes", "-r", str(lock)],
            [str(venv / "bin" / "python"), "-m", "pip", "check"],
            [str(venv / "bin" / "python"), "-m", "unittest", "tests.test_mcp_client", "tests.test_mcp_adapter", "-v"],
        ]
        outputs = []
        env = {**os.environ, "PIP_NO_INDEX": "1", "PIP_DISABLE_PIP_VERSION_CHECK": "1", "PYTHONDONTWRITEBYTECODE": "1"}
        for command in commands:
            result = subprocess.run(command, cwd=root, env=env, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, text=True, timeout=timeout)
            normalized_command = [Path(command[0]).name, *command[1:]]
            normalized_command = [item.replace(str(root), "<P3>").replace(temp, "<MCP_TEMP>")
                                  if isinstance(item, str) else item for item in normalized_command]
            outputs.append({"command": normalized_command, "exit_code": result.returncode,
                            "output": result.stdout.replace(str(root), "<P3>").replace(temp, "<MCP_TEMP>")})
            if result.returncode:
                return {"status": "FAIL", "target": "macos-arm64-cp311", "steps": outputs}
    return {"status": "PASS", "target": "macos-arm64-cp311", "steps": outputs,
            "qualification_scope": "offline install, pip dependency consistency, synthetic official-SDK stdio and Streamable HTTP fixtures",
            "company_approval": "PENDING_INTERNAL", "windows_linux_native_install": "NOT_RUN"}
