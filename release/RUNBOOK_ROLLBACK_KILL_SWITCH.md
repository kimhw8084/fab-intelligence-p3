# Operator control and rollback

Codex must supply a verified one-command stop/cancel action for every worker and query, a bounded force-stop path with audit preservation, no uncontrolled background jobs, per-operation limits, and a complete rollback/uninstall. The included bootstrap launches no server or background service. During product development, tests must prove that cancellation interrupts pending operations and that rollback preserves existing company data and approved MCP knowledge. Source-write and control-actuation functions are out of scope.

## Current P3 candidate controls

- Start only on loopback: `python -m fabintel serve --port 8765` binds `127.0.0.1`; stop with Ctrl-C. There are no child processes, query workers, persistent service registrations or background jobs. If the process does not stop, identify it by the operator's terminal session and terminate that process; do not use a broad process-name kill.
- The local UI and JSON API are synthetic-only, bounded to 10 MiB per request and do not log request bodies. They have no company connector or data store.
- Roll back by stopping the local process and removing the extracted candidate folder and any explicitly exported synthetic evidence files. The candidate writes no company files and makes no schema or manufacturing-system changes.
- This does not qualify production cancellation or rollback. The target site must rerun authorization, audit retention, interruption, and rollback checks through its approved host before internal use.
