# Skrya Full

Injected into a `claude` coding session for substantial work in this repository.

## Full Pipeline

1. Read `CLAUDE.md`, `README.md`, `design/current-system-design.md`, and `design/core-skills-spec.md`.
2. Treat `skills-src/` and `prompt-templates/` as the source of truth for agent-facing assets.
3. If the request concerns unconfigured ongoing tracking, route through `topic-curation` before digest or deep-analysis behavior.
4. When skill or prompt behavior changes, regenerate all checked-in agent assets with `python -m skrya_orchestrator.main build-agent-assets --root . --host all`.
5. Update tests and docs together with the behavior change.
6. Before finishing, run the full unittest suite and report the verification result.

