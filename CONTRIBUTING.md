# Contributing

Thanks for improving Skrya. Please keep changes grounded in real user journeys, not just internal neatness. The system has enough moving parts already. Fascinatingly, humans keep adding more.

## Development Setup

```bash
python3 -m pip install -e .
PYTHONPATH=src python3 -m unittest discover -s tests
```

If you change skill wording, host packaging, or prompt-pack behavior, update the source templates first and rebuild generated artifacts:

```bash
PYTHONPATH=src python3 -m skrya_orchestrator.main build-skill-pack --root . --host all
```

## Source Of Truth

- Root skill: `skill-pack.json` and `SKILL.md.tmpl`
- Bundled skills: `<skill>/skill.json` and `<skill>/SKILL.md.tmpl`
- Host prompt packs: `prompt-templates/`
- Runtime user data: `~/.skrya` or configured `.skrya/data`
- Generated host artifacts: `.skrya/hosts/`

Do not treat generated runtime files as the source of truth.

## Change Guidelines

- Start from a user scenario and update the smallest durable surface that solves it.
- Add or update tests for behavior changes, especially skill contract tests.
- Keep user-facing output in Chinese by default.
- Do not expose raw request ids, internal debug fields, or implementation metadata in normal user output.
- Do not save unconfirmed source candidates into `sources.json`.
- Do not make durable topic config depend on a third-party retrieval provider name.
- Preserve channel boundaries when the host exposes channels or conversations.
- Use `thread`, not `event-thread`, for the continuing-event entity.

## Upgrade-Sensitive Changes

If a change affects data layout, filenames, interface versions, or installation behavior:

1. Update [docs/upgrade.md](docs/upgrade.md).
2. Add a migration or compatibility path when practical.
3. Add tests covering old-to-new behavior.
4. Rebuild the skill pack.

Examples include data-root changes, `thread` file naming, prompt-pack structure, and source schema changes.

## Pull Request Checklist

- Tests pass with `PYTHONPATH=src python3 -m unittest discover -s tests`.
- Generated `SKILL.md` and `agents/openai.yaml` artifacts are rebuilt when templates changed.
- README or docs are updated for user-visible behavior.
- Upgrade notes are updated for migration-sensitive changes.
- No runtime user data, secrets, raw provider dumps, or local cache files are committed.

