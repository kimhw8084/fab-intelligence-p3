# Configured MCP read adapter

P3 uses the official Model Context Protocol Python SDK `mcp==2.3.0` (source commit `2118f14f8a19bc158d8a1cf90af58d85d187f849`) for stdio and Streamable HTTP protocol behavior. The former product-owned JSON-RPC transport was removed. `fabintel.mcp_client.MCPClient` is a small synchronous facade around SDK `ClientSession`; the existing `ReadOnlyMCPAdapter` remains the logical boundary for approved tools, semantic sources, query plans, bounded reads, provenance, audit, and refusal behavior.

The local wheelhouse under `vendor/mcp-sdk-2.3.0/macos-arm64-cp311/` is complete for macOS arm64 / CPython 3.11 and includes a SHA-256 requirements lock, license inventory, and CycloneDX SBOM. It was installed with pip `--no-index --require-hashes` and `pip check` passed in an isolated local environment. It is still a candidate: there is no company OSS/security clearance or current vulnerability database, and Windows/Linux native installation and internal OpenCode compatibility have not run. Do not use the macOS wheelhouse on another target.

Run the candidate SDK integration tests on the matching target without network access:

```sh
python3.11 -m venv .venv-mcp
. .venv-mcp/bin/activate
python -m pip install --no-index --find-links vendor/mcp-sdk-2.3.0/macos-arm64-cp311/wheelhouse --require-hashes -r vendor/mcp-sdk-2.3.0/macos-arm64-cp311/requirements.lock
python -m pip check
python -m unittest tests.test_mcp_client tests.test_mcp_adapter -v
```

The analysis core and synthetic workflow do not import the SDK. In a standard-library-only environment, SDK-dependent integration tests skip and configured MCP use fails closed with a local wheelhouse hint. There is no dynamic installer or network fallback.

## Logical adapter boundary

The adapter does not invent production tool names or semantic mappings. `requirements/mcp-adapter.template.json` contains placeholders only. A site-approved config must bind each logical operation to an exact tool descriptor hash and approval reference, supply approved source IDs and semantic versions, and register each allowed read plan with its exact canonical SHA-256 and approval reference. A runtime caller cannot grant approval by adding a boolean to a plan. Credentials stay in an environment provider: stdio credentials are mapped to child environment variables and HTTP credentials to request header names. Secret values are never written into configuration.

Tool annotations are treated as hints; an exact site approval is also required. Raw SQL and unapproved sources are refused. Relationship requests require timezone-aware bounded windows; bounded reads require the exact single-source read-only scope; returned rows are bounded and accompanied by local hashes and audit metadata. Cancellation stops waiting through the SDK's request lifecycle; no local cancellation signal is described as proof that a remote operation stopped.

For Streamable HTTP, non-loopback endpoints require HTTPS. Cleartext is limited to loopback, URL credentials/query/fragment are rejected, inherited proxy settings are disabled, and the SDK enforces its same-origin redirect policy. The adapter itself never uses a corporate endpoint until the administrator supplies an approved mapping.

To inspect an explicitly configured site-approved MCP service:

```sh
python -m fabintel mcp-discover --config /absolute/path/to/approved-p3-mcp.json
```

The result is deliberately labeled `CONFIGURED_READ_ONLY_UNQUALIFIED`; external code cannot set internal qualification ready. No company endpoint, tool name, data source, semantic definition or credential is bundled.

The official SDK client is tested against `tests/fixtures/mcp_mock_server.py`, a synthetic standard-library protocol peer that exercises modern/legacy negotiation, permission denials, schema drift and cancellation. A local HTTP/SSE fixture exercises the official SDK Streamable HTTP client. The peer is test-only; the production P3 package contains no custom JSON-RPC framing or duplicate MCP transport.
