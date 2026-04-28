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

## Architecture

Skrya is a topic-driven skill pack. The repository is both:

- an installable runtime skill tree for agent hosts
- a source workspace for generating host-specific prompt and metadata artifacts

The main runtime flow is:

1. `topic-curation` turns a user request into a durable topic.
2. `source-curation` confirms sources and runtime retrieval capabilities.
3. `digest` consumes normalized events and writes the daily briefing.
4. `deep-analysis` expands a selected digest item.
5. `request-curation` converts feedback into durable preferences.
6. Thread support connects related digest items into a continuing timeline.

Topic data lives outside the skill source by default. Normal desktop hosts use `~/.skrya`; OpenClaw or mounted workspace hosts may use `.skrya/data`.

## Runtime Data

User topic data lives under the resolved Skrya data root, not necessarily inside this repository.

Defaults:

- Normal desktop hosts: `~/.skrya`
- OpenClaw, containers, and mounted-workspace hosts: `.skrya/data`

The data root can be changed through the orchestrator data-root command or host-specific setup flow. When migrating data, copy existing topic and run state into the new root without deleting the old files unless the user explicitly requests cleanup.

Expected topic files:

```text
<skrya-data-root>/topics/<topic-id>/
  topic.json
  brief.json
  sources.json
  digest.md
  deep-analysis.md
  thread-seeds.json
```

Expected runtime artifacts:

```text
<skrya-data-root>/runs/<topic-id>/
  latest-digest.md
  latest-digest-events.json
  ingest/latest-ingest.json
  threads/latest-threads.json
```

## Code Layout

```text
.
  skill-pack.json             # root skill metadata
  SKILL.md.tmpl               # root skill template
  SKILL.md                    # generated root skill
  agents/openai.yaml          # generated metadata

  topic-curation/             # bundled topic setup skill
  request-curation/           # durable preference update skill
  source-curation/            # source confirmation skill
  digest/                     # daily briefing skill
  deep-analysis/              # selected item analysis skill

  prompt-templates/           # host prompt-pack templates
  docs/                       # user journeys and interface docs
  design/                     # internal design notes
  topics/                     # checked-in fixtures only
  src/skrya_orchestrator/     # CLI, build/install, ingest, digest runtime
  tests/                      # unit and contract tests
```

Important modules:

- `agent_assets.py`: builds and installs the skill pack.
- `main.py`: CLI entry point.
- `paths.py`: data-root resolution and migrations.
- `ingest.py`: provider-neutral retrieval and ingest normalization.
- `intelligence.py`: digest, deep-analysis, and thread rendering.
- `version.py`: local version and upstream revision checks.

## Technical Design Notes

- Topic-scoped work always resolves a stable internal `topic-id`.
- Language is topic-scoped through `topic.json.language`, not install-scoped. Current output languages are Chinese and English.
- Durable config should be provider-neutral. Third-party retrieval providers may appear in runtime ingest artifacts, but not as required long-term dependencies.
- Channel-aware hosts should bind recurring delivery to the creating channel/conversation by default.
- Test runs use the real digest template but do not save `latest-digest.md` unless the user explicitly asks.
- Uninstall supports `skills-keep-data`, `data-keep-skills`, and `complete`; complete uninstall must preserve unrelated global instructions.

## Change Guidelines

- Start from a user scenario and update the smallest durable surface that solves it.
- Add or update tests for behavior changes, especially skill contract tests.
- Keep user-facing output aligned with the topic language or the user's current feedback language. Do not introduce install-time language settings.
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
