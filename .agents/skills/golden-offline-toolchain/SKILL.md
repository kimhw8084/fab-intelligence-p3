---
name: golden-offline-toolchain
description: Stage and verify pinned open-source dependencies, licenses, and runtime assets for offline product use
---

# Offline tools and OSS

Adapted from Golden Agentic Engineering v0.1.0-dev, pinned commit `dc2ece864b2d744e47dfe8c7d9ad78aadbed369e` (`.opencode/skills/golden-offline-toolchain/SKILL.md`). Golden's catalog is pre-qualification; a local pass does not imply company clearance.

- Start with resources already present in the authorized workspace. Do not use public registries or dynamic installers during implementation or release verification.
- For every imported dependency, pin exact source/version and hashes, inspect the full transitive license inventory, freshness of vulnerability data, target OS/ABI, and operation with egress blocked.
- Keep complete wheels/native assets, lockfiles, SBOM, and notices together in the release artifact. Verify hashes before offline installation, then run dependency consistency checks.
- Distinguish source archives from complete runnable bundles. A platform candidate that was not installed on that platform remains unqualified.
- Fail closed on missing packages. Preserve a no-dependency deterministic mode where it is useful and safe.
