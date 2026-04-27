# Skrya Upgrade Flow

Use this when an agent has cloned a newer Skrya version or when a user asks to update Skrya.

## 1. Inspect The Current Install

```bash
PYTHONPATH=src python3 -m skrya_orchestrator.main version --root . --check-latest
PYTHONPATH=src python3 -m skrya_orchestrator.main data-root --root .
```

If a visible upstream revision is newer, ask the user whether to update before pulling or replacing files.

## 2. Update The Code

Use the host's normal non-destructive update path, for example:

```bash
git pull --ff-only
```

If the repository was freshly cloned into a skill directory, keep existing runtime user data under the configured Skrya data root. Do not copy runtime data into the skill-pack source tree unless the host explicitly uses workspace `.skrya/data`.

## 3. Run Required Migrations

```bash
PYTHONPATH=src python3 -m skrya_orchestrator.main upgrade --root . --migrate-thread-naming
```

When moving older workspace-local `topics/` and `runs/` into the configured data root, run:

```bash
PYTHONPATH=src python3 -m skrya_orchestrator.main upgrade --root . --migrate-data --migrate-thread-naming
```

This migration currently handles:

- workspace `topics/` and `runs/` copied into the configured data root when requested
- `event-thread-seeds.json` copied to `thread-seeds.json`
- `runs/<topic-id>/event-threads/latest-event-threads.json` copied to `runs/<topic-id>/threads/latest-threads.json`
- legacy payload keys and interface strings rewritten to `thread`

The migration copies missing new files and leaves legacy files in place for rollback and audit.

## 4. Rebuild Skill Artifacts

```bash
PYTHONPATH=src python3 -m skrya_orchestrator.main build-skill-pack --root . --host all
```

If this is a global skill install, reinstall for the active host:

```bash
PYTHONPATH=src python3 -m skrya_orchestrator.main install-skill-pack --root . --host auto
```

## 5. Verify

```bash
PYTHONPATH=src python3 -m unittest discover -s tests
PYTHONPATH=src python3 -m skrya_orchestrator.main digest --topic <topic-id> --root . --sample
```

Check that the digest ends with `## 系统提示`, includes the Skrya version, and uses `thread` wording.

