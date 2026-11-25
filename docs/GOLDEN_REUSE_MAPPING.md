# Golden reuse mapping

Golden is pinned to `dc2ece864b2d744e47dfe8c7d9ad78aadbed369e` (`0.1.0-dev`) as a reusable development-method foundation, not as a fully qualified enforcement platform. The current full report has eight passing rules and eleven `NOT_RUN`. The former `PY-003`, `UI-001`, and `SEC-001` gates now pass; remaining checks are constrained by Golden's command allowlist, P1-owned toolchain, or missing independent applicability/host evidence.

See [`GOLDEN_NOT_RUN_AUDIT.md`](GOLDEN_NOT_RUN_AUDIT.md) for the individual audit of all 14 prior `NOT_RUN` rules, exact external checks, tool hashes, limitations and remaining prerequisites. The latest full machine report is `release/GOLDEN_PILOT_FULL_EVIDENCE.json` and `qualifies_release` remains false.

P3's adapted Codex skills live in `.agents/skills/`; original Golden/OpenCode assets remain unmodified and are not copied wholesale into every model context. The product reuses Golden's source pinning, bounded command execution, evidence-bound test runs, dependency audit, offline package and release-gate concepts. Separate passing P1 UI, MCP SDK, scientific and browser observations are not claimed as Golden-enforced checks.
