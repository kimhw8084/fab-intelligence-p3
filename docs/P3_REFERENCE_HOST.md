# P3 standalone reference host

The reference host runs P3 without the P1 application. It composes the official MCP SDK adapter, reviewed read-only configuration, the C01–C05 engine, spatial-map v2 contract, and local React/ECharts assets. The default source is an explicitly synthetic protocol-compatible MCP peer. Configured mode is available only when `FABINTEL_MCP_CONFIG` names a site-prepared adapter configuration; permissions, tool bindings, semantic versions, bounded reads, units, geometry, and source audits are still checked by the adapter.

## Offline startup

The current recorded SDK wheelhouse supports macOS arm64 with CPython 3.11. Use the environment's Python to launch the host; the system Python may not contain the SDK.

```sh
python3.11 -m venv .venv
.venv/bin/python -m pip install --no-index --disable-pip-version-check \
  --find-links vendor/mcp-sdk-2.3.0/macos-arm64-cp311/wheelhouse \
  --require-hashes -r vendor/mcp-sdk-2.3.0/macos-arm64-cp311/requirements.lock
.venv/bin/python -m pip check
.venv/bin/python -m fabintel reference-host --port 8765
```

The ZIP already contains the production React/ECharts assets under products/p3/reference_host/static/; Node.js and npm are not runtime dependencies. The ZIP does not include node_modules or an npm cache. Rebuilding the frontend is a development-only operation and requires an approved environment with the package-lock dependencies pre-cached for offline npm use.

Open `http://127.0.0.1:8765/`, select the synthetic source, and run the five supplied demonstration plans. Configured mode uses only the plan IDs provided by the site's adapter configuration. The source configuration path and credential environment are never accepted from the browser request.

The process binds only to IPv4 loopback. Browser API posts enforce same-origin checks, request size and plan-count limits, no-store headers, and a restrictive content security policy. No browser asset needs a CDN or network access. Stop the process with Ctrl-C; active bounded MCP operations receive cancellation. A cancelled or refused read does not return partial scientific evidence.

## Investigation result and export

The host response is `p3-reference-module.v2`. It carries the validated evidence envelope, C01–C05 capability statuses, current measured observations in `fab-spatial-map.v2`, source/version/hash provenance, and a separately labeled `suite-ui-module.v1` compatibility adapter. That legacy adapter is present only when it can represent the selected observations without loss; defect-event data is refused by v1. It is not used by the independent P3 host.

The spatial map distinguishes numeric measurements, categorical measurements, defect events, and explicit missing measurements. Numeric strings are rejected; numeric category codes remain JSON numbers; an unlabeled defect event is not counted as a missing measurement. A typed accessible table accompanies the chart, and only measured sites are shown. Evidence export downloads the exact canonical JSON bytes whose SHA-256 is displayed in the host.

## Qualification boundary

The synthetic peer validates external workflow behavior, not Samsung tool names, credentials, permissions, mappings, source quality, OS compatibility, or production calibration. Configured reads remain `READ_ONLY_UNQUALIFIED` until company approval. P1 integration is a separate compatibility check and remains pending while its actual converter fails the categorical and event regression cases. The P3 host can operate and be externally qualified independently of that state.
