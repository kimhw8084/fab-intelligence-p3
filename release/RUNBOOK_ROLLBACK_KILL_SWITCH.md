# Operator control and rollback

Codex must supply a verified one-command stop/cancel action for every worker and query, a bounded force-stop path with audit preservation, no uncontrolled background jobs, per-operation limits, and a complete rollback/uninstall. The included bootstrap launches no server or background service. During product development, tests must prove that cancellation interrupts pending operations and that rollback preserves existing company data and approved MCP knowledge. Source-write and control-actuation functions are out of scope.

- P3 has no local route, API server, or persistent process. The CLI analysis entrypoint exits after the requested deterministic operation.
- The P3 suite panel is a host-mounted module. The suite host owns its route lifecycle and cancellation controls; stop or unmount it through the approved host procedure.
- Roll back by removing the extracted candidate folder and any explicitly exported synthetic evidence files. The candidate writes no company files and makes no schema or manufacturing-system changes.
- This does not qualify production cancellation or rollback. The target site must rerun authorization, audit retention, interruption, and rollback checks through its approved host before internal use.
