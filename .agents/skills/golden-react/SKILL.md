---
name: golden-react
description: Build a headless React TypeScript FAB Intelligence product panel that follows the shared suite contract
---

# React product panel

Adapted from Golden Agentic Engineering v0.1.0-dev, pinned commit `dc2ece864b2d744e47dfe8c7d9ad78aadbed369e` (`.opencode/skills/golden-react/SKILL.md`). Golden remains pre-qualification; these instructions are guidance, not an enforced standard.

- Read P1's `suite-ui-module.v1` and `suite-chart.v1` contracts before adding UI.
- P1 owns the suite shell, route, design tokens, request lifecycle, shared evidence inspector, and chart renderer. Add only a product panel; never add a product route server or shell.
- Reuse the installed host React runtime and existing token/component source. Do not install packages or add a competing design system.
- Keep evidence, provenance, uncertainty, refusal, loading, empty, and error states visible. Synthetic data must be labeled.
- Delegate visualization to the suite renderer and retain a semantic HTML table. A map may render only when its coordinate system is verified; do not interpolate unobserved sites.
- Check keyboard semantics and run the staged typecheck, panel tests, and build. Do not claim host or target-OS qualification from local checks.
