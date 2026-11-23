---
name: golden-manufacturing-data
description: Analyze wafer, lot, die, equipment, SPC, metrology, and test data with reproducible manufacturing methods
---

# Manufacturing analytics

Adapted from Golden Agentic Engineering v0.1.0-dev, pinned commit `dc2ece864b2d744e47dfe8c7d9ad78aadbed369e` (`.opencode/skills/golden-manufacturing-data/SKILL.md`). Golden remains pre-qualification; these instructions are guidance, not an enforced standard.

- Verify schema, units, time zone, wafer/lot/die identifiers, provenance, missingness, coordinate definition, and sampling before analysis.
- Execute numerical methods in deterministic code and compare them with independent oracles and simple baselines. Prefer qualified, pinned OSS when it reduces total maintenance cost without weakening evidence.
- Do not confuse control limits with specifications. Keep baseline windows explicit.
- Validate anomaly and change methods on independent labeled incidents before making production claims; report false alerts, misses, and delay.
- Keep results read-only, scoped, traceable, and conditional on study design. No process decisions, recipe changes, or manufacturing actuation.
