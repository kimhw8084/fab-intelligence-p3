# MCP Python SDK candidate bundle

This folder contains one offline installation candidate for the official MCP Python SDK: macOS arm64 with CPython 3.11. It is not company-approved and does not establish compatibility with a company target image.

## Pinned source

- Package: `mcp==2.3.0`
- Upstream: [modelcontextprotocol/python-sdk](https://github.com/modelcontextprotocol/python-sdk)
- Source commit: `2118f14f8a19bc158d8a1cf90af58d85d187f849`
- Target wheelhouse: `macos-arm64-cp311/wheelhouse/` (28 wheels)

The target directory includes the hash-locked requirements, embedded license inventory, CycloneDX SBOM, and wheel files. Each wheel has an embedded license file, but the inventory is not a legal review or company OSS approval. The wheelhouse was installed with `pip --no-index --require-hashes`; `pip check` passed. The project qualification also exercises the SDK against synthetic stdio and Streamable HTTP fixtures.

## Offline install check

Run from the P3 repository root on a matching macOS arm64 / CPython 3.11 host:

```sh
python qualification/mcp_sdk_offline.py
```

The helper creates an isolated environment, installs only from this local wheelhouse, runs `pip check`, and exercises the SDK and read-only adapter tests. It does not connect to a real MCP server.

## Limits

- No Windows or Linux wheelhouse is included in this repository.
- No native target installation, company OpenCode handshake, Samsung semantic mapping, endpoint, credential, source grant, or approval is included.
- Do not use this candidate on a different OS, architecture, Python ABI, or company image. Obtain the authorized target inventory and company OSS/security review before preparing an internal package.
