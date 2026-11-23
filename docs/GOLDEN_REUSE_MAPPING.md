# Golden reuse and pilot-check evidence

Golden is pinned to `dc2ece864b2d744e47dfe8c7d9ad78aadbed369e` (`0.1.0-dev`). Its skills, project manifest, route decisions, offline methods, and local runner are reused as a development-method foundation. Golden remains pre-qualification; its checks do not represent company-enforced controls or complete release qualification.

Five relevant Golden skills were adapted with Codex metadata under `.agents/skills/`. Their OpenCode counterparts under `.opencode/skills/` match the pinned source files byte-for-byte. No unrelated NiceGUI or general agent skills were imported. The project manifest configures the actual Python test command. React and visualization dependencies stay with the P1 suite host, and the P3 panel has no competing shell or chart engine.

The pinned Golden `scripts/golden.py` was run directly from the local source snapshot verified at the pinned commit. Fast mode passed `GOLD-001` and `PY-001`, deferred 11 full-only checks, and left six applicability or criticality rules `NOT_RUN`. Full mode passed `GOLD-001`–`GOLD-003` and `PY-001`–`PY-002`; 14 mandatory checks remained `NOT_RUN`, so `qualifies_release` is false. The full report records the unrun rules and blocker IDs. This runner requires a P3-local locked Node toolchain for its web checks and does not accept the P1-hosted toolchain, so those Golden checks stay `NOT_RUN` even though P3's separate P1-hosted typecheck and five panel tests passed.

| Golden rule | Full pilot status | P3 evidence or scope decision |
|---|---|---|
| GOLD-001 | PASS | `golden.project.json` schema and Golden pin validated. |
| GOLD-002 | PASS | `README.md` exists. |
| GOLD-003 | PASS | Git worktree detected. |
| PY-001 | PASS | Golden parsed 39 Python files; P3 bootstrap also passed. |
| PY-002 | PASS | Configured Golden Python command exited successfully. The separate P3 local qualification ran all 75 Python tests and the optional 15 SDK/adapter tests. |
| PY-003 | NOT_RUN | No Golden-approved Ruff command was configured or run. |
| WEB-001 | NOT_RUN | Golden requires a P3-local locked TypeScript toolchain; P3 uses the P1-owned toolchain and does not copy it. P3's separate strict typecheck passed. |
| WEB-002 | NOT_RUN | Golden requires a P3-local locked Vitest toolchain; P3's separate P1-hosted run passed all five panel tests. |
| UI-001 | NOT_RUN | P3 panel checks pass separately; P1 suite-host integration and the shared spatial-map contract remain pending. |
| UI-002 | NOT_RUN | No shared browser host or engineer accessibility/usability study was available. |
| API-001 | NOT_RUN | P3 has no runtime API service; `tests/fixtures/headless_api.py` is test-only. Golden does not infer non-applicability from a false flag. |
| DB-001 | NOT_RUN | P3 has no database; Golden does not infer non-applicability from a false flag. |
| SEC-001 | NOT_RUN | No Golden-approved Bandit command or current vulnerability database was available; see the separate pending supply-chain review. |
| OPS-001 | NOT_RUN | P3 ships no observability service; Golden does not infer non-applicability from a false flag. |
| JOBS-001 | NOT_RUN | P3 has no queue or durable job service; Golden does not infer non-applicability from a false flag. |
| MCP-001 | NOT_RUN | The Golden pilot has no approved MCP command. Separate offline install and 15 official-SDK/adapter tests passed on macOS arm64 CPython 3.11; internal authority remains pending. |
| AI-001 | NOT_RUN | P3 deliberately has no model or agent runtime; Golden does not infer non-applicability from a false flag. |
| DATA-001 | NOT_RUN | The Golden pilot has no approved data-test command. Separate P3 evidence has 12/12 critical cases and 100/100 numeric oracle cases passing on synthetic data. |
| REL-001 | NOT_RUN | P3 declares workflow criticality; production-critical recovery applicability lacks independent owner evidence. Candidate archive rollback checks are separate. |

Machine-readable runner results: `release/GOLDEN_PILOT_FAST_EVIDENCE.json` and `release/GOLDEN_PILOT_FULL_EVIDENCE.json`. The full run returned the pilot's unqualified status, not a successful product release qualification. The P3 tests, offline SDK install, source inventory, release builder, and host-blocked egress evidence remain separate evidence with their stated scopes.
