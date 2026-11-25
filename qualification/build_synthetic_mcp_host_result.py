"""Create the test-only P3 module response from the official-SDK mock MCP peer."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fabintel.mcp_adapter import ReadOnlyMCPAdapter
from fabintel.mcp_client import MCPClient
from fabintel.mcp_workflow import run_mcp_host_module
from fabintel.synthetic_mcp import synthetic_adapter_config


def main() -> int:
    destination = Path(sys.argv[1])
    transport = {"type": "stdio", "command": [sys.executable, "-S", "-m", "qualification.synthetic_mcp_peer",
                                                    "--protocol", "dual"], "cwd": str(ROOT)}
    client = MCPClient(transport, request_timeout=8)
    try:
        adapter = ReadOnlyMCPAdapter(client, synthetic_adapter_config(client, ROOT))
        result = run_mcp_host_module(adapter,
            ["SYN-WF-CURRENT", "SYN-WF-PREVIOUS", "SYN-WF-BASELINE", "SYN-WF-HISTORY", "SYN-WF-ASSOCIATION"],
            time_window={"start": "2026-01-01T00:00:00Z", "end": "2026-02-01T00:00:00Z"},
            operation_id="SYN-P1-HOST-INTEGRATION")
        # The P1 harness consumes only the explicitly lossless legacy adapter.
        # This fixture does not stand in for the standalone P3 v2 workflow.
        compatibility = result["suite_compatibility"]
        if compatibility["status"] != "COMPATIBLE" or compatibility["spatial_map"] is None:
            raise ValueError("synthetic continuous map could not be represented by the reviewed P1 v1 contract")
        p1_module = {"contract_version": compatibility["contract_version"],
                     "product_id": result["product_id"], "capabilities": result["capabilities"],
                     "source_preview": result["source_preview"], "evidence": result["evidence"],
                     "spatial_map": compatibility["spatial_map"]}
        destination.write_text(json.dumps(p1_module, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    finally:
        client.close()
    print(json.dumps({"status": "PASS", "product_id": result["product_id"],
                      "evidence_status": result["evidence"]["status"],
                      "p3_contract_version": result["contract_version"],
                      "point_count": len(result["suite_compatibility"]["spatial_map"]["points"]),
                      "source_count": len(result["evidence"]["sources"]),
                      "bounded_read_count": len(result["evidence"]["provenance"]["mcp_workflow"]["bounded_reads"])}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
