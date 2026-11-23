# Configured MCP read adapter

P3 now includes MCP stdio and Streamable HTTP clients and a logical read-only adapter. The stdio transport starts a server by an argument array (never a shell string) and exchanges bounded newline-delimited JSON-RPC. The HTTP transport uses HTTPS for non-loopback servers, validates session/protocol headers, refuses redirects, and handles bounded JSON or Server-Sent Event responses. Both negotiate the current per-request metadata protocol and support the `2025-11-25` initialize handshake. The client bounds frames, tool inventory, calls and timeouts; sends cooperative cancellation; and refuses server-initiated requests and additional-input tool results.

The adapter does not invent production tool names or semantic mappings. `requirements/mcp-adapter.template.json` contains placeholders only. A site-approved config must bind each logical operation to an exact tool descriptor hash and approval reference, supply approved source IDs and semantic versions, and register each allowed read plan with its exact canonical SHA-256 and approval reference. A runtime caller cannot grant approval by adding a boolean to a plan. Credentials stay in an environment provider: stdio credentials are mapped to child environment variables and HTTP credentials to request header names. Secret values are never written into configuration. Tool annotations are treated as hints; an exact site approval is also required. Raw SQL and unapproved sources are refused. Relationship requests require timezone-aware bounded windows; bounded reads require the exact single-source read-only scope; returned rows are bounded and accompanied by local hashes and audit metadata.

To inspect a site-configured MCP service:

```sh
python -m fabintel mcp-discover --config /absolute/path/to/approved-p3-mcp.json
```

The result is deliberately labeled `CONFIGURED_READ_ONLY_UNQUALIFIED`; external code cannot set internal qualification ready. No Samsung-specific endpoint, tool name, data source or semantic definition is bundled. HTTP cancellation is cooperative and bounded by the configured request timeout; neither a cancellation notification nor a local timeout proves a remote operation stopped, so audit remains necessary.

The subprocess transport and logical adapter are tested against `fabintel.mcp_mock_server`, a synthetic JSON-RPC server that exercises both modern and legacy MCP versions, permission denials, schema drift and cancellation. Streamable HTTP is tested against a local HTTP/SSE protocol fixture. Neither test connects to company systems or uses company data.

Protocol references:

- [MCP 2026-07-28 stdio transport](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/stdio)
- [MCP 2026-07-28 versioning and legacy compatibility](https://modelcontextprotocol.io/specification/2026-07-28/basic/versioning)
- [MCP tools and annotations](https://modelcontextprotocol.io/specification/2026-07-28/server/tools)
