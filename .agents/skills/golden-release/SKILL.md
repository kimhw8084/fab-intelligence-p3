---
name: golden-release
description: Prepare repeatable offline qualification and product release evidence without self-approval claims
---

# Qualification and release

Adapted from Golden Agentic Engineering v0.1.0-dev, pinned commit `dc2ece864b2d744e47dfe8c7d9ad78aadbed369e` (`.opencode/skills/golden-release/SKILL.md`). Golden remains pre-qualification; only directly run checks count as local evidence.

- Preserve release ID, source commit, checksums, dependency and license evidence, qualified OS, rollback, and last known-good artifact.
- Run every applicable independent check and report `NOT_RUN`, `FAIL`, `PENDING_INTERNAL`, and `NOT_APPLICABLE` explicitly.
- Separate code readiness from company approval, host integration, native OS support, and production deployment.
- Measure delivery time, defects, rework, task success, maintainability, and operations separately; never collapse them into a fabricated ROI number.
- Do not publish a qualified/released claim without the stated authority and evidence. Routine development commits and public source publication are distinct from company deployment approval.
