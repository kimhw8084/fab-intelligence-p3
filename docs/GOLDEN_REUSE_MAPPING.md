# Golden reuse and pilot-check evidence

Golden is pinned to `dc2ece864b2d744e47dfe8c7d9ad78aadbed369e` (`0.1.0-dev`). Its pilot rule catalog and local runner are a method reference, not fully qualified or company-enforced controls. Selected skills were adapted into `.agents/skills/` with Codex frontmatter and kept byte-compatible under `.opencode/skills/` for later handoff. `golden.project.json` records the version and relevant P3 capabilities; `products/p3/ui/package.json` declares React as a host-supplied peer without adding a second UI runtime.

The pinned pilot runner was executed in `FAST` mode. It reported `GOLD-001` (manifest/version pin) and `PY-001` (39 Python files parsed) as `PASS`; 11 full-only checks were `DEFERRED`; and six capability/criticality decisions were `NOT_RUN`. The report explicitly has `qualifies_release: false`. The runner does not prove complete Golden compliance.

| Golden rule | P3 evidence or scope decision | Pilot status | P3 interpretation |
|---|---|---|---|
| GOLD-001 | `golden.project.json`, `release/GOLDEN_PILOT_FAST_EVIDENCE.json` | PASS | Pin verified against Golden `0.1.0-dev`; source commit recorded. |
| GOLD-002 | `README.md`, `START_HERE.md` | DEFERRED | Usage docs exist; full README check was not run. |
| GOLD-003 | Version-controlled worktree and commit history | DEFERRED | Fast mode did not run the worktree rule; Git state is recorded separately. |
| PY-001 | Pilot evidence; `bootstrap_check.py` | PASS | Golden AST check parsed 39 Python files. |
| PY-002 | `release/LOCAL_TEST_EVIDENCE.json`, `release/LOCAL_TEST_LOG.txt` | DEFERRED | Separate P3 runner passed 75 Python tests; Golden full command adapter was not used. |
| PY-003 | `release/SUPPLY_CHAIN_AUDIT.json` | DEFERRED | Ruff was not staged, so no Ruff result is claimed. |
| WEB-001 | `release/LOCAL_UI_EVIDENCE.json` | DEFERRED | Separate strict TypeScript check passed using P1's staged toolchain. |
| WEB-002 | `release/LOCAL_UI_EVIDENCE.json` | DEFERRED | Separate P1 Vitest run passed all five P3 panel tests. |
| UI-001 | `tests/test_schema_and_ui.py`, `products/p3/ui/P3Panel.test.tsx` | DEFERRED | Product module and accessible table behaviors have local tests; suite-host integration remains pending. |
| UI-002 | `release/LOCAL_UI_EVIDENCE.json` | DEFERRED | No shared browser host or engineer accessibility/usability study was available. |
| API-001 | `fabintel/cli.py`, `tests/fixtures/headless_api.py` | NOT_RUN | No product API server remains; the HTTP fixture is test-only. Golden did not infer non-applicability from a false capability flag. |
| DB-001 | Product runtime inventory | NOT_RUN | P3 has no database. Golden did not infer non-applicability from a false capability flag. |
| SEC-001 | `release/SUPPLY_CHAIN_AUDIT.json`, `vendor/mcp-sdk-2.3.0/macos-arm64-cp311/` | DEFERRED | Local inventory and hashes exist; no current vulnerability database or company license approval exists. |
| OPS-001 | Product runtime inventory | NOT_RUN | P3 ships no observability service. Golden did not infer non-applicability from a false capability flag. |
| JOBS-001 | Product runtime inventory | NOT_RUN | P3 has no queue or durable job service. Golden did not infer non-applicability from a false capability flag. |
| MCP-001 | `release/LOCAL_TEST_EVIDENCE.json`, `docs/MCP_ADAPTER.md` | DEFERRED | Separate offline install and 15 official-SDK/adapter tests passed on macOS arm64 CPython 3.11; internal authority stays pending. |
| AI-001 | `product.json`, deterministic engine tests | NOT_RUN | P3 deliberately has no model or agent runtime. Golden did not infer non-applicability from a false capability flag. |
| DATA-001 | `release/CRITICAL_CASE_EVIDENCE.json`, `release/SCIENTIFIC_PERFORMANCE_BENCHMARK.json` | DEFERRED | Separate P3 evidence has 12/12 critical cases and 100/100 numeric oracle cases passing. |
| REL-001 | `release/PACKAGE_QUALIFICATION.json`, `release/RUNBOOK_ROLLBACK_KILL_SWITCH.md` | NOT_RUN | P3 candidate archive rollback is checked separately; production-critical recovery remains outside this unapproved candidate. |

The six `NOT_RUN` pilot results above are not represented as Golden passes. P3's own tests, offline install, source inventory, release builder, and host-blocked egress evidence remain separate product evidence with their stated scopes. Golden's fast runner is retained as an auditable method sample, not a release gate.
